#!/usr/bin/env python3
"""
Генерация лида поверх заданного баса.
Принимает bass.mid, загружает модель, генерирует лид, сохраняет mix.mid.
"""

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import torch
from miditoolkit import MidiFile, Note, TempoChange, TimeSignature, Instrument

from train import MusicTransformer, BassLeadTokenizer


# ---------------------------------------------------------------------------
# Вспомогательные функции для работы с MIDI
# ---------------------------------------------------------------------------

def load_midi_info(midi_path: Path) -> Tuple[MidiFile, float, int]:
    """
    Загружает MIDI и возвращает: (MidiFile, original_bpm, original_ticks_per_beat)
    """
    midi = MidiFile(str(midi_path))
    
    # Определяем темп
    if midi.tempo_changes:
        original_bpm = midi.tempo_changes[0].tempo
    else:
        original_bpm = 120.0
    
    original_ticks = midi.ticks_per_beat
    
    return midi, original_bpm, original_ticks


def extract_bass_notes(midi: MidiFile) -> Tuple[List[Note], int]:
    """
    Извлекает ноты из первого трека MIDI (считаем его басом).
    Возвращает список нот и program number.
    """
    if not midi.instruments:
        raise ValueError("MIDI не содержит инструментов")
    
    instrument = midi.instruments[0]
    notes = sorted(instrument.notes, key=lambda n: n.start)
    program = instrument.program if instrument.program is not None else 33
    
    return notes, program


def normalize_notes_to_tempo(notes: List[Note], original_bpm: float, 
                             target_bpm: float = 120.0) -> List[Note]:
    """
    Масштабирует времена нот к целевому темпу.
    Возвращает НОВЫЙ список нот (не модифицирует оригинал).
    """
    if abs(original_bpm - target_bpm) < 0.1:
        return [Note(n.pitch, n.start, n.end, n.velocity) for n in notes]
    
    scale = original_bpm / target_bpm
    
    new_notes = []
    for note in notes:
        new_note = Note(
            pitch=note.pitch,
            start=int(note.start * scale),
            end=int(note.end * scale),
            velocity=note.velocity
        )
        new_notes.append(new_note)
    
    return new_notes


def denormalize_notes_to_tempo(notes: List[Note], target_bpm: float,
                               original_bpm: float = 120.0) -> List[Note]:
    """
    Обратное масштабирование: от target_bpm к original_bpm.
    """
    if abs(original_bpm - target_bpm) < 0.1:
        return [Note(n.pitch, n.start, n.end, n.velocity) for n in notes]
    
    scale = target_bpm / original_bpm
    
    new_notes = []
    for note in notes:
        new_note = Note(
            pitch=note.pitch,
            start=int(note.start * scale),
            end=int(note.end * scale),
            velocity=note.velocity
        )
        new_notes.append(new_note)
    
    return new_notes


def notes_to_midi(notes: List[Note], ticks_per_beat: int = 480, 
                  tempo: float = 120.0) -> MidiFile:
    """
    Создаёт MIDI-файл из списка нот.
    """
    midi = MidiFile(ticks_per_beat=ticks_per_beat)
    midi.tempo_changes.append(TempoChange(tempo=tempo, time=0))
    midi.time_signature_changes.append(TimeSignature(numerator=4, denominator=4, time=0))
    
    instrument = Instrument(program=0, name="Piano")
    instrument.notes = notes
    midi.instruments.append(instrument)
    
    return midi


def get_total_duration_ticks(notes: List[Note]) -> int:
    """Общая длительность нот в тиках (максимальный конец)."""
    if not notes:
        return 0
    return max(n.end for n in notes)


# ---------------------------------------------------------------------------
# Токенизация баса для подачи в модель
# ---------------------------------------------------------------------------

def tokenize_bass_only(
    tokenizer: BassLeadTokenizer,
    bass_notes: List[Note],
    ticks_per_beat: int = 480,
    tempo: float = 120.0
) -> List[str]:
    """
    Токенизирует только бас в формат:
    [BOS] [TRACK_BASS] бас-токены [BASS_END]
    """
    # Создаём временный MIDI только с басом
    bass_midi = MidiFile(ticks_per_beat=ticks_per_beat)
    bass_midi.tempo_changes.append(TempoChange(tempo=tempo, time=0))
    bass_midi.time_signature_changes.append(TimeSignature(numerator=4, denominator=4, time=0))
    
    instrument = Instrument(program=33, name="Bass")
    instrument.notes = bass_notes
    bass_midi.instruments.append(instrument)
    
    # Токенизируем через REMI
    remi_tokens = tokenizer.remi.midi_to_tokens(bass_midi)
    if not remi_tokens:
        raise ValueError("Не удалось токенизировать бас")
    
    bass_seq = remi_tokens[0]
    
    # Убираем BOS и EOS от REMI
    if bass_seq and bass_seq[0] == "BOS":
        bass_seq = bass_seq[1:]
    if bass_seq and bass_seq[-1] == "EOS":
        bass_seq = bass_seq[:-1]
    
    # Собираем полную префикс-последовательность
    prefix = ["BOS", "TRACK_BASS"] + bass_seq + ["BASS_END", "TRACK_LEAD"]
    
    return prefix


# ---------------------------------------------------------------------------
# Разбиение на окна для длинного баса
# ---------------------------------------------------------------------------

def split_into_windows(
    bass_notes: List[Note],
    window_size_measures: int = 16,
    overlap_measures: int = 4,
    beats_per_measure: int = 4,
    ticks_per_beat: int = 480
) -> List[Tuple[int, int, List[Note]]]:
    """
    Разбивает басовые ноты на перекрывающиеся окна.
    
    Возвращает список: [(start_tick, end_tick, window_notes), ...]
    где window_notes — ноты, попадающие в это окно (со сдвигом времени к началу окна).
    """
    window_ticks = window_size_measures * beats_per_measure * ticks_per_beat
    overlap_ticks = overlap_measures * beats_per_measure * ticks_per_beat
    stride = window_ticks - overlap_ticks
    
    total_ticks = get_total_duration_ticks(bass_notes)
    
    windows = []
    current_start = 0
    
    while current_start < total_ticks:
        current_end = current_start + window_ticks
        
        # Выбираем ноты, попадающие в окно
        window_notes = []
        for note in bass_notes:
            # Нота пересекается с окном
            if note.start < current_end and note.end > current_start:
                # Сдвигаем время к началу окна
                new_note = Note(
                    pitch=note.pitch,
                    start=max(0, note.start - current_start),
                    end=min(window_ticks, note.end - current_start),
                    velocity=note.velocity
                )
                window_notes.append(new_note)
        
        if window_notes:
            windows.append((current_start, current_end, window_notes))
        
        current_start += stride
    
    return windows


# ---------------------------------------------------------------------------
# Генерация лида
# ---------------------------------------------------------------------------

def generate_lead(
    model: MusicTransformer,
    tokenizer: BassLeadTokenizer,
    bass_notes: List[Note],
    ticks_per_beat: int = 480,
    window_size: int = 16,
    overlap: int = 4,
    temperature: float = 0.9,
    lead_tail_beats: int = 16,  # 4 такта = 16 долей
    device: str = "cuda",
) -> List[Note]:
    """
    Генерирует лид поверх заданного баса.
    
    Если бас длинный — разбивает на окна и склеивает результат.
    """
    total_ticks = get_total_duration_ticks(bass_notes)
    max_tokens = model.max_len
    
    # Токенизируем бас целиком
    prefix_tokens = tokenize_bass_only(tokenizer, bass_notes, ticks_per_beat)
    prefix_ids = tokenizer.tokens_to_ids(prefix_tokens)
    
    eos_id = tokenizer.token_to_id.get("EOS")
    
    # Если бас короткий — генерируем сразу
    if len(prefix_ids) < max_tokens // 2:
        print("  Бас короткий, генерируем одним проходом...")
        generated_ids = model.generate(
            prefix_ids=prefix_ids,
            max_new_tokens=max_tokens - len(prefix_ids),
            temperature=temperature,
            eos_id=eos_id,
        )
        return decode_lead_notes(tokenizer, generated_ids, ticks_per_beat, bass_notes, lead_tail_beats)
    
    # Длинный бас — разбиваем на окна
    print(f"  Бас длинный ({total_ticks} тиков), разбиваем на окна по {window_size} тактов...")
    
    windows = split_into_windows(
        bass_notes,
        window_size_measures=window_size,
        overlap_measures=overlap,
        ticks_per_beat=ticks_per_beat,
    )
    
    print(f"  Всего окон: {len(windows)}")
    
    all_lead_notes = []
    
    for win_idx, (win_start, win_end, win_bass_notes) in enumerate(windows):
        print(f"  Генерация окна {win_idx + 1}/{len(windows)} (тики {win_start}-{win_end})...")
        
        # Токенизируем бас этого окна
        win_prefix = tokenize_bass_only(tokenizer, win_bass_notes, ticks_per_beat)
        win_prefix_ids = tokenizer.tokens_to_ids(win_prefix)
        
        # Генерируем лид для окна
        win_generated_ids = model.generate(
            prefix_ids=win_prefix_ids,
            max_new_tokens=max_tokens - len(win_prefix_ids),
            temperature=temperature,
            eos_id=eos_id,
        )
        
        # Декодируем ноты лида из этого окна
        win_lead_notes = decode_lead_notes(
            tokenizer, win_generated_ids, ticks_per_beat,
            win_bass_notes, lead_tail_beats
        )
        
        # Сдвигаем ноты к глобальному времени
        for note in win_lead_notes:
            note.start += win_start
            note.end += win_start
        
        all_lead_notes.extend(win_lead_notes)
    
    # Склеиваем перекрытия: в зоне overlap выбираем ноты из более позднего окна
    all_lead_notes = merge_overlapping_notes(all_lead_notes, overlap, ticks_per_beat)
    
    return all_lead_notes


def decode_lead_notes(
    tokenizer: BassLeadTokenizer,
    generated_ids: List[int],
    ticks_per_beat: int,
    bass_notes: List[Note],
    lead_tail_beats: int,
) -> List[Note]:
    """
    Декодирует сгенерированные ID обратно в ноты лида.
    Отфильтровывает только то, что после TRACK_LEAD.
    """
    # Конвертируем ID в токены
    tokens = tokenizer.ids_to_tokens(generated_ids)
    
    # Находим TRACK_LEAD
    try:
        lead_start = tokens.index("TRACK_LEAD")
        lead_tokens = tokens[lead_start + 1:]  # всё после TRACK_LEAD
    except ValueError:
        lead_tokens = tokens
    
    # Убираем всё после EOS
    if "EOS" in lead_tokens:
        eos_idx = lead_tokens.index("EOS")
        lead_tokens = lead_tokens[:eos_idx]
    
    # Убираем специальные токены, оставляем только музыкальные
    special_tokens = {"PAD", "BOS", "EOS", "MASK", "TRACK_BASS", "TRACK_LEAD", "BASS_END"}
    lead_tokens = [t for t in lead_tokens if t not in special_tokens]
    
    # Конвертируем REMI-токены обратно в MIDI
    if not lead_tokens:
        return []
    
    # Создаём MIDI из токенов
    try:
        lead_midi = tokenizer.remi.tokens_to_midi(
            [lead_tokens],
            ticks_per_beat=ticks_per_beat,
        )
    except Exception as e:
        print(f"  ⚠️ Ошибка декодирования токенов лида: {e}")
        return []
    
    if not lead_midi.instruments:
        return []
    
    lead_notes = lead_midi.instruments[0].notes
    
    # Обрезаем лид по длительности баса + хвост
    max_bass_tick = max(n.end for n in bass_notes) if bass_notes else 0
    max_lead_tick = max_bass_tick + lead_tail_beats * ticks_per_beat
    
    lead_notes = [n for n in lead_notes if n.start <= max_lead_tick]
    
    return lead_notes


def merge_overlapping_notes(
    notes: List[Note],
    overlap_measures: int,
    ticks_per_beat: int,
    beats_per_measure: int = 4,
) -> List[Note]:
    """
    Склеивает ноты из перекрывающихся окон.
    В зоне перекрытия оставляет ноты из более позднего окна.
    """
    if not notes:
        return []
    
    overlap_ticks = overlap_measures * beats_per_measure * ticks_per_beat
    
    # Сортируем по началу
    notes = sorted(notes, key=lambda n: n.start)
    
    # Находим зоны перекрытия и удаляем дубликаты
    # Упрощённый подход: удаляем ноты, которые полностью перекрыты более поздними
    result = []
    for note in notes:
        # Проверяем, нет ли уже ноты в этом же месте
        is_duplicate = False
        for existing in result:
            if (abs(existing.start - note.start) < ticks_per_beat // 4 and
                existing.pitch == note.pitch):
                # Оставляем более длинную или более позднюю
                is_duplicate = True
                break
        
        if not is_duplicate:
            result.append(note)
    
    return result


# ---------------------------------------------------------------------------
# Сборка выходного микса
# ---------------------------------------------------------------------------

def build_output_midi(
    bass_notes: List[Note],
    lead_notes: List[Note],
    original_bpm: float,
    output_path: Path,
    bass_program: int = 33,
    lead_program: int = 29,
    ticks_per_beat: int = 480,
):
    """
    Собирает финальный MIDI с басом и лидом.
    """
    midi = MidiFile(ticks_per_beat=ticks_per_beat)
    
    # Темп и размер
    midi.tempo_changes.append(TempoChange(tempo=original_bpm, time=0))
    midi.time_signature_changes.append(TimeSignature(numerator=4, denominator=4, time=0))
    
    # Трек баса
    bass_instrument = Instrument(program=bass_program, name="Bass")
    bass_instrument.notes = sorted(bass_notes, key=lambda n: n.start)
    midi.instruments.append(bass_instrument)
    
    # Трек лида
    lead_instrument = Instrument(program=lead_program, name="Lead")
    lead_instrument.notes = sorted(lead_notes, key=lambda n: n.start)
    midi.instruments.append(lead_instrument)
    
    # Сохраняем
    output_path.parent.mkdir(parents=True, exist_ok=True)
    midi.dump(str(output_path))


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Генерация лида поверх заданного баса"
    )
    
    # Вход/выход
    parser.add_argument("bass_midi", type=Path,
                       help="Входной MIDI с басом")
    parser.add_argument("--output", type=Path, default=Path("mix.mid"),
                       help="Выходной микс (по умолчанию mix.mid)")
    
    # Модель
    parser.add_argument("--model_dir", type=Path, default=Path("./model_output"),
                       help="Папка с обученной моделью и токенизатором")
    parser.add_argument("--checkpoint", type=str, default="best_model.pt",
                       help="Имя чекпоинта (best_model.pt, final_model.pt, или checkpoint_epoch_N.pt)")
    
    # Параметры генерации
    parser.add_argument("--temperature", type=float, default=0.9,
                       help="Температура семплирования (0.1-2.0)")
    parser.add_argument("--seed", type=int, default=None,
                       help="Seed для воспроизводимости")
    parser.add_argument("--lead_tail", type=float, default=4.0,
                       help="Максимальный хвост лида после баса (в тактах)")
    
    # Параметры окон
    parser.add_argument("--window_size", type=int, default=16,
                       help="Размер окна в тактах")
    parser.add_argument("--overlap", type=int, default=4,
                       help="Перекрытие окон в тактах")
    
    # Параметры инструментов
    parser.add_argument("--bass_program", type=int, default=33,
                       help="MIDI program для баса (по умолчанию 33 = Electric Bass)")
    parser.add_argument("--lead_program", type=int, default=29,
                       help="MIDI program для лида (по умолчанию 29 = Overdriven Guitar)")
    
    # Прочее
    parser.add_argument("--device", type=str, default="cuda",
                       help="Устройство (cuda/cpu)")
    parser.add_argument("--save_lead_only", action="store_true",
                       help="Сохранить только лид (без баса) в отдельный файл")
    
    args = parser.parse_args()
    
    # Проверяем входной файл
    if not args.bass_midi.exists():
        print(f"❌ Файл не найден: {args.bass_midi}")
        sys.exit(1)
    
    # Устанавливаем seed
    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)
        torch.manual_seed(args.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(args.seed)
        print(f"🎲 Seed: {args.seed}")
    else:
        # Генерируем случайный seed и выводим его
        seed = random.randint(0, 2**32 - 1)
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        print(f"🎲 Seed (сохраните для воспроизведения): {seed}")
    
    # Устройство
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    print(f"💻 Устройство: {device}")
    
    # Загружаем токенизатор
    print("\n📚 Загрузка токенизатора...")
    vocab_path = args.model_dir / "tokenizer_vocab.json"
    if not vocab_path.exists():
        print(f"❌ Словарь токенизатора не найден: {vocab_path}")
        sys.exit(1)
    
    with open(vocab_path, "r") as f:
        vocab = json.load(f)
    
    # Создаём токенизатор и восстанавливаем словарь
    tokenizer = BassLeadTokenizer(beat_res=8)
    tokenizer.token_to_id = vocab
    tokenizer.id_to_token = {int(v): k for k, v in vocab.items()}
    tokenizer.vocab_size = len(vocab)
    tokenizer.remi.vocab = vocab
    tokenizer.remi._vocab_base = vocab.copy()
    print(f"  Размер словаря: {tokenizer.vocab_size}")
    
    # Загружаем конфиг модели
    config_path = args.model_dir / "config.json"
    if config_path.exists():
        with open(config_path, "r") as f:
            config = json.load(f)
    else:
        # Значения по умолчанию
        config = {
            "vocab_size": tokenizer.vocab_size,
            "d_model": 512,
            "nhead": 8,
            "num_layers": 8,
            "dim_feedforward": 2048,
            "max_len": 2048,
            "dropout": 0.1,
        }
        print("  ⚠️ config.json не найден, используем параметры по умолчанию")
    
    # Загружаем модель
    print("\n🧠 Загрузка модели...")
    model = MusicTransformer(
        vocab_size=config["vocab_size"],
        d_model=config["d_model"],
        nhead=config["nhead"],
        num_layers=config["num_layers"],
        dim_feedforward=config["dim_feedforward"],
        max_len=config["max_len"],
        dropout=config.get("dropout", 0.1),
    ).to(device)
    
    checkpoint_path = args.model_dir / args.checkpoint
    if not checkpoint_path.exists():
        print(f"❌ Чекпоинт не найден: {checkpoint_path}")
        sys.exit(1)
    
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    print(f"  Загружен чекпоинт: {args.checkpoint}")
    print(f"  Эпоха: {checkpoint.get('epoch', 'неизвестно')}")
    print(f"  Loss: {checkpoint.get('loss', 'неизвестно')}")
    
    # Загружаем бас
    print(f"\n🎸 Загрузка баса: {args.bass_midi}")
    bass_midi, original_bpm, original_ticks = load_midi_info(args.bass_midi)
    bass_notes, detected_bass_program = extract_bass_notes(bass_midi)
    print(f"  Нот: {len(bass_notes)}")
    print(f"  Исходный темп: {original_bpm:.1f} BPM")
    print(f"  Program: {detected_bass_program}")
    
    if not bass_notes:
        print("❌ В басовом треке нет нот")
        sys.exit(1)
    
    # Нормализуем бас к 120 BPM
    print("\n⏱️  Нормализация темпа к 120 BPM...")
    bass_notes_normalized = normalize_notes_to_tempo(bass_notes, original_bpm, 120.0)
    
    # Генерируем лид
    print("\n🎶 Генерация лида...")
    lead_tail_beats = int(args.lead_tail * 4)  # такты → доли
    
    lead_notes_normalized = generate_lead(
        model=model,
        tokenizer=tokenizer,
        bass_notes=bass_notes_normalized,
        ticks_per_beat=480,
        window_size=args.window_size,
        overlap=args.overlap,
        temperature=args.temperature,
        lead_tail_beats=lead_tail_beats,
        device=device,
    )
    
    print(f"  Сгенерировано нот лида: {len(lead_notes_normalized)}")
    
    # Денормализуем обратно к исходному темпу
    print(f"\n⏱️  Денормализация к исходному темпу ({original_bpm:.1f} BPM)...")
    lead_notes_final = denormalize_notes_to_tempo(lead_notes_normalized, 120.0, original_bpm)
    
    # Собираем выходной микс
    print(f"\n💾 Сохранение микса...")
    build_output_midi(
        bass_notes=bass_notes,
        lead_notes=lead_notes_final,
        original_bpm=original_bpm,
        output_path=args.output,
        bass_program=args.bass_program if args.bass_program != 33 else detected_bass_program,
        lead_program=args.lead_program,
        ticks_per_beat=original_ticks,
    )
    print(f"  ✅ Микс сохранён: {args.output}")
    
    # Опционально сохраняем только лид
    if args.save_lead_only:
        lead_only_path = args.output.parent / f"{args.output.stem}_lead_only.mid"
        lead_midi = MidiFile(ticks_per_beat=original_ticks)
        lead_midi.tempo_changes.append(TempoChange(tempo=original_bpm, time=0))
        lead_midi.time_signature_changes.append(TimeSignature(numerator=4, denominator=4, time=0))
        lead_instrument = Instrument(program=args.lead_program, name="Lead")
        lead_instrument.notes = sorted(lead_notes_final, key=lambda n: n.start)
        lead_midi.instruments.append(lead_instrument)
        lead_midi.dump(str(lead_only_path))
        print(f"  ✅ Только лид: {lead_only_path}")
    
    # Итоговая статистика
    print("\n" + "=" * 60)
    print("📊 Статистика:")
    print(f"  Бас: {len(bass_notes)} нот, {get_total_duration_ticks(bass_notes) / original_ticks / 4:.1f} тактов")
    print(f"  Лид: {len(lead_notes_final)} нот")
    print(f"  Темп: {original_bpm:.1f} BPM")
    print(f"  Seed: {args.seed if args.seed else seed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
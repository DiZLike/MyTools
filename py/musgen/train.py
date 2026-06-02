#!/usr/bin/env python3
"""
Обучение модели для генерации лида поверх баса.
Читает MIDI с двумя треками (бас + лид), токенизирует, обучает Transformer.
"""

import argparse
import json
import math
import random
from pathlib import Path
from typing import List, Optional
from datetime import datetime

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR

from miditoolkit import MidiFile
from miditok import REMI
from miditok.constants import PITCH_RANGE, NB_VELOCITIES, BEAT_RES


# ---------------------------------------------------------------------------
# Кастомный токенизатор (расширяем REMI)
# ---------------------------------------------------------------------------

class BassLeadTokenizer:
    """
    Обёртка над MidiTok REMI с дополнительными токенами для баса и лида.
    """
    
    # Дополнительные токены, которых нет в стандартном REMI
    CUSTOM_TOKENS = [
        "TRACK_BASS",      # переключение на бас
        "TRACK_LEAD",      # переключение на лид
        "BASS_END",        # конец басовой партии
        "LEAD_REST",       # явная пауза лида
    ]
    
    def __init__(self, beat_res: int = 8, ticks_per_beat: int = 480):
        # Стандартный REMI токенизатор
        self.remi = REMI(
            pitch_range=PITCH_RANGE,
            beat_res={(0, 4): beat_res},
            nb_velocities=NB_VELOCITIES,
            special_tokens=["PAD", "BOS", "EOS", "MASK"],
            mask=True,
            additional_tokens={
                "Chord": True,
                "Rest": True,
                "Tempo": False,
                "TimeSignature": False,
            }
        )
        
        self.beat_res = beat_res
        self.ticks_per_beat = ticks_per_beat
        
        # Получаем базовый словарь REMI
        base_vocab = self.remi.vocab
        
        # Добавляем наши токены
        for token in self.CUSTOM_TOKENS:
            if token not in base_vocab:
                base_vocab[token] = len(base_vocab)
        
        # Обновляем словарь в REMI
        self.remi.vocab = base_vocab
        self.remi._vocab_base = base_vocab.copy()
        
        # Словари для конвертации
        self.token_to_id = base_vocab
        self.id_to_token = {v: k for k, v in base_vocab.items()}
        self.vocab_size = len(base_vocab)
    
    def tokenize_midi(self, midi_path: Path) -> Optional[List[str]]:
        """
        Токенизирует MIDI с басом и лидом в единую последовательность.
        Формат: [BOS] [TRACK_BASS] бас-токены [BASS_END] [TRACK_LEAD] лид-токены [EOS]
        """
        try:
            midi = MidiFile(str(midi_path))
        except Exception:
            return None
        
        if len(midi.instruments) < 2:
            return None
        
        # Токенизируем бас
        bass_midi = MidiFile(ticks_per_beat=self.ticks_per_beat)
        bass_midi.instruments = [midi.instruments[0]]
        bass_midi.tempo_changes = midi.tempo_changes
        bass_midi.time_signature_changes = midi.time_signature_changes
        
        # Токенизируем лид
        lead_midi = MidiFile(ticks_per_beat=self.ticks_per_beat)
        lead_midi.instruments = [midi.instruments[1]]
        lead_midi.tempo_changes = midi.tempo_changes
        lead_midi.time_signature_changes = midi.time_signature_changes
        
        try:
            bass_tokens = self.remi.midi_to_tokens(bass_midi)
            lead_tokens = self.remi.midi_to_tokens(lead_midi)
        except Exception:
            return None
        
        if not bass_tokens or not lead_tokens:
            return None
        
        # Собираем полную последовательность
        # BOS уже есть в начале bass_tokens[0] от REMI
        full_sequence = ["BOS", "TRACK_BASS"]
        
        # Добавляем бас (пропускаем BOS и EOS от REMI)
        bass_seq = bass_tokens[0]
        if bass_seq and bass_seq[0] == "BOS":
            bass_seq = bass_seq[1:]
        if bass_seq and bass_seq[-1] == "EOS":
            bass_seq = bass_seq[:-1]
        full_sequence.extend(bass_seq)
        
        # Маркер конца баса и начало лида
        full_sequence.append("BASS_END")
        full_sequence.append("TRACK_LEAD")
        
        # Добавляем лид (пропускаем BOS, оставляем EOS)
        lead_seq = lead_tokens[0]
        if lead_seq and lead_seq[0] == "BOS":
            lead_seq = lead_seq[1:]
        # EOS оставляем — это конец всего произведения
        full_sequence.extend(lead_seq)
        
        # Если EOS нет в конце лида, добавляем
        if full_sequence[-1] != "EOS":
            full_sequence.append("EOS")
        
        return full_sequence
    
    def tokens_to_ids(self, tokens: List[str]) -> List[int]:
        """Конвертирует токены в ID."""
        return [self.token_to_id.get(t, self.token_to_id["PAD"]) for t in tokens]
    
    def ids_to_tokens(self, ids: List[int]) -> List[str]:
        """Конвертирует ID обратно в токены."""
        return [self.id_to_token.get(i, "PAD") for i in ids]


# ---------------------------------------------------------------------------
# Аугментация: транспонирование
# ---------------------------------------------------------------------------

def transpose_tokens(tokens: List[str], semitones: int) -> List[str]:
    """
    Транспонирует все Pitch-токены на заданное число полутонов.
    Токены вида "Pitch_60" становятся "Pitch_67" при semitones=7.
    """
    result = []
    for token in tokens:
        if token.startswith("Pitch_"):
            try:
                pitch = int(token.split("_")[1])
                new_pitch = pitch + semitones
                if 0 <= new_pitch <= 127:
                    result.append(f"Pitch_{new_pitch}")
                else:
                    # Выходит за диапазон — оставляем исходный
                    result.append(token)
            except (IndexError, ValueError):
                result.append(token)
        else:
            result.append(token)
    return result


# ---------------------------------------------------------------------------
# Датасет
# ---------------------------------------------------------------------------

class BassLeadDataset(Dataset):
    """Датасет для обучения: последовательности токенов, сдвинутые на 1."""
    
    def __init__(
        self,
        tokenizer: BassLeadTokenizer,
        midi_dir: Path,
        max_len: int = 2048,
        augment_transpose: bool = True,
        stats_path: Optional[Path] = None
    ):
        self.tokenizer = tokenizer
        self.max_len = max_len
        self.sequences = []
        
        midi_files = sorted(midi_dir.glob("*.mid"))
        print(f"Загрузка MIDI из {midi_dir}...")
        
        skipped = 0
        total_notes_processed = 0
        
        for midi_path in midi_files:
            tokens = tokenizer.tokenize_midi(midi_path)
            if tokens is None:
                skipped += 1
                continue
            
            ids = tokenizer.tokens_to_ids(tokens)
            
            # Добавляем оригинал
            self._add_sequence(ids, tokens)
            
            # Аугментация: транспонирование во все 12 тональностей
            if augment_transpose:
                for semitones in range(-6, 7):
                    if semitones == 0:
                        continue
                    transposed = transpose_tokens(tokens, semitones)
                    transposed_ids = tokenizer.tokens_to_ids(transposed)
                    self._add_sequence(transposed_ids, transposed)
            
            total_notes_processed += 1
        
        print(f"Загружено файлов: {total_notes_processed}, пропущено: {skipped}")
        print(f"Всего обучающих примеров (с аугментацией): {len(self.sequences)}")
        
        # Сохраняем статистику
        if stats_path:
            stats = {
                "total_files": len(midi_files),
                "loaded": total_notes_processed,
                "skipped": skipped,
                "total_examples": len(self.sequences),
                "max_len": max_len,
                "vocab_size": tokenizer.vocab_size,
                "augment_transpose": augment_transpose,
            }
            stats_path.parent.mkdir(parents=True, exist_ok=True)
            with open(stats_path, 'w') as f:
                json.dump(stats, f, indent=2)
    
    def _add_sequence(self, ids: List[int], tokens: List[str]):
        """Разбивает длинную последовательность на окна."""
        # Если последовательность короче max_len, дополняем PAD
        if len(ids) <= self.max_len:
            self.sequences.append(ids)
        else:
            # Разбиваем на перекрывающиеся окна
            stride = self.max_len // 2
            for start in range(0, len(ids) - self.max_len + 1, stride):
                window = ids[start:start + self.max_len]
                self.sequences.append(window)
    
    def __len__(self):
        return len(self.sequences)
    
    def __getitem__(self, idx):
        seq = self.sequences[idx]
        # padding до max_len
        padded = seq + [self.tokenizer.token_to_id["PAD"]] * (self.max_len - len(seq))
        padded = padded[:self.max_len]
        
        x = torch.tensor(padded[:-1], dtype=torch.long)
        y = torch.tensor(padded[1:], dtype=torch.long)
        return x, y


# ---------------------------------------------------------------------------
# Модель: Transformer Decoder с Rotary Position Embeddings
# ---------------------------------------------------------------------------

class RotaryPositionalEmbedding(nn.Module):
    """Rotary Position Embedding (RoPE) для лучшей работы с длинными последовательностями."""
    
    def __init__(self, d_model: int, max_len: int = 4096):
        super().__init__()
        self.d_model = d_model
        self.max_len = max_len
        
        # Предвычисляем частоты
        position = torch.arange(max_len).unsqueeze(1).float()
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        self.register_buffer("sin", torch.sin(position * div_term))
        self.register_buffer("cos", torch.cos(position * div_term))
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Применяет RoPE к входному тензору.
        x: [batch, seq_len, d_model]
        """
        seq_len = x.shape[1]
        sin = self.sin[:seq_len, :].unsqueeze(0)  # [1, seq_len, d_model/2]
        cos = self.cos[:seq_len, :].unsqueeze(0)  # [1, seq_len, d_model/2]
        
        # Разделяем на чётные и нечётные индексы
        x_even = x[..., 0::2]
        x_odd = x[..., 1::2]
        
        # Применяем поворот
        x_rotated_even = x_even * cos - x_odd * sin
        x_rotated_odd = x_even * sin + x_odd * cos
        
        # Собираем обратно
        result = torch.zeros_like(x)
        result[..., 0::2] = x_rotated_even
        result[..., 1::2] = x_rotated_odd
        
        return result


class MusicTransformer(nn.Module):
    """Transformer Decoder для генерации музыки."""
    
    def __init__(
        self,
        vocab_size: int,
        d_model: int = 512,
        nhead: int = 8,
        num_layers: int = 8,
        dim_feedforward: int = 2048,
        max_len: int = 2048,
        dropout: float = 0.1,
    ):
        super().__init__()
        
        self.token_embedding = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.rope = RotaryPositionalEmbedding(d_model, max_len)
        self.dropout = nn.Dropout(dropout)
        
        # Transformer decoder layers
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
        )
        self.transformer = nn.TransformerDecoder(decoder_layer, num_layers=num_layers)
        
        self.output_proj = nn.Linear(d_model, vocab_size)
        self.max_len = max_len
        
        # Инициализация весов
        self._init_weights()
    
    def _init_weights(self):
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: [batch, seq_len] — токены
        возвращает: [batch, seq_len, vocab_size] — логиты
        """
        B, L = x.shape
        
        # Эмбеддинги
        x_emb = self.token_embedding(x)  # [B, L, d_model]
        
        # RoPE
        x_emb = self.rope(x_emb)
        x_emb = self.dropout(x_emb)
        
        # Каузальная маска (не смотреть в будущее)
        causal_mask = nn.Transformer.generate_square_subsequent_mask(L).to(x.device)
        
        # Transformer decoder (self-attention только)
        # memory = x_emb для self-attention режима
        out = self.transformer(
            tgt=x_emb,
            memory=x_emb,
            tgt_mask=causal_mask,
            memory_mask=causal_mask,
        )
        
        # Проекция на словарь
        logits = self.output_proj(out)  # [B, L, vocab_size]
        
        return logits
    
    @torch.no_grad()
    def generate(
        self,
        prefix_ids: List[int],
        max_new_tokens: int = 512,
        temperature: float = 0.9,
        top_k: int = 50,
        top_p: float = 0.95,
        eos_id: Optional[int] = None,
    ) -> List[int]:
        """
        Авторегрессионная генерация.
        prefix_ids: начальные токены (бас + BASS_END + TRACK_LEAD)
        """
        self.eval()
        generated = list(prefix_ids)
        
        for _ in range(max_new_tokens):
            # Берём последние max_len токенов
            input_ids = generated[-self.max_len:]
            input_tensor = torch.tensor([input_ids], device=next(self.parameters()).device)
            
            # Предсказание
            logits = self(input_tensor)  # [1, L, vocab]
            next_logits = logits[0, -1, :]  # [vocab]
            
            # Температура
            next_logits = next_logits / temperature
            
            # Top-K фильтрация
            if top_k > 0:
                top_k_values, top_k_indices = torch.topk(next_logits, top_k)
                next_logits = torch.full_like(next_logits, float('-inf'))
                next_logits[top_k_indices] = top_k_values
            
            # Top-P (nucleus) фильтрация
            if top_p < 1.0:
                sorted_logits, sorted_indices = torch.sort(next_logits, descending=True)
                cumulative_probs = torch.cumsum(torch.softmax(sorted_logits, dim=-1), dim=-1)
                sorted_indices_to_remove = cumulative_probs > top_p
                sorted_indices_to_remove[1:] = sorted_indices_to_remove[:-1].clone()
                sorted_indices_to_remove[0] = False
                indices_to_remove = sorted_indices[sorted_indices_to_remove]
                next_logits[indices_to_remove] = float('-inf')
            
            # Семплирование
            probs = torch.softmax(next_logits, dim=-1)
            next_token = torch.multinomial(probs, 1).item()
            
            generated.append(next_token)
            
            # Проверка на EOS
            if eos_id is not None and next_token == eos_id:
                break
        
        return generated


# ---------------------------------------------------------------------------
# Обучение
# ---------------------------------------------------------------------------

def train_epoch(model, dataloader, optimizer, criterion, device):
    model.train()
    total_loss = 0
    
    for batch_idx, (x, y) in enumerate(dataloader):
        x, y = x.to(device), y.to(device)
        
        optimizer.zero_grad()
        logits = model(x)  # [B, L, vocab]
        
        # Переформатируем для CrossEntropy
        loss = criterion(
            logits.reshape(-1, logits.size(-1)),
            y.reshape(-1)
        )
        
        loss.backward()
        
        # Gradient clipping
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        
        optimizer.step()
        total_loss += loss.item()
        
        if batch_idx % 50 == 0:
            print(f"  Батч {batch_idx}/{len(dataloader)}, loss: {loss.item():.4f}")
    
    return total_loss / len(dataloader)


def main():
    parser = argparse.ArgumentParser(description="Обучение модели бас+лид")
    
    # Данные
    parser.add_argument("--midi_dir", type=Path, default=Path("./midi_dataset"),
                       help="Папка с MIDI-файлами")
    parser.add_argument("--output_dir", type=Path, default=Path("./model_output"),
                       help="Папка для сохранения модели")
    
    # Параметры токенизатора
    parser.add_argument("--beat_res", type=int, default=8,
                       help="Разрешение сетки (делений на долю)")
    
    # Параметры модели
    parser.add_argument("--d_model", type=int, default=512,
                       help="Размерность модели")
    parser.add_argument("--nhead", type=int, default=8,
                       help="Число голов внимания")
    parser.add_argument("--num_layers", type=int, default=8,
                       help="Число слоёв трансформера")
    parser.add_argument("--dim_feedforward", type=int, default=2048,
                       help="Размерность скрытого слоя FFN")
    parser.add_argument("--max_len", type=int, default=2048,
                       help="Максимальная длина последовательности")
    parser.add_argument("--dropout", type=float, default=0.1,
                       help="Dropout")
    
    # Параметры обучения
    parser.add_argument("--batch_size", type=int, default=8,
                       help="Размер батча")
    parser.add_argument("--epochs", type=int, default=50,
                       help="Количество эпох")
    parser.add_argument("--lr", type=float, default=1e-4,
                       help="Learning rate")
    parser.add_argument("--weight_decay", type=float, default=0.01,
                       help="Weight decay")
    
    # Аугментация
    parser.add_argument("--no_augment", action="store_true",
                       help="Отключить транспонирование")
    
    # Прочее
    parser.add_argument("--device", type=str, default="cuda",
                       help="Устройство (cuda/cpu)")
    parser.add_argument("--num_workers", type=int, default=4,
                       help="Количество воркеров для DataLoader")
    
    args = parser.parse_args()
    
    # Устройство
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    print(f"Устройство: {device}")
    
    # Создаём токенизатор
    print("Инициализация токенизатора...")
    tokenizer = BassLeadTokenizer(beat_res=args.beat_res)
    print(f"Размер словаря: {tokenizer.vocab_size}")
    
    # Загружаем датасет
    print("\nЗагрузка датасета...")
    dataset = BassLeadDataset(
        tokenizer=tokenizer,
        midi_dir=args.midi_dir,
        max_len=args.max_len,
        augment_transpose=not args.no_augment,
        stats_path=args.output_dir / "dataset_stats.json",
    )
    
    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=True,
    )
    
    # Создаём модель
    print("\nСоздание модели...")
    model = MusicTransformer(
        vocab_size=tokenizer.vocab_size,
        d_model=args.d_model,
        nhead=args.nhead,
        num_layers=args.num_layers,
        dim_feedforward=args.dim_feedforward,
        max_len=args.max_len,
        dropout=args.dropout,
    ).to(device)
    
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Параметров: {total_params:,} (обучаемых: {trainable_params:,})")
    
    # Оптимизатор и планировщик
    optimizer = AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=args.weight_decay,
        betas=(0.9, 0.98),
    )
    scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=args.lr * 0.1)
    criterion = nn.CrossEntropyLoss(ignore_index=tokenizer.token_to_id["PAD"])
    
    # Создаём выходную папку
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Сохраняем конфиг
    config = vars(args).copy()
    config["vocab_size"] = tokenizer.vocab_size
    config["total_params"] = total_params
    config["trainable_params"] = trainable_params
    with open(args.output_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2, default=str)
    
    # Обучение
    print("\n" + "=" * 60)
    print("Начинаем обучение")
    print("=" * 60)
    
    best_loss = float('inf')
    
    for epoch in range(args.epochs):
        print(f"\nЭпоха {epoch + 1}/{args.epochs}")
        print("-" * 40)
        
        train_loss = train_epoch(model, dataloader, optimizer, criterion, device)
        scheduler.step()
        
        current_lr = scheduler.get_last_lr()[0]
        print(f"Средний loss: {train_loss:.4f}, LR: {current_lr:.6f}")
        
        # Сохраняем чекпоинт
        checkpoint = {
            "epoch": epoch + 1,
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "loss": train_loss,
            "config": config,
        }
        
        # Сохраняем каждые 10 эпох и лучшую модель
        if (epoch + 1) % 10 == 0:
            torch.save(checkpoint, args.output_dir / f"checkpoint_epoch_{epoch+1}.pt")
        
        if train_loss < best_loss:
            best_loss = train_loss
            torch.save(checkpoint, args.output_dir / "best_model.pt")
            print(f"  ✓ Новая лучшая модель (loss: {best_loss:.4f})")
    
    # Сохраняем финальную модель и токенизатор
    torch.save(checkpoint, args.output_dir / "final_model.pt")
    
    # Сохраняем словарь токенизатора
    with open(args.output_dir / "tokenizer_vocab.json", "w") as f:
        json.dump(tokenizer.token_to_id, f, indent=2)
    
    print("\n" + "=" * 60)
    print(f"Обучение завершено! Лучший loss: {best_loss:.4f}")
    print(f"Модель сохранена в {args.output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
"""
compare.py
Сравнение качества аудио треков с референсом (регрессия).
Поддерживает ансамбль из нескольких моделей.
С онлайн-коррекцией (без катастрофического забывания).

Использование:
  python compare.py <референс> <трек1> <трек2> ...
  python compare.py --train <референс> <трек1> <трек2> ...
  python compare.py --model compare_model.pth <референс> <трек1> ...
"""

import os
import sys
import argparse
import json
import copy
import numpy as np
import torch
import torch.nn as nn
import librosa
import subprocess
import tempfile
from tqdm import tqdm
from collections import deque
import warnings
warnings.filterwarnings('ignore')

# ========== НАСТРОЙКИ ==========
SR = 44100
SEGMENT_DURATION = 1.0
SAMPLES_PER_SEGMENT = int(SEGMENT_DURATION * SR)
HOP = SAMPLES_PER_SEGMENT
N_MELS = 128
N_FFT = 2048
HOP_LENGTH = 512

# Параметры онлайн-обучения
ONLINE_LR = 0.00001        # Очень маленький LR чтобы не сломать веса
ONLINE_MARGIN = 0.03       # Минимальная разница между better и worse
ONLINE_STEPS = 3           # Количество шагов градиента на одну правку
MAX_CORRECTIONS = 50       # Максимум правок за сессию (защита)
EWC_LAMBDA_ONLINE = 10000  # Сильный EWC для защиты весов
BUFFER_SIZE = 20           # Буфер для реплея старых примеров

DEFAULT_MODELS = [
    "compare_model_mp3.pth",
    "compare_model_aac.pth", 
    "compare_model_opus.pth",
]

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
AUDIO_EXTENSIONS = {'.wav', '.flac', '.mp3', '.opus', '.m4a', '.aac', '.ogg', '.wma', '.aiff', '.aif'}


# ========== МОДЕЛЬ ==========
class SEBlock(nn.Module):
    def __init__(self, channels, reduction=16):
        super().__init__()
        self.fc = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(channels, channels // reduction),
            nn.ReLU(),
            nn.Linear(channels // reduction, channels),
            nn.Sigmoid()
        )
    
    def forward(self, x):
        b, c, _, _ = x.shape
        return x * self.fc(x).view(b, c, 1, 1)


class AudioEncoder(nn.Module):
    def __init__(self, in_channels=1):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(in_channels, 32, 3, padding=1),
            nn.BatchNorm2d(32), nn.ReLU(), SEBlock(32),
            nn.MaxPool2d(2), nn.Dropout2d(0.1),
            
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64), nn.ReLU(), SEBlock(64),
            nn.MaxPool2d(2), nn.Dropout2d(0.2),
            
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128), nn.ReLU(), SEBlock(128),
            nn.MaxPool2d(2), nn.Dropout2d(0.3),
            
            nn.Conv2d(128, 256, 3, padding=1),
            nn.BatchNorm2d(256), nn.ReLU(), SEBlock(256),
            nn.AdaptiveAvgPool2d((4, 4)),
        )
        self.embedding_dim = 256 * 4 * 4
    
    def forward(self, x):
        return self.features(x)


class AudioCompareNet(nn.Module):
    """Регрессия: предсказывает similarity 0..1."""
    def __init__(self, in_channels=1):
        super().__init__()
        self.encoder = AudioEncoder(in_channels)
        embed_dim = self.encoder.embedding_dim
        
        self.regressor = nn.Sequential(
            nn.Linear(embed_dim * 3, 512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid()
        )
    
    def forward(self, spec_a, spec_b):
        emb_a = self.encoder(spec_a).flatten(1)
        emb_b = self.encoder(spec_b).flatten(1)
        diff = torch.abs(emb_a - emb_b)
        combined = torch.cat([emb_a, emb_b, diff], dim=1)
        return self.regressor(combined)


# ========== ЗАГРУЗКА АУДИО ==========
def load_audio(path, target_sr=SR):
    if path.lower().endswith('.opus'):
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_name = tmp.name
            cmd = [
                'ffmpeg', '-y', '-i', os.path.abspath(path),
                '-vn', '-ac', '1', '-ar', str(target_sr),
                '-f', 'wav', tmp_name
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            y, _ = librosa.load(tmp_name, sr=target_sr, mono=True)
            os.unlink(tmp_name)
            return y
        except:
            return None

    try:
        y, _ = librosa.load(path, sr=target_sr, mono=True)
        return y
    except:
        pass

    try:
        import soundfile as sf
        y, sr = sf.read(path, dtype='float32')
        if y.ndim > 1:
            y = y.mean(axis=1)
        if sr != target_sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
        return y
    except:
        pass

    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_name = tmp.name
        cmd = [
            'ffmpeg', '-y', '-i', os.path.abspath(path),
            '-vn', '-ac', '1', '-ar', str(target_sr),
            '-f', 'wav', tmp_name
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        y, _ = librosa.load(tmp_name, sr=target_sr, mono=True)
        os.unlink(tmp_name)
        return y
    except:
        return None


def extract_mel(audio):
    mel = librosa.feature.melspectrogram(
        y=audio, sr=SR, n_mels=N_MELS, n_fft=N_FFT, hop_length=HOP_LENGTH
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)
    mel_db = (mel_db - mel_db.mean()) / (mel_db.std() + 1e-8)
    return mel_db.astype(np.float32)


def align_audio(reference, target):
    correlation = np.correlate(reference[:min(5*SR, len(reference))], 
                               target[:min(5*SR, len(target))], mode='full')
    lag = np.argmax(correlation) - (min(5*SR, len(target)) - 1)
    
    if lag > 0:
        target = target[lag:]
        reference = reference[:len(target)]
    elif lag < 0:
        reference = reference[-lag:]
        target = target[:len(reference)]
    
    return reference, target


def trim_silence(audio, top_db=30):
    trimmed, _ = librosa.effects.trim(audio, top_db=top_db)
    if len(trimmed) == 0:
        return audio
    return trimmed


def collect_audio_files(paths):
    files = []
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, filenames in os.walk(path):
                for f in sorted(filenames):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in AUDIO_EXTENSIONS:
                        files.append(os.path.join(root, f))
        elif os.path.isfile(path):
            files.append(path)
        else:
            print(f"  ⚠ Пропущено (не найдено): {path}")
    return files


def load_models(model_paths):
    """Загружает несколько моделей."""
    models = {}
    
    for path in model_paths:
        if not os.path.exists(path):
            print(f"  ⚠ Модель не найдена: {path}")
            continue
        
        model = AudioCompareNet(in_channels=1).to(DEVICE)
        model.load_state_dict(torch.load(path, map_location=DEVICE, weights_only=False))
        model.eval()
        
        name = os.path.splitext(os.path.basename(path))[0]
        models[name] = model
        print(f"  ✓ {name}")
    
    return models


def compare_with_model(model, ref_audio, track_paths):
    """Сравнивает треки с референсом используя одну модель (регрессия)."""
    results = []
    
    for track_path in tqdm(track_paths, desc="Сравнение", leave=False):
        track_audio = load_audio(track_path)
        if track_audio is None:
            results.append((track_path, 0.0))
            continue
        
        track_audio = trim_silence(track_audio)
        ref_aligned, track_aligned = align_audio(ref_audio.copy(), track_audio.copy())
        min_len = min(len(ref_aligned), len(track_aligned))
        ref_aligned = ref_aligned[:min_len]
        track_aligned = track_aligned[:min_len]
        
        scores = []
        
        for start in range(0, min_len - SAMPLES_PER_SEGMENT + 1, HOP):
            ref_seg = ref_aligned[start:start + SAMPLES_PER_SEGMENT]
            track_seg = track_aligned[start:start + SAMPLES_PER_SEGMENT]
            
            mel_ref = extract_mel(ref_seg)
            mel_track = extract_mel(track_seg)
            
            spec_ref = torch.FloatTensor(mel_ref).unsqueeze(0).unsqueeze(0).to(DEVICE)
            spec_track = torch.FloatTensor(mel_track).unsqueeze(0).unsqueeze(0).to(DEVICE)
            
            with torch.no_grad():
                score = model(spec_ref, spec_track).item()
                scores.append(score)
        
        mean_score = np.mean(scores) if scores else 0.0
        results.append((track_path, mean_score))
    
    return results


def ensemble_compare(models, ref_audio, track_paths):
    """Сравнивает треки используя ансамбль моделей."""
    all_model_results = {}
    
    for name, model in models.items():
        print(f"\n  Модель: {name}")
        results = compare_with_model(model, ref_audio, track_paths)
        all_model_results[name] = results
    
    final_results = []
    for i, track_path in enumerate(track_paths):
        scores = []
        for name in all_model_results:
            score = all_model_results[name][i][1]
            if score > 0:
                scores.append(score)
        
        avg_score = np.mean(scores) if scores else 0.0
        final_results.append((track_path, avg_score))
    
    return final_results, all_model_results


def print_results(results, ref_path, model_names=None):
    """Вывод результатов сравнения."""
    sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
    
    models_info = f" ({', '.join(model_names)})" if model_names else ""
    
    print(f"\n{'='*75}")
    print(f"СРАВНЕНИЕ КАЧЕСТВА{models_info}")
    print(f"{'='*75}")
    print(f"Эталон: {os.path.basename(ref_path)}")
    print(f"{'─'*75}")
    print(f"{'Ранг':<6} {'Файл':<38} {'Похожесть':<12} {'Близость'}")
    print(f"{'─'*75}")
    
    for rank, (path, score) in enumerate(sorted_results, 1):
        filename = os.path.basename(path)[:37]
        bar_len = int(score * 20)
        bar = "#" * bar_len + "-" * (20 - bar_len)
        
        crown = " <-- лучший" if rank == 1 else ""
        print(f"{rank:<6} {filename:<38} {score*100:5.1f}%      {bar}{crown}")
    
    print(f"{'─'*75}")
    if sorted_results:
        print(f"Итог: {os.path.basename(sorted_results[0][0])} — ближе всех к эталону ({sorted_results[0][1]*100:.1f}%)")
    print(f"{'='*75}")
    
    return sorted_results


# ========== ОНЛАЙН-КОРРЕКЦИЯ ==========
class OnlineTrainer:
    """Безопасное онлайн-обучение с EWC и буфером реплея."""
    
    def __init__(self, model, model_path, ref_audio):
        self.model = model
        self.model_path = model_path
        self.ref_audio = ref_audio
        
        # Сохраняем исходные веса для EWC
        self.original_weights = {}
        for name, param in model.named_parameters():
            self.original_weights[name] = param.data.clone()
        
        self.optimizer = torch.optim.AdamW(model.parameters(), lr=ONLINE_LR)
        self.correction_count = 0
        
        # Буфер для реплея (защита от забывания)
        self.replay_buffer = deque(maxlen=BUFFER_SIZE)
    
    def _load_aligned(self, track_path):
        """Загружает и выравнивает трек с референсом."""
        audio = load_audio(track_path)
        if audio is None:
            return None
        audio = trim_silence(audio)
        ref_aligned, track_aligned = align_audio(self.ref_audio.copy(), audio.copy())
        min_len = min(len(ref_aligned), len(track_aligned))
        return ref_aligned[:min_len], track_aligned[:min_len]
    
    def _extract_random_segment(self, ref_audio, track_audio):
        """Извлекает случайный сегмент из аудио."""
        if len(ref_audio) < SAMPLES_PER_SEGMENT:
            return None, None
        
        start = np.random.randint(0, len(ref_audio) - SAMPLES_PER_SEGMENT)
        
        ref_seg = ref_audio[start:start + SAMPLES_PER_SEGMENT]
        track_seg = track_audio[start:start + SAMPLES_PER_SEGMENT]
        
        mel_ref = extract_mel(ref_seg)
        mel_track = extract_mel(track_seg)
        
        spec_ref = torch.FloatTensor(mel_ref).unsqueeze(0).unsqueeze(0).to(DEVICE)
        spec_track = torch.FloatTensor(mel_track).unsqueeze(0).unsqueeze(0).to(DEVICE)
        
        return spec_ref, spec_track
    
    def correct(self, better_path, worse_path):
        """Одна итерация коррекции: better должен быть ближе к референсу, чем worse."""
        if self.correction_count >= MAX_CORRECTIONS:
            print(f"  ⚠ Достигнут лимит коррекций ({MAX_CORRECTIONS})")
            return False
        
        self.model.train()
        
        # Загружаем и выравниваем оба трека
        better_data = self._load_aligned(better_path)
        worse_data = self._load_aligned(worse_path)
        
        if better_data is None or worse_data is None:
            print("  ⚠ Не удалось загрузить аудио для коррекции")
            self.model.eval()
            return False
        
        ref_better, track_better = better_data
        ref_worse, track_worse = worse_data
        
        total_loss = 0
        
        for step in range(ONLINE_STEPS):
            # Тренировочный пример (better должен быть ближе)
            spec_ref_b, spec_better = self._extract_random_segment(ref_better, track_better)
            spec_ref_w, spec_worse = self._extract_random_segment(ref_worse, track_worse)
            
            if spec_ref_b is None or spec_ref_w is None:
                continue
            
            self.optimizer.zero_grad()
            
            score_better = self.model(spec_ref_b, spec_better)
            score_worse = self.model(spec_ref_w, spec_worse)
            
            # Triplet loss: better должен быть выше worse на margin
            triplet_loss = torch.clamp(ONLINE_MARGIN - (score_better - score_worse), min=0)
            
            # EWC loss: удерживаем веса близко к оригинальным
            ewc_loss = 0
            for name, param in self.model.named_parameters():
                if name in self.original_weights:
                    ewc_loss += torch.sum((param - self.original_weights[name]) ** 2)
            
            loss = triplet_loss + EWC_LAMBDA_ONLINE * ewc_loss
            loss.backward()
            
            # Gradient clipping для дополнительной защиты
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            
            self.optimizer.step()
            total_loss += loss.item()
        
        # Сохраняем в буфер реплея
        self.replay_buffer.append((better_path, worse_path))
        
        # Реплей старых примеров для предотвращения забывания
        if len(self.replay_buffer) >= 4:
            self._replay()
        
        self.correction_count += 1
        self.model.eval()
        
        avg_loss = total_loss / ONLINE_STEPS
        print(f"  ✓ Коррекция #{self.correction_count}: {os.path.basename(better_path)} > {os.path.basename(worse_path)} (loss={avg_loss:.6f})")
        return True
    
    def _replay(self):
        """Повторяет старые примеры из буфера для защиты от забывания."""
        if len(self.replay_buffer) < 2:
            return
        
        # Берём 2 случайных старых примера
        indices = np.random.choice(len(self.replay_buffer), min(2, len(self.replay_buffer)), replace=False)
        
        for idx in indices:
            better_path, worse_path = self.replay_buffer[idx]
            
            better_data = self._load_aligned(better_path)
            worse_data = self._load_aligned(worse_path)
            
            if better_data is None or worse_data is None:
                continue
            
            ref_better, track_better = better_data
            ref_worse, track_worse = worse_data
            
            spec_ref_b, spec_better = self._extract_random_segment(ref_better, track_better)
            spec_ref_w, spec_worse = self._extract_random_segment(ref_worse, track_worse)
            
            if spec_ref_b is None or spec_ref_w is None:
                continue
            
            self.optimizer.zero_grad()
            
            score_better = self.model(spec_ref_b, spec_better)
            score_worse = self.model(spec_ref_w, spec_worse)
            
            triplet_loss = torch.clamp(ONLINE_MARGIN - (score_better - score_worse), min=0)
            
            ewc_loss = 0
            for name, param in self.model.named_parameters():
                if name in self.original_weights:
                    ewc_loss += torch.sum((param - self.original_weights[name]) ** 2)
            
            loss = triplet_loss + EWC_LAMBDA_ONLINE * ewc_loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimizer.step()
    
    def save(self):
        """Сохраняет обновлённую модель."""
        backup_path = self.model_path.replace('.pth', '_backup.pth')
        if os.path.exists(self.model_path) and not os.path.exists(backup_path):
            shutil.copy(self.model_path, backup_path)
            print(f"  ✓ Оригинал сохранён в {backup_path}")
        
        torch.save(self.model.state_dict(), self.model_path)
        print(f"  ✓ Модель сохранена: {self.model_path} (коррекций: {self.correction_count})")


# ========== ГЛАВНАЯ ==========
def main():
    parser = argparse.ArgumentParser(description="Сравнение качества аудио (регрессия + онлайн-коррекция)")
    parser.add_argument("--model", type=str, default=None,
                        help="Модели через запятую")
    parser.add_argument("--train", action="store_true",
                        help="Режим онлайн-коррекции")
    parser.add_argument("inputs", nargs="+", help="Референс и треки")
    args = parser.parse_args()
    
    if len(args.inputs) < 2:
        print("✗ Нужен референс и минимум 1 трек для сравнения")
        sys.exit(1)
    
    ref_path = args.inputs[0]
    raw_paths = args.inputs[1:]
    
    if not os.path.exists(ref_path):
        print(f"✗ Референс не найден: {ref_path}")
        sys.exit(1)
    
    track_paths = collect_audio_files(raw_paths)
    if not track_paths:
        print("✗ Не найдено аудиофайлов для сравнения")
        sys.exit(1)
    
    # Загрузка модели
    if args.model:
        model_paths = [p.strip() for p in args.model.split(",")]
    else:
        model_paths = [m for m in DEFAULT_MODELS if os.path.exists(m)]
        if not model_paths:
            model_paths = ["compare_model.pth"]
    
    if args.train and len(model_paths) > 1:
        print("⚠ Онлайн-коррекция работает только с одной моделью. Использую первую.")
        model_paths = model_paths[:1]
    
    print(f"\nЗагрузка моделей ({len(model_paths)}):")
    models = load_models(model_paths)
    
    if not models:
        print("✗ Ни одна модель не загружена")
        sys.exit(1)
    
    print(f"\nРеференс: {os.path.basename(ref_path)}")
    print(f"Треков для сравнения: {len(track_paths)}")
    
    print(f"\nЗагрузка референса...")
    ref_audio = load_audio(ref_path)
    if ref_audio is None:
        print(f"✗ Не удалось загрузить референс: {ref_path}")
        sys.exit(1)
    ref_audio = trim_silence(ref_audio)
    
    # Онлайн-коррекция
    trainer = None
    if args.train:
        model = list(models.values())[0]
        model_name = list(models.keys())[0]
        model_path = model_paths[0]
        trainer = OnlineTrainer(model, model_path, ref_audio)
        print(f"\n  ⚡ Режим онлайн-коррекции (модель: {model_name})")
        print(f"  EWC lambda: {EWC_LAMBDA_ONLINE}")
        print(f"  LR: {ONLINE_LR}")
        print(f"  Максимум коррекций: {MAX_CORRECTIONS}")
    
    while True:
        # Сравнение
        if len(models) == 1:
            name = list(models.keys())[0]
            results = compare_with_model(models[name], ref_audio, track_paths)
            sorted_results = print_results(results, ref_path, [name])
        else:
            final_results, all_results = ensemble_compare(models, ref_audio, track_paths)
            sorted_results = print_results(final_results, ref_path, list(models.keys()))
        
        # Меню коррекции (только в режиме --train)
        if not args.train:
            break
        
        print(f"\n{'─'*75}")
        print("КОРРЕКЦИЯ:")
        print(f"  Укажите, кто НА САМОМ ДЕЛЕ лучше (ближе к эталону):")
        
        for i, (path, score) in enumerate(sorted_results, 1):
            print(f"  {i} - {os.path.basename(path)}")
        
        print(f"  0 - Выход (сохранить модель)")
        print(f"  R - Повторить сравнение")
        
        choice = input("\n  Ваш выбор: ").strip().lower()
        
        if choice == '0':
            trainer.save()
            print("\nГотово!")
            break
        elif choice == 'r':
            continue
        
        # Парсим выбор: "1 2" означает "1 лучше, чем 2"
        try:
            parts = choice.split()
            if len(parts) == 1:
                # Одна цифра — этот трек лучше всех
                better_idx = int(parts[0]) - 1
                for i, (path, score) in enumerate(sorted_results):
                    if i != better_idx:
                        trainer.correct(sorted_results[better_idx][0], path)
            elif len(parts) == 2:
                # Две цифры: первый лучше второго
                better_idx = int(parts[0]) - 1
                worse_idx = int(parts[1]) - 1
                trainer.correct(sorted_results[better_idx][0], sorted_results[worse_idx][0])
        except (ValueError, IndexError):
            print("  ⚠ Неверный ввод. Попробуйте снова.")
            continue
    
    if not args.train:
        print("\nГотово!")


if __name__ == "__main__":
    import shutil
    main()
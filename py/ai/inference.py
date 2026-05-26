import numpy as np
import torch
import torch.nn as nn
import librosa
import subprocess
import tempfile
import os
import sys
from collections import Counter
import warnings
warnings.filterwarnings('ignore')

# ========== 1. Модель (должна совпадать с train.py) ==========
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


class DualHeadCNN(nn.Module):
    def __init__(self, num_lossy):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1),
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
        self.head_lossless = nn.Sequential(
            nn.Flatten(), nn.Linear(4096, 128), nn.ReLU(), nn.Dropout(0.3), nn.Linear(128, 2)
        )
        self.head_codec = nn.Sequential(
            nn.Flatten(), nn.Linear(4096, 256), nn.ReLU(), nn.Dropout(0.4),
            nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.3), nn.Linear(128, num_lossy)
        )

    def forward(self, x):
        f = self.features(x)
        return self.head_lossless(f), self.head_codec(f)


# ========== 2. Параметры ==========
SR = 44100
SEGMENT_DURATION = 1.0
SAMPLES_PER_SEGMENT = int(SEGMENT_DURATION * SR)
HOP = SAMPLES_PER_SEGMENT // 2
N_MELS = 128
MODEL_PATH = "best_model.pth"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Классы
ALL_NAMES = [
    "lossless",
    "mp3_32", "mp3_64", "mp3_128", "mp3_high",
    "aac_64", "aac_high",
    "opus_32", "opus_64", "opus_96", "opus_high"
]
NUM_LOSSY = len(ALL_NAMES) - 1

# Расшифровка составных классов
CLASS_DESCRIPTION = {
    "lossless": "Lossless (без сжатия)",
    "mp3_32": "MP3 32 kbps",
    "mp3_64": "MP3 64 kbps",
    "mp3_128": "MP3 128 kbps",
    "mp3_high": "MP3 192-320 kbps",
    "aac_64": "AAC 64 kbps",
    "aac_high": "AAC 128-256 kbps",
    "opus_32": "Opus 32 kbps",
    "opus_64": "Opus 64 kbps",
    "opus_96": "Opus 96 kbps",
    "opus_high": "Opus 128-192 kbps",
}


# ========== 3. Загрузка аудио ==========
def load_audio(path, target_sr=44100):
    """Загружает аудио в моно, 44100 Гц. Работает с любыми форматами."""
    
    # Пробуем librosa (WAV, FLAC, MP3)
    try:
        y, sr = librosa.load(path, sr=target_sr, mono=True)
        return y
    except:
        pass
    
    # Пробуем soundfile
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
    
    # FFmpeg для всех остальных (Opus, M4A, и т.д.)
    try:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_name = tmp.name
        
        cmd = [
            'ffmpeg', '-y', '-i', os.path.abspath(path),
            '-vn', '-ac', '1', '-ar', str(target_sr),
            '-f', 'wav', tmp_name
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, check=True)
        
        y, _ = librosa.load(tmp_name, sr=target_sr, mono=True)
        os.unlink(tmp_name)
        return y
    except:
        return None


# ========== 4. Извлечение спектрограмм ==========
def extract_spectrograms(audio):
    """Режет аудио на сегменты и возвращает массив спектрограмм."""
    specs = []
    
    for start in range(0, len(audio) - SAMPLES_PER_SEGMENT + 1, HOP):
        segment = audio[start:start + SAMPLES_PER_SEGMENT]
        
        mel = librosa.feature.melspectrogram(
            y=segment, sr=SR, n_mels=N_MELS,
            n_fft=2048, hop_length=512
        )
        mel_db = librosa.power_to_db(mel, ref=np.max)
        mel_db = (mel_db - mel_db.mean()) / (mel_db.std() + 1e-8)
        
        specs.append(mel_db)
    
    if len(specs) == 0:
        return None
    
    return np.array(specs, dtype=np.float32)


# ========== 5. Предсказание ==========
@torch.no_grad()
def predict(model, specs):
    """Прогоняет спектрограммы через модель и возвращает предсказанные классы."""
    model.eval()
    predictions = []
    
    # Обрабатываем батчами для скорости
    batch_size = 128
    for i in range(0, len(specs), batch_size):
        batch = torch.FloatTensor(specs[i:i+batch_size]).unsqueeze(1).to(DEVICE)
        
        out_bin, out_codec = model(batch)
        
        pred_bin = out_bin.argmax(1)  # 0=lossy, 1=lossless
        
        final = torch.zeros(len(batch), dtype=torch.long, device=DEVICE)
        final[pred_bin == 1] = 0  # lossless -> класс 0
        
        lossy_mask = pred_bin == 0
        if lossy_mask.any():
            final[lossy_mask] = out_codec[lossy_mask].argmax(1) + 1  # lossy -> +1
        
        predictions.extend(final.cpu().numpy())
    
    return predictions


# ========== 6. Анализ и вывод ==========
def analyze_predictions(predictions):
    """Анализирует предсказания всех сегментов и формирует итоговый вердикт."""
    counter = Counter(predictions)
    total = len(predictions)
    
    print(f"\n{'='*60}")
    print(f"Проанализировано сегментов: {total}")
    print(f"{'='*60}")
    
    # Сортируем по убыванию
    print("\nРаспределение предсказаний по сегментам:")
    for class_idx, count in counter.most_common():
        name = ALL_NAMES[class_idx]
        desc = CLASS_DESCRIPTION[name]
        pct = 100 * count / total
        bar = '█' * int(pct / 2)
        print(f"  {desc:<30} {count:>5} ({pct:5.1f}%) {bar}")
    
    # Итоговый вердикт — самый частый класс
    top_class_idx = counter.most_common(1)[0][0]
    top_name = ALL_NAMES[top_class_idx]
    top_desc = CLASS_DESCRIPTION[top_name]
    top_pct = 100 * counter[top_class_idx] / total
    
    # Уверенность
    if top_pct > 80:
        confidence = "Высокая"
    elif top_pct > 60:
        confidence = "Средняя"
    else:
        confidence = "Низкая (возможно, файл имеет нестандартное сжатие)"
    
    print(f"\n{'='*60}")
    print(f"ИТОГОВЫЙ ВЕРДИКТ")
    print(f"{'='*60}")
    print(f"  Кодек/битрейт: {top_desc}")
    print(f"  Уверенность:    {confidence} ({top_pct:.0f}% сегментов)")
    print(f"{'='*60}\n")
    
    return top_name, top_pct


# ========== 7. Главная функция ==========
def main():
    if len(sys.argv) < 2:
        print("Использование: python inference.py <путь_к_аудиофайлу>")
        print("Пример: python inference.py my_song.mp3")
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    if not os.path.exists(filepath):
        print(f"✗ Файл не найден: {filepath}")
        sys.exit(1)
    
    print(f"→ Анализирую: {os.path.basename(filepath)}")
    print(f"  Размер: {os.path.getsize(filepath) / 1024**2:.1f} МБ")
    
    # Загружаем модель
    print("→ Загружаю модель...")
    model = DualHeadCNN(NUM_LOSSY).to(DEVICE)
    model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE, weights_only=False))
    print(f"  Модель загружена на {DEVICE}")
    
    # Загружаем аудио
    print("→ Загружаю аудио...")
    audio = load_audio(filepath, SR)
    if audio is None:
        print("✗ Не удалось загрузить аудиофайл")
        sys.exit(1)
    
    duration = len(audio) / SR
    print(f"  Длительность: {duration:.1f} сек ({duration/60:.1f} мин)")
    
    # Извлекаем спектрограммы
    print("→ Извлекаю спектрограммы...")
    specs = extract_spectrograms(audio)
    if specs is None:
        print("✗ Аудио слишком короткое (меньше 1 сек)")
        sys.exit(1)
    
    print(f"  Получено сегментов: {len(specs)}")
    
    # Предсказываем
    print("→ Анализирую...")
    predictions = predict(model, specs)
    
    # Выводим результат
    analyze_predictions(predictions)
    print("\nГотово! Нажми Enter для выхода..."); input()

if __name__ == "__main__":
    main()
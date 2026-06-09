"""
DATASET BUILDER — Noise Removal (50Hz Hum + Pink Noise)
Берёт чистые lossless-файлы, добавляет гул 50 Гц с гармониками и розовый шум.
Выход: noisy (зашумлённый WAV) и clean (чистый WAV)
"""
import os
import numpy as np
import soundfile as sf
from pathlib import Path
from tqdm import tqdm
from scipy import signal
import multiprocessing as mp

# ======================== КОНФИГ ========================
INPUT_FOLDER = Path("E:/AI_RESTORE/music_hi_res")
OUTPUT_FOLDER = Path("E:/AI_RESTORE/dataset_noise_50hz")

SR = 44100
SEGMENT_DURATION = 3.0
OVERLAP = 0.5
SKIP_START = 5.0        # Пропускаем самое начало (может быть тишина)
MAX_DURATION = 60.0     # Берём первые 60с

SAMPLES_PER_SEGMENT = int(SR * SEGMENT_DURATION)
HOP = int(SAMPLES_PER_SEGMENT * (1 - OVERLAP))

# ======================== ГЕНЕРАТОРЫ ШУМА ========================

def generate_hum(length_samples, sr=44100, base_freq=50.0):
    """
    Реалистичный гул 50 Гц с гармониками.
    Особенности:
    - Дрейф частоты (±0.3 Гц) с плавным блужданием
    - Амплитудная модуляция 120 Гц (от двухполупериодного выпрямителя)
    - Гармоники: 50, 100, 150, 200, 250, 300, 350, 400 Гц
    - Нечётные гармоники сильнее (характерно для магнитных наводок)
    """
    t = np.arange(length_samples, dtype=np.float64) / sr

    # Дрейф частоты — медленное случайное блуждание со сглаживанием
    drift_raw = np.cumsum(np.random.randn(length_samples) * 0.015)
    # Сильно сглаживаем (окно ~0.5 сек)
    window_len = min(22051, length_samples // 2 * 2 + 1)  # нечётное
    if window_len > 3:
        freq_drift = signal.savgol_filter(drift_raw, window_len, 3)
    else:
        freq_drift = drift_raw
    freq_instant = base_freq + freq_drift

    # Амплитудная модуляция: пульсации 120 Гц + медленное дыхание
    amp_mod_120 = 1.0 + 0.12 * np.sin(2 * np.pi * 120 * t + np.random.rand() * 2 * np.pi)
    amp_mod_slow = 1.0 + 0.08 * np.sin(2 * np.pi * 0.3 * t + np.random.rand() * 2 * np.pi)
    amp_mod = amp_mod_120 * amp_mod_slow

    hum = np.zeros(length_samples, dtype=np.float64)
    harmonics = [
        (1, 1.0),    # 50 Гц
        (2, 0.30),   # 100 Гц (чётная — слабее)
        (3, 0.55),   # 150 Гц (нечётная — сильнее)
        (4, 0.12),   # 200 Гц
        (5, 0.22),   # 250 Гц
        (6, 0.06),   # 300 Гц
        (7, 0.10),   # 350 Гц
        (8, 0.03),   # 400 Гц
    ]

    for harmonic, amp in harmonics:
        phase = np.random.rand() * 2 * np.pi
        # Интегрируем мгновенную частоту для получения фазы
        phase_accum = 2 * np.pi * harmonic * np.cumsum(freq_instant) / sr + phase
        hum += amp * np.sin(phase_accum)

    hum *= amp_mod
    return hum.astype(np.float32)


def generate_pink_noise(length_samples):
    """
    Розовый шум (1/f спектр).
    Метод: фильтрация белого шума через аппроксимацию pink-фильтра.
    """
    white = np.random.randn(length_samples).astype(np.float64)
    # Коэффициенты pink-фильтра (аппроксимация)
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1.0, -2.494956002, 2.017265875, -0.522189400]
    pink = signal.lfilter(b, a, white)
    # Убираем переходной процесс
    if len(pink) > 1000:
        pink = pink[1000:]
    # Дополняем до нужной длины
    if len(pink) < length_samples:
        pink = np.pad(pink, (0, length_samples - len(pink)), mode='reflect')
    pink = pink[:length_samples]
    # Нормализуем
    std = np.std(pink)
    if std > 1e-8:
        pink = pink / std
    return pink.astype(np.float32)


def generate_brown_noise(length_samples):
    """Коричневый (brown) шум — ещё более низкочастотный"""
    white = np.random.randn(length_samples).astype(np.float64)
    brown = np.cumsum(white)
    # High-pass чтобы не уходил в разнос
    b_hp, a_hp = signal.butter(1, 20 / (SR/2), 'high')
    brown = signal.lfilter(b_hp, a_hp, brown)
    std = np.std(brown)
    if std > 1e-8:
        brown = brown / std
    return brown.astype(np.float32)


def generate_burst_noise(length_samples, sr=44100):
    """
    Короткие всплески помех (дребезг, треск контактов).
    Частота — в среднем 1-3 всплеска за 3 секунды.
    """
    bursty = np.zeros(length_samples, dtype=np.float32)
    avg_bursts = np.random.randint(0, 5)  # 0-4 всплеска
    for _ in range(avg_bursts):
        pos = np.random.randint(0, max(1, length_samples - 100))
        length = np.random.randint(10, 80)  # 0.2-1.8 мс
        # Затухающая синусоида на случайной частоте
        t_burst = np.arange(length) / sr
        freq = np.random.uniform(200, 4000)
        decay = np.exp(-t_burst * np.random.uniform(500, 3000))
        burst = np.sin(2 * np.pi * freq * t_burst) * decay
        bursty[pos:pos+length] += burst[:min(length, length_samples-pos)]
    return bursty


def mix_noisy(clean, sr=44100):
    """
    Микширует чистый сигнал с шумами.
    Возвращает: noisy, clean (оба нормированы)
    """
    length = len(clean)
    
    # Случайные параметры SNR
    hum_snr = np.random.uniform(3, 30)     # гул: от сильного (3dB) до еле заметного (30dB)
    pink_snr = np.random.uniform(8, 40)    # розовый шум
    brown_snr = np.random.uniform(12, 45)  # коричневый шум
    burst_gain = np.random.uniform(0, 0.08)  # всплески: от отсутствуют до заметных
    
    # Генерируем шумы
    hum = generate_hum(length, sr)
    pink = generate_pink_noise(length)
    brown = generate_brown_noise(length)
    burst = generate_burst_noise(length, sr)
    
    # Нормализуем чистый сигнал
    clean_rms = np.sqrt(np.mean(clean**2) + 1e-8)
    
    # Микшируем
    noisy = clean.copy()
    noisy += hum * (clean_rms / (10 ** (hum_snr / 20)))
    noisy += pink * (clean_rms / (10 ** (pink_snr / 20)))
    noisy += brown * (clean_rms / (10 ** (brown_snr / 20)))
    noisy += burst * clean_rms * burst_gain
    
    # Варианты:
    # 15% — только гул (без широкополосного шума)
    if np.random.rand() < 0.15:
        noisy = clean + hum * (clean_rms / (10 ** (hum_snr / 20)))
    # 10% — только широкополосный шум
    elif np.random.rand() < 0.12:
        noisy = clean + pink * (clean_rms / (10 ** (pink_snr / 20)))
    # 5% — экстремально сильный гул
    elif np.random.rand() < 0.05:
        hum_snr = np.random.uniform(-5, 5)
        noisy = clean + hum * (clean_rms / (10 ** (hum_snr / 20)))
    
    # Финальная нормализация
    max_val = np.max(np.abs(noisy))
    if max_val > 0.99:
        scale = 0.99 / max_val
        noisy *= scale
        clean *= scale
    
    return noisy.astype(np.float32), clean.astype(np.float32)


# ======================== ОБРАБОТКА ФАЙЛА ========================

def process_file(file_path, output_noisy_dir, output_clean_dir):
    """Загружает, добавляет шум, режет на сегменты"""
    try:
        y, sr = sf.read(file_path)
        if sr != SR:
            import librosa
            y = librosa.resample(y, orig_sr=sr, target_sr=SR)
            sr = SR
    except Exception as e:
        tqdm.write(f"❌ Ошибка загрузки {file_path.name}: {e}")
        return 0

    # Конвертируем в моно
    if y.ndim > 1:
        y = np.mean(y, axis=1)

    # Обрезаем
    start_sample = int(SKIP_START * sr)
    if len(y) <= start_sample:
        return 0
    y = y[start_sample:]
    
    max_samples = int(MAX_DURATION * sr)
    if len(y) > max_samples:
        y = y[:max_samples]
    
    # Нормализуем
    y = y / (np.max(np.abs(y)) + 1e-8)
    
    if len(y) < SAMPLES_PER_SEGMENT:
        return 0

    # Генерируем зашумлённую версию
    noisy, clean = mix_noisy(y, sr)
    
    # Режем на сегменты
    seg_count = 0
    for start in range(0, len(y) - SAMPLES_PER_SEGMENT + 1, HOP):
        noisy_seg = noisy[start:start + SAMPLES_PER_SEGMENT]
        clean_seg = clean[start:start + SAMPLES_PER_SEGMENT]
        
        base_name = f"{file_path.stem}_{seg_count:04d}"
        sf.write(output_noisy_dir / f"{base_name}.wav", noisy_seg, sr)
        sf.write(output_clean_dir / f"{base_name}.wav", clean_seg, sr)
        seg_count += 1
    
    return seg_count


# ======================== MAIN ========================
if __name__ == "__main__":
    print("╔══════════════════════════════════════╗")
    print("║  Dataset Builder — Noise Removal    ║")
    print("║  50Hz Hum + Pink/Brown Noise        ║")
    print("╚══════════════════════════════════════╝")
    print()

    output_noisy = OUTPUT_FOLDER / "noisy"
    output_clean = OUTPUT_FOLDER / "clean"
    output_noisy.mkdir(parents=True, exist_ok=True)
    output_clean.mkdir(parents=True, exist_ok=True)

    audio_files = list(INPUT_FOLDER.glob("*.wav")) + list(INPUT_FOLDER.glob("*.flac"))
    
    if not audio_files:
        print(f"❌ Нет файлов в {INPUT_FOLDER}")
        exit(1)

    print(f"🎵 Найдено треков: {len(audio_files)}")
    print(f"📂 Вход:  {INPUT_FOLDER}")
    print(f"📂 Выход: {OUTPUT_FOLDER}")
    print(f"🎧 Гул 50 Гц + гармоники + розовый/коричневый шум")
    print(f"⏱️  Сегменты: {SEGMENT_DURATION}с, перекрытие {OVERLAP}с")
    print()

    total_segments = 0
    
    for f in tqdm(audio_files, desc="🔪 Обработка треков", unit="track"):
        segs = process_file(f, output_noisy, output_clean)
        total_segments += segs
        if segs > 0:
            tqdm.write(f"   ✅ {f.name}: {segs} сегментов")

    print(f"\n🏁 Готово! Всего сегментов: {total_segments}")
    print(f"   noisy:  {output_noisy}")
    print(f"   clean:  {output_clean}")
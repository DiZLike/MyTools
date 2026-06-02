"""
build_dataset.py
Генерация датасета для обучения AudioCompareNet.
Использует психоакустическую метрику для вычисления сходства с эталоном.
Оценка зависит от контента, а не только от названия кодека.
v12: Спектр + high_freq_loss + mid_penalty.

Использование: python build_dataset.py --codec mp3|opus|aac|vorbis [--limit N]
"""

import os
import sys
import argparse
import subprocess
import tempfile
import shutil
import pickle
import time
import gc
import itertools
import numpy as np
import librosa
import torch
import torchaudio
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')


# ========== НАСТРОЙКИ ==========
INPUT_DIR = "originals"
OUTPUT_DATASET_DIR = "dataset_files"
BASE_SPECTROGRAMS_DIR = "spectrograms"

SR = 44100
SEGMENT_DURATION = 1.0
SAMPLES_PER_SEGMENT = int(SEGMENT_DURATION * SR)
HOP = SAMPLES_PER_SEGMENT
N_MELS = 128
N_FFT = 2048
HOP_LENGTH = 512

CODEC_CONFIGS_MAP = {
    "mp3": [
        ("lossless", "pcm_s16le", None, ".wav", []),
        ("mp3_32", "libmp3lame", "32k", ".mp3", []),
        ("mp3_64", "libmp3lame", "64k", ".mp3", []),
        ("mp3_128", "libmp3lame", "128k", ".mp3", []),
        ("mp3_192", "libmp3lame", "192k", ".mp3", []),
        ("mp3_320", "libmp3lame", "320k", ".mp3", []),
    ],
    "opus": [
        ("lossless", "pcm_s16le", None, ".wav", []),
        ("opus_32", "libopus", "32k", ".opus", ["-frame_duration", "60"]),
        ("opus_64", "libopus", "64k", ".opus", ["-frame_duration", "60"]),
        ("opus_128", "libopus", "128k", ".opus", ["-frame_duration", "60"]),
        ("opus_192", "libopus", "192k", ".opus", ["-frame_duration", "60"]),
        ("opus_320", "libopus", "320k", ".opus", ["-frame_duration", "60"]),
    ],
    "aac": [
        ("lossless", "pcm_s16le", None, ".wav", []),
        ("aac_32", "aac", "32k", ".mp4", []),
        ("aac_64", "aac", "64k", ".mp4", []),
        ("aac_128", "aac", "128k", ".mp4", []),
        ("aac_192", "aac", "192k", ".mp4", []),
        ("aac_320", "aac", "320k", ".mp4", []),
    ],
    "vorbis": [
        ("lossless", "pcm_s16le", None, ".wav", []),
        ("vorbis_32", "libvorbis", "48k", ".ogg", []),
        ("vorbis_64", "libvorbis", "64k", ".ogg", []),
        ("vorbis_128", "libvorbis", "128k", ".ogg", []),
        ("vorbis_192", "libvorbis", "192k", ".ogg", []),
        ("vorbis_320", "libvorbis", "320k", ".ogg", []),
    ],
}

NUM_WORKERS = min(os.cpu_count(), 8)

# Пороги для 4 классов похожести
SIMILARITY_THRESHOLDS = [0.3, 0.55, 0.8]
CLASS_LABELS = ["Плохо", "Средне", "Хорошо", "Отлично"]

# GPU
USE_GPU = torch.cuda.is_available()
BATCH_GPU = 128


# ========== ЗАГРУЗКА АУДИО ==========
def load_audio_mono(path, target_sr=SR):
    """Загружает аудио в моно с заданной частотой дискретизации."""
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


def load_all_audio_parallel(file_list, max_workers=8):
    """Загружает аудио параллельно в несколько потоков."""
    audio_cache = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(load_audio_mono, f): f for f in file_list}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Загрузка аудио"):
            f = futures[future]
            try:
                y = future.result()
                if y is not None:
                    audio_cache[f] = y
            except Exception as e:
                tqdm.write(f"  ⚠ Ошибка загрузки {os.path.basename(f)}: {e}")
    return audio_cache


# ========== ПСИХОАКУСТИЧЕСКАЯ МЕТРИКА (v12) ==========
def compute_mel_once(audio_cache, n_mels=128, sr=44100, n_fft=2048, hop_length=512):
    """Извлекает и кеширует мел-спектрограммы (в dB) для всех аудио."""
    mel_cache = {}
    for path, y in tqdm(audio_cache.items(), desc="Мел-спектрограммы"):
        try:
            mel = librosa.feature.melspectrogram(
                y=y, sr=sr, n_mels=n_mels, n_fft=n_fft, hop_length=hop_length
            )
            mel_db = librosa.power_to_db(mel, ref=np.max)
            mel_cache[path] = mel_db
        except Exception as e:
            tqdm.write(f"  ⚠ Ошибка спектрограммы {os.path.basename(path)}: {e}")
    return mel_cache


def compute_distance_from_mel(mel_ref, mel_deg, n_mels=128, sr=44100):
    """
    Вычисляет РАССТОЯНИЕ до референса по мел-спектрограммам.
    v12.3: Спектр + high_freq_loss + pre_echo. Параметры 2.0/1.2.
    
    Возвращает: float от 0 (идентично) до 1 (максимальное различие).
    """
    min_time_frames = min(mel_ref.shape[1], mel_deg.shape[1])
    mel_ref = mel_ref[:, :min_time_frames]
    mel_deg = mel_deg[:, :min_time_frames]
    
    diff_db = np.abs(mel_ref - mel_deg)
    
    freqs = librosa.mel_frequencies(n_mels=n_mels, fmin=0, fmax=sr//2)
    weights = np.exp(-0.5 * ((freqs - 3000) / 2000) ** 2)
    weights = np.clip(weights, 0.15, 1.0)
    
    weighted_diff = diff_db * weights.reshape(-1, 1)
    
    # Базовая спектральная метрика
    p50 = np.percentile(weighted_diff, 50)
    p75 = np.percentile(weighted_diff, 75)
    p90 = np.percentile(weighted_diff, 90)
    p95 = np.percentile(weighted_diff, 95)
    
    base_combined = 0.25 * p50 + 0.30 * p75 + 0.25 * p90 + 0.20 * p95
    
    # Потеря высоких частот (MP3 режет сильнее AAC)
    high_freq_mask = freqs > 16000
    if high_freq_mask.any():
        energy_ref = np.mean(mel_ref[high_freq_mask, :])
        energy_deg = np.mean(mel_deg[high_freq_mask, :])
        if energy_ref > 1.0:
            high_freq_loss = np.clip(1.0 - energy_deg / (energy_ref + 1e-8), 0, 1)
        else:
            high_freq_loss = 0.0
    else:
        high_freq_loss = 0.0
    
    high_penalty = high_freq_loss * 6.0
    
    # Pre-echo (MP3 страдает больше, чем AAC)
    temporal_diff = np.mean(weighted_diff, axis=0)
    frame_diff = np.abs(np.diff(temporal_diff))
    jitter = np.mean(frame_diff)
    pre_echo_penalty = jitter * 1.0
    
    # Итог
    combined_diff = base_combined + high_penalty + pre_echo_penalty
    
    center_db = 2.0
    slope_db = 1.2
    distance = 1.0 / (1.0 + np.exp(-(combined_diff - center_db) / slope_db))
    
    return float(np.clip(distance, 0.0, 1.0))


def count_segments(y_a, y_b):
    """Считает количество сегментов для пары аудио (они уже в памяти)."""
    if y_a is None or y_b is None:
        return 0
    min_len = min(len(y_a), len(y_b))
    if min_len < SAMPLES_PER_SEGMENT:
        return 1
    return (min_len - SAMPLES_PER_SEGMENT) // HOP + 1


# ========== КОНВЕРТАЦИЯ ==========
def convert_one(args):
    original_path, class_name, codec, bitrate, ext, extra_flags, output_dir = args

    base = os.path.splitext(os.path.basename(original_path))[0]
    output_name = f"{class_name}_{base}{ext}"
    output_path = os.path.join(output_dir, output_name)

    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return f"SKIP {output_name}"

    try:
        if class_name == "lossless":
            shutil.copy(original_path, output_path)
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", original_path,
                "-vn",
                "-c:a", codec,
            ]
            # Добавляем битрейт только если указан
            if bitrate is not None:
                cmd += ["-b:a", bitrate]
            
            cmd += ["-map_metadata", "-1"] + extra_flags + [output_path]

            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            if result.returncode != 0:
                err_msg = result.stderr.decode('utf-8', errors='ignore').strip().split('\n')[-1]
                return f"ERROR {output_name}: {err_msg[:100]}"

        return f"OK {output_name}"
    except Exception as e:
        return f"ERROR {output_name}: {e}"


def convert_all_originals(codec_configs, limit=0):
    os.makedirs(OUTPUT_DATASET_DIR, exist_ok=True)

    originals = []
    for f in sorted(os.listdir(INPUT_DIR)):
        if f.lower().endswith(('.wav', '.flac', '.aiff', '.aif')):
            path = os.path.join(INPUT_DIR, f)
            if os.path.isfile(path):
                originals.append(path)

    if limit > 0:
        originals = originals[:limit]

    if not originals:
        print(f"✗ Нет исходников в '{INPUT_DIR}/'")
        return False

    print(f"  Исходников для конвертации: {len(originals)}")

    tasks = []
    for orig in originals:
        for class_name, codec, bitrate, ext, extra_flags in codec_configs:
            tasks.append((orig, class_name, codec, bitrate, ext, extra_flags, OUTPUT_DATASET_DIR))

    print(f"  Всего задач конвертации: {len(tasks)}")
    print(f"  Запуск в {NUM_WORKERS} потоков...\n")

    results = []
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = {executor.submit(convert_one, task): task for task in tasks}
        with tqdm(total=len(tasks), desc="Конвертация") as pbar:
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                pbar.update(1)
                if result.startswith("ERROR"):
                    tqdm.write(f"  ⚠ {result}")

    ok = sum(1 for r in results if r.startswith("OK"))
    skip = sum(1 for r in results if r.startswith("SKIP"))
    err = sum(1 for r in results if r.startswith("ERROR"))

    print(f"\n  Конвертация: OK={ok}, SKIP={skip}, ERROR={err}")
    return True


# ========== ОТБОР ПАР ==========
def select_pairs(available_classes):
    """Генерирует все уникальные пары классов."""
    pairs = []
    for i, class_a in enumerate(available_classes):
        for class_b in available_classes[i:]:
            pairs.append((class_a, class_b))
    return pairs


# ========== ИЗВЛЕЧЕНИЕ СПЕКТРОГРАММ (GPU) ==========
_mel_transform = None
_amp_to_db = None
_device = None

def _init_gpu_transforms(device='cuda'):
    global _mel_transform, _amp_to_db, _device
    if _mel_transform is None or _device != device:
        _mel_transform = torchaudio.transforms.MelSpectrogram(
            sample_rate=SR,
            n_mels=N_MELS,
            n_fft=N_FFT,
            hop_length=HOP_LENGTH,
            power=2.0,
        ).to(device)
        _amp_to_db = torchaudio.transforms.AmplitudeToDB().to(device)
        _device = device


def extract_mel_batch(audio_chunks, device='cuda'):
    """Извлекает мел-спектрограммы батчем на GPU."""
    _init_gpu_transforms(device)
    
    batch = torch.FloatTensor(np.stack(audio_chunks)).to(device)
    mel = _mel_transform(batch)
    mel_db = _amp_to_db(mel)
    
    mean = mel_db.mean(dim=(1, 2), keepdim=True)
    std = mel_db.std(dim=(1, 2), keepdim=True) + 1e-8
    mel_db = (mel_db - mean) / std
    
    return mel_db.unsqueeze(1).cpu().numpy().astype(np.float32)


def extract_mel_cpu(audio_chunk):
    """Извлечение мел-спектрограммы на CPU (fallback)."""
    mel = librosa.feature.melspectrogram(
        y=audio_chunk, sr=SR, n_mels=N_MELS, n_fft=N_FFT, hop_length=HOP_LENGTH
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)
    mel_db = (mel_db - mel_db.mean()) / (mel_db.std() + 1e-8)
    return mel_db[np.newaxis, :, :].astype(np.float32)


# ========== ГЛАВНАЯ ==========
def main():
    parser = argparse.ArgumentParser(description="Build dataset for AudioCompareNet")
    parser.add_argument("--codec", type=str, required=True, choices=["mp3", "opus", "aac", "vorbis"],
                        help="Codec to generate dataset for")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of tracks for testing (0 = all tracks)")
    args = parser.parse_args()

    codec = args.codec
    track_limit = args.limit
    codec_configs = CODEC_CONFIGS_MAP[codec]
    class_names = [cfg[0] for cfg in codec_configs]
    class_to_idx = {name: i for i, name in enumerate(class_names)}
    output_dir = f"{BASE_SPECTROGRAMS_DIR}_{codec}"

    print("=" * 60)
    print(f"BUILD DATASET — AudioCompareNet ({codec.upper()})")
    print("=" * 60)
    print(f"  Классов: {len(class_names)}")
    print(f"  Метрика: психоакустическая v12")
    print(f"  Сигмоида: центр 2.0 dB, крутизна 1.2 dB")
    if track_limit > 0:
        print(f"  ⚠ ТЕСТОВЫЙ РЕЖИМ: только {track_limit} треков")
    if USE_GPU:
        print(f"  GPU: {torch.cuda.get_device_name(0)} (batch={BATCH_GPU})")
    else:
        print(f"  CPU: librosa")
    t_start = time.time()

    # Фаза 1: Конвертация
    print("\n→ Фаза 1: Конвертация исходников...")
    if not os.path.exists(INPUT_DIR):
        print(f"✗ Папка '{INPUT_DIR}' не найдена!")
        sys.exit(1)
        
    all_originals = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.wav', '.flac', '.aiff', '.aif'))]
    
    if track_limit > 0:
        originals_list = all_originals[:track_limit]
        print(f"  ⚠ Ограничение: {len(originals_list)} из {len(all_originals)} треков")
    else:
        originals_list = all_originals

    # Проверяем наличие файлов только для текущего кодека
    all_exist = True
    missing_files = []
    for orig in originals_list:
        base = os.path.splitext(orig)[0]
        for class_name, codec, bitrate, ext, extra_flags in codec_configs:
            expected_name = f"{class_name}_{base}{ext}"
            expected_path = os.path.join(OUTPUT_DATASET_DIR, expected_name)
            if not os.path.exists(expected_path) or os.path.getsize(expected_path) < 1000:
                all_exist = False
                missing_files.append(expected_name)

    expected_total = len(originals_list) * len(codec_configs)
    if not all_exist:
        print(f"  Отсутствует {len(missing_files)} из {expected_total} файлов")
        if len(missing_files) <= 10:
            for mf in missing_files:
                print(f"    - {mf}")
        if not convert_all_originals(codec_configs, track_limit):
            sys.exit(1)
    else:
        print(f"  Пропущено — все {expected_total} файлов кодека '{codec}' уже есть в '{OUTPUT_DATASET_DIR}'")

    # Фаза 2: Группировка файлов
    print("\n→ Фаза 2: Группировка файлов...")
    dataset_files = {}
    for f in os.listdir(OUTPUT_DATASET_DIR):
        if f.startswith('.'):
            continue
        path = os.path.join(OUTPUT_DATASET_DIR, f)
        if not os.path.isfile(path):
            continue
        for class_name in class_names:
            if f.startswith(class_name + "_"):
                original_name = f[len(class_name) + 1:]
                original_name = os.path.splitext(original_name)[0]
                if original_name not in dataset_files:
                    dataset_files[original_name] = {}
                dataset_files[original_name][class_name] = path
                break
    
    if track_limit > 0:
        limited = dict(itertools.islice(dataset_files.items(), track_limit))
        if len(limited) < len(dataset_files):
            print(f"  ⚠ ТЕСТОВЫЙ РЕЖИМ: оставлено {len(limited)} из {len(dataset_files)} треков")
        dataset_files = limited
    else:
        print(f"  Исходников с версиями: {len(dataset_files)}")

    if len(dataset_files) == 0:
        print("✗ Не найдено файлов для обработки!")
        sys.exit(1)

    # Фаза 3: Загрузка аудио + метрики + подсчёт сегментов
    print("\n→ Фаза 3: Загрузка аудио, вычисление метрик и подсчёт сегментов...")
    
    needed_files_set = set()
    for versions in dataset_files.values():
        for class_name, path in versions.items():
            needed_files_set.add(path)
    
    print(f"  Уникальных файлов для загрузки: {len(needed_files_set)}")
    
    audio_cache = load_all_audio_parallel(list(needed_files_set), max_workers=NUM_WORKERS)
    print(f"  Загружено: {len(audio_cache)}/{len(needed_files_set)} файлов")
    
    if len(audio_cache) == 0:
        print("✗ Не удалось загрузить ни одного файла!")
        sys.exit(1)
    
    ram_usage = sum(y.nbytes for y in audio_cache.values()) / 1024**3
    print(f"  Размер кеша в RAM: ~{ram_usage:.1f} ГБ")
    
    mel_cache = compute_mel_once(audio_cache, N_MELS, SR, N_FFT, HOP_LENGTH)
    print(f"  Извлечено спектрограмм: {len(mel_cache)}/{len(audio_cache)}")
    
    pair_tasks = []
    distance_stats = []
    similarity_stats = []
    skipped_no_ref = 0
    skipped_no_audio = 0
    
    print("  Вычисление расстояний и similarity...")
    for orig_name, versions in tqdm(dataset_files.items(), desc="Метрики"):
        if 'lossless' not in versions or versions['lossless'] not in mel_cache:
            skipped_no_ref += 1
            continue
        
        available_classes = list(versions.keys())
        selected_pairs = select_pairs(available_classes)
        mel_ref = mel_cache[versions['lossless']]
        y_ref = audio_cache[versions['lossless']]
        
        for class_a, class_b in selected_pairs:
            if versions[class_a] not in audio_cache or versions[class_b] not in audio_cache:
                skipped_no_audio += 1
                continue
            
            y_a = audio_cache[versions[class_a]]
            y_b = audio_cache[versions[class_b]]
            
            seg_count = count_segments(y_a, y_b)
            if seg_count == 0:
                continue
            
            if class_a == 'lossless':
                dist_a = 0.0
            else:
                dist_a = compute_distance_from_mel(mel_ref, mel_cache[versions[class_a]])
            
            if class_b == 'lossless':
                dist_b = 0.0
            else:
                dist_b = compute_distance_from_mel(mel_ref, mel_cache[versions[class_b]])
            
            avg_dist = (dist_a + dist_b) / 2.0
            similarity = 1.0 - avg_dist
            similarity = float(np.clip(similarity, 0.0, 1.0))
            
            pair_tasks.append((versions[class_a], versions[class_b], similarity, seg_count))
            distance_stats.append(avg_dist)
            similarity_stats.append(similarity)
    
    print(f"  Всего пар: {len(pair_tasks)}")
    if skipped_no_ref > 0:
        print(f"  ⚠ Пропущено треков без референса: {skipped_no_ref}")
    if skipped_no_audio > 0:
        print(f"  ⚠ Пропущено пар из-за ошибок загрузки: {skipped_no_audio}")
    
    if distance_stats:
        print(f"  Расстояния: min={min(distance_stats):.3f}, max={max(distance_stats):.3f}, mean={np.mean(distance_stats):.3f}, median={np.median(distance_stats):.3f}")
    if similarity_stats:
        print(f"  Similarity: min={min(similarity_stats):.3f}, max={max(similarity_stats):.3f}, mean={np.mean(similarity_stats):.3f}, median={np.median(similarity_stats):.3f}, std={np.std(similarity_stats):.3f}")

    total_segments = sum(seg_count for _, _, _, seg_count in pair_tasks)
    print(f"  Всего сегментов: {total_segments:,}")

    if total_segments == 0:
        print("✗ Нет данных для создания датасета!")
        sys.exit(1)

    # Фаза 4: Создание memory-mapped массивов
    print("\n→ Фаза 4: Создание memory-mapped массивов...")
    os.makedirs(output_dir, exist_ok=True)

    specs_a_path = os.path.join(output_dir, 'specs_a.npy')
    specs_b_path = os.path.join(output_dir, 'specs_b.npy')
    similarities_path = os.path.join(output_dir, 'similarities.npy')

    for p in [specs_a_path, specs_b_path, similarities_path]:
        if os.path.exists(p):
            os.remove(p)

    spec_shape = (total_segments, 1, N_MELS, 87)
    sim_shape = (total_segments,)

    specs_a_mmap = np.lib.format.open_memmap(specs_a_path, mode='w+', dtype=np.float32, shape=spec_shape)
    specs_b_mmap = np.lib.format.open_memmap(specs_b_path, mode='w+', dtype=np.float32, shape=spec_shape)
    sims_mmap = np.lib.format.open_memmap(similarities_path, mode='w+', dtype=np.float32, shape=sim_shape)

    size_gb = specs_a_mmap.nbytes / 1024**3
    print(f"  specs_a: {spec_shape} ({size_gb:.2f} ГБ на диске)")
    print(f"  specs_b: {spec_shape} ({size_gb:.2f} ГБ на диске)")
    print(f"  similarities: {sim_shape}")
    print(f"  Итого на диске: ~{size_gb * 2:.1f} ГБ")

    # Фаза 5: Извлечение спектрограмм (GPU)
    print(f"\n→ Фаза 5: Извлечение спектрограмм (GPU)...")
    if USE_GPU:
        print(f"  Используется GPU: {torch.cuda.get_device_name(0)} (batch={BATCH_GPU})")
        torch.cuda.synchronize()
    else:
        print(f"  Используется CPU (librosa)")

    errors = 0
    processed_pairs = 0
    write_idx = 0

    with tqdm(total=len(pair_tasks), desc="Извлечение") as pbar:
        for file_a, file_b, similarity, seg_count in pair_tasks:
            if seg_count == 0:
                pbar.update(1)
                continue

            y_a = audio_cache.get(file_a)
            y_b = audio_cache.get(file_b)

            if y_a is None or y_b is None:
                errors += 1
                pbar.update(1)
                continue

            min_len = min(len(y_a), len(y_b))
            y_a = y_a[:min_len]
            y_b = y_b[:min_len]

            starts = list(range(0, min_len - SAMPLES_PER_SEGMENT + 1, HOP))
            if not starts:
                errors += 1
                pbar.update(1)
                continue

            num_segments = len(starts)
            segments_a = np.empty((num_segments, 1, N_MELS, 87), dtype=np.float32)
            segments_b = np.empty((num_segments, 1, N_MELS, 87), dtype=np.float32)
            idx = 0

            for batch_start in range(0, len(starts), BATCH_GPU):
                batch_starts = starts[batch_start:batch_start + BATCH_GPU]
                
                chunks_a = [y_a[s:s + SAMPLES_PER_SEGMENT] for s in batch_starts]
                chunks_b = [y_b[s:s + SAMPLES_PER_SEGMENT] for s in batch_starts]
                
                if USE_GPU:
                    mels_a = extract_mel_batch(chunks_a)
                    mels_b = extract_mel_batch(chunks_b)
                else:
                    mels_a = np.array([extract_mel_cpu(c) for c in chunks_a])
                    mels_b = np.array([extract_mel_cpu(c) for c in chunks_b])
                
                del chunks_a, chunks_b
                
                batch_len = len(batch_starts)
                segments_a[idx:idx + batch_len] = mels_a
                segments_b[idx:idx + batch_len] = mels_b
                idx += batch_len
                
                del mels_a, mels_b

            specs_a_mmap[write_idx:write_idx + num_segments] = segments_a
            specs_b_mmap[write_idx:write_idx + num_segments] = segments_b
            sims_mmap[write_idx:write_idx + num_segments] = np.float32(similarity)

            write_idx += num_segments
            processed_pairs += 1

            del segments_a, segments_b
            pbar.update(1)
            
            if USE_GPU and processed_pairs % 100 == 0:
                torch.cuda.empty_cache()

    audio_cache.clear()
    mel_cache.clear()
    del audio_cache, mel_cache
    
    if USE_GPU:
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
    gc.collect()

    print(f"  Записано пар: {processed_pairs}, ошибок: {errors}")
    final_count = write_idx

    # Фаза 6: Сохранение метаинформации
    print("\n→ Фаза 6: Сохранение метаинформации...")

    meta = {
        'codec': codec,
        'class_names': class_names,
        'class_to_idx': class_to_idx,
        'sr': SR,
        'segment_duration': SEGMENT_DURATION,
        'n_mels': N_MELS,
        'n_fft': N_FFT,
        'hop_length': HOP_LENGTH,
        'hop_segments': HOP,
        'num_segments': final_count,
        'channels': 1,
        'similarity_thresholds': SIMILARITY_THRESHOLDS,
        'metric_type': 'psychoacoustic_v12',
        'metric_params': {
            'sigmoid_center_db': 2.0,
            'sigmoid_slope_db': 1.2,
        }
    }

    with open(os.path.join(output_dir, 'meta.pkl'), 'wb') as f:
        pickle.dump(meta, f)

    # Статистика
    elapsed = time.time() - t_start
    
    if USE_GPU:
        torch.cuda.synchronize()
    
    print("\n" + "=" * 60)
    print(f"СТАТИСТИКА ДАТАСЕТА — {codec.upper()}")
    print("=" * 60)
    print(f"  Метрика: психоакустическая v12")
    print(f"  Классов: {len(class_names)}")
    print(f"  Сегментов: {final_count:,}")

    if final_count > 0:
        sims_actual = sims_mmap[:final_count]
        print(f"  Диапазон похожести: {sims_actual.min():.3f} – {sims_actual.max():.3f}")
        print(f"  Средняя похожесть: {sims_actual.mean():.3f}")
        print(f"  Медиана похожести: {np.median(sims_actual):.3f}")
        print(f"  STD похожести: {sims_actual.std():.3f}")

        bins = [0.0, 0.3, 0.55, 0.8, 1.0]
        print("\n  Распределение похожести:")
        for i in range(len(bins) - 1):
            count = ((sims_actual >= bins[i]) & (sims_actual < bins[i+1])).sum()
            pct = 100 * count / final_count if final_count > 0 else 0
            bar = '█' * int(pct / 2)
            print(f"  {CLASS_LABELS[i]:<10} {bins[i]:.1f}-{bins[i+1]:.1f}: {count:>8,} ({pct:5.1f}%) {bar}")
    else:
        print("  ⚠ Нет данных для статистики!")

    del specs_a_mmap, specs_b_mmap, sims_mmap
    
    print(f"\n✓ Датасет сохранён в '{output_dir}/'")
    print(f"  Время выполнения: {elapsed/60:.1f} мин")
    print(f"  Размер на диске: ~{size_gb * 2:.1f} ГБ")
    print(f"\n  Для теста: python build_dataset.py --codec {codec} --limit 3")


if __name__ == "__main__":
    main()
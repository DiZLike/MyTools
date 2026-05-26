import os
import sys
import re
import numpy as np
import librosa
import pickle
import subprocess
import tempfile
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

DATASET_DIR = "dataset"
OUTPUT_DIR = "spectrograms"
SEGMENT_DURATION = 1.0
SR = 44100
N_MELS = 128
SAMPLES_PER_SEGMENT = int(SEGMENT_DURATION * SR)
HOP = SAMPLES_PER_SEGMENT // 2

os.makedirs(OUTPUT_DIR, exist_ok=True)

class_names = [
    "lossless",
    "mp3_32", "mp3_64", "mp3_128", "mp3_192", "mp3_320",
    "aac_64", "aac_128", "aac_256",
    "opus_32", "opus_64", "opus_96", "opus_128", "opus_192"
]
class_to_idx = {name: i for i, name in enumerate(class_names)}


def load_audio(path, target_sr=44100):
    if path.lower().endswith('.opus'):
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
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, check=True)
        y, _ = librosa.load(tmp_name, sr=target_sr, mono=True)
        os.unlink(tmp_name)
        return y
    except:
        return None


def count_segments(audio_length):
    if audio_length < SAMPLES_PER_SEGMENT:
        return 1
    return (audio_length - SAMPLES_PER_SEGMENT) // HOP + 1


def main():
    all_files = []
    for f in os.listdir(DATASET_DIR):
        if f.startswith('.'):
            continue
        path = os.path.join(DATASET_DIR, f)
        if not os.path.isfile(path):
            continue
        match = re.match(r'^(.+?)_(?:t_|original)\d+', f)
        if match and match.group(1) in class_to_idx:
            all_files.append(f)

    print(f"Найдено файлов: {len(all_files)}")
    print(f"Классов: {len(class_names)}")

    print("\n→ Фаза 1: подсчёт сегментов...")
    total_segments = 0
    file_info = []
    errors = 0

    for fname in tqdm(all_files, desc="Сканирование"):
        path = os.path.join(DATASET_DIR, fname)
        match = re.match(r'^(.+?)_(?:t_|original)\d+', fname)
        class_name = match.group(1)
        label = class_to_idx[class_name]

        y = load_audio(path, SR)
        if y is None:
            tqdm.write(f"⚠ Не загрузился: {fname}")
            errors += 1
            continue

        n = count_segments(len(y))
        total_segments += n
        file_info.append((os.path.abspath(path), label, n))

    print(f"  Всего сегментов: {total_segments:,}")
    print(f"  Файлов: {len(file_info)}, ошибок: {errors}")

    if total_segments == 0:
        print("✗ Нет данных!")
        sys.exit(1)

    print("\n→ Фаза 2: создаём массивы на диске...")
    specs_path = os.path.join(OUTPUT_DIR, 'spectrograms.npy')
    labels_path = os.path.join(OUTPUT_DIR, 'labels.npy')

    for p in [specs_path, labels_path]:
        if os.path.exists(p):
            os.remove(p)

    spec_shape = (total_segments, N_MELS, 87)
    label_shape = (total_segments,)

    specs_mmap = np.lib.format.open_memmap(
        specs_path, mode='w+', dtype=np.float32, shape=spec_shape
    )
    labels_mmap = np.lib.format.open_memmap(
        labels_path, mode='w+', dtype=np.int64, shape=label_shape
    )
    print(f"  Спектрограммы: {spec_shape} ({specs_mmap.nbytes / 1024**3:.1f} ГБ на диске)")

    print("\n→ Фаза 3: нарезка...")
    write_idx = 0

    for path, label, expected_n in tqdm(file_info, desc="Обработка"):
        y = load_audio(path, SR)
        if y is None:
            tqdm.write(f"⚠ Не загрузился: {os.path.basename(path)}")
            errors += 1
            continue

        for start in range(0, len(y) - SAMPLES_PER_SEGMENT + 1, HOP):
            if write_idx >= total_segments:
                break
            segment = y[start:start + SAMPLES_PER_SEGMENT]
            mel = librosa.feature.melspectrogram(
                y=segment, sr=SR, n_mels=N_MELS, n_fft=2048, hop_length=512
            )
            mel_db = librosa.power_to_db(mel, ref=np.max)
            mel_db = (mel_db - mel_db.mean()) / (mel_db.std() + 1e-8)
            specs_mmap[write_idx] = mel_db.astype(np.float32)
            labels_mmap[write_idx] = label
            write_idx += 1

        remainder_start = (len(y) // HOP) * HOP
        if remainder_start > 0 and remainder_start < len(y) and write_idx < total_segments:
            segment = np.zeros(SAMPLES_PER_SEGMENT, dtype=np.float32)
            tail_len = len(y) - remainder_start
            if tail_len > 0:
                segment[:tail_len] = y[remainder_start:]
            mel = librosa.feature.melspectrogram(
                y=segment, sr=SR, n_mels=N_MELS, n_fft=2048, hop_length=512
            )
            mel_db = librosa.power_to_db(mel, ref=np.max)
            mel_db = (mel_db - mel_db.mean()) / (mel_db.std() + 1e-8)
            specs_mmap[write_idx] = mel_db.astype(np.float32)
            labels_mmap[write_idx] = label
            write_idx += 1

    if write_idx < total_segments:
        print(f"\n  Обрезаю до {write_idx:,} сегментов...")
        specs_mmap = specs_mmap[:write_idx]
        labels_mmap = labels_mmap[:write_idx]
        np.save(specs_path, specs_mmap)
        np.save(labels_path, labels_mmap)

    with open(os.path.join(OUTPUT_DIR, 'classes.pkl'), 'wb') as f:
        pickle.dump({'class_to_idx': class_to_idx, 'idx_to_class': class_names}, f)

    final_count = write_idx if write_idx < total_segments else total_segments
    print(f"\nГотово! Сегментов: {final_count:,}, ошибок: {errors}")

    unique, counts = np.unique(labels_mmap[:final_count], return_counts=True)
    print("\nРаспределение по классам:")
    for u, c in zip(unique, counts):
        print(f"  {class_names[u]}: {c:,} сегментов")

    print(f"\nДанные сохранены в '{OUTPUT_DIR}'")


if __name__ == "__main__":
    main()
"""
DATASET BUILDER — MP3 128 kbps
Берёт lossless-файлы, кодирует в MP3 128kbps, режет на сегменты по 3с
Выход: low_res (MP3→WAV) и high_res (lossless)
"""
import os
import subprocess
import numpy as np
import soundfile as sf
from pathlib import Path
from tqdm import tqdm
import tempfile
import shutil

# ======================== КОНФИГ ========================
INPUT_FOLDER = Path("E:/AI_RESTORE/music_hi_res")
OUTPUT_FOLDER = Path("E:/AI_RESTORE/dataset_audio_mp3_128")
BITRATE = "128k"
SR = 44100
SEGMENT_DURATION = 3.0
OVERLAP = 0.5
SKIP_START = 30
MAX_DURATION = 60

SAMPLES_PER_SEGMENT = int(SR * SEGMENT_DURATION)
HOP = int(SAMPLES_PER_SEGMENT * (1 - OVERLAP))

# ======================== ФУНКЦИИ ========================
def check_ffmpeg():
    """Проверяем наличие ffmpeg"""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ ffmpeg не найден. Установите ffmpeg и добавьте в PATH")
        return False

def encode_mp3(y, sr, bitrate, tmp_dir):
    """Кодирует аудио в MP3 и декодирует обратно"""
    # Временные файлы
    wav_in = tmp_dir / "input.wav"
    mp3_file = tmp_dir / "encoded.mp3"
    wav_out = tmp_dir / "output.wav"
    
    # Сохраняем WAV
    sf.write(wav_in, y, sr)
    
    # Кодируем в MP3
    subprocess.run([
        "ffmpeg", "-y", "-i", str(wav_in),
        "-codec:a", "libmp3lame", "-b:a", bitrate,
        "-qscale:a", "2",  # Высокое качество внутри битрейта
        str(mp3_file)
    ], capture_output=True, check=True)
    
    # Декодируем обратно
    subprocess.run([
        "ffmpeg", "-y", "-i", str(mp3_file),
        "-acodec", "pcm_s16le", "-ar", str(sr),
        "-ac", "1",
        str(wav_out)
    ], capture_output=True, check=True)
    
    # Читаем результат
    y_mp3, _ = sf.read(wav_out)
    
    # Чистим временные файлы
    for f in [wav_in, mp3_file, wav_out]:
        if f.exists():
            f.unlink()
    
    return y_mp3

def process_file(file_path, output_low_dir, output_high_dir, tmp_dir):
    """Обрабатывает один файл: кодирует целиком, потом режет на сегменты"""
    try:
        y, sr = sf.read(file_path)
        if sr != SR:
            import librosa
            y = librosa.resample(y, orig_sr=sr, target_sr=SR)
            sr = SR
    except Exception as e:
        tqdm.write(f"❌ Ошибка загрузки {file_path.name}: {e}")
        return 0

    # Нормализация
    y = y / (np.max(np.abs(y)) + 1e-8)

    # Обрезаем начало и конец
    start_sample = int(SKIP_START * sr)
    if len(y) <= start_sample:
        return 0
    y = y[start_sample:]
    
    max_samples = int(MAX_DURATION * sr)
    if len(y) > max_samples:
        y = y[:max_samples]
    
    if len(y) < SAMPLES_PER_SEGMENT:
        return 0

    # Кодируем ВЕСЬ трек в MP3 и обратно (один проход кодеком!)
    tqdm.write(f"   🎧 Кодирование {file_path.name} в MP3 {BITRATE}...")
    try:
        y_mp3 = encode_mp3(y, sr, BITRATE, tmp_dir)
    except Exception as e:
        tqdm.write(f"❌ Ошибка кодирования {file_path.name}: {e}")
        return 0
    
    # Режем на сегменты
    seg_count = 0
    for start in range(0, len(y) - SAMPLES_PER_SEGMENT + 1, HOP):
        high_res = y[start:start + SAMPLES_PER_SEGMENT]
        low_res = y_mp3[start:start + SAMPLES_PER_SEGMENT]
        
        base_name = f"{file_path.stem}_{seg_count:04d}"
        sf.write(output_high_dir / f"{base_name}.wav", high_res, sr)
        sf.write(output_low_dir / f"{base_name}.wav", low_res, sr)
        seg_count += 1
    
    return seg_count

# ======================== MAIN ========================
if __name__ == "__main__":
    if not check_ffmpeg():
        exit(1)
    
    output_low = OUTPUT_FOLDER / "low_res"
    output_high = OUTPUT_FOLDER / "high_res"
    output_low.mkdir(parents=True, exist_ok=True)
    output_high.mkdir(parents=True, exist_ok=True)

    audio_files = list(INPUT_FOLDER.glob("*.wav")) + list(INPUT_FOLDER.glob("*.flac"))

    if not audio_files:
        print(f"❌ Нет файлов в {INPUT_FOLDER}")
        exit(1)

    print(f"🎵 Найдено треков: {len(audio_files)}")
    print(f"📂 Вход:  {INPUT_FOLDER}")
    print(f"📂 Выход: {OUTPUT_FOLDER}")
    print(f"🎧 Битрейт: {BITRATE}")
    print(f"⏱️  Сегменты: {SEGMENT_DURATION}с, перекрытие {OVERLAP}с")
    print()

    total_segments = 0
    tmp_dir = Path(tempfile.mkdtemp())
    
    try:
        for f in tqdm(audio_files, desc="🔪 Обработка треков", unit="track"):
            segs = process_file(f, output_low, output_high, tmp_dir)
            total_segments += segs
            if segs > 0:
                tqdm.write(f"   ✅ {f.name}: {segs} сегментов")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"\n🏁 Готово! Всего сегментов: {total_segments}")
    print(f"   low_res:  {output_low}")
    print(f"   high_res: {output_high}")
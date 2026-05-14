import os
import subprocess
import sys
import tempfile
import re
from pathlib import Path
import time

# ============ НАСТРОЙКИ ============
AUDIO_FOLDER = r"Z:\\web\\media\\music"
BITRATE = 64
FRAME_SIZE = 60
COMPLEXITY = 10
# ====================================

# Пути к инструментам
SCRIPT_DIR = Path(__file__).parent
TOOLS_DIR = SCRIPT_DIR / "tools"
OPUSENC = TOOLS_DIR / "opusenc.exe"
FFMPEG = TOOLS_DIR / "ffmpeg.exe"

# Локальная папка для временных файлов
TEMP_DIR = Path(tempfile.gettempdir()) / "mp3_to_opus_temp"

def check_tools():
    """Проверяем наличие необходимых инструментов"""
    if not OPUSENC.exists():
        print(f"Ошибка: opusenc не найден по пути {OPUSENC}")
        print("Скачайте opus-tools с https://opus-codec.org/downloads/")
        return False
    
    if not FFMPEG.exists():
        print(f"Ошибка: ffmpeg не найден по пути {FFMPEG}")
        print("Скачайте ffmpeg с https://ffmpeg.org/download.html")
        return False
    
    return True

def setup_temp_dir():
    """Создаем временную папку если её нет"""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Временная папка: {TEMP_DIR}")

def cleanup_temp_dir():
    """Очищаем временную папку"""
    if TEMP_DIR.exists():
        try:
            for file in TEMP_DIR.glob("*"):
                file.unlink()
            TEMP_DIR.rmdir()
            print("Временная папка очищена")
        except Exception as e:
            print(f"Предупреждение: не удалось очистить временную папку: {e}")

def get_audio_duration(mp3_path):
    """Получаем длительность аудио в секундах через ffprobe"""
    try:
        cmd = [
            str(FFMPEG).replace('ffmpeg.exe', 'ffprobe.exe'),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(mp3_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except:
        return None

def format_time(seconds):
    """Форматируем время в читаемый вид"""
    if seconds is None:
        return "??:??"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def convert_mp3_to_wav(mp3_path, wav_path, total_duration):
    """Конвертируем MP3 в WAV через ffmpeg с прогрессом"""
    cmd = [
        str(FFMPEG),
        "-i", str(mp3_path),
        "-acodec", "pcm_s16le",
        "-ar", "48000",
        "-ac", "2",
        "-y",
        "-progress", "pipe:1",  # Вывод прогресса в stdout
        "-nostats",  # Не выводить статистику
        str(wav_path)
    ]
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        # Читаем прогресс
        last_time = 0
        for line in process.stdout:
            if "out_time_ms=" in line:
                try:
                    time_ms = int(line.split("=")[1])
                    time_sec = time_ms / 1000000  # Конвертируем микросекунды в секунды
                    
                    if total_duration and total_duration > 0:
                        progress = min(100, (time_sec / total_duration) * 100)
                        # Обновляем прогресс не чаще 2 раз в секунду
                        if time_sec - last_time >= 0.5 or progress >= 100:
                            print(f"\r  -> MP3 -> WAV: {progress:.0f}% [{format_time(time_sec)} / {format_time(total_duration)}]", end="", flush=True)
                            last_time = time_sec
                except:
                    pass
        
        process.wait()
        
        if process.returncode == 0:
            print(f"\r  -> MP3 -> WAV: 100% ✓")
            return True
        else:
            stderr = process.stderr.read()
            print(f"\r  -> ОШИБКА ffmpeg: {stderr}")
            return False
            
    except Exception as e:
        print(f"\r  -> Ошибка при конвертации MP3 в WAV: {e}")
        return False

def convert_wav_to_opus(wav_path, opus_path):
    """Конвертируем WAV в Opus через opusenc с прогрессом"""
    cmd = [
        str(OPUSENC),
        "--bitrate", str(BITRATE),
        "--framesize", str(FRAME_SIZE),
        "--comp", str(COMPLEXITY),
        "--music",
        str(wav_path),
        str(opus_path)
    ]
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        # opusenc выводит прогресс в формате "Encoding ... %"
        for line in process.stdout:
            # Ищем процент выполнения
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
            if match:
                percent = float(match.group(1))
                print(f"\r  -> WAV -> Opus: {percent:.0f}%", end="", flush=True)
        
        process.wait()
        
        if process.returncode == 0:
            print(f"\r  -> WAV -> Opus: 100%  ✓")
            return True
        else:
            print(f"\r  -> ОШИБКА opusenc")
            return False
            
    except Exception as e:
        print(f"\r  -> Ошибка при конвертации WAV в Opus: {e}")
        return False

def process_folder():
    """Рекурсивно обрабатываем папку с аудио"""
    audio_folder = Path(AUDIO_FOLDER)
    
    if not audio_folder.exists():
        print(f"Ошибка: Папка {audio_folder} не существует!")
        return
    
    # Собираем все MP3 файлы
    mp3_files = list(audio_folder.rglob("*.mp3"))
    
    if not mp3_files:
        print(f"MP3 файлы не найдены в {audio_folder}")
        return
    
    print(f"Найдено {len(mp3_files)} MP3 файлов")
    print(f"Настройки: битрейт={BITRATE}kbps, размер кадра={FRAME_SIZE}ms, сложность={COMPLEXITY}")
    print("-" * 50)
    
    successful = 0
    failed = 0
    skipped = 0
    start_time = time.time()
    
    for i, mp3_file in enumerate(mp3_files, 1):
        opus_file = mp3_file.with_suffix(".opus")
        
        # Проверяем, существует ли уже Opus файл
        if opus_file.exists():
            print(f"[{i}/{len(mp3_files)}] Пропущен (уже существует): {mp3_file.name}")
            skipped += 1
            continue
        
        print(f"\n[{i}/{len(mp3_files)}] Обработка: {mp3_file.relative_to(audio_folder)}")
        
        # Получаем длительность аудио
        duration = get_audio_duration(mp3_file)
        
        # Создаем временный WAV файл в локальной папке
        wav_temp = TEMP_DIR / f"{mp3_file.stem}.temp.wav"
        
        try:
            # Шаг 1: MP3 -> WAV
            if not convert_mp3_to_wav(mp3_file, wav_temp, duration):
                print(f"  -> ОШИБКА при создании WAV!")
                failed += 1
                continue
            
            # Шаг 2: WAV -> Opus
            if not convert_wav_to_opus(wav_temp, opus_file):
                print(f"  -> ОШИБКА при создании Opus!")
                failed += 1
                continue
            
            # Получаем размеры файлов для статистики
            mp3_size = mp3_file.stat().st_size / (1024 * 1024)  # МБ
            opus_size = opus_file.stat().st_size / (1024 * 1024)  # МБ
            compression = (1 - opus_size / mp3_size) * 100
            
            print(f"  -> Успешно! {mp3_size:.1f}MB -> {opus_size:.1f}MB (экономия {compression:.0f}%)")
            successful += 1
            
        finally:
            # Удаляем временный WAV файл локально
            if wav_temp.exists():
                wav_temp.unlink()
    
    elapsed_time = time.time() - start_time
    
    print("\n" + "=" * 50)
    print(f"ГОТОВО!")
    print(f"Успешно: {successful}")
    print(f"Ошибок: {failed}")
    print(f"Пропущено: {skipped}")
    print(f"Время выполнения: {format_time(elapsed_time)}")
    print("=" * 50)

if __name__ == "__main__":
    if not check_tools():
        sys.exit(1)
    
    setup_temp_dir()
    
    try:
        process_folder()
    finally:
        cleanup_temp_dir()
    input("\nНажмите Enter для выхода...")
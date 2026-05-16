import os
import subprocess
import sys
import tempfile
import re
from pathlib import Path
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ============ НАСТРОЙКИ ============
AUDIO_FOLDER = "Z:/!Evgeny/src/py/downloads"
BITRATE = 40
FRAME_SIZE = 60
COMPLEXITY = 10
MAX_WORKERS = os.cpu_count() or 4
# ====================================

SCRIPT_DIR = Path(__file__).parent
TOOLS_DIR = SCRIPT_DIR / "tools"
OPUSENC = TOOLS_DIR / "opusenc.exe"
FFMPEG = TOOLS_DIR / "ffmpeg.exe"
FFPROBE = TOOLS_DIR / "ffprobe.exe"
TEMP_DIR = Path(tempfile.gettempdir()) / "mp3_to_opus_temp"

# Глобальные переменные для прогресса
progress_lock = threading.Lock()
stats = {"success": 0, "failed": 0, "skipped": 0, "total_bytes_orig": 0, "total_bytes_opus": 0, "completed": 0}
start_time = 0
total_files = 0
converted_pairs = []

def format_time(seconds):
    if seconds is None: return "??:??"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024: return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def check_tools():
    for tool, path in [("opusenc", OPUSENC), ("ffmpeg", FFMPEG), ("ffprobe", FFPROBE)]:
        if not path.exists():
            print(f"Ошибка: {tool} не найден по пути {path}")
            return False
    return True

def get_duration(path):
    try:
        p = subprocess.run([str(FFPROBE), "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                          capture_output=True, text=True, timeout=30)
        return float(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else None
    except: return None

def extract_metadata(mp3_path):
    try:
        p = subprocess.run([str(FFPROBE), "-v", "quiet", "-print_format", "json", "-show_entries", "format_tags", str(mp3_path)],
                          capture_output=True, text=True, timeout=30)
        if p.returncode != 0: return {}
        tags = json.loads(p.stdout).get('format', {}).get('tags', {})
        keys = ['title', 'artist', 'album', 'date', 'track', 'genre', 'comment']
        return {k: tags[k] for k in keys if tags.get(k)}
    except: return {}

def convert_mp3_to_opus(mp3_path, opus_path):
    """Прямая конвертация MP3 -> Opus (два шага: MP3->WAV->Opus)"""
    wav_temp = TEMP_DIR / f"{mp3_path.stem}_{threading.get_ident()}.wav"
    try:
        # MP3 -> WAV
        p = subprocess.run([str(FFMPEG), "-i", str(mp3_path), "-acodec", "pcm_s16le",
                           "-ar", "48000", "-ac", "2", "-y", "-nostats", str(wav_temp)],
                          capture_output=True, text=True, timeout=300)
        if p.returncode != 0 or not wav_temp.exists() or wav_temp.stat().st_size == 0:
            return False
        
        # WAV -> Opus
        p = subprocess.run([str(OPUSENC), "--bitrate", str(BITRATE), "--framesize", str(FRAME_SIZE),
                           "--comp", str(COMPLEXITY), "--music", str(wav_temp), str(opus_path)],
                          capture_output=True, text=True, timeout=300)
        return p.returncode == 0 and opus_path.exists() and opus_path.stat().st_size > 0
    except: return False
    finally:
        if wav_temp.exists():
            try: wav_temp.unlink()
            except: pass

def validate_opus(path):
    try:
        p = subprocess.run([str(FFPROBE), "-v", "error", "-show_entries", "stream=codec_name",
                           "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                          capture_output=True, text=True, timeout=30)
        return p.returncode == 0 and 'opus' in p.stdout.lower()
    except: return False

def apply_metadata(opus_path, metadata):
    if not metadata: return True
    temp_path = opus_path.with_suffix('.temp.opus')
    try:
        cmd = [str(FFMPEG), "-i", str(opus_path)]
        for k, v in metadata.items():
            cmd.extend(["-metadata", f"{k}={v}"])
        cmd.extend(["-c", "copy", "-y", str(temp_path)])
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if p.returncode == 0 and temp_path.exists() and temp_path.stat().st_size > 0:
            opus_path.unlink()
            temp_path.rename(opus_path)
            return True
        return False
    except: return False
    finally:
        if temp_path and temp_path.exists():
            try: temp_path.unlink()
            except: pass

def print_progress():
    """Вывод двухстрочного прогресс-бара"""
    with progress_lock:
        elapsed = time.time() - start_time
        completed = stats['completed']
        percent = (completed / total_files * 100) if total_files > 0 else 0
        files_per_min = completed / (elapsed / 60) if elapsed > 0 else 0
        mb_per_sec = (stats['total_bytes_opus'] / (1024 * 1024)) / elapsed if elapsed > 0 else 0
        total_orig = stats['total_bytes_orig']
        total_opus = stats['total_bytes_opus']
        saved = total_orig - total_opus
        saved_pct = (saved / total_orig * 100) if total_orig > 0 else 0
        
        if files_per_min > 0:
            remaining = (total_files - completed) / files_per_min * 60
            eta = format_time(remaining)
        else:
            eta = "..."
        
        bar_len = 30
        filled = int(bar_len * completed / total_files) if total_files > 0 else 0
        bar = '█' * filled + '░' * (bar_len - filled)
        
        line1 = (f"📊 [{bar}] {percent:.1f}% | "
                 f"Файлов: {completed}/{total_files} | "
                 f"✅ {stats['success']} | ⏭️ {stats['skipped']} | ❌ {stats['failed']}")
        
        line2 = (f"💾 Было: {format_size(total_orig)} | Стало: {format_size(total_opus)} | "
                 f"Экономия: {saved_pct:.1f}% ({format_size(saved)}) | "
                 f"⚡ {files_per_min:.1f} файл/мин | 📀 {mb_per_sec:.1f} MB/s | "
                 f"⏱️ {format_time(elapsed)} | 🕐 {eta}")
        
        print(f"\r\033[K{line1}\n\033[K{line2}", end='', flush=True)
        print(f"\r\033[1A", end='', flush=True)

def process_file(mp3_file):
    """Обработка одного MP3 файла"""
    opus_file = mp3_file.with_suffix(".opus")
    
    # Проверяем существование Opus
    if opus_file.exists():
        with progress_lock:
            stats['completed'] += 1
            stats['skipped'] += 1
        return ('skipped', None, None, None)
    
    # Извлекаем метаданные
    metadata = extract_metadata(mp3_file)
    
    # Конвертируем
    if not convert_mp3_to_opus(mp3_file, opus_file):
        with progress_lock:
            stats['completed'] += 1
            stats['failed'] += 1
        return ('failed', None, None, None)
    
    # Проверяем валидность
    if not validate_opus(opus_file):
        if opus_file.exists():
            opus_file.unlink()
        with progress_lock:
            stats['completed'] += 1
            stats['failed'] += 1
        return ('failed', None, None, None)
    
    # Применяем метаданные
    if metadata:
        apply_metadata(opus_file, metadata)
    
    # Размеры
    mp3_size = mp3_file.stat().st_size
    opus_size = opus_file.stat().st_size
    
    with progress_lock:
        stats['completed'] += 1
        stats['success'] += 1
        stats['total_bytes_orig'] += mp3_size
        stats['total_bytes_opus'] += opus_size
    
    return ('success', mp3_file, opus_file, mp3_size, opus_size)

def delete_originals(pairs):
    if not pairs: return
    total = 0
    for mp3_path, _ in pairs:
        try:
            if mp3_path.exists():
                total += mp3_path.stat().st_size
                mp3_path.unlink()
        except: pass
    print(f"\nУдалено: {format_size(total)}")

def process_folder():
    global start_time, total_files, converted_pairs, stats
    
    audio_folder = Path(AUDIO_FOLDER)
    if not audio_folder.exists():
        print(f"Ошибка: Папка {audio_folder} не существует!")
        return
    
    mp3_files = list(audio_folder.rglob("*.mp3"))
    if not mp3_files:
        print(f"MP3 файлы не найдены в {audio_folder}")
        return
    
    total_files = len(mp3_files)
    stats = {"success": 0, "failed": 0, "skipped": 0, "total_bytes_orig": 0, "total_bytes_opus": 0, "completed": 0}
    converted_pairs = []
    start_time = time.time()
    
    print(f"Найдено {total_files} MP3 файлов")
    print(f"Битрейт: {BITRATE}kbps, Кадр: {FRAME_SIZE}ms, Сложность: {COMPLEXITY}")
    print(f"Потоков: {MAX_WORKERS}")
    print()
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_file, f): f for f in mp3_files}
        
        # Периодически обновляем прогресс
        done_count = 0
        for future in as_completed(futures):
            result = future.result()
            if result[0] == 'success':
                converted_pairs.append((result[1], result[2]))
            done_count += 1
            if done_count % 10 == 0 or done_count == total_files:
                print_progress()
    
    print("\n")
    print_progress()
    print("\n\n" + "=" * 60)
    print(f"ГОТОВО! Успешно: {stats['success']}, Ошибок: {stats['failed']}, Пропущено: {stats['skipped']}")
    print(f"Экономия: {format_size(stats['total_bytes_orig'] - stats['total_bytes_opus'])} ({(1 - stats['total_bytes_opus']/stats['total_bytes_orig'])*100:.1f}%)" if stats['total_bytes_orig'] > 0 else "")
    print("=" * 60)
    
    if converted_pairs:
        print(f"\nУспешно конвертировано: {len(converted_pairs)} файлов")
        choice = input("\nУдалить оригинальные MP3? (y/n): ").lower().strip()
        if choice in ['y', 'yes']:
            delete_originals(converted_pairs)

if __name__ == "__main__":
    if not check_tools():
        sys.exit(1)
    
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Временная папка: {TEMP_DIR}")
    
    try:
        process_folder()
    finally:
        # Очистка временной папки
        if TEMP_DIR.exists():
            try:
                for f in TEMP_DIR.glob("*"): f.unlink()
                TEMP_DIR.rmdir()
            except: pass
    
    input("\nНажмите Enter для выхода...")
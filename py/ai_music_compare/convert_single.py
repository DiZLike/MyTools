"""
convert_single.py
Конвертирует один трек во все кодеки/битрейты для тестирования.
Использует qaac64, opusenc, lame из папки tools.
Пропускает уже существующие файлы.
"""

import os
import sys
import subprocess

# ========== НАСТРОЙКИ ==========
TOOLS_DIR = "tools"
OUTPUT_DIR = "data"

QAAC = os.path.join(TOOLS_DIR, "qaac64.exe")
OPUSENC = os.path.join(TOOLS_DIR, "opusenc.exe")
LAME = os.path.join(TOOLS_DIR, "lame.exe")

# ========== КОНФИГУРАЦИИ ==========
CONFIGS = [
    ("opus_60ms", "opus", [32, 48, 64, 96, 128, 160, 192, 256, 320]),
    ("mp3", "mp3", [32, 64, 96, 128, 160, 192, 256, 320]),
    ("aac", "aac", [64, 96, 128, 160, 192, 256, 320]),
    ("aac_he", "aac_he", [32, 48, 64, 80]),
]


def check_tools():
    """Проверяет наличие всех кодеров."""
    missing = []
    for tool, path in [("qaac64", QAAC), ("opusenc", OPUSENC), ("lame", LAME)]:
        if not os.path.exists(path):
            missing.append(f"{tool} ({path})")
    
    if missing:
        print("✗ Не найдены кодеры:")
        for m in missing:
            print(f"  - {m}")
        print(f"\nПоместите их в папку '{TOOLS_DIR}/'")
        return False
    return True


def convert_opus(input_path, output_path, bitrate, frame_ms):
    """Конвертирует в Opus через opusenc."""
    cmd = [
        OPUSENC,
        "--bitrate", str(bitrate),
        "--framesize", str(frame_ms),
        "--music",
        "--quiet",
        input_path,
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
    if result.returncode != 0:
        print(f"    opusenc error: {result.stderr.strip()}")
    return result.returncode == 0


def convert_mp3(input_path, output_path, bitrate):
    """Конвертирует в MP3 через lame."""
    cmd = [
        LAME,
        "-b", str(bitrate),
        "-q", "2",
        "--quiet",
        input_path,
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
    if result.returncode != 0:
        print(f"    lame error: {result.stderr.strip()}")
    return result.returncode == 0


def convert_aac(input_path, output_path, bitrate, profile="lc"):
    """Конвертирует в AAC через qaac64."""
    cmd_aac = [
        QAAC,
        "--cbr", str(bitrate),
        "--quality", "2",
        "--silent",
    ]
    
    if profile == "he":
        cmd_aac.append("--he")
    
    cmd_aac += ["-o", output_path, input_path]
    
    result = subprocess.run(cmd_aac, capture_output=True, text=True, errors='replace')
    if result.returncode != 0:
        print(f"    qaac error: {result.stderr.strip()}")
    return result.returncode == 0


def get_output_filename(input_name, codec_name, bitrate):
    """Формирует имя выходного файла."""
    if "opus" in codec_name:
        return f"{codec_name}_{bitrate}k.opus"
    elif codec_name == "mp3":
        return f"{codec_name}_{bitrate}k.mp3"
    elif "aac" in codec_name:
        return f"{codec_name}_{bitrate}k.m4a"
    return f"{codec_name}_{bitrate}k.xxx"


def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python convert_single.py <путь_к_треку>")
        print()
        print("Пример:")
        print("  python convert_single.py my_track.flac")
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    if not os.path.exists(input_path):
        print(f"✗ Файл не найден: {input_path}")
        sys.exit(1)
    
    if not check_tools():
        sys.exit(1)
    
    print("=" * 60)
    print("КОНВЕРТАЦИЯ ТРЕКА ВО ВСЕ КОДЕКИ/БИТРЕЙТЫ")
    print("=" * 60)
    print(f"  Исходник: {os.path.basename(input_path)}")
    print(f"  Размер:   {os.path.getsize(input_path) / 1024**2:.1f} МБ")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    input_name = os.path.splitext(os.path.basename(input_path))[0]
    
    # Конвертируем в WAV один раз
    wav_path = os.path.join(OUTPUT_DIR, f"{input_name}_temp_44100.wav")
    if not os.path.exists(wav_path):
        print("\n→ Конвертация в WAV (44100 Hz, stereo)...")
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vn", "-ac", "2",
            "-ar", "44100",
            "-f", "wav",
            wav_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors='replace')
        
        if not os.path.exists(wav_path):
            print(f"✗ Не удалось конвертировать в WAV")
            print(f"  ffmpeg: {result.stderr.strip()}")
            sys.exit(1)
        print(f"  ✓ {os.path.basename(wav_path)} ({os.path.getsize(wav_path) // 1024**2} МБ)")
    else:
        print(f"\n→ WAV уже существует: {os.path.basename(wav_path)}")
    
    # Собираем список задач
    tasks = []
    for codec_name, codec_type, bitrates in CONFIGS:
        for bitrate in bitrates:
            output_file = get_output_filename(input_name, codec_name, bitrate)
            output_path = os.path.join(OUTPUT_DIR, output_file)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                tasks.append((codec_name, codec_type, bitrate, output_file, output_path, True))
            else:
                tasks.append((codec_name, codec_type, bitrate, output_file, output_path, False))
    
    total = len(tasks)
    done = 0
    errors = 0
    skipped = sum(1 for t in tasks if t[5])
    
    if skipped > 0:
        print(f"\n  Уже готово: {skipped} файлов")
    
    print(f"\n→ Конвертация ({total - skipped} новых из {total})...\n")
    
    for codec_name, codec_type, bitrate, output_file, output_path, exists in tasks:
        if exists:
            size_kb = os.path.getsize(output_path) // 1024
            print(f"  [{done+1:3}/{total}] ⊙ {output_file:<35} {size_kb:>6} KB (пропущен)")
            done += 1
            continue
        
        if codec_type == "opus":
            frame_ms = 20 if "20ms" in codec_name else 60
            success = convert_opus(wav_path, output_path, bitrate, frame_ms)
        
        elif codec_type == "mp3":
            success = convert_mp3(wav_path, output_path, bitrate)
        
        elif codec_type in ("aac", "aac_he", "aac_he_v2"):
            profile = {"aac": "lc", "aac_he": "he", "aac_he_v2": "he_v2"}[codec_type]
            success = convert_aac(wav_path, output_path, bitrate, profile)
        
        else:
            continue
        
        done += 1
        status = "✓" if success else "✗"
        if success and os.path.exists(output_path):
            size_kb = os.path.getsize(output_path) // 1024
            print(f"  [{done:3}/{total}] {status} {output_file:<35} {size_kb:>6} KB")
        else:
            print(f"  [{done:3}/{total}] {status} {output_file:<35}       0 KB")
        
        if not success:
            errors += 1
    
    # Удаляем временный WAV
    if os.path.exists(wav_path):
        os.remove(wav_path)
    
    # Статистика
    print(f"\n{'='*60}")
    print(f"Готово! Файлов: {done}, ошибок: {errors}, пропущено: {skipped}")
    print(f"Выходная папка: '{OUTPUT_DIR}/'")
    
    # Группировка по кодекам
    files = sorted([f for f in os.listdir(OUTPUT_DIR) if not f.endswith('.tmp.wav')])
    
    print(f"\nСгенерированные файлы:")
    current_codec = None
    for f in files:
        codec = f.split('_')[0]
        if codec != current_codec:
            if current_codec is not None:
                print()
            current_codec = codec
            print(f"  {codec}:")
        print(f"    {f}")


if __name__ == "__main__":
    main()
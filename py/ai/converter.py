import subprocess
import os
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

INPUT_DIR = "originals"
OUTPUT_DIR = "dataset"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CODEC_CONFIGS = [
    ("lossless",   "pcm_s16le",  None,  ".wav"),
    
    # MP3
    ("mp3_32",     "libmp3lame", "32k",  ".mp3"),
    ("mp3_64",     "libmp3lame", "64k",  ".mp3"),
    ("mp3_128",    "libmp3lame", "128k", ".mp3"),
    ("mp3_192",    "libmp3lame", "192k", ".mp3"),
    ("mp3_320",    "libmp3lame", "320k", ".mp3"),
    
    # AAC
    ("aac_64",     "aac",        "64k",  ".mp4"),
    ("aac_128",    "aac",        "128k", ".mp4"),
    ("aac_256",    "aac",        "256k", ".mp4"),
    
    # Opus 60ms
    ("opus_32",    "libopus",    "32k",  ".opus"),
    ("opus_64",    "libopus",    "64k",  ".opus"),
    ("opus_96",    "libopus",    "96k",  ".opus"),
    ("opus_128",   "libopus",    "128k", ".opus"),
    ("opus_192",   "libopus",    "192k", ".opus"),
]


def convert_one(args):
    original_path, class_name, codec, bitrate, ext, output_dir = args
    
    base = os.path.splitext(os.path.basename(original_path))[0]
    output_name = f"{class_name}_{base}{ext}"
    output_path = os.path.join(output_dir, output_name)
    
    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return f"⊙ {output_name} (уже есть)"
    
    try:
        if class_name == "lossless":
            shutil.copy(original_path, output_path)
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", original_path,
                "-vn",
                "-c:a", codec,
                "-b:a", bitrate,
                "-map_metadata", "-1",
            ]
            
            if "opus" in class_name:
                cmd.extend(["-frame_duration", "60"])
            else:
                cmd.extend(["-ar", "44100"])
            
            cmd.append(output_path)
            
            result = subprocess.run(cmd, capture_output=True, text=False)
            if result.returncode != 0:
                err_text = result.stderr.decode('utf-8', errors='ignore').strip() if result.stderr else "нет вывода"
                err_lines = err_text.split('\n')[-2:]
                return f"✗ Ошибка: {output_name}\n  {chr(10).join(err_lines)}"
        
        return f"✓ {output_name}"
    except Exception as e:
        return f"✗ Исключение: {output_name} - {e}"


def main():
    originals = []
    for f in sorted(os.listdir(INPUT_DIR)):
        if f.lower().endswith('.wav'):
            path = os.path.join(INPUT_DIR, f)
            if os.path.isfile(path):
                originals.append(path)
    
    print(f"Найдено исходников: {len(originals)}")
    
    tasks = []
    for orig in originals:
        for class_name, codec, bitrate, ext in CODEC_CONFIGS:
            tasks.append((orig, class_name, codec, bitrate, ext, OUTPUT_DIR))
    
    print(f"Всего задач: {len(tasks)}")
    print(f"Запуск в {os.cpu_count()} потоков...\n")
    
    results = []
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = {executor.submit(convert_one, task): task for task in tasks}
        
        with tqdm(total=len(tasks), desc="Конвертация") as pbar:
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                pbar.update(1)
                if result.startswith("✗"):
                    tqdm.write(result)
    
    success = sum(1 for r in results if r.startswith("✓"))
    skipped = sum(1 for r in results if "уже есть" in r)
    errors = sum(1 for r in results if r.startswith("✗"))
    
    print(f"\nГотово! Успешно: {success}, Пропущено: {skipped}, Ошибок: {errors}")
    print(f"Файлов в '{OUTPUT_DIR}': {len(os.listdir(OUTPUT_DIR))}")


if __name__ == "__main__":
    main()
# main.py — полная замена

import sys
import os
import argparse
from pathlib import Path
from pydub import AudioSegment

from config import PRESETS, DEFAULT_CONFIG
from encoder import audio_to_pages
from decoder import decode_pages
from utils import ensure_dir, clean_temp_files


def mp3_to_wav(mp3_path: str, wav_path: str) -> str:
    """Конвертирует MP3 в WAV для обработки."""
    print(f"   Конвертация MP3: {Path(mp3_path).name}")
    audio = AudioSegment.from_mp3(mp3_path)
    audio.export(wav_path, format="wav")
    size_mb = Path(wav_path).stat().st_size / (1024 * 1024)
    print(f"   WAV создан ({size_mb:.1f} MB)")
    return wav_path


def cmd_encode(args):
    """Команда encode: аудио → страницы для печати."""
    config = DEFAULT_CONFIG.copy()
    
    # Переопределение из аргументов
    if args.preset:
        config['active_preset'] = args.preset
    if args.dpi:
        config['dpi'] = args.dpi
    if args.calibration is not None:
        config['calibration_enabled'] = args.calibration
    if args.trim_start is not None:
        config['trim_enabled'] = True
        config['trim_start'] = args.trim_start
    if args.trim_end is not None:
        config['trim_enabled'] = True
        config['trim_end'] = args.trim_end
    
    input_file = args.input
    data_dir = config.get('data_dir', 'data')
    ensure_dir(data_dir)
    
    # Имя выходных файлов
    if args.output:
        output_base = str(Path(data_dir) / args.output)
    else:
        output_base = str(Path(data_dir) / Path(input_file).stem)
    
    # Проверяем входной файл
    if not os.path.exists(input_file):
        print(f"❌ Файл не найден: {input_file}")
        sys.exit(1)
    
    # Конвертируем в WAV если нужно
    ext = Path(input_file).suffix.lower()
    
    if ext in ('.mp3', '.m4a', '.aac', '.ogg', '.flac'):
        wav_temp = str(Path(data_dir) / "temp_encode.wav")
        try:
            mp3_to_wav(input_file, wav_temp)
            input_file = wav_temp
        except Exception as e:
            print(f"❌ Ошибка конвертации: {e}")
            print("   Поддерживаются форматы: WAV, MP3, FLAC, M4A, AAC, OGG")
            sys.exit(1)
    elif ext != '.wav':
        print(f"❌ Неподдерживаемый формат: {ext}")
        print("   Поддерживаются: WAV, MP3, FLAC, M4A, AAC, OGG")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"КОДИРОВАНИЕ: {Path(input_file).name} → страницы A4")
    print(f"{'='*60}")
    
    try:
        saved_files, metadata = audio_to_pages(input_file, output_base, config)
        
        print(f"\n{'='*60}")
        print(f"ГОТОВО! Создано файлов: {len(saved_files)} (включая QR-страницу)")
        print(f"{'='*60}")
        for f in saved_files:
            size_mb = Path(f).stat().st_size / (1024 * 1024)
            print(f"   {Path(f).name} ({size_mb:.1f} MB)")
        
        print(f"\n   📋 Для декодирования:")
        if metadata.get('total_pages', 1) > 1:
            print(f"   python main.py decode --input \"{output_base}_page*of{metadata['total_pages']}.png\" --output recovered.wav")
        else:
            print(f"   python main.py decode --input \"{saved_files[0]}\" --output recovered.wav")
        print(f"   (QR-страница {output_base}_qr.png будет найдена автоматически)")
        
    except Exception as e:
        print(f"\n❌ Ошибка кодирования: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Очистка временных файлов
        if 'wav_temp' in locals():
            clean_temp_files(wav_temp)


def cmd_decode(args):
    """Команда decode: скан → аудио."""
    config = DEFAULT_CONFIG.copy()
    
    # Переопределение из аргументов
    if args.calibration is not None:
        config['calibration_enabled'] = args.calibration
    if args.iterations:
        config['phase_generate_iterations'] = args.iterations
    if args.mode:
        config['griffin_lim_mode'] = args.mode
    
    data_dir = config.get('data_dir', 'data')
    ensure_dir(data_dir)
    
    # Собираем входные файлы
    input_paths = []
    for inp in args.input:
        # Поддержка glob-паттернов
        if '*' in inp or '?' in inp:
            import glob
            matches = sorted(glob.glob(inp))
            input_paths.extend(matches)
        else:
            input_paths.append(inp)
    
    if not input_paths:
        print("❌ Не найдены файлы для декодирования")
        sys.exit(1)
    
    output_file = str(Path(data_dir) / args.output) if args.output else str(Path(data_dir) / "recovered.wav")
    
    print(f"\n{'='*60}")
    print(f"ДЕКОДИРОВАНИЕ: {len(input_paths)} файлов → {output_file}")
    print(f"{'='*60}")
    
    # Если входной файл — директория, ищем в ней
    if len(input_paths) == 1 and Path(input_paths[0]).is_dir():
        import glob
        png_files = sorted(glob.glob(str(Path(input_paths[0]) / "*.png")))
        jpg_files = sorted(glob.glob(str(Path(input_paths[0]) / "*.jpg")))
        jpeg_files = sorted(glob.glob(str(Path(input_paths[0]) / "*.jpeg")))
        input_paths = png_files + jpg_files + jpeg_files
        if not input_paths:
            print(f"❌ В директории не найдены изображения: {args.input[0]}")
            sys.exit(1)
    
    try:
        audio = decode_pages(input_paths, config, output_file)
        
        duration = audio.shape[0] / 44100
        size_mb = Path(output_file).stat().st_size / (1024 * 1024)
        print(f"\n{'='*60}")
        print(f"ГОТОВО!")
        print(f"   Выходной файл: {output_file} ({size_mb:.1f} MB)")
        print(f"   Длительность: {duration:.2f} сек")
        print(f"   Каналов: {audio.shape[1]}")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"\n❌ Ошибка декодирования: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_info(args):
    """Команда info: показывает информацию о пресетах и конфигурации."""
    from config import PAPER_SIZES, PRESETS, DEFAULT_CONFIG
    print(f"\n{'='*60}")
    print(f"ДОСТУПНЫЕ ПРЕСЕТЫ")
    print(f"{'='*60}")
    print(f"{'Название':<20} {'N_FFT':<8} {'HOP_LENGTH':<12} {'Перекрытие'}")
    print(f"{'-'*50}")
    
    for name, preset in PRESETS.items():
        n_fft = preset['N_FFT']
        hop = preset['HOP_LENGTH']
        overlap = (1 - hop / n_fft) * 100
        print(f"{name:<20} {n_fft:<8} {hop:<12} {overlap:.1f}%")
    
    print(f"\n{'='*60}")
    print(f"ТЕКУЩАЯ КОНФИГУРАЦИЯ (DEFAULT_CONFIG)")
    print(f"{'='*60}")
    print(f"   Режимы Griffin-Lim: standard, fast")
    print(f"   Метаданные: отдельная QR-страница")
    print(f"   Ранняя остановка: включена")
    print()
    
    config = DEFAULT_CONFIG.copy()
    for key, value in config.items():
        if not key.startswith('_'):
            print(f"   {key}: {value}")
    
    print(f"\nРазмеры бумаги при {DEFAULT_CONFIG['dpi']} DPI:")
    for name, size in PAPER_SIZES.items():
        from utils import mm_to_pixels
        w = mm_to_pixels(size['width_mm'], DEFAULT_CONFIG['dpi'])
        h = mm_to_pixels(size['height_mm'], DEFAULT_CONFIG['dpi'])
        print(f"   {name}: {size['width_mm']}×{size['height_mm']} мм = {w}×{h} px")


def main():
    parser = argparse.ArgumentParser(
        description='AudioPrint v2: кодирование аудио в изображения для печати и обратно',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python main.py encode --input track.mp3
  python main.py encode --input track.wav --preset 87p_n4096
  python main.py decode --input "data/track_page*of6.png"
  python main.py decode --input data/ --output my_recovered.wav
  python main.py info
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Команды')
    
    # --- Encode ---
    encode_parser = subparsers.add_parser('encode', help='Аудио → страницы A4')
    encode_parser.add_argument('--input', '-i', required=True, 
                               help='Входной аудиофайл (WAV/MP3/FLAC)')
    encode_parser.add_argument('--output', '-o', 
                               help='Базовое имя выходных файлов (без расширения, в папку data/)')
    encode_parser.add_argument('--preset', '-p', 
                               help='Пресет из config.py (по умолчанию 75p_n4096)')
    encode_parser.add_argument('--dpi', type=int, 
                               help='DPI для печати (по умолчанию 300)')
    encode_parser.add_argument('--calibration', type=bool, 
                               help='Добавить калибровочную шкалу (True/False)')
    encode_parser.add_argument('--trim-start', type=float, 
                               help='Начало фрагмента в секундах')
    encode_parser.add_argument('--trim-end', type=float, 
                               help='Конец фрагмента в секундах')
    
    # --- Decode ---
    decode_parser = subparsers.add_parser('decode', help='Скан → аудио')
    decode_parser.add_argument('--input', '-i', nargs='+', required=True, 
                               help='Файлы сканов (можно wildcards: "data/*_page*.png")')
    decode_parser.add_argument('--output', '-o', 
                               help='Выходной WAV файл (в папку data/, по умолчанию recovered.wav)')
    decode_parser.add_argument('--calibration', type=bool, 
                               help='Использовать калибровочную шкалу')
    decode_parser.add_argument('--iterations', type=int, 
                               help='Число итераций Griffin-Lim')
    decode_parser.add_argument('--mode', choices=['standard', 'fast'],
                               help='Режим Griffin-Lim: standard или fast')
    
    # --- Info ---
    info_parser = subparsers.add_parser('info', 
                                        help='Информация о пресетах и конфигурации')
    
    args = parser.parse_args()
    
    if args.command == 'encode':
        cmd_encode(args)
    elif args.command == 'decode':
        cmd_decode(args)
    elif args.command == 'info':
        cmd_info(args)
    else:
        parser.print_help()
        print(f"\nИспользуйте: python main.py [encode|decode|info] --help для справки")


if __name__ == "__main__":
    main()
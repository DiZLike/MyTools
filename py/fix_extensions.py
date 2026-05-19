import os
import magic
import mimetypes
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import logging
from tqdm import tqdm

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fix_extensions.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Маппинг MIME-типов на расширения (только изображения)
MIME_TO_EXT = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
    'image/tiff': '.tiff',
    'image/svg+xml': '.svg',
    'image/x-icon': '.ico',
    'image/heic': '.heic',
    'image/heif': '.heif',
    'image/avif': '.avif',
}

# Альтернативные signal bytes для надежности (если python-magic не справляется)
SIGNATURES = {
    b'\x89PNG\r\n\x1a\n': '.png',
    b'\xff\xd8\xff': '.jpg',
    b'GIF87a': '.gif',
    b'GIF89a': '.gif',
    b'RIFF': '.webp',  # требует доп. проверки
    b'BM': '.bmp',
    b'II*\x00': '.tiff',
    b'MM\x00*': '.tiff',
    b'<?xml': '.svg',
    b'<svg': '.svg',
    b'\x00\x00\x01\x00': '.ico',
}


def detect_format_by_signature(file_path):
    """Определение формата по сигнатурам (заголовкам файла)"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(12)
        
        # Проверяем известные сигнатуры
        for sig, ext in SIGNATURES.items():
            if header.startswith(sig):
                # Специальная проверка для WEBP
                if ext == '.webp' and header[8:12] == b'WEBP':
                    return ext
                elif ext == '.webp':
                    continue  # Не WEBP, пробуем другие сигнатуры
                return ext
        
        # Дополнительные проверки
        if header[6:10] == b'JFIF' or header[6:10] == b'Exif':
            return '.jpg'
        
    except Exception as e:
        logger.debug(f"Signature detection failed for {file_path}: {e}")
    return None


def detect_format_by_magic(file_path):
    """Определение формата через python-magic"""
    try:
        mime = magic.from_file(file_path, mime=True)
        return MIME_TO_EXT.get(mime)
    except Exception as e:
        logger.debug(f"Magic detection failed for {file_path}: {e}")
    return None


def detect_format_by_mimetypes(file_path):
    """Определение формата через встроенный mimetypes"""
    try:
        mime = mimetypes.guess_type(file_path)[0]
        return MIME_TO_EXT.get(mime)
    except Exception:
        return None


def get_real_extension(file_path):
    """Определяет реальный формат файла"""
    # Пробуем несколько методов в порядке надежности
    ext = detect_format_by_signature(file_path)
    if ext:
        return ext
    
    ext = detect_format_by_magic(file_path)
    if ext:
        return ext
    
    ext = detect_format_by_mimetypes(file_path)
    return ext


def process_file(file_path):
    """
    Проверяет и исправляет расширение файла
    Возвращает (old_name, new_name, full_old_path, full_new_path) если было изменение, иначе None
    """
    try:
        path = Path(file_path)
        
        # Пропускаем не-файлы
        if not path.is_file():
            return None
        
        # Текущее расширение
        current_ext = path.suffix.lower()
        
        # Если нет расширения - пропускаем
        if not current_ext:
            return None
        
        # Получаем реальное расширение
        real_ext = get_real_extension(file_path)
        
        # Если не удалось определить или расширение правильное
        if not real_ext or current_ext == real_ext.lower():
            return None
        
        # Формируем новый путь
        new_path = path.with_suffix(real_ext)
        
        # Проверяем, не существует ли уже файл с таким именем
        if new_path.exists():
            logger.warning(f"Target file already exists: {new_path.name}")
            # Добавляем суффикс чтобы избежать конфликта
            counter = 1
            while True:
                new_path = path.with_name(f"{path.stem}_{counter}{real_ext}")
                if not new_path.exists():
                    break
                counter += 1
        
        # Переименовываем файл
        path.rename(new_path)
        
        # Выводим только имена файлов
        logger.info(f"{path.name} -> {new_path.name}")
        
        return (path.name, new_path.name, str(path), str(new_path))
    
    except Exception as e:
        logger.error(f"Error processing {Path(file_path).name}: {e}")
        return None


def scan_and_fix(root_dir, max_workers=8, extensions_to_check=None):
    """
    Рекурсивно сканирует директорию и исправляет расширения изображений
    
    Args:
        root_dir: корневая директория для сканирования
        max_workers: количество потоков (увеличьте для SSD)
        extensions_to_check: список расширений для проверки (None = все изображения)
    """
    # Расширения, которые будем проверять
    if extensions_to_check is None:
        extensions_to_check = {'.png', '.jpg', '.jpeg', '.gif', '.webp', 
                              '.bmp', '.tiff', '.tif', '.svg', '.ico'}
    
    root_path = Path(root_dir)
    if not root_path.exists():
        logger.error(f"Directory not found: {root_dir}")
        return []
    
    # Собираем все файлы для обработки
    print("Collecting files...")
    files_to_process = []
    stats = defaultdict(int)
    
    for file_path in root_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in extensions_to_check:
            files_to_process.append(file_path)
            stats['total_found'] += 1
    
    print(f"Found {stats['total_found']} files to check")
    
    if not files_to_process:
        print("No files to process")
        return []
    
    # Обрабатываем файлы параллельно
    results = []
    print(f"Processing with {max_workers} workers...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_file, f): f for f in files_to_process}
        
        with tqdm(total=len(files_to_process), desc="Processing", unit="files") as pbar:
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        stats['renamed'] += 1
                    else:
                        stats['skipped'] += 1
                except Exception as e:
                    stats['errors'] += 1
                    logger.error(f"Unexpected error: {e}")
                pbar.update(1)
    
    # Выводим статистику
    print()
    print("=" * 50)
    print("SUMMARY:")
    print(f"  Total files checked: {stats['total_found']}")
    print(f"  Files renamed: {stats['renamed']}")
    print(f"  Files skipped (correct extension): {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")
    print("=" * 50)
    
    return results


def preview_changes(root_dir, max_files=10):
    """
    Предварительный просмотр изменений без переименования
    """
    root_path = Path(root_dir)
    files_checked = 0
    changes = []
    
    print(f"\nPreviewing changes in {root_dir}")
    print("-" * 60)
    
    for file_path in root_path.rglob('*'):
        if files_checked >= max_files:
            break
            
        if file_path.is_file():
            ext = file_path.suffix.lower()
            if ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}:
                real_ext = get_real_extension(file_path)
                if real_ext and ext != real_ext.lower():
                    changes.append((file_path.name, file_path.with_suffix(real_ext).name))
                    print(f"  {file_path.name} -> {file_path.with_suffix(real_ext).name}")
                    files_checked += 1
    
    if not changes:
        print("  No changes needed in scanned files")
    else:
        print(f"\n  Found {len(changes)} files to rename (showing first {max_files})")
    
    return changes


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Fix image file extensions based on actual content'
    )
    parser.add_argument('directory', help='Root directory to scan')
    parser.add_argument('--workers', type=int, default=8,
                       help='Number of worker threads (default: 8)')
    parser.add_argument('--preview', action='store_true',
                       help='Preview changes without renaming')
    parser.add_argument('--extensions', nargs='+',
                       help='Specific extensions to check (e.g., .png .jpg)')
    
    args = parser.parse_args()
    
    if args.preview:
        preview_changes(args.directory, max_files=50)
    else:
        # Спрашиваем подтверждение
        print(f"\nThis will scan and fix file extensions in: {args.directory}")
        response = input("Continue? [y/N]: ")
        
        if response.lower() == 'y':
            results = scan_and_fix(
                args.directory,
                max_workers=args.workers,
                extensions_to_check=set(args.extensions) if args.extensions else None
            )
            print(f"\nDone! Renamed {len(results)} files.")
            print("Check fix_extensions.log for details.")
        else:
            print("Aborted.")
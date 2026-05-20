import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import logging
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich import box

try:
    import magic
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False
    print("python-magic не установлен. pip install python-magic")

import mimetypes

console = Console()

# Логирование в файл
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.FileHandler('fix_extensions.log', encoding='utf-8')]
)
logger = logging.getLogger(__name__)

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

SIGNATURES = {
    b'\x89PNG\r\n\x1a\n': '.png',
    b'\xff\xd8\xff': '.jpg',
    b'GIF87a': '.gif',
    b'GIF89a': '.gif',
    b'RIFF': '.webp',
    b'BM': '.bmp',
    b'II*\x00': '.tiff',
    b'MM\x00*': '.tiff',
    b'<?xml': '.svg',
    b'<svg': '.svg',
    b'\x00\x00\x01\x00': '.ico',
}


def detect_format_by_signature(file_path):
    try:
        with open(file_path, 'rb') as f:
            header = f.read(12)
        
        for sig, ext in SIGNATURES.items():
            if header.startswith(sig):
                if ext == '.webp' and header[8:12] == b'WEBP':
                    return ext
                elif ext == '.webp':
                    continue
                return ext
        
        if header[6:10] == b'JFIF' or header[6:10] == b'Exif':
            return '.jpg'
    except Exception:
        pass
    return None


def detect_format_by_magic(file_path):
    if not HAS_MAGIC:
        return None
    try:
        mime = magic.from_file(file_path, mime=True)
        return MIME_TO_EXT.get(mime)
    except Exception:
        return None


def detect_format_by_mimetypes(file_path):
    try:
        mime = mimetypes.guess_type(file_path)[0]
        return MIME_TO_EXT.get(mime)
    except Exception:
        return None


def get_real_extension(file_path):
    ext = detect_format_by_signature(file_path)
    if ext:
        return ext
    ext = detect_format_by_magic(file_path)
    if ext:
        return ext
    return detect_format_by_mimetypes(file_path)


def process_file(file_path):
    """Проверяет и исправляет расширение файла"""
    try:
        path = Path(file_path)
        if not path.is_file():
            return None
        
        current_ext = path.suffix.lower()
        if not current_ext:
            return None
        
        real_ext = get_real_extension(file_path)
        if not real_ext or current_ext == real_ext.lower():
            return None  # Пропускаем, расширение правильное
        
        new_path = path.with_suffix(real_ext)
        
        if new_path.exists():
            counter = 1
            while True:
                new_path = path.with_name(f"{path.stem}_{counter}{real_ext}")
                if not new_path.exists():
                    break
                counter += 1
        
        path.rename(new_path)
        logger.info(f"{path.name} -> {new_path.name}")
        
        return {
            'old': path.name,
            'new': new_path.name,
            'old_ext': current_ext,
            'new_ext': real_ext,
        }
    except Exception as e:
        logger.error(f"Error: {path.name} - {e}")
        return None


def scan_and_fix(root_dir, max_workers=8, extensions_to_check=None):
    """Рекурсивно сканирует директорию и исправляет расширения"""
    if extensions_to_check is None:
        extensions_to_check = {'.png', '.jpg', '.jpeg', '.gif', '.webp', 
                              '.bmp', '.tiff', '.tif', '.svg', '.ico'}
    
    root_path = Path(root_dir)
    if not root_path.exists():
        console.print(f"[red]Директория не найдена: {root_dir}[/red]")
        return []
    
    # Сбор файлов
    console.print("\n[bold yellow]Сбор файлов...[/bold yellow]")
    files_to_process = []
    
    for file_path in root_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in extensions_to_check:
            files_to_process.append(file_path)
    
    total = len(files_to_process)
    console.print(f"Найдено: [bold]{total:,}[/bold] файлов для проверки")
    
    if not total:
        console.print("[dim]Нет файлов для обработки[/dim]")
        return []
    
    # Статистика
    stats = defaultdict(int)
    stats['total'] = total
    
    # Таблица переименованных
    renamed_table = Table(
        title="Переименованные файлы",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold cyan"
    )
    renamed_table.add_column("Было", style="red", max_width=35)
    renamed_table.add_column("Стало", style="green", max_width=35)
    
    # Счётчики по расширениям
    ext_changes = defaultdict(lambda: defaultdict(int))  # {'.jpg': {'.png': 5}}
    
    # Обработка
    console.print(f"\n[bold yellow]Обработка[/bold yellow] (потоков: {max_workers})")
    
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed:,}/{task.total:,}"),
        TextColumn("•"),
        TextColumn("{task.fields[renamed]} переименовано"),
        console=console
    ) as progress:
        
        task = progress.add_task("Проверка", total=total, renamed=0)
        renamed_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_file, f): f for f in files_to_process}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        renamed_count += 1
                        stats['renamed'] += 1
                        ext_changes[result['old_ext']][result['new_ext']] += 1
                        renamed_table.add_row(result['old'], result['new'])
                        progress.update(task, renamed=renamed_count)
                except Exception:
                    stats['errors'] += 1
                progress.advance(task)
    
    # Вывод таблицы переименованных
    if stats['renamed'] > 0:
        console.print(renamed_table)
    
    # Итоговая статистика
    console.print(f"\n[bold green]{'='*60}[/bold green]")
    
    summary = Table(box=box.SIMPLE, show_header=False)
    summary.add_column("Параметр", style="cyan", justify="right")
    summary.add_column("Значение", style="white")
    
    summary.add_row("Проверено файлов", f"{stats['total']:,}")
    summary.add_row("Переименовано", f"[green]{stats['renamed']:,}[/green]")
    summary.add_row("Пропущено (ок)", f"[dim]{stats['total'] - stats['renamed'] - stats['errors']:,}[/dim]")
    if stats['errors'] > 0:
        summary.add_row("Ошибок", f"[red]{stats['errors']:,}[/red]")
    
    console.print(summary)
    
    # Статистика по переходам расширений
    if ext_changes:
        console.print(f"\n[bold cyan]Переходы расширений:[/bold cyan]")
        trans_table = Table(box=box.SIMPLE)
        trans_table.add_column("Было → Стало", style="bold")
        trans_table.add_column("Количество", justify="right")
        
        for old_ext, new_exts in sorted(ext_changes.items()):
            for new_ext, count in sorted(new_exts.items(), key=lambda x: x[1], reverse=True):
                trans_table.add_row(
                    f"[red]{old_ext}[/red] → [green]{new_ext}[/green]",
                    str(count)
                )
        
        console.print(trans_table)
    
    return stats


def preview_changes(root_dir, max_files=50):
    """Предпросмотр без переименования"""
    root_path = Path(root_dir)
    extensions_to_check = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.ico'}
    
    console.print(f"\n[bold cyan]Предпросмотр: {root_dir}[/bold cyan]")
    
    changes = []
    files_checked = 0
    
    for file_path in root_path.rglob('*'):
        if files_checked >= max_files * 3:  # Проверяем больше, показываем max_files
            break
        
        if file_path.is_file() and file_path.suffix.lower() in extensions_to_check:
            real_ext = get_real_extension(file_path)
            current_ext = file_path.suffix.lower()
            
            if real_ext and current_ext != real_ext.lower():
                changes.append((file_path.name, file_path.with_suffix(real_ext).name,
                              current_ext, real_ext))
            
            files_checked += 1
    
    if not changes:
        console.print("  [dim]Изменений не найдено[/dim]")
        return []
    
    preview_table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    preview_table.add_column("Было", style="red", max_width=35)
    preview_table.add_column("Стало", style="green", max_width=35)
    preview_table.add_column("Переход", width=14)
    
    shown = changes[:max_files]
    for old, new, old_ext, new_ext in shown:
        preview_table.add_row(old, new, f"[red]{old_ext}[/red] → [green]{new_ext}[/green]")
    
    console.print(preview_table)
    
    if len(changes) > max_files:
        console.print(f"  [dim]... и ещё {len(changes) - max_files} файлов[/dim]")
    
    console.print(f"\nВсего изменений: [bold]{len(changes)}[/bold]")
    
    return changes


if __name__ == "__main__":
    import argparse
    
    console.print(Panel.fit(
        "[bold blue]FIX IMAGE EXTENSIONS[/bold blue]\n"
        "[dim]Исправление расширений по реальному содержимому[/dim]",
        border_style="blue"
    ))
    
    parser = argparse.ArgumentParser(description='Fix image file extensions based on actual content')
    parser.add_argument('directory', nargs='?', default='.', help='Root directory to scan')
    parser.add_argument('--workers', type=int, default=8, help='Number of worker threads (default: 8)')
    parser.add_argument('--preview', action='store_true', help='Preview changes without renaming')
    
    args = parser.parse_args()
    
    if args.preview:
        preview_changes(args.directory, max_files=50)
    else:
        console.print(f"\nБудет просканирована директория: [bold]{os.path.abspath(args.directory)}[/bold]")
        
        # Автоматически запускаем без подтверждения
        stats = scan_and_fix(args.directory, max_workers=args.workers)
        
        if isinstance(stats, dict):
            console.print(f"\n[bold green]Готово![/bold green] Переименовано: {stats.get('renamed', 0):,} файлов")
            console.print("[dim]Подробности в fix_extensions.log[/dim]")
        else:
            console.print(f"\n[bold green]Готово![/bold green]")
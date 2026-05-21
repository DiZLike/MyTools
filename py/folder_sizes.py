import os
import sys
from pathlib import Path
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint


def get_size(path: Path) -> int:
    """Рекурсивно вычисляет размер папки/файла в байтах"""
    if path.is_file():
        return path.stat().st_size
    
    total_size = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total_size += entry.stat().st_size
                elif entry.is_dir(follow_symlinks=False):
                    total_size += get_size(Path(entry.path))
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        return 0
    
    return total_size


def format_size(size_bytes: int) -> str:
    """Форматирует размер в читаемый вид"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


def get_folder_sizes(directory: Path) -> List[Tuple[str, int]]:
    """Получает размеры всех папок в указанной директории"""
    folders = []
    
    # Собираем все папки
    try:
        for entry in os.scandir(directory):
            if entry.is_dir(follow_symlinks=False):
                folders.append(Path(entry.path))
    except (PermissionError, OSError) as e:
        rprint(f"[red]Ошибка доступа к {directory}: {e}[/red]")
        return []
    
    if not folders:
        return []
    
    folder_sizes = []
    
    # Используем ThreadPoolExecutor для параллельного вычисления размеров
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=Console()
    ) as progress:
        
        task = progress.add_task(
            f"[cyan]Вычисление размеров папок в {directory.name}...", 
            total=len(folders)
        )
        
        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            future_to_folder = {
                executor.submit(get_size, folder): folder 
                for folder in folders
            }
            
            for future in as_completed(future_to_folder):
                folder = future_to_folder[future]
                try:
                    size = future.result()
                    folder_sizes.append((folder.name, size))
                except Exception as e:
                    rprint(f"[red]Ошибка при обработке {folder.name}: {e}[/red]")
                    folder_sizes.append((folder.name, 0))
                
                progress.update(task, advance=1)
    
    # Сортируем по размеру (по убыванию)
    folder_sizes.sort(key=lambda x: x[1], reverse=True)
    
    return folder_sizes


def display_folder_sizes(directory: str):
    """Отображает размеры папок в виде таблицы"""
    console = Console()
    target_path = Path(directory).resolve()
    
    # Проверяем, существует ли путь
    if not target_path.exists():
        rprint(f"[red]Ошибка: Путь '{directory}' не существует![/red]")
        return
    
    # Проверяем, является ли путь директорией
    if not target_path.is_dir():
        rprint(f"[red]Ошибка: '{directory}' не является директорией![/red]")
        return
    
    # Заголовок
    title = Text(f"Размеры папок в: {target_path}", style="bold blue")
    console.print(Panel(title, border_style="blue"))
    
    # Получаем размеры папок
    folder_sizes = get_folder_sizes(target_path)
    
    if not folder_sizes:
        rprint("[yellow]В этой директории нет подпапок.[/yellow]")
        return
    
    # Создаем таблицу
    table = Table(show_header=True, header_style="bold magenta", show_lines=True)
    table.add_column("№", style="dim", width=4, justify="right")
    table.add_column("Название папки", style="cyan", no_wrap=False)
    table.add_column("Размер", justify="right", style="green")
    table.add_column("% от общего", justify="right", style="yellow")
    
    # Вычисляем общий размер
    total_size = sum(size for _, size in folder_sizes)
    
    # Заполняем таблицу
    for i, (name, size) in enumerate(folder_sizes, 1):
        percentage = (size / total_size * 100) if total_size > 0 else 0
        table.add_row(
            str(i),
            name,
            format_size(size),
            f"{percentage:.1f}%"
        )
    
    # Добавляем итоговую строку
    table.add_row(
        "",
        Text("ОБЩИЙ РАЗМЕР", style="bold"),
        Text(format_size(total_size), style="bold green"),
        Text("100%", style="bold yellow")
    )
    
    console.print(table)
    
    # Дополнительная информация
    info_text = Text()
    info_text.append(f"\nВсего папок: ", style="dim")
    info_text.append(str(len(folder_sizes)), style="bold cyan")
    info_text.append(f" | Общий размер: ", style="dim")
    info_text.append(format_size(total_size), style="bold green")
    
    console.print(info_text)


def main():
    """Главная функция"""
    console = Console()
    
    # Получаем путь из аргументов командной строки или запрашиваем у пользователя
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        console.print("[yellow]Введите путь к директории:[/yellow] ", end="")
        directory = input().strip()
        
        # Удаляем кавычки, если они есть
        directory = directory.strip('"\'')
    
    # Запускаем отображение
    display_folder_sizes(directory)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        rprint("\n[yellow]Программа прервана пользователем.[/yellow]")
        sys.exit(0)
    except Exception as e:
        rprint(f"[red]Неожиданная ошибка: {e}[/red]")
        sys.exit(1)
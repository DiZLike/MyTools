#!/usr/bin/env python3
"""
Верификатор архива иконок
Проверяет:
  1. Целостность архива (все записи читаются без ошибок)
  2. Соответствие размеров (оригинальный vs распакованный)
  3. Корректность данных (выборочная проверка содержимого)
  4. Статистика по типам файлов и методам сжатия
"""

import os
import zlib
import struct
import random
from collections import defaultdict
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn
from rich.panel import Panel
from rich.tree import Tree
from rich import box

try:
    import brotli
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False

console = Console()

# Константы
COMPRESSION_NONE = 0
COMPRESSION_ZLIB = 1
COMPRESSION_BROTLI = 2
COMPRESSION_SHARED_BROTLI = 3
COMPRESSION_SHARED_ZLIB = 4

METHOD_NAMES = {
    0: "store",
    1: "zlib",
    2: "brotli",
    3: "shared+brotli",
    4: "shared+zlib",
}

METHOD_STYLES = {
    0: "dim",
    1: "yellow",
    2: "green",
    3: "cyan",
    4: "blue",
}


class ArchiveVerifier:
    """Верификатор архива иконок (без сравнения с исходниками)"""
    
    MAGIC = b'ICN4'
    
    def __init__(self, dat_file, deep_check_count=0):
        """
        Args:
            dat_file: путь к файлу архива
            deep_check_count: сколько файлов проверить глубоко (0 = все, -1 = ни одного)
        """
        self.dat_file = dat_file
        self.deep_check_count = deep_check_count
        self.shared_prefix = b''
        self.entries = []
        self.errors = []
        self.warnings = []
        
        # Статистика
        self.total_files = 0
        self.total_original_size = 0
        self.total_compressed_size = 0
        self.files_by_method = defaultdict(int)
        self.files_by_ext = defaultdict(lambda: {'count': 0, 'original': 0, 'compressed': 0})
        self.checks_passed = 0
        self.checks_failed = 0
    
    def _get_ext(self, path):
        return os.path.splitext(path)[1].lower()
    
    def verify(self):
        """Полная проверка архива"""
        console.print(Panel.fit(
            "[bold blue]🔍 Archive Integrity Check[/bold blue]",
            border_style="blue"
        ))
        console.print(f"  Файл: [bold]{self.dat_file}[/bold]")
        
        if not os.path.exists(self.dat_file):
            console.print(f"\n[red]✗ ОШИБКА:[/red] Файл не найден")
            return False
        
        file_size = os.path.getsize(self.dat_file)
        console.print(f"  Размер: {file_size:,} байт ({file_size/1024/1024:.1f} МБ)")
        
        # Шаг 1: Чтение заголовка и оглавления
        if not self._read_toc():
            return False
        
        # Шаг 2: Проверка записей
        if not self._verify_entries():
            return False
        
        # Шаг 3: Глубокая проверка (если запрошена)
        if self.deep_check_count != -1:
            self._deep_verify()
        
        # Шаг 4: Итоговый отчёт
        self._print_summary()
        
        return len(self.errors) == 0
    
    def _read_toc(self):
        """Чтение TOC (Table of Contents)"""
        console.print(f"\n[bold yellow]📋 Чтение оглавления...[/bold yellow]")
        
        try:
            with open(self.dat_file, 'rb') as f:
                # Сигнатура
                magic = f.read(4)
                if magic != self.MAGIC:
                    self.errors.append(f"Неверная сигнатура: {magic!r}")
                    return False
                
                # Заголовок
                count = struct.unpack('<I', f.read(4))[0]
                data_start = struct.unpack('<Q', f.read(8))[0]
                prefix_len = struct.unpack('<H', f.read(2))[0]
                
                if prefix_len > 0:
                    self.shared_prefix = f.read(prefix_len)
                
                console.print(f"  Записей в архиве: [bold]{count:,}[/bold]")
                console.print(f"  Смещение данных: [dim]{data_start}[/dim]")
                console.print(f"  Shared префикс: [dim]{prefix_len} байт[/dim]")
                
                # Проверка базовой целостности
                if data_start > os.path.getsize(self.dat_file):
                    self.errors.append(f"Смещение данных ({data_start}) за пределами файла")
                    return False
                
                if data_start < 4 + 4 + 8 + 2 + prefix_len:
                    self.errors.append(f"Некорректное смещение данных: {data_start}")
                    return False
                
                # Чтение записей TOC
                entries_read = 0
                for i in range(count):
                    if f.tell() >= data_start:
                        self.errors.append(f"TOC выходит за границу данных (запись {i+1})")
                        break
                    
                    path_len = struct.unpack('<H', f.read(2))[0]
                    path = f.read(path_len).decode('utf-8', errors='replace')
                    offset = struct.unpack('<Q', f.read(8))[0]
                    size_comp = struct.unpack('<I', f.read(4))[0]
                    size_orig = struct.unpack('<I', f.read(4))[0]
                    compression = struct.unpack('<B', f.read(1))[0]
                    
                    # Валидация полей
                    if compression not in METHOD_NAMES:
                        self.errors.append(f"Неизвестный метод сжатия {compression} для {path}")
                    
                    if offset < data_start:
                        self.errors.append(f"Смещение {offset} < data_start для {path}")
                    
                    if offset + size_comp > os.path.getsize(self.dat_file):
                        self.errors.append(f"Данные {path} выходят за границы файла")
                    
                    if compression != COMPRESSION_NONE and size_orig == 0:
                        self.warnings.append(f"size_original=0 при сжатии для {path}")
                    
                    if compression == COMPRESSION_NONE and size_orig != 0:
                        self.warnings.append(f"size_original={size_orig} при store для {path}")
                    
                    self.entries.append({
                        'path': path,
                        'offset': offset,
                        'size_compressed': size_comp,
                        'size_original': size_orig,
                        'compression': compression,
                    })
                    entries_read += 1
                
                if entries_read != count:
                    self.errors.append(f"Прочитано {entries_read} записей из {count}")
                
                self.total_files = entries_read
                
                # Проверка на перекрытие данных
                sorted_entries = sorted(self.entries, key=lambda e: e['offset'])
                for i in range(len(sorted_entries) - 1):
                    e1 = sorted_entries[i]
                    e2 = sorted_entries[i + 1]
                    end1 = e1['offset'] + e1['size_compressed']
                    if end1 > e2['offset']:
                        self.errors.append(
                            f"Перекрытие данных: {e1['path']} (конец={end1}) и {e2['path']} (начало={e2['offset']})"
                        )
                
                console.print(f"  [green]✓ TOC прочитан успешно[/green]")
                return True
                
        except struct.error as e:
            self.errors.append(f"Ошибка структуры: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Ошибка чтения: {e}")
            return False
    
    def _verify_entries(self):
        """Базовая проверка всех записей (размеры, доступность)"""
        console.print(f"\n[bold yellow]📦 Проверка записей...[/bold yellow]")
        
        if not self.entries:
            self.errors.append("Нет записей для проверки")
            return False
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed:,}/{task.total:,}"),
            console=console
        ) as progress:
            task = progress.add_task("Проверка", total=len(self.entries))
            
            with open(self.dat_file, 'rb') as f:
                for entry in self.entries:
                    # Проверяем что данные читаются
                    try:
                        f.seek(entry['offset'])
                        data = f.read(entry['size_compressed'])
                        
                        if len(data) != entry['size_compressed']:
                            self.errors.append(
                                f"Неполные данные: {entry['path']} "
                                f"(прочитано {len(data)} из {entry['size_compressed']})"
                            )
                        
                        # Считаем статистику
                        self.total_compressed_size += entry['size_compressed']
                        self.total_original_size += entry['size_original'] if entry['size_original'] > 0 else entry['size_compressed']
                        
                        method = entry['compression']
                        self.files_by_method[method] += 1
                        
                        ext = self._get_ext(entry['path'])
                        self.files_by_ext[ext]['count'] += 1
                        self.files_by_ext[ext]['compressed'] += entry['size_compressed']
                        self.files_by_ext[ext]['original'] += (
                            entry['size_original'] if entry['size_original'] > 0 
                            else entry['size_compressed']
                        )
                        
                    except Exception as e:
                        self.errors.append(f"Ошибка чтения {entry['path']}: {e}")
                    
                    progress.advance(task)
        
        if not self.errors:
            console.print(f"  [green]✓ Все записи доступны[/green]")
        return True
    
    def _decompress_data(self, data, method):
        """Распаковка данных"""
        if method == COMPRESSION_NONE:
            return data
        elif method == COMPRESSION_ZLIB:
            return zlib.decompress(data)
        elif method == COMPRESSION_BROTLI:
            if not HAS_BROTLI:
                raise RuntimeError("brotli не установлен")
            return brotli.decompress(data)
        elif method == COMPRESSION_SHARED_BROTLI:
            if not HAS_BROTLI:
                raise RuntimeError("brotli не установлен")
            return self.shared_prefix + brotli.decompress(data)
        elif method == COMPRESSION_SHARED_ZLIB:
            return self.shared_prefix + zlib.decompress(data)
        else:
            raise ValueError(f"Неизвестный метод: {method}")
    
    def _check_content_validity(self, data, path):
        """Эвристическая проверка валидности содержимого"""
        ext = self._get_ext(path)
        
        # SVG — должен содержать <svg
        if ext == '.svg':
            if b'<svg' not in data.lower() and b'<svg' not in data:
                return False, "SVG не содержит тег <svg>"
            return True, None
        
        # PNG — проверка сигнатуры
        if ext == '.png':
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                return False, "Неверная сигнатура PNG"
            # Проверка IEND
            if not data.endswith(b'IEND\xaeB`\x82'):
                return False, "PNG не завершается IEND"
            return True, None
        
        # JPEG
        if ext in ('.jpg', '.jpeg'):
            if not data.startswith(b'\xff\xd8\xff'):
                return False, "Неверная сигнатура JPEG"
            if not data.endswith(b'\xff\xd9'):
                return False, "JPEG не завершается маркером"
            return True, None
        
        # GIF
        if ext == '.gif':
            if not (data.startswith(b'GIF87a') or data.startswith(b'GIF89a')):
                return False, "Неверная сигнатура GIF"
            return True, None
        
        # ICO
        if ext == '.ico':
            if not data.startswith(b'\x00\x00\x01\x00'):
                return False, "Неверная сигнатура ICO"
            return True, None
        
        # WebP
        if ext == '.webp':
            if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
                return False, "Неверная сигнатура WebP"
            return True, None
        
        # JSON
        if ext == '.json':
            try:
                import json
                json.loads(data)
            except:
                return False, "Некорректный JSON"
            return True, None
        
        # Неизвестный формат — проверяем что не пустой
        if len(data) == 0:
            return False, "Пустой файл"
        
        return True, None
    
    def _deep_verify(self):
        """Глубокая проверка: распаковка и анализ содержимого"""
        
        entries_to_check = self.entries
        if self.deep_check_count > 0 and self.deep_check_count < len(self.entries):
            entries_to_check = random.sample(self.entries, self.deep_check_count)
        
        count = len(entries_to_check)
        total = len(self.entries)
        
        if self.deep_check_count > 0:
            console.print(f"\n[bold yellow]🔬 Глубокая проверка[/bold yellow] ([cyan]{count}[/cyan] из [dim]{total}[/dim] файлов)")
        else:
            console.print(f"\n[bold yellow]🔬 Глубокая проверка всех файлов[/bold yellow]")
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed:,}/{task.total:,}"),
            console=console
        ) as progress:
            task = progress.add_task("Распаковка и проверка", total=count)
            
            with open(self.dat_file, 'rb') as f:
                for entry in entries_to_check:
                    try:
                        # Читаем сжатые данные
                        f.seek(entry['offset'])
                        compressed = f.read(entry['size_compressed'])
                        
                        # Распаковываем
                        decompressed = self._decompress_data(compressed, entry['compression'])
                        
                        # Проверяем размер
                        if entry['compression'] != COMPRESSION_NONE:
                            if entry['size_original'] > 0 and len(decompressed) != entry['size_original']:
                                self.errors.append(
                                    f"Несовпадение размера: {entry['path']} "
                                    f"(ожидалось {entry['size_original']}, получено {len(decompressed)})"
                                )
                                self.checks_failed += 1
                                progress.advance(task)
                                continue
                        
                        # Проверяем содержимое
                        valid, error_msg = self._check_content_validity(decompressed, entry['path'])
                        if not valid:
                            self.warnings.append(f"Подозрительное содержимое {entry['path']}: {error_msg}")
                            self.checks_failed += 1
                        else:
                            self.checks_passed += 1
                            
                    except zlib.error as e:
                        self.errors.append(f"Ошибка zlib {entry['path']}: {e}")
                        self.checks_failed += 1
                    except Exception as e:
                        if HAS_BROTLI or 'brotli' not in str(e).lower():
                            self.errors.append(f"Ошибка распаковки {entry['path']}: {e}")
                        else:
                            self.warnings.append(f"Пропущен {entry['path']} (brotli не установлен)")
                        self.checks_failed += 1
                    
                    progress.advance(task)
        
        if not self.errors:
            console.print(f"  [green]✓ Глубокая проверка пройдена[/green]")
    
    def _print_summary(self):
        """Вывод итоговой статистики"""
        console.print(f"\n[bold cyan]{'═'*60}[/bold cyan]")
        console.print(f"[bold cyan]📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ[/bold cyan]")
        console.print(f"[bold cyan]{'═'*60}[/bold cyan]\n")
        
        # Дерево результатов
        tree = Tree(f"[bold]Архив: {os.path.basename(self.dat_file)}[/bold]")
        
        # Ошибки
        if self.errors:
            err_node = tree.add(f"[red]✗ Ошибок: {len(self.errors)}[/red]")
            for err in self.errors[:10]:
                err_node.add(f"[red]• {err}[/red]")
            if len(self.errors) > 10:
                err_node.add(f"[dim]... и ещё {len(self.errors) - 10}[/dim]")
        else:
            tree.add("[green]✓ Ошибок нет[/green]")
        
        # Предупреждения
        if self.warnings:
            warn_node = tree.add(f"[yellow]⚠ Предупреждений: {len(self.warnings)}[/yellow]")
            for warn in self.warnings[:5]:
                warn_node.add(f"[yellow]• {warn}[/yellow]")
            if len(self.warnings) > 5:
                warn_node.add(f"[dim]... и ещё {len(self.warnings) - 5}[/dim]")
        
        # Статистика распаковки
        if self.checks_passed + self.checks_failed > 0:
            check_node = tree.add(f"🔬 Глубокая проверка")
            check_node.add(f"[green]✓ Успешно: {self.checks_passed:,}[/green]")
            if self.checks_failed > 0:
                check_node.add(f"[red]✗ С ошибками: {self.checks_failed:,}[/red]")
        
        console.print(tree)
        
        # Таблица методов сжатия
        if self.files_by_method:
            method_table = Table(title="Методы сжатия", box=box.SIMPLE)
            method_table.add_column("Метод", style="cyan")
            method_table.add_column("Файлов", justify="right")
            method_table.add_column("%", justify="right")
            
            for method_id in sorted(self.files_by_method.keys()):
                count = self.files_by_method[method_id]
                pct = count / self.total_files * 100 if self.total_files else 0
                style = METHOD_STYLES.get(method_id, "white")
                method_table.add_row(
                    f"[{style}]{METHOD_NAMES[method_id]}[/{style}]",
                    f"{count:,}",
                    f"{pct:.1f}%"
                )
            
            console.print(method_table)
        
        # Таблица расширений
        if self.files_by_ext:
            ext_table = Table(title="Типы файлов", box=box.SIMPLE)
            ext_table.add_column("Расширение", style="cyan")
            ext_table.add_column("Файлов", justify="right")
            ext_table.add_column("Исходный", justify="right")
            ext_table.add_column("Сжатый", justify="right")
            ext_table.add_column("Экономия", justify="right")
            
            sorted_exts = sorted(self.files_by_ext.items(), 
                                key=lambda x: x[1]['original'], reverse=True)
            
            for ext, stats in sorted_exts[:15]:
                if stats['original'] > 0:
                    ratio = (1 - stats['compressed'] / stats['original']) * 100
                    ratio_str = f"[green]{ratio:.1f}%[/green]" if ratio > 0 else "[dim]0%[/dim]"
                else:
                    ratio_str = "[dim]-[/dim]"
                
                ext_table.add_row(
                    ext if ext else "(нет)",
                    str(stats['count']),
                    f"{stats['original']/1024:.1f} KB",
                    f"{stats['compressed']/1024:.1f} KB",
                    ratio_str
                )
            
            console.print(ext_table)
        
        # Общая статистика
        total_table = Table(box=box.ROUNDED, title="Общая статистика", title_style="bold")
        total_table.add_column("Параметр", style="cyan", justify="right")
        total_table.add_column("Значение", style="white")
        
        total_table.add_row("Всего файлов", f"{self.total_files:,}")
        total_table.add_row("Исходный размер", f"{self.total_original_size/1024/1024:.1f} МБ")
        total_table.add_row("Сжатый размер", f"{self.total_compressed_size/1024/1024:.1f} МБ")
        
        if self.total_original_size > 0:
            ratio = (1 - self.total_compressed_size / self.total_original_size) * 100
            total_table.add_row("Общая экономия", f"[bold green]{ratio:.1f}%[/bold green]")
        
        archive_size = os.path.getsize(self.dat_file)
        overhead = archive_size - self.total_compressed_size
        total_table.add_row("Размер архива", f"{archive_size/1024/1024:.1f} МБ")
        total_table.add_row("Служебные данные", f"{overhead/1024:.0f} байт ({overhead/archive_size*100:.1f}%)")
        
        console.print(total_table)
        
        # Итоговый вердикт
        if not self.errors:
            console.print(f"\n[bold green]✅ АРХИВ КОРРЕКТЕН[/bold green]\n")
        else:
            console.print(f"\n[bold red]❌ НАЙДЕНЫ ОШИБКИ ({len(self.errors)})[/bold red]\n")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Верификатор архива иконок",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s icons.dat                    # Базовая проверка структуры
  %(prog)s icons.dat --deep 50          # + глубокая проверка 50 случайных файлов
  %(prog)s icons.dat --deep 0           # Глубокая проверка ВСЕХ файлов
  %(prog)s icons.dat --no-deep          # Только структура (быстро)
        """
    )
    
    parser.add_argument('archive', help='Путь к файлу архива (.dat)')
    parser.add_argument(
        '--deep', '-d',
        type=int,
        default=10,
        help='Количество файлов для глубокой проверки (0=все, по умолчанию 10)'
    )
    parser.add_argument(
        '--no-deep', '-n',
        action='store_true',
        help='Отключить глубокую проверку'
    )
    
    args = parser.parse_args()
    
    deep_count = -1 if args.no_deep else args.deep
    
    verifier = ArchiveVerifier(args.archive, deep_check_count=deep_count)
    success = verifier.verify()
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
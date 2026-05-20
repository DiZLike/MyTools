#!/usr/bin/env python3
"""
Независимая проверка целостности архива icons.dat
Не требует импорта bin_packer
"""

import os
import sys
import struct
import zlib
import random
from collections import defaultdict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, FileSizeColumn
from rich.box import ROUNDED

try:
    import brotli
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False

console = Console()

MAGIC = b'ICN4'

COMPRESSION_NONE = 0
COMPRESSION_ZLIB = 1
COMPRESSION_BROTLI = 2
COMPRESSION_SHARED_BROTLI = 3
COMPRESSION_SHARED_ZLIB = 4

METHOD_NAMES = {
    COMPRESSION_NONE: "store",
    COMPRESSION_ZLIB: "zlib",
    COMPRESSION_BROTLI: "brotli",
    COMPRESSION_SHARED_BROTLI: "shared+brotli",
    COMPRESSION_SHARED_ZLIB: "shared+zlib",
}


def read_toc(archive_path):
    """Читает заголовок и TOC архива"""
    with open(archive_path, 'rb') as f:
        # Заголовок
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError(f"Неверный MAGIC: {magic!r}, ожидался {MAGIC!r}")

        count = struct.unpack('<I', f.read(4))[0]
        data_start = struct.unpack('<Q', f.read(8))[0]
        prefix_len = struct.unpack('<H', f.read(2))[0]
        prefix = f.read(prefix_len) if prefix_len > 0 else b''

        # TOC
        entries = {}
        for _ in range(count):
            path_len = struct.unpack('<H', f.read(2))[0]
            path = f.read(path_len).decode('utf-8')
            offset = struct.unpack('<Q', f.read(8))[0]
            size_compressed = struct.unpack('<I', f.read(4))[0]
            size_original = struct.unpack('<I', f.read(4))[0]
            compression = struct.unpack('<B', f.read(1))[0]

            entries[path] = {
                'offset': offset,
                'size_compressed': size_compressed,
                'size_original': size_original,
                'compression': compression,
            }

    return entries, prefix


def decompress_entry(archive_path, entry, prefix):
    """Распаковывает одну запись"""
    with open(archive_path, 'rb') as f:
        f.seek(entry['offset'])
        compressed = f.read(entry['size_compressed'])

    method = entry['compression']

    if method == COMPRESSION_ZLIB:
        return zlib.decompress(compressed)
    elif method == COMPRESSION_BROTLI:
        if not HAS_BROTLI:
            raise RuntimeError("brotli не установлен")
        return brotli.decompress(compressed)
    elif method == COMPRESSION_SHARED_BROTLI:
        if not HAS_BROTLI:
            raise RuntimeError("brotli не установлен")
        return prefix + brotli.decompress(compressed)
    elif method == COMPRESSION_SHARED_ZLIB:
        return prefix + zlib.decompress(compressed)
    else:
        return compressed


def verify_archive(archive_path='icons.dat', sample_count=10):
    console.print(Panel.fit(
        "[bold blue]ПРОВЕРКА АРХИВА[/bold blue]\n"
        f"[dim]{archive_path}[/dim]",
        border_style="blue"
    ))

    if not os.path.exists(archive_path):
        console.print(f"[red]✗ Архив не найден[/red]")
        return False

    file_size = os.path.getsize(archive_path)
    console.print(f"Размер архива: [bold]{file_size / (1024**3):.2f} ГБ[/bold] "
                  f"({file_size:,} байт)")

    # ===== Чтение TOC =====
    console.print("\n[bold cyan]ЧТЕНИЕ СТРУКТУРЫ[/bold cyan]")

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        FileSizeColumn(),
        TextColumn("• {task.percentage:.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Чтение TOC", total=file_size)

        try:
            entries, prefix = read_toc(archive_path)
        except Exception as e:
            console.print(f"[red]✗ Ошибка чтения: {e}[/red]")
            return False

        progress.update(task, completed=file_size)

    total = len(entries)
    console.print(f"  Файлов в архиве: [bold]{total:,}[/bold]")
    console.print(f"  Префикс: [bold]{len(prefix)} байт[/bold]")

    # ===== Статистика =====
    console.print("\n[bold cyan]СТАТИСТИКА СЖАТИЯ[/bold cyan]")

    ext_stats = defaultdict(lambda: {
        'count': 0, 'original': 0, 'compressed': 0,
        'brotli': 0, 'zlib': 0, 'shared': 0, 'store': 0
    })

    for path, entry in entries.items():
        ext = os.path.splitext(path)[1].lower() or '(нет)'
        comp_size = entry['size_compressed']
        orig_size = entry['size_original'] if entry['compression'] != COMPRESSION_NONE else comp_size
        method = entry['compression']

        ext_stats[ext]['count'] += 1
        ext_stats[ext]['original'] += orig_size
        ext_stats[ext]['compressed'] += comp_size

        if method == COMPRESSION_BROTLI:
            ext_stats[ext]['brotli'] += 1
        elif method == COMPRESSION_ZLIB:
            ext_stats[ext]['zlib'] += 1
        elif method in (COMPRESSION_SHARED_BROTLI, COMPRESSION_SHARED_ZLIB):
            ext_stats[ext]['shared'] += 1
        else:
            ext_stats[ext]['store'] += 1

    table = Table(title="Сжатие по типам файлов", box=ROUNDED)
    table.add_column("Расширение", style="cyan", width=10)
    table.add_column("Файлов", justify="right", width=8)
    table.add_column("Brotli", justify="right", width=8)
    table.add_column("Zlib", justify="right", width=8)
    table.add_column("Shared", justify="right", width=8)
    table.add_column("Store", justify="right", width=8)
    table.add_column("Исходный", justify="right", width=12)
    table.add_column("Сжатый", justify="right", width=12)
    table.add_column("Экономия", justify="right", width=10)

    sorted_exts = sorted(ext_stats.items(), key=lambda x: x[1]['original'], reverse=True)

    for ext, stats in sorted_exts:
        if stats['original'] > 0:
            ratio = (1 - stats['compressed'] / stats['original']) * 100
            ratio_str = f"[green]{ratio:.1f}%[/green]" if ratio > 0 else f"[dim]{ratio:.1f}%[/dim]"
        else:
            ratio_str = "[dim]-[/dim]"

        table.add_row(
            ext,
            str(stats['count']),
            str(stats['brotli']) if stats['brotli'] > 0 else "-",
            str(stats['zlib']) if stats['zlib'] > 0 else "-",
            str(stats['shared']) if stats['shared'] > 0 else "-",
            str(stats['store']) if stats['store'] > 0 else "-",
            f"{stats['original'] / 1024:.1f} KB",
            f"{stats['compressed'] / 1024:.1f} KB",
            ratio_str
        )

    total_original = sum(s['original'] for s in ext_stats.values())
    total_compressed = sum(s['compressed'] for s in ext_stats.values())
    total_brotli = sum(s['brotli'] for s in ext_stats.values())
    total_zlib = sum(s['zlib'] for s in ext_stats.values())
    total_shared = sum(s['shared'] for s in ext_stats.values())
    total_store = sum(s['store'] for s in ext_stats.values())

    if total_original > 0:
        total_ratio = (1 - total_compressed / total_original) * 100
        total_ratio_str = f"[bold green]{total_ratio:.1f}%[/bold green]" if total_ratio > 0 else f"[dim]{total_ratio:.1f}%[/dim]"
    else:
        total_ratio_str = "[dim]-[/dim]"

    table.add_section()
    table.add_row(
        "[bold]ИТОГО[/bold]",
        f"[bold]{total}[/bold]",
        f"[bold]{total_brotli}[/bold]" if total_brotli > 0 else "-",
        f"[bold]{total_zlib}[/bold]" if total_zlib > 0 else "-",
        f"[bold]{total_shared}[/bold]" if total_shared > 0 else "-",
        f"[bold]{total_store}[/bold]",
        f"[bold]{total_original / 1024:.1f} KB[/bold]",
        f"[bold]{total_compressed / 1024:.1f} KB[/bold]",
        total_ratio_str
    )

    console.print(table)

    # ===== Выборочная проверка =====
    console.print(f"\n[bold cyan]ВЫБОРОЧНАЯ РАСПАКОВКА[/bold cyan] "
                  f"({min(sample_count, total)} из {total:,})")

    all_paths = list(entries.keys())
    sample = random.sample(all_paths, min(sample_count, total))

    errors = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console
    ) as progress:
        task = progress.add_task("Проверка", total=len(sample))

        for path in sample:
            entry = entries[path]
            try:
                data = decompress_entry(archive_path, entry, prefix)
                expected = entry['size_original'] if entry['compression'] != COMPRESSION_NONE else entry['size_compressed']
                if len(data) != expected:
                    errors.append(f"{path}: размер {len(data)} ≠ {expected}")
            except Exception as e:
                errors.append(f"{path}: {e}")

            progress.update(task, advance=1)

    ok = len(sample) - len(errors)
    result_table = Table(box=ROUNDED)
    result_table.add_column("Успешно", justify="right", style="green")
    result_table.add_column("Ошибок", justify="right", style="red")
    result_table.add_row(str(ok), str(len(errors)))
    console.print(result_table)

    if errors:
        console.print("\n[red]Ошибки:[/red]")
        for e in errors:
            console.print(f"  [red]•[/red] {e}")
    else:
        console.print("\n[green]✓ Все проверенные файлы в порядке[/green]")

    # ===== Итоги =====
    console.print(f"\n[bold]Итого:[/bold]")
    console.print(f"  Файлов в архиве: {total:,}")
    console.print(f"  Исходный размер: {total_original / (1024**2):.1f} МБ")
    console.print(f"  Размер архива:  {file_size / (1024**2):.1f} МБ")
    console.print(f"  Экономия:       {total_ratio_str}")

    return len(errors) == 0


if __name__ == '__main__':
    ok = verify_archive('icons.dat', sample_count=10)
    sys.exit(0 if ok else 1)
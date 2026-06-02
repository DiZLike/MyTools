import os
import struct
import zlib
import random
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, FileSizeColumn
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.box import SIMPLE, ROUNDED

try:
    import brotli
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False

console = Console()

# Методы сжатия
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

SVG_CLEANUPS = [
    (re.compile(rb'<!--.*?-->', re.DOTALL), b''),
    (re.compile(rb'>\s+<'), b'><'),
    (re.compile(rb'^\s+|\s+$'), b''),
    (re.compile(rb'\n\s*\n'), b'\n'),
]


def _find_common_prefix(data_list):
    if not data_list or len(data_list) < 2:
        return b''
    prefix = data_list[0]
    for data in data_list[1:]:
        min_len = min(len(prefix), len(data))
        i = 0
        while i < min_len and prefix[i] == data[i]:
            i += 1
        prefix = prefix[:i]
        if not prefix:
            break
    return prefix


def _optimize_svg(raw):
    for pattern, replacement in SVG_CLEANUPS:
        raw = pattern.sub(replacement, raw)
    return raw


def _compress_body(raw, shared_prefix):
    """
    Сжимает тело файла (после возможного вырезания префикса).
    Возвращает (compressed, method).
    method: COMPRESSION_SHARED_* если префикс был, COMPRESSION_* если нет.
    """
    has_prefix = False
    body = raw
    
    if shared_prefix and raw.startswith(shared_prefix):
        body = raw[len(shared_prefix):]
        has_prefix = True
    
    # Brotli
    if HAS_BROTLI:
        try:
            compressed = brotli.compress(body, quality=11)
            if len(compressed) < len(body):
                method = COMPRESSION_SHARED_BROTLI if has_prefix else COMPRESSION_BROTLI
                return compressed, method
        except Exception:
            pass
    
    # Zlib
    compressed = zlib.compress(body, 9)
    if len(compressed) < len(body):
        method = COMPRESSION_SHARED_ZLIB if has_prefix else COMPRESSION_ZLIB
        return compressed, method
    
    # Не сжалось
    if has_prefix:
        # Возвращаем префикс обратно — храним целиком без сжатия
        return raw, COMPRESSION_NONE
    return raw, COMPRESSION_NONE


def _compress_worker(args):
    relpath, raw, shared_prefix = args
    
    # Оптимизация SVG
    if relpath.lower().endswith('.svg'):
        raw = _optimize_svg(raw)
    
    compressed, method = _compress_body(raw, shared_prefix)
    original_size = len(raw)
    
    return relpath, compressed, method, original_size


class IconPacker:
    MAGIC = b'ICN4'
    
    def __init__(self, source_dir='icons', output_file='icons.dat', workers=None):
        self.source_dir = source_dir
        self.output_file = output_file
        self.workers = workers or min(8, os.cpu_count() or 4)
    
    def scan_files(self):
        files = []
        for root, dirs, filenames in os.walk(self.source_dir):
            for filename in filenames:
                if filename.endswith('.json'):
                    continue
                filepath = os.path.join(root, filename)
                relpath = os.path.relpath(filepath, self.source_dir).replace('\\', '/')
                files.append((filepath, relpath))
        return files
    
    def _get_ext(self, path):
        return os.path.splitext(path)[1].lower()
    
    def pack(self):
        files = self.scan_files()
        total_files = len(files)
        
        console.print(f"\n[bold cyan]Найдено файлов:[/bold cyan] {total_files:,}")
        
        if not HAS_BROTLI:
            console.print("[yellow]⚠ Brotli не установлен (pip install brotli), только zlib[/yellow]\n")
        
        # ===== Шаг 1: Чтение всех файлов =====
        console.print(f"[bold yellow]Чтение файлов...[/bold yellow]")
        
        raw_files = {}  # relpath -> raw_bytes
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed:,}/{task.total:,}"),
            console=console
        ) as progress:
            task = progress.add_task("Чтение", total=total_files)
            for filepath, relpath in files:
                with open(filepath, 'rb') as f:
                    raw_files[relpath] = f.read()
                progress.advance(task)
        
        # ===== Шаг 2: Поиск общего префикса для SVG =====
        console.print(f"\n[bold yellow]Анализ SVG...[/bold yellow]")
        
        shared_prefix = b''
        svg_files = {p: _optimize_svg(d) for p, d in raw_files.items() 
                     if p.lower().endswith('.svg')}
        
        if len(svg_files) >= 2:
            # Группируем по первым 128 байтам
            groups = defaultdict(list)
            for path, data in svg_files.items():
                key = data[:128]
                groups[key].append(data)
            
            # Ищем лучший префикс
            best_prefix = b''
            best_count = 0
            
            for key, items in groups.items():
                if len(items) < 2:
                    continue
                prefix = _find_common_prefix(items)
                if len(prefix) >= 20 and len(items) > best_count:
                    best_prefix = prefix
                    best_count = len(items)
            
            if best_prefix:
                shared_prefix = best_prefix
                console.print(f"  [green]Найден общий префикс:[/green] {len(shared_prefix)} байт, "
                              f"подходит для {best_count} из {len(svg_files)} SVG")
            else:
                console.print("  [dim]Общий префикс не найден[/dim]")
        else:
            console.print(f"  [dim]SVG файлов: {len(svg_files)} (нужно ≥2 для префикса)[/dim]")
        
        # ===== Шаг 3: Параллельное сжатие =====
        console.print(f"\n[bold yellow]Сжатие[/bold yellow] (потоков: {self.workers})")
        
        tasks = [(p, d, shared_prefix) for p, d in raw_files.items()]
        
        # Статистика
        ext_stats = defaultdict(lambda: {'total': 0, 'raw_size': 0, 'compressed_size': 0,
                                          'brotli': 0, 'zlib': 0, 'shared_brotli': 0,
                                          'shared_zlib': 0, 'stored': 0})
        compressed_map = {}  # relpath -> (compressed, method, original_size)
        
        # Прогресс-бар + Live таблица
        main_progress = Progress(
            TextColumn("[bold]{task.percentage:>3.0f}%"),
            BarColumn(bar_width=None),
            TextColumn("[bold]{task.completed:,}/{task.total:,}"),
            console=console,
            expand=True
        )
        main_task = main_progress.add_task("", total=total_files)
        main_progress.start()
        
        def make_stats_table():
            t = Table(box=SIMPLE, show_header=True, header_style="bold cyan", expand=True)
            t.add_column("Расширение", style="cyan", width=10)
            t.add_column("Всего", justify="right", width=8)
            t.add_column("Brotli", justify="right", width=8)
            t.add_column("Zlib", justify="right", width=8)
            t.add_column("Shared", justify="right", width=8)
            t.add_column("Store", justify="right", width=8)
            t.add_column("Исходный", justify="right", width=12)
            t.add_column("Стало", justify="right", width=12)
            t.add_column("Экономия", justify="right", width=10)
            
            sorted_exts = sorted(ext_stats.items(), key=lambda x: x[1]['raw_size'], reverse=True)
            
            for ext, stats in sorted_exts:
                if stats['raw_size'] > 0:
                    ratio = (1 - stats['compressed_size'] / stats['raw_size']) * 100
                    ratio_str = f"[green]{ratio:.1f}%[/green]" if ratio > 0 else f"[dim]{ratio:.1f}%[/dim]"
                else:
                    ratio_str = "[dim]-[/dim]"
                
                shared_count = stats['shared_brotli'] + stats['shared_zlib']
                
                t.add_row(
                    ext if ext else "(нет)",
                    str(stats['total']),
                    str(stats['brotli']) if stats['brotli'] > 0 else "-",
                    str(stats['zlib']) if stats['zlib'] > 0 else "-",
                    str(shared_count) if shared_count > 0 else "-",
                    str(stats['stored']) if stats['stored'] > 0 else "-",
                    f"{stats['raw_size'] / 1024:.1f} KB",
                    f"{stats['compressed_size'] / 1024:.1f} KB",
                    ratio_str
                )
            
            total_compressed = sum(s['compressed_size'] for s in ext_stats.values())
            total_raw_all = sum(s['raw_size'] for s in ext_stats.values())
            total_brotli = sum(s['brotli'] for s in ext_stats.values())
            total_zlib = sum(s['zlib'] for s in ext_stats.values())
            total_shared = sum(s['shared_brotli'] + s['shared_zlib'] for s in ext_stats.values())
            total_stored = sum(s['stored'] for s in ext_stats.values())
            
            if total_raw_all > 0:
                total_ratio = (1 - total_compressed / total_raw_all) * 100
                total_ratio_str = f"[bold green]{total_ratio:.1f}%[/bold green]" if total_ratio > 0 else f"[dim]{total_ratio:.1f}%[/dim]"
            else:
                total_ratio_str = "[dim]-[/dim]"
            
            t.add_section()
            t.add_row(
                "[bold]ИТОГО[/bold]",
                f"[bold]{total_files}[/bold]",
                f"[bold]{total_brotli}[/bold]" if total_brotli > 0 else "-",
                f"[bold]{total_zlib}[/bold]" if total_zlib > 0 else "-",
                f"[bold]{total_shared}[/bold]" if total_shared > 0 else "-",
                f"[bold]{total_stored}[/bold]",
                f"[bold]{total_raw_all / 1024:.1f} KB[/bold]",
                f"[bold]{total_compressed / 1024:.1f} KB[/bold]",
                total_ratio_str
            )
            
            return t
        
        with Live(make_stats_table(), refresh_per_second=10, console=console) as live:
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                futures = {executor.submit(_compress_worker, t): t[0] for t in tasks}
                
                for future in as_completed(futures):
                    relpath, compressed, method, original_size = future.result()
                    
                    ext = self._get_ext(relpath)
                    ext_stats[ext]['total'] += 1
                    ext_stats[ext]['raw_size'] += original_size
                    ext_stats[ext]['compressed_size'] += len(compressed)
                    
                    if method == COMPRESSION_BROTLI:
                        ext_stats[ext]['brotli'] += 1
                    elif method == COMPRESSION_ZLIB:
                        ext_stats[ext]['zlib'] += 1
                    elif method == COMPRESSION_SHARED_BROTLI:
                        ext_stats[ext]['shared_brotli'] += 1
                    elif method == COMPRESSION_SHARED_ZLIB:
                        ext_stats[ext]['shared_zlib'] += 1
                    else:
                        ext_stats[ext]['stored'] += 1
                    
                    compressed_map[relpath] = (compressed, method, original_size)
                    
                    main_progress.update(main_task, completed=len(compressed_map))
                    live.update(make_stats_table())
        
        main_progress.stop()
        console.print()
        
        # ===== Шаг 4: Запись =====
        # Строим оглавление
        entries = []
        current_offset = 0
        
        header_size = 4 + 4 + 8 + 2 + len(shared_prefix)  # MAGIC + count + data_start + prefix_len + prefix
        toc_entry_size = 2 + 8 + 4 + 4 + 1  # path_len(N) + offset + size_comp + size_orig + compression
        toc_size = sum(toc_entry_size + len(p.encode('utf-8')) for p in compressed_map.keys())
        data_start = header_size + toc_size
        
        for relpath, (compressed, method, original_size) in compressed_map.items():
            size_original = original_size if method != COMPRESSION_NONE else 0
            entries.append({
                'path': relpath,
                'offset': data_start + current_offset,
                'size_compressed': len(compressed),
                'size_original': size_original,
                'compression': method,
                'data': compressed,
            })
            current_offset += len(compressed)
        
        total_bytes = header_size + toc_size + sum(e['size_compressed'] for e in entries)
        
        console.print(f"[bold yellow]Запись {self.output_file}[/bold yellow]")
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            FileSizeColumn(),
            TextColumn("•"),
            TextColumn("{task.percentage:.0f}%"),
            console=console
        ) as progress:
            
            task = progress.add_task("Запись", total=total_bytes)
            
            with open(self.output_file, 'wb', buffering=16*1024*1024) as out:
                # Заголовок
                out.write(self.MAGIC)
                out.write(struct.pack('<I', len(entries)))
                out.write(struct.pack('<Q', data_start))
                out.write(struct.pack('<H', len(shared_prefix)))
                if shared_prefix:
                    out.write(shared_prefix)
                progress.advance(task, header_size)
                
                # Оглавление
                for entry in entries:
                    path_bytes = entry['path'].encode('utf-8')
                    out.write(struct.pack('<H', len(path_bytes)))
                    out.write(path_bytes)
                    out.write(struct.pack('<Q', entry['offset']))
                    out.write(struct.pack('<I', entry['size_compressed']))
                    out.write(struct.pack('<I', entry['size_original']))
                    out.write(struct.pack('<B', entry['compression']))
                    progress.advance(task, toc_entry_size + len(path_bytes))
                
                # Данные
                for entry in entries:
                    out.write(entry['data'])
                    progress.advance(task, len(entry['data']))
        
        # ===== Итоги =====
        total_raw = sum(s['raw_size'] for s in ext_stats.values())
        total_archive = os.path.getsize(self.output_file)
        ratio_raw = (1 - total_archive / total_raw) * 100 if total_raw > 0 else 0
        
        console.print(f"\n[bold green]✓ Упаковка завершена![/bold green]")
        
        final_table = Table(title="РЕЗУЛЬТАТЫ", box=ROUNDED, title_style="bold green")
        final_table.add_column("Параметр", style="cyan", justify="right")
        final_table.add_column("Значение", style="white")
        
        total_brotli = sum(s['brotli'] for s in ext_stats.values())
        total_zlib = sum(s['zlib'] for s in ext_stats.values())
        total_shared = sum(s['shared_brotli'] + s['shared_zlib'] for s in ext_stats.values())
        total_stored = sum(s['stored'] for s in ext_stats.values())
        
        final_table.add_row("Файлов всего", f"{total_files:,}")
        final_table.add_row("  ├─ Brotli", f"[green]{total_brotli:,}[/green]" if total_brotli > 0 else "[dim]-[/dim]")
        final_table.add_row("  ├─ Zlib", f"[yellow]{total_zlib:,}[/yellow]" if total_zlib > 0 else "[dim]-[/dim]")
        final_table.add_row("  ├─ Shared prefix", f"[cyan]{total_shared:,}[/cyan]" if total_shared > 0 else "[dim]-[/dim]")
        final_table.add_row("  └─ Без сжатия", f"[dim]{total_stored:,}[/dim]")
        if shared_prefix:
            final_table.add_row("", "")
            final_table.add_row("Префикс SVG", f"{len(shared_prefix)} байт")
        final_table.add_row("", "")
        final_table.add_row("Исходный размер", f"{total_raw / (1024*1024):.1f} МБ")
        final_table.add_row("Размер архива", f"[bold green]{total_archive / (1024*1024):.1f} МБ[/bold green]")
        final_table.add_row("Экономия", f"[bold]{ratio_raw:.1f}%[/bold]")
        final_table.add_row("", "")
        final_table.add_row("Выходной файл", f"[bold blue]{self.output_file}[/bold blue]")
        
        console.print(final_table)
        
        return entries


class IconUnpacker:
    MAGIC = b'ICN4'
    
    def __init__(self, dat_file, buffer_size=16*1024*1024):
        self.dat_file = dat_file
        self.entries = {}
        self.shared_prefix = b''
        self._fd = open(dat_file, 'rb', buffering=buffer_size)
        self._load_toc()
    
    def _load_toc(self):
        self._fd.seek(0, os.SEEK_END)
        file_size = self._fd.tell()
        self._fd.seek(0)
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            FileSizeColumn(),
            console=console
        ) as progress:
            
            task = progress.add_task("Чтение архива", total=file_size)
            
            magic = self._fd.read(4)
            if magic != self.MAGIC:
                raise ValueError(f"Неверный формат файла")
            
            count = struct.unpack('<I', self._fd.read(4))[0]
            data_start = struct.unpack('<Q', self._fd.read(8))[0]
            prefix_len = struct.unpack('<H', self._fd.read(2))[0]
            
            if prefix_len > 0:
                self.shared_prefix = self._fd.read(prefix_len)
            
            progress.advance(task, 4 + 4 + 8 + 2 + prefix_len)
            
            for _ in range(count):
                path_len = struct.unpack('<H', self._fd.read(2))[0]
                path = self._fd.read(path_len).decode('utf-8')
                offset = struct.unpack('<Q', self._fd.read(8))[0]
                size_compressed = struct.unpack('<I', self._fd.read(4))[0]
                size_original = struct.unpack('<I', self._fd.read(4))[0]
                compression = struct.unpack('<B', self._fd.read(1))[0]
                
                self.entries[path] = {
                    'offset': offset,
                    'size_compressed': size_compressed,
                    'size_original': size_original,
                    'compression': compression,
                }
                progress.advance(task, 2 + path_len + 8 + 4 + 4 + 1)
        
        console.print(f"  [dim]Записей: {count:,}, префикс: {len(self.shared_prefix)} байт[/dim]")
    
    def extract(self, path, output_path):
        path = path.replace('\\', '/')
        
        if path not in self.entries:
            raise FileNotFoundError(f"Файл не найден: {path}")
        
        entry = self.entries[path]
        self._fd.seek(entry['offset'])
        data = self._fd.read(entry['size_compressed'])
        
        method = entry['compression']
        
        # Распаковка
        if method == COMPRESSION_ZLIB:
            data = zlib.decompress(data)
        elif method == COMPRESSION_BROTLI:
            if not HAS_BROTLI:
                raise RuntimeError("brotli не установлен")
            data = brotli.decompress(data)
        elif method == COMPRESSION_SHARED_BROTLI:
            if not HAS_BROTLI:
                raise RuntimeError("brotli не установлен")
            data = self.shared_prefix + brotli.decompress(data)
        elif method == COMPRESSION_SHARED_ZLIB:
            data = self.shared_prefix + zlib.decompress(data)
        # COMPRESSION_NONE — данные как есть
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as out:
            out.write(data)
        
        return len(data)
    
    def get_random_paths(self, count=5):
        all_paths = list(self.entries.keys())
        return random.sample(all_paths, min(count, len(all_paths)))
    
    def close(self):
        if hasattr(self, '_fd') and not self._fd.closed:
            self._fd.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
    
    def __del__(self):
        self.close()


def test_random_extract(count=5):
    console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
    console.print(f"[bold cyan]ТЕСТ РАСПАКОВКИ[/bold cyan] ({count} случайных файлов)")
    console.print(f"[bold cyan]{'='*60}[/bold cyan]\n")
    
    with IconUnpacker('icons.dat') as unpacker:
        paths = unpacker.get_random_paths(count)
        
        table = Table(box=SIMPLE)
        table.add_column("#", style="dim", width=4)
        table.add_column("Статус", width=2)
        table.add_column("Файл", style="cyan")
        table.add_column("Метод", width=14)
        table.add_column("Размер", justify="right", style="green")
        
        for i, path in enumerate(paths, 1):
            output_file = f"test_extract/{path}"
            try:
                entry = unpacker.entries[path]
                method_name = METHOD_NAMES.get(entry['compression'], "?")
                
                if entry['compression'] in (COMPRESSION_SHARED_BROTLI, COMPRESSION_SHARED_ZLIB):
                    method_style = "[cyan]" + method_name + "[/cyan]"
                elif entry['compression'] == COMPRESSION_BROTLI:
                    method_style = "[green]" + method_name + "[/green]"
                elif entry['compression'] == COMPRESSION_ZLIB:
                    method_style = "[yellow]" + method_name + "[/yellow]"
                else:
                    method_style = "[dim]" + method_name + "[/dim]"
                
                size = unpacker.extract(path, output_file)
                table.add_row(str(i), "[green]✓[/green]", path, method_style, f"{size:,} байт")
            except Exception as e:
                table.add_row(str(i), "[red]✗[/red]", path, "?", f"[red]{e}[/red]")
        
        console.print(table)
    
    console.print(f"\n[dim]Файлы извлечены в папку test_extract/[/dim]\n")


if __name__ == '__main__':
    console.print(Panel.fit(
        "[bold blue]ICON PACKER[/bold blue]\n"
        "[dim]Brotli + Zlib + Shared SVG prefix + Параллельное сжатие[/dim]",
        border_style="blue"
    ))
    
    packer = IconPacker(source_dir='icons', output_file='icons.dat')
    packer.pack()
    
    test_random_extract(5)
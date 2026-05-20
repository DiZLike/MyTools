import sqlite3
import json
import os
import re
import time
from pathlib import Path
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    MofNCompleteColumn,
)
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint
from rich.tree import Tree


def extract_words(text, min_length=2):
    """Извлекает слова из текста, убирая цифры и спецсимволы"""
    if not text:
        return []
    text = text.lower()
    words = re.findall(r'[a-zа-яё]+', text)
    seen = set()
    result = []
    for w in words:
        if len(w) >= min_length and w not in seen:
            seen.add(w)
            result.append(w)
    return result


def process_pack(pack_path):
    """
    Обрабатывает один пак.
    Возвращает: (pack_name, pack_tags, icons_list)
    icons_list = [(filepath, icon_tags), ...]
    """
    pack_name = os.path.basename(pack_path)
    json_path = os.path.join(pack_path, 'meta.json')
    icons_dir = os.path.join(pack_path, 'icons')

    if not os.path.exists(json_path) or not os.path.exists(icons_dir):
        return None

    with open(json_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    # --- pack_tags ---
    pack_words = []
    pack_words.extend(extract_words(meta.get('title', '')))
    pack_words.extend(extract_words(meta.get('style', '')))
    pack_words.extend(extract_words(meta.get('categories', '')))
    pack_words.extend(extract_words(pack_name))

    for tag in meta.get('tags', []):
        pack_words.extend(extract_words(tag))

    pack_tags = ' '.join(dict.fromkeys(pack_words))

    # --- Словарь персональных тегов из JSON ---
    icons_meta = {}
    for icon in meta.get('icons', []):
        icon_words = []
        icon_words.extend(extract_words(icon.get('name', '')))
        for tag in icon.get('tags', []):
            icon_words.extend(extract_words(tag))
        
        key = icon.get('name', '').lower()
        icons_meta[key] = ' '.join(dict.fromkeys(icon_words))

    # --- Сканируем папку ---
    icons_list = []
    for filename in os.listdir(icons_dir):
        if filename.endswith('.json'):
            continue

        filepath = os.path.join(icons_dir, filename)
        if not os.path.isfile(filepath):
            continue

        file_basename = os.path.splitext(filename)[0]
        icon_tags = icons_meta.get(file_basename.lower(), '')

        if not icon_tags:
            file_words = extract_words(file_basename)
            icon_tags = ' '.join(file_words)

        icons_list.append((filepath, icon_tags))

    return (pack_name, pack_tags, icons_list)


def create_db(db_path, console):
    """Создаёт БД с нуля"""
    if os.path.exists(db_path):
        os.remove(db_path)
        console.print("  [yellow]🗑️  Старая БД удалена[/]")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")

    conn.executescript("""
        CREATE TABLE packs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            tags TEXT
        );

        CREATE TABLE icons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT NOT NULL UNIQUE,
            pack_id INTEGER REFERENCES packs(id),
            icon_tags TEXT
        );

        CREATE VIRTUAL TABLE icons_fts USING fts5(
            icon_tags,
            pack_tags,
            tokenize='unicode61 remove_diacritics 0'
        );
    """)

    conn.close()
    console.print("  [green]✅ БД создана[/]")


def main():
    console = Console()
    
    # Красивый заголовок
    title = Text("🔍 ICONS DATABASE BUILDER", style="bold cyan")
    console.print(Panel(title, border_style="cyan"))
    console.print()
    
    root_dir = 'icons'
    db_path = 'icons.db'
    
    # Общее время выполнения
    total_start = time.time()

    # Этап 1: Создание БД
    console.print("[bold]📦 Этап 1: Создание базы данных[/]")
    stage_start = time.time()
    create_db(db_path, console)
    stage_time = time.time() - stage_start
    console.print(f"  ⏱️  Время: {stage_time:.2f}с\n")
    
    # Этап 2: Сбор и обработка данных
    console.print("[bold]📂 Этап 2: Сбор и обработка паков[/]")
    stage_start = time.time()
    
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Собираем паки
    packs = []
    for item in os.listdir(root_dir):
        pack_path = os.path.join(root_dir, item)
        if os.path.isdir(pack_path) and os.path.exists(os.path.join(pack_path, 'meta.json')):
            packs.append(pack_path)

    total_icons = 0
    total_packs = 0
    icon_batch = []
    batch_size = 1000
    failed_packs = []

    # Прогресс-бар с Rich
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
        refresh_per_second=10,
    ) as progress:
        
        task = progress.add_task(
            "[cyan]Обработка паков...", 
            total=len(packs)
        )
        
        for pack_path in packs:
            result = process_pack(pack_path)
            if result is None:
                failed_packs.append(os.path.basename(pack_path))
                progress.update(task, advance=1)
                continue

            pack_name, pack_tags, icons_list = result
            total_packs += 1

            # Вставляем пак
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO packs (name, tags) VALUES (?, ?)",
                    (pack_name, pack_tags)
                )
                pack_id = conn.execute(
                    "SELECT id FROM packs WHERE name = ?", (pack_name,)
                ).fetchone()[0]
            except Exception as e:
                console.print(f"  [red]❌ Ошибка при вставке пака {pack_name}: {e}[/]")
                failed_packs.append(pack_name)
                progress.update(task, advance=1)
                continue

            # Копим иконки
            for filepath, icon_tags in icons_list:
                icon_batch.append((filepath, pack_id, icon_tags))

            # Сбрасываем пачками
            while len(icon_batch) >= batch_size:
                chunk = icon_batch[:batch_size]
                conn.executemany(
                    "INSERT OR IGNORE INTO icons (filepath, pack_id, icon_tags) VALUES (?, ?, ?)",
                    chunk
                )
                conn.commit()
                total_icons += len(chunk)
                icon_batch = icon_batch[batch_size:]
                progress.update(task, description=f"[cyan]Обработка паков... ({total_icons} иконок)")

            progress.update(task, advance=1)

    # Остаток
    if icon_batch:
        conn.executemany(
            "INSERT OR IGNORE INTO icons (filepath, pack_id, icon_tags) VALUES (?, ?, ?)",
            icon_batch
        )
        conn.commit()
        total_icons += len(icon_batch)

    stage_time = time.time() - stage_start
    console.print(f"  ⏱️  Время: {stage_time:.2f}с\n")

    # Этап 3: Индексация FTS
    console.print("[bold]🔍 Этап 3: Индексация полнотекстового поиска[/]")
    stage_start = time.time()
    
    conn.execute("""
        INSERT INTO icons_fts(rowid, icon_tags, pack_tags)
        SELECT i.id, i.icon_tags, p.tags
        FROM icons i
        JOIN packs p ON i.pack_id = p.id
    """)
    conn.commit()
    conn.close()
    
    stage_time = time.time() - stage_start
    console.print(f"  ⏱️  Время: {stage_time:.2f}с\n")

    total_time = time.time() - total_start

    # Итоговая статистика
    stats_table = Table(
        title="📊 ИТОГОВАЯ СТАТИСТИКА",
        title_style="bold cyan",
        border_style="cyan",
        show_header=True,
        header_style="bold white"
    )
    stats_table.add_column("Параметр", style="yellow")
    stats_table.add_column("Значение", style="green", justify="right")
    
    stats_table.add_row("Паков обработано", f"{total_packs}/{len(packs)}")
    stats_table.add_row("Паков с ошибками", str(len(failed_packs)))
    stats_table.add_row("Иконок всего", f"{total_icons:,}")
    stats_table.add_row("Размер БД", f"{os.path.getsize(db_path) / 1024 / 1024:.2f} МБ")
    stats_table.add_row("Общее время", f"{total_time:.2f} сек")
    stats_table.add_row("Путь к БД", db_path)
    
    if failed_packs:
        stats_table.add_row("Проблемные паки", ", ".join(failed_packs[:5]))
    
    console.print(stats_table)
    console.print()

    # Дерево результатов поиска
    console.print(Panel("🔍 ТЕСТИРОВАНИЕ ПОИСКА", border_style="magenta"))
    
    tests = [
        ('acdc', 'wide'),
        ('acdc', 'exact'),
        ('hell', 'wide'),
        ('hell', 'exact'),
        ('highway hell', 'wide'),
        ('highway hell', 'exact'),
        ('tnt', 'wide'),
        ('tnt', 'exact'),
    ]

    for query, mode in tests:
        search_start = time.time()
        results = search(query, mode)
        search_time = time.time() - search_start
        
        mode_style = {
            'wide': 'blue',
            'exact': 'green'
        }
        
        tree = Tree(
            f"[{mode_style.get(mode, 'white')}][{mode.upper()}][/] "
            f"[bold]'{query}'[/] → "
            f"[yellow]найдено: {len(results)}[/] "
            f"[dim]({search_time:.3f}с)[/]"
        )
        
        for path in results[:5]:
            tree.add(f"[dim]{path}[/]")
        
        if len(results) > 5:
            tree.add(f"[dim]... и ещё {len(results) - 5}[/]")
        
        console.print(tree)
    
    console.print()
    console.print(Panel("[bold green]✅ Готово![/]", border_style="green"))


def search(query, mode='wide'):
    """
    Поиск иконок.
    mode='wide'  — ищет по icon_tags + pack_tags
    mode='exact' — ищет только по icon_tags
    """
    conn = sqlite3.connect('icons.db')

    words = query.split()
    if not words:
        conn.close()
        return []

    fts_query = ' OR '.join(words)

    if mode == 'exact':
        fts_query = ' OR '.join(f'icon_tags: {w}' for w in words)
    
    results = conn.execute(
        """SELECT i.filepath
           FROM icons_fts f
           JOIN icons i ON f.rowid = i.id
           WHERE icons_fts MATCH ?""",
        (fts_query,)
    ).fetchall()

    conn.close()
    return [r[0] for r in results]


if __name__ == '__main__':
    main()
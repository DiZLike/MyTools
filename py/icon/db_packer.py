import sqlite3
import json
import os
import re
from pathlib import Path
from tqdm import tqdm

def extract_words(text):
    """Извлекает слова из текста, убирая цифры и спецсимволы"""
    if not text:
        return []
    text = text.lower()
    words = re.findall(r'[a-zа-яё]+', text)
    return list(dict.fromkeys(words))

def process_pack(pack_path):
    """Обрабатывает один пак, возвращает список (filepath, search_text)"""
    pack_name = os.path.basename(pack_path)
    json_path = os.path.join(pack_path, 'pack.json')
    icons_dir = os.path.join(pack_path, 'icons')

    if not os.path.exists(json_path) or not os.path.exists(icons_dir):
        return []

    with open(json_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    # Собираем слова из json
    all_words = []
    all_words.extend(extract_words(meta.get('title', '')))
    all_words.extend(extract_words(meta.get('category', '')))
    all_words.extend(extract_words(meta.get('style', '')))
    for tag in meta.get('tags', []):
        all_words.extend(extract_words(tag))

    # Сканируем иконки
    results = []
    for filename in os.listdir(icons_dir):
        if filename.endswith('.json'):
            continue

        filepath = os.path.join(icons_dir, filename)
        if not os.path.isfile(filepath):
            continue

        # Добавляем слова из имени пака и файла
        file_words = all_words.copy()
        file_words.extend(extract_words(pack_name))
        file_words.extend(extract_words(os.path.splitext(filename)[0]))

        search_text = ' '.join(dict.fromkeys(file_words))
        results.append((filepath, search_text))

    return results

def main():
    root_dir = 'icons'
    db_path = 'icons.db'

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Создаём таблицы
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS icons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT NOT NULL UNIQUE,
            search_text TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS icons_fts USING fts5(
            search_text,
            content='icons',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 0'
        );

        CREATE TRIGGER IF NOT EXISTS icons_ai AFTER INSERT ON icons BEGIN
            INSERT INTO icons_fts(rowid, search_text) VALUES (new.id, new.search_text);
        END;

        CREATE TRIGGER IF NOT EXISTS icons_ad AFTER DELETE ON icons BEGIN
            INSERT INTO icons_fts(icons_fts, rowid, search_text) VALUES('delete', old.id, old.search_text);
        END;

        CREATE TRIGGER IF NOT EXISTS icons_au AFTER UPDATE ON icons BEGIN
            INSERT INTO icons_fts(icons_fts, rowid, search_text) VALUES('delete', old.id, old.search_text);
            INSERT INTO icons_fts(rowid, search_text) VALUES (new.id, new.search_text);
        END;
    """)

    # Собираем все паки
    packs = []
    for item in os.listdir(root_dir):
        pack_path = os.path.join(root_dir, item)
        if os.path.isdir(pack_path):
            packs.append(pack_path)

    # Обрабатываем с прогресс-баром
    total_icons = 0
    total_packs = 0
    skipped = 0

    with tqdm(total=len(packs), desc="Обработка паков", unit="пак") as pbar:
        for pack_path in packs:
            results = process_pack(pack_path)
            if results:
                # INSERT OR IGNORE пропустит дубликаты по filepath
                cursor = conn.executemany(
                    "INSERT OR IGNORE INTO icons (filepath, search_text) VALUES (?, ?)",
                    results
                )
                conn.commit()
                added = cursor.rowcount
                total_icons += added
                skipped += (len(results) - added)
                total_packs += 1

            pbar.set_postfix(иконок=total_icons, пропущено=skipped)
            pbar.update(1)

    conn.close()

    # Вывод статистики
    print(f"\n{'='*40}")
    print(f"Обработка завершена!")
    print(f"Паков обработано: {total_packs}/{len(packs)}")
    print(f"Иконок добавлено: {total_icons}")
    print(f"Дубликатов пропущено: {skipped}")
    print(f"База данных: {db_path}")
    print(f"{'='*40}")

def search(query):
    """Поиск иконок. Пробелы = OR"""
    conn = sqlite3.connect('icons.db')
    
    words = query.split()
    if not words:
        return []
    
    fts_query = ' OR '.join(words)
    
    results = conn.execute(
        "SELECT i.filepath FROM icons_fts f JOIN icons i ON f.rowid = i.id WHERE f.search_text MATCH ?",
        (fts_query,)
    ).fetchall()
    conn.close()
    return [r[0] for r in results]

if __name__ == '__main__':
    main()

    # Примеры поиска
    print("\nПримеры поиска:")
    
    queries = ['arrow', 'direct', 'стрелка', 'mp3', 'audio']
    
    for q in queries:
        results = search(q)
        print(f"\n'{q}' — найдено: {len(results)}")
        for path in results[:5]:
            print(f"  {path}")
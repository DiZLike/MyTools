import sqlite3
import sys
sys.path.insert(0, '.')

# Подключаемся к БД
conn = sqlite3.connect('icons.db')

def search(query, mode='wide'):
    """Поиск с выводом деталей"""
    words = query.split()
    if not words:
        return []
    
    if mode == 'exact':
        fts_query = ' OR '.join(f'icon_tags: {w}' for w in words)
    else:
        fts_query = ' OR '.join(words)
    
    print(f"\n{'='*70}")
    print(f"Режим: {mode.upper()}")
    print(f"Запрос: '{query}'")
    print(f"FTS: {fts_query}")
    
    # Поиск
    results = conn.execute("""
        SELECT i.filepath, i.icon_tags, p.tags
        FROM icons_fts f
        JOIN icons i ON f.rowid = i.id
        JOIN packs p ON i.pack_id = p.id
        WHERE icons_fts MATCH ?
        LIMIT 30
    """, (fts_query,)).fetchall()
    
    print(f"Найдено: {len(results)}")
    
    # Группируем по пакам
    packs_found = {}
    for filepath, icon_tags, pack_tags in results:
        pack_name = filepath.split('/')[0]
        if pack_name not in packs_found:
            packs_found[pack_name] = {'count': 0, 'files': [], 'pack_tags': pack_tags}
        packs_found[pack_name]['count'] += 1
        packs_found[pack_name]['files'].append((filepath, icon_tags))
    
    print(f"Паков затронуто: {len(packs_found)}")
    
    for pack_name, info in packs_found.items():
        print(f"\n  📁 {pack_name} ({info['count']} иконок)")
        print(f"     pack_tags: {info['pack_tags'][:120]}...")
        for filepath, icon_tags in info['files'][:5]:
            print(f"     └─ {filepath}")
            print(f"        icon_tags: {icon_tags}")
        if info['count'] > 5:
            print(f"     └─ ... и ещё {info['count'] - 5}")
    
    conn.close()
    return results


if __name__ == '__main__':
    # Список тестовых запросов
    tests = [
        "arrow",
        "sound",
        "play",
    ]
    
    print("ТЕСТЫ ПОИСКА")
    print("=" * 70)
    
    for q in tests:
        # Wide
        conn = sqlite3.connect('icons.db')
        wide_results = search(q, mode='wide')
        
        # Exact
        conn = sqlite3.connect('icons.db')
        exact_results = search(q, mode='exact')
        
        print(f"\n  >>> WIDE: {len(wide_results)} | EXACT: {len(exact_results)}")
    
    print("\n" + "=" * 70)
    print("ГОТОВО")
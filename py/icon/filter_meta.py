import os
import json
from pathlib import Path

def process_meta_files(root_dir="."):
    """
    Рекурсивно ищет файлы meta.json в указанной директории,
    фильтрует их и сохраняет как pack.json рядом с оригиналом
    """
    
    # Счётчики для отображения прогресса
    total_processed = 0
    total_found = 0
    
    print(f"🔍 Начинаю поиск meta.json в: {os.path.abspath(root_dir)}")
    print("-" * 50)
    
    # Рекурсивный обход всех директорий
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file == "meta.json":
                total_found += 1
                meta_path = os.path.join(root, file)
                pack_path = os.path.join(root, "pack.json")
                
                print(f"[{total_found}] 📄 Найден: {meta_path}")
                
                try:
                    # Читаем meta.json
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Создаём отфильтрованную копию
                    filtered_data = {k: v for k, v in data.items() 
                                   if k not in ['url', 'author', 'author_url', 
                                               'icons_count', 'license']}
                    
                    # Сохраняем pack.json
                    with open(pack_path, 'w', encoding='utf-8') as f:
                        json.dump(filtered_data, f, ensure_ascii=False, indent=2)
                    
                    total_processed += 1
                    print(f"   ✅ Сохранён: {pack_path}")
                    print(f"   📊 Ключей удалено: {len(data) - len(filtered_data)}")
                    
                except json.JSONDecodeError as e:
                    print(f"   ❌ Ошибка JSON: {e}")
                except Exception as e:
                    print(f"   ❌ Ошибка: {e}")
                
                print()
    
    # Финальная статистика
    print("-" * 50)
    print(f"📈 Статистика:")
    print(f"   - Найдено файлов meta.json: {total_found}")
    print(f"   - Успешно обработано: {total_processed}")
    if total_found > total_processed:
        print(f"   - С ошибками: {total_found - total_processed}")

if __name__ == "__main__":
    # Запускаем обработку из текущей директории
    process_meta_files(".")
    
    # Или можно указать конкретную директорию:
    # process_meta_files("/путь/к/папке")
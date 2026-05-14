import sys
import os

output_file = "output.txt"

def is_binary(filepath, chunk_size=1024):
    """Проверяет, является ли файл бинарным"""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(chunk_size)
            if b'\x00' in chunk:
                return True
            # Проверяем, что это текст (декодируется как utf-8)
            try:
                chunk.decode('utf-8')
                return False
            except UnicodeDecodeError:
                return True
    except:
        return True

def process_path(path):
    """Обрабатывает файл или директорию"""
    if os.path.isfile(path):
        if not is_binary(path):
            return [path]
    elif os.path.isdir(path):
        files = []
        for root, _, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(root, filename)
                if not is_binary(filepath):
                    files.append(filepath)
        return files
    return []

if len(sys.argv) < 2:
    print("Перетащите файл или папку на скрипт")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

paths_to_process = sys.argv[1:]
all_files = []

for path in paths_to_process:
    all_files.extend(process_path(path))

# Дописываем результат в файл с содержимым
with open(output_file, 'a', encoding='utf-8') as f:
    f.write("=" * 80 + "\n")
    for filepath in all_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as source_file:
                content = source_file.read()
            
            f.write(f"Файл: {filepath}\n")
            f.write("-" * 40 + "\n")
            f.write(content)
            if not content.endswith('\n'):
                f.write('\n')
            f.write("-" * 40 + "\n\n")
        except Exception as e:
            f.write(f"Файл: {filepath}\n")
            f.write(f"Ошибка при чтении: {str(e)}\n")
            f.write("-" * 40 + "\n\n")
    f.write("=" * 80 + "\n")

print(f"Добавлено {len(all_files)} файлов с содержимым в {output_file}")
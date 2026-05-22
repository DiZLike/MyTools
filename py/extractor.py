import sys
import os

output_file_base = "output"
output_file_ext = ".txt"
max_lines_per_file = 1000

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

def get_output_filename(base, ext, counter=None):
    """Генерирует имя выходного файла с учетом счетчика"""
    if counter is None or counter == 0:
        return f"{base}{ext}"
    else:
        return f"{base}_{counter}{ext}"

def count_lines_in_file(filepath):
    """Подсчитывает количество строк в файле"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return sum(1 for _ in f)
    except:
        return 0

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

# Определяем текущий выходной файл
current_counter = 0
current_output = get_output_filename(output_file_base, output_file_ext)

# Проверяем существующие файлы и находим последний
while os.path.exists(current_output):
    current_counter += 1
    current_output = get_output_filename(output_file_base, output_file_ext, current_counter)

# Возвращаемся к последнему существующему или начинаем с первого
if current_counter > 0:
    current_counter -= 1
    current_output = get_output_filename(output_file_base, output_file_ext, current_counter if current_counter > 0 else None)

# Функция для подготовки содержимого одного файла
def prepare_file_content(filepath):
    """Подготавливает строки содержимого для одного файла"""
    lines = []
    lines.append(f"Файл: {filepath}")
    lines.append("-" * 40)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as source_file:
            content = source_file.read()
        lines.append(content.rstrip('\n'))
    except Exception as e:
        lines.append(f"Ошибка при чтении: {str(e)}")
    
    lines.append("-" * 40)
    lines.append("")  # пустая строка
    return lines

# Обрабатываем каждый файл и пишем в выходные файлы
current_file_lines = count_lines_in_file(current_output)
file_counter = 0  # счетчик для имени файла

# Ищем номер для нового файла
temp_counter = 0
while os.path.exists(get_output_filename(output_file_base, output_file_ext, temp_counter if temp_counter > 0 else None)):
    temp_counter += 1
file_counter = temp_counter

# Начинаем запись
output_lines = []
separator_lines = ["=" * 80]

# Если начинаем новый файл, добавляем разделитель
if current_file_lines == 0 or not os.path.exists(current_output):
    output_lines = separator_lines.copy()
    current_file_lines = 1

for filepath in all_files:
    file_content_lines = prepare_file_content(filepath)
    
    # Проверяем, не превысит ли добавление лимит строк
    if current_file_lines + len(file_content_lines) > max_lines_per_file:
        # Добавляем завершающий разделитель в текущий файл
        output_lines.extend(separator_lines)
        
        # Записываем текущий файл
        current_output = get_output_filename(output_file_base, output_file_ext, file_counter if file_counter > 0 else None)
        mode = 'w' if not os.path.exists(current_output) or current_file_lines == len(separator_lines) else 'a'
        
        with open(current_output, mode, encoding='utf-8') as f:
            f.write('\n'.join(output_lines) + '\n')
        
        # Создаем новый файл
        file_counter += 1
        output_lines = separator_lines.copy()
        current_file_lines = 1
    
    # Добавляем содержимое файла
    output_lines.extend(file_content_lines)
    current_file_lines += len(file_content_lines)

# Записываем оставшиеся данные
if output_lines and output_lines != separator_lines:
    output_lines.extend(separator_lines)
    current_output = get_output_filename(output_file_base, output_file_ext, file_counter if file_counter > 0 else None)
    mode = 'a' if os.path.exists(current_output) else 'w'
    
    with open(current_output, mode, encoding='utf-8') as f:
        f.write('\n'.join(output_lines) + '\n')

# Выводим информацию о созданных файлах
created_files = []
for i in range(file_counter + 1):
    filename = get_output_filename(output_file_base, output_file_ext, i if i > 0 else None)
    if os.path.exists(filename):
        created_files.append(filename)

print(f"Обработано {len(all_files)} файлов")
print(f"Создано/обновлено выходных файлов: {len(created_files)}")
for f in created_files:
    lines = count_lines_in_file(f)
    print(f"  {f}: {lines} строк")
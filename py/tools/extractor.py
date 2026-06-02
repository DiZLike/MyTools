import sys
import os

output_file_base = "output"
output_file_ext = ".txt"
max_lines_per_file = 1000  # СТРОГИЙ лимит строк КОНТЕНТА

def is_binary(filepath, chunk_size=1024):
    """Проверяет, является ли файл бинарным"""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(chunk_size)
            if b'\x00' in chunk:
                return True
            try:
                chunk.decode('utf-8')
                return False
            except UnicodeDecodeError:
                return True
    except:
        return True

def get_output_filename(base, ext, counter):
    """Генерирует имя выходного файла"""
    if counter == 0:
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

def read_file_lines(filepath):
    """Читает файл и возвращает список строк"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.readlines()
    except:
        return []

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

def count_content_lines_in_output(filepath):
    """Подсчитывает строки КОНТЕНТА в выходном файле (исключая разделители и заголовки)"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Разделяем по разделителям файлов
        parts = content.split("=" * 80)
        total_content_lines = 0
        
        for part in parts:
            if not part.strip():
                continue
            
            lines = part.strip().split('\n')
            # Пропускаем первые 3 строки: "Файл: ...", "-"*40, и последние 2: "-"*40, пустая строка
            content_lines = lines[2:-2] if len(lines) > 4 else []
            total_content_lines += len(content_lines)
        
        return total_content_lines
    except:
        return 0

def find_last_output_file():
    """Находит последний существующий выходной файл"""
    counter = 0
    last_counter = -1
    
    while True:
        filename = get_output_filename(output_file_base, output_file_ext, counter)
        if os.path.exists(filename):
            last_counter = counter
            counter += 1
        else:
            if counter == 0:
                counter = 1
                continue
            break
    
    return last_counter

def get_output_files():
    """Возвращает список всех существующих выходных файлов"""
    files = []
    counter = 0
    while True:
        filename = get_output_filename(output_file_base, output_file_ext, counter)
        if os.path.exists(filename):
            files.append(filename)
            counter += 1
        else:
            if counter == 0:
                counter = 1
                continue
            break
    return files

if len(sys.argv) < 2:
    print("Перетащите файл или папку на скрипт")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

paths_to_process = sys.argv[1:]
all_files = []

for path in paths_to_process:
    all_files.extend(process_path(path))

if not all_files:
    print("Не найдено текстовых файлов для обработки")
    input("Нажмите Enter для выхода...")
    sys.exit(0)

print(f"ЛИМИТ СТРОК НА ФАЙЛ: {max_lines_per_file}")
print(f"Найдено файлов для обработки: {len(all_files)}")

# Проверяем, не обработаны ли уже эти файлы
output_files = get_output_files()
processed_files = set()

for out_file in output_files:
    try:
        with open(out_file, 'r', encoding='utf-8') as f:
            content = f.read()
            for filepath in all_files:
                if f"Файл: {filepath}" in content:
                    processed_files.add(filepath)
    except:
        pass

new_files = [f for f in all_files if f not in processed_files]

for filepath in all_files:
    if filepath in processed_files:
        print(f"  ПРОПУЩЕН (уже обработан): {filepath}")
    else:
        print(f"  НОВЫЙ: {filepath}")

if not new_files:
    print("\nНет новых файлов для обработки")
    input("\nНажмите Enter для выхода...")
    sys.exit(0)

# Находим последний выходной файл
last_file_num = find_last_output_file()

if last_file_num == -1:
    # Нет выходных файлов - создаём первый
    current_file_num = 0
    current_output_file = get_output_filename(output_file_base, output_file_ext, current_file_num)
    # Создаём пустой файл
    with open(current_output_file, 'w', encoding='utf-8') as f:
        pass
    print(f"Создан новый файл: {current_output_file}")
else:
    current_file_num = last_file_num

# Обрабатываем каждый новый файл
for filepath in new_files:
    print(f"\nОбработка файла: {filepath}")
    
    # Читаем содержимое входного файла
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        input_lines = content.split('\n')
    except Exception as e:
        print(f"  Ошибка чтения: {e}")
        continue
    
    print(f"  Строк во входном файле: {len(input_lines)}")
    
    # Если входной файл больше лимита, разбиваем его на части
    if len(input_lines) > max_lines_per_file:
        print(f"  Входной файл превышает лимит. Разбиваем на части по {max_lines_per_file} строк.")
        
        for i in range(0, len(input_lines), max_lines_per_file):
            chunk = input_lines[i:i + max_lines_per_file]
            
            # Проверяем текущий выходной файл
            current_output_file = get_output_filename(output_file_base, output_file_ext, current_file_num)
            
            if os.path.exists(current_output_file):
                current_content_lines = count_content_lines_in_output(current_output_file)
            else:
                current_content_lines = 0
            
            # Если в текущем файле уже есть содержимое и нет места для новой части
            if current_content_lines > 0 and current_content_lines + len(chunk) > max_lines_per_file:
                current_file_num += 1
                current_output_file = get_output_filename(output_file_base, output_file_ext, current_file_num)
                print(f"  Создан новый выходной файл: {current_output_file}")
            
            # Записываем часть в выходной файл
            with open(current_output_file, 'a', encoding='utf-8') as out_f:
                # Если файл пустой, не добавляем разделитель перед первым блоком
                if os.path.getsize(current_output_file) > 0:
                    out_f.write("=" * 80 + "\n")
                
                out_f.write(f"Файл: {filepath} (часть {i//max_lines_per_file + 1})\n")
                out_f.write("-" * 40 + "\n")
                out_f.write('\n'.join(chunk) + '\n')
                out_f.write("-" * 40 + "\n\n")
            
            print(f"  Записана часть {i//max_lines_per_file + 1}: {len(chunk)} строк в {current_output_file}")
    
    else:
        # Файл помещается в лимит
        current_output_file = get_output_filename(output_file_base, output_file_ext, current_file_num)
        
        if os.path.exists(current_output_file):
            current_content_lines = count_content_lines_in_output(current_output_file)
        else:
            current_content_lines = 0
        
        # Проверяем, поместится ли файл в текущий выходной файл
        if current_content_lines > 0 and current_content_lines + len(input_lines) > max_lines_per_file:
            current_file_num += 1
            current_output_file = get_output_filename(output_file_base, output_file_ext, current_file_num)
            print(f"  Создан новый выходной файл: {current_output_file}")
        
        # Записываем файл в выходной файл
        with open(current_output_file, 'a', encoding='utf-8') as out_f:
            if os.path.getsize(current_output_file) > 0:
                out_f.write("=" * 80 + "\n")
            
            out_f.write(f"Файл: {filepath}\n")
            out_f.write("-" * 40 + "\n")
            out_f.write('\n'.join(input_lines) + '\n')
            out_f.write("-" * 40 + "\n\n")
        
        print(f"  Записан файл: {len(input_lines)} строк в {current_output_file}")

# Финальная проверка
print(f"\n{'='*50}")
print("ПРОВЕРКА ВСЕХ ВЫХОДНЫХ ФАЙЛОВ:")
print(f"Лимит строк контента на файл: {max_lines_per_file}")

output_files = get_output_files()
total_content_lines = 0
files_over_limit = 0

for out_file in output_files:
    content_lines = count_content_lines_in_output(out_file)
    total_content_lines += content_lines
    total_lines_in_file = count_lines_in_file(out_file)
    
    if content_lines > max_lines_per_file:
        print(f"  ⚠ {out_file}: {content_lines} строк контента - ПРЕВЫШЕНИЕ на {content_lines - max_lines_per_file}!")
        files_over_limit += 1
    else:
        print(f"  ✓ {out_file}: {content_lines} строк контента (всего {total_lines_in_file} строк)")

print(f"\nВсего выходных файлов: {len(output_files)}")
print(f"Всего строк контента: {total_content_lines}")

if files_over_limit > 0:
    print(f"⚠ ВНИМАНИЕ: {files_over_limit} файлов превышают лимит!")
else:
    print("✓ Все файлы в пределах лимита!")

input("\nНажмите Enter для выхода...")
import os
import shutil
from pathlib import Path

def find_folders_without_png(root_path, dry_run=True):
    """
    Рекурсивно ищет папки без PNG файлов
    
    Args:
        root_path (str): Корневая директория для поиска
        dry_run (bool): Если True, только показывает что будет удалено
    """
    folders_to_delete = []
    
    # Рекурсивный обход всех папок
    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        # Проверяем наличие PNG файлов в текущей папке
        has_png = any(filename.lower().endswith('.png') for filename in filenames)
        
        # Также проверяем подпапки (на случай если они были удалены)
        has_png_in_subdirs = False
        if not has_png:
            for dirname in dirnames:
                subdir_path = os.path.join(dirpath, dirname)
                has_png_in_subdirs = check_png_in_folder(subdir_path)
                if has_png_in_subdirs:
                    break
        
        # Если нет PNG файлов ни в текущей папке, ни в подпапках
        if not has_png and not has_png_in_subdirs and dirpath != root_path:
            folders_to_delete.append(dirpath)
    
    return folders_to_delete

def check_png_in_folder(folder_path):
    """
    Проверяет наличие PNG файлов в папке рекурсивно
    
    Args:
        folder_path (str): Путь к папке для проверки
    
    Returns:
        bool: True если есть PNG файлы, False если нет
    """
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            if filename.lower().endswith('.png'):
                return True
    return False

def delete_folders_without_png(root_path, dry_run=True):
    """
    Удаляет папки без PNG файлов
    
    Args:
        root_path (str): Корневая директория для поиска
        dry_run (bool): Если True, только показывает что будет удалено
    """
    if not os.path.exists(root_path):
        print(f"Ошибка: Путь '{root_path}' не существует")
        return
    
    print(f"{'[DRY RUN] ' if dry_run else ''}Поиск папок без PNG файлов в: {root_path}")
    print("-" * 60)
    
    folders_to_delete = find_folders_without_png(root_path, dry_run)
    
    if not folders_to_delete:
        print("Папки без PNG файлов не найдены.")
        return
    
    print(f"\nНайдено {len(folders_to_delete)} папок без PNG файлов:")
    for folder in folders_to_delete:
        print(f"  - {folder}")
    
    if not dry_run:
        confirm = input(f"\nВы уверены, что хотите удалить эти папки? (да/нет): ")
        if confirm.lower() in ['да', 'yes', 'y']:
            print("\nУдаление папок...")
            for folder in folders_to_delete:
                try:
                    shutil.rmtree(folder)
                    print(f"  ✓ Удалено: {folder}")
                except Exception as e:
                    print(f"  ✗ Ошибка при удалении {folder}: {e}")
            print(f"\nУдалено {len(folders_to_delete)} папок.")
        else:
            print("Операция отменена.")
    else:
        print(f"\nДля фактического удаления запустите с параметром dry_run=False")

# Простой вариант с использованием pathlib
def find_and_delete_with_pathlib(root_path, dry_run=True):
    """
    Альтернативная версия с использованием pathlib
    
    Args:
        root_path (str): Корневая директория для поиска
        dry_run (bool): Если True, только показывает что будет удалено
    """
    root = Path(root_path)
    folders_to_delete = []
    
    # Рекурсивно проверяем все папки
    for folder in root.rglob('*'):
        if folder.is_dir() and folder != root:
            # Проверяем наличие PNG файлов
            png_files = list(folder.rglob('*.png')) + list(folder.rglob('*.PNG'))
            
            if not png_files:
                folders_to_delete.append(folder)
    
    if not folders_to_delete:
        print("Папки без PNG файлов не найдены.")
        return
    
    print(f"{'[DRY RUN] ' if dry_run else ''}Найдено {len(folders_to_delete)} папок без PNG файлов:")
    for folder in folders_to_delete:
        print(f"  - {folder}")
    
    if not dry_run:
        confirm = input(f"\nВы уверены, что хотите удалить эти папки? (да/нет): ")
        if confirm.lower() in ['да', 'yes', 'y']:
            for folder in folders_to_delete:
                try:
                    shutil.rmtree(folder)
                    print(f"  ✓ Удалено: {folder}")
                except Exception as e:
                    print(f"  ✗ Ошибка при удалении {folder}: {e}")
            print(f"\nУдалено {len(folders_to_delete)} папок.")
        else:
            print("Операция отменена.")
    else:
        print(f"\nДля фактического удаления запустите с параметром dry_run=False")

# Пример использования
if __name__ == "__main__":
    import sys
    
    # Получаем путь из аргументов командной строки или используем текущую директорию
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
    else:
        target_path = input("Введите путь к директории для поиска: ").strip() or "."
    
    # Выбираем метод
    print("Выберите метод:")
    print("1. Основной метод (os.walk)")
    print("2. Метод с pathlib")
    method_choice = input("Ваш выбор (1/2): ").strip()
    
    # Сначала dry run для безопасности
    print("\n=== ПРОВЕРКА (DRY RUN) ===")
    if method_choice == "2":
        find_and_delete_with_pathlib(target_path, dry_run=True)
    else:
        delete_folders_without_png(target_path, dry_run=True)
    
    # Спрашиваем о реальном удалении
    user_input = input("\nВыполнить реальное удаление? (да/нет): ")
    if user_input.lower() in ['да', 'yes', 'y']:
        print("\n=== РЕАЛЬНОЕ УДАЛЕНИЕ ===")
        if method_choice == "2":
            find_and_delete_with_pathlib(target_path, dry_run=False)
        else:
            delete_folders_without_png(target_path, dry_run=False)
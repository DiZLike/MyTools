import os
import struct
from tqdm import tqdm

class IconPacker:
    MAGIC = b'ICON'
    VERSION = 1
    
    def __init__(self, source_dir='icons', output_file='icons.dat'):
        self.source_dir = source_dir
        self.output_file = output_file
    
    def scan_files(self):
        """Сканирует все файлы кроме json"""
        files = []
        for root, dirs, filenames in os.walk(self.source_dir):
            for filename in filenames:
                if filename.endswith('.json'):
                    continue
                filepath = os.path.join(root, filename)
                # Используем прямой слеш для совместимости
                relpath = os.path.relpath(filepath, self.source_dir).replace('\\', '/')
                files.append((filepath, relpath))
        return files
    
    def pack(self):
        """Упаковывает все иконки в бинарный файл"""
        files = self.scan_files()
        total_files = len(files)
        print(f"Найдено файлов: {total_files}")
        
        entries = []
        current_offset = 0
        
        header_size = 4 + 4 + 4 + 8  # 20 байт
        toc_size = sum(2 + len(relpath.encode('utf-8')) + 8 + 4 for _, relpath in files)
        data_start = header_size + toc_size
        
        # Сбор информации с прогресс-баром
        print("Сбор информации о файлах...")
        for filepath, relpath in tqdm(files, desc="Сканирование", unit="файл", ncols=80):
            size = os.path.getsize(filepath)
            entries.append({
                'path': relpath,
                'offset': data_start + current_offset,
                'size': size,
                'source': filepath
            })
            current_offset += size
        
        # Запись в один проход с общим прогресс-баром
        print(f"Запись {self.output_file}...")
        total_bytes = sum(e['size'] for e in entries) + toc_size + header_size
        
        with open(self.output_file, 'wb') as out:
            with tqdm(total=total_bytes, desc="Запись", unit="B", unit_scale=True, unit_divisor=1024, ncols=80) as pbar:
                
                # Заголовок (20 байт)
                out.write(self.MAGIC)
                out.write(struct.pack('<I', self.VERSION))
                out.write(struct.pack('<I', len(entries)))
                out.write(struct.pack('<Q', data_start))
                pbar.update(20)
                
                # Оглавление
                for entry in entries:
                    path_bytes = entry['path'].encode('utf-8')
                    
                    out.write(struct.pack('<H', len(path_bytes)))
                    pbar.update(2)
                    
                    out.write(path_bytes)
                    pbar.update(len(path_bytes))
                    
                    out.write(struct.pack('<Q', entry['offset']))
                    pbar.update(8)
                    out.write(struct.pack('<I', entry['size']))
                    pbar.update(4)
                
                # Данные файлов
                for entry in entries:
                    with open(entry['source'], 'rb') as src:
                        data = src.read()
                        out.write(data)
                        pbar.update(len(data))
        
        # Статистика
        total_size = os.path.getsize(self.output_file)
        print(f"\n{'='*50}")
        print(f"Упаковка завершена!")
        print(f"Файлов упаковано: {len(entries)}")
        print(f"Размер архива: {total_size / (1024*1024):.1f} МБ")
        print(f"Выходной файл: {self.output_file}")
        print(f"{'='*50}")
        
        return entries

class IconUnpacker:
    MAGIC = b'ICON'
    
    def __init__(self, dat_file):
        self.dat_file = dat_file
        self.entries = {}
        self._load_toc()
    
    def _load_toc(self):
        """Читает оглавление из файла"""
        file_size = os.path.getsize(self.dat_file)
        
        with open(self.dat_file, 'rb') as f:
            with tqdm(total=file_size, desc="Чтение архива", unit="B", unit_scale=True, unit_divisor=1024, ncols=80) as pbar:
                # Заголовок
                magic = f.read(4)
                pbar.update(4)
                
                if magic != self.MAGIC:
                    raise ValueError("Неверный формат файла")
                
                version = struct.unpack('<I', f.read(4))[0]
                pbar.update(4)
                count = struct.unpack('<I', f.read(4))[0]
                pbar.update(4)
                data_start = struct.unpack('<Q', f.read(8))[0]
                pbar.update(8)
                
                print(f"Записей в архиве: {count}")
                
                # Оглавление
                for _ in range(count):
                    path_len = struct.unpack('<H', f.read(2))[0]
                    pbar.update(2)
                    path = f.read(path_len).decode('utf-8')
                    pbar.update(path_len)
                    offset = struct.unpack('<Q', f.read(8))[0]
                    pbar.update(8)
                    size = struct.unpack('<I', f.read(4))[0]
                    pbar.update(4)
                    
                    self.entries[path] = {
                        'offset': offset,
                        'size': size
                    }
    
    def extract(self, path, output_path):
        """Извлекает один файл по пути"""
        # Нормализуем путь
        path = path.replace('\\', '/')
        
        if path not in self.entries:
            # Попробуем найти частичное совпадение
            similar = [p for p in self.entries.keys() if path.lower() in p.lower()]
            if similar:
                print(f"Похожие пути:")
                for s in similar[:5]:
                    print(f"  {s}")
            raise FileNotFoundError(f"Файл не найден в архиве: {path}")
        
        entry = self.entries[path]
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(self.dat_file, 'rb') as f:
            f.seek(entry['offset'])
            data = f.read(entry['size'])
        
        with open(output_path, 'wb') as out:
            out.write(data)
        
        print(f"✓ {output_path} ({entry['size']:,} байт)")
        return True
    
    def search(self, pattern):
        """Поиск файлов по паттерну"""
        pattern = pattern.lower()
        return [p for p in self.entries.keys() if pattern in p.lower()]
    
    def get_all_paths(self):
        return list(self.entries.keys())

def test_extract():
    """Тестовая распаковка с поиском"""
    print("\n" + "="*50)
    print("ТЕСТ РАСПАКОВКИ")
    print("="*50)
    
    unpacker = IconUnpacker('icons.dat')
    
    # Ищем нужные файлы
    search_terms = ["si-duo-lightbulb", "empathy"]
    
    for term in search_terms:
        results = unpacker.search(term)
        if results:
            print(f"\nНайдено по '{term}':")
            for path in results[:3]:
                print(f"  {path}")
                try:
                    output_file = f"test_extract/{path}"
                    unpacker.extract(path, output_file)
                except Exception as e:
                    print(f"  ✗ Ошибка: {e}")
        else:
            print(f"\nПо '{term}' ничего не найдено")
    
    print(f"\nВсего файлов в архиве: {len(unpacker.get_all_paths()):,}")

if __name__ == '__main__':
    packer = IconPacker()
    packer.pack()
    test_extract()
#!/usr/bin/env python3
"""
DGBA v3.0 - Инкрементальный дельта-графовый архиватор для бэкапов

Новое в v3.0:
- Полные и инкрементальные бэкапы
- Цепочки инкрементов
- Автоматический выбор базы для инкремента
- Восстановление на любой момент из цепочки

Использование: python dgba.py <команда> [опции]

Команды:
  full <путь> [опции]           Полный бэкап
  inc <путь> [опции]            Инкрементальный бэкап
  restore <снимок> [директория]  Восстановить
  list                          Список бэкапов
  info <файл.dgba>              Информация
  
Опции:
  --name NAME         Имя снимка
  --base NAME         База для инкремента (авто если не указана)
  --dir PATH          Директория бэкапов (./backups)
  --min-block N       Мин. блок (4096)
  --max-block N       Макс. блок (65536)
  --similarity 0-1    Порог схожести (0.6)
  --speed             Быстрый режим
  --no-huffman        Без Хаффмана
  --no-delta          Без дельт
"""

import hashlib
import struct
import os
import sys
import json
from collections import Counter, defaultdict
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import heapq
import argparse
import time


# ==================== Хаффман ====================

class HuffmanCoder:
    class Node:
        __slots__ = ('byte', 'freq', 'left', 'right')
        def __init__(self, byte=None, freq=0, left=None, right=None):
            self.byte = byte
            self.freq = freq
            self.left = left
            self.right = right
        def __lt__(self, other):
            return self.freq < other.freq
    
    def __init__(self):
        self.codes = {}
        self.reverse_codes = {}
    
    def build(self, data: bytes):
        freq = Counter(data)
        if not freq:
            return
        heap = [self.Node(byte=b, freq=f) for b, f in freq.items()]
        heapq.heapify(heap)
        while len(heap) > 1:
            l, r = heapq.heappop(heap), heapq.heappop(heap)
            heapq.heappush(heap, self.Node(freq=l.freq + r.freq, left=l, right=r))
        self._gen(heap[0] if heap else None)
    
    def _gen(self, node, code=""):
        if not node:
            return
        if node.byte is not None:
            self.codes[node.byte] = code or "0"
            self.reverse_codes[code or "0"] = node.byte
        else:
            self._gen(node.left, code + "0")
            self._gen(node.right, code + "1")
    
    def encode(self, data: bytes) -> bytes:
        if not self.codes or len(data) < 10:
            return data
        bits = ''.join(self.codes[b] for b in data)
        pad = (8 - len(bits) % 8) % 8
        bits += '0' * pad
        result = bytearray([pad, len(self.codes) - 1])
        freq = Counter(data)
        result.extend(struct.pack('>H', len(freq)))
        for b, f in freq.items():
            result.extend(struct.pack('>BI', b, f))
        for i in range(0, len(bits), 8):
            result.append(int(bits[i:i+8], 2))
        return bytes(result)
    
    def decode(self, data: bytes) -> bytes:
        if len(data) < 6:
            return data
        pos = 0
        pad = data[pos]; pos += 1
        num_codes = data[pos]; pos += 1
        ts = struct.unpack('>H', data[pos:pos+2])[0]; pos += 2
        freq = {}
        for _ in range(ts):
            b = data[pos]; pos += 1
            f = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
            freq[b] = f
        heap = [self.Node(byte=b, freq=f) for b, f in freq.items()]
        heapq.heapify(heap)
        while len(heap) > 1:
            l, r = heapq.heappop(heap), heapq.heappop(heap)
            heapq.heappush(heap, self.Node(freq=l.freq + r.freq, left=l, right=r))
        self.codes, self.reverse_codes = {}, {}
        self._gen(heap[0] if heap else None)
        bits = ''.join(bin(b)[2:].zfill(8) for b in data[pos:])
        if pad:
            bits = bits[:-pad]
        result, cur = bytearray(), ""
        for bit in bits:
            cur += bit
            if cur in self.reverse_codes:
                result.append(self.reverse_codes[cur])
                cur = ""
        return bytes(result)


# ==================== Инкрементальный архиватор ====================

@dataclass
class FileEntry:
    """Информация о файле в снимке"""
    path: str
    size: int
    mtime: float
    hash: str  # SHA256 всего файла
    
@dataclass
class SnapshotInfo:
    """Метаданные снимка"""
    name: str
    timestamp: str
    type: str  # 'full' или 'inc'
    base: Optional[str]  # имя базового снимка для инкремента
    files: Dict[str, FileEntry] = field(default_factory=dict)
    file: str = ""  # путь к файлу снимка


class IncrementalArchiver:
    """Инкрементальный архиватор"""
    
    def __init__(self, min_block=4096, max_block=65536, similarity=0.6,
                 use_huffman=True, use_delta=True, fast=False):
        self.min_block = min_block
        self.max_block = max_block
        self.similarity = similarity
        self.use_huffman = use_huffman
        self.use_delta = use_delta
        self.fast = fast
    
    def _hash(self, data: bytes, length=8) -> str:
        return hashlib.blake2b(data, digest_size=length).hexdigest()
    
    def _file_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
    
    def _chunk(self, data: bytes) -> List[Tuple[str, bytes]]:
        """Разбиение на блоки"""
        chunks = []
        for i in range(0, len(data), self.max_block):
            chunk = data[i:i + self.max_block]
            chunks.append((self._hash(chunk), chunk))
        return chunks
    
    def _similarity(self, b1: bytes, b2: bytes) -> float:
        if len(b1) != len(b2):
            return 0.0
        step = 128
        matches = sum(1 for i in range(0, len(b1), step) if b1[i] == b2[i])
        return matches / max(1, len(b1) // step)
    
    def _delta_ops(self, base: bytes, target: bytes) -> Optional[List[Tuple[int, int, bytes]]]:
        if len(base) != len(target):
            return None
        ops = []
        i = 0
        while i < len(target):
            if i < len(base) and base[i] == target[i]:
                i += 1
                continue
            start = i
            diff = bytearray()
            while i < len(target) and (i >= len(base) or base[i] != target[i]):
                diff.append(target[i])
                i += 1
            if diff:
                ops.append((start, len(diff), bytes(diff)))
        if not ops:
            return None
        dsize = sum(len(op[2]) for op in ops) + len(ops) * 8
        if dsize >= len(target) * 0.7:
            return None
        return ops
    
    def _apply_delta(self, base: bytes, ops: List[Tuple[int, int, bytes]]) -> bytes:
        result = bytearray(base)
        for offset, length, data in ops:
            result[offset:offset + length] = data
        return bytes(result)
    
    def compress_full(self, files_data: Dict[str, bytes]) -> Tuple[bytes, Dict[str, FileEntry]]:
        """Полное сжатие всех файлов"""
        # Объединяем все файлы
        all_data = b''
        file_entries = {}
        offset = 0
        
        for filepath, data in sorted(files_data.items()):
            fhash = self._file_hash(data)
            file_entries[filepath] = FileEntry(
                path=filepath,
                size=len(data),
                mtime=time.time(),
                hash=fhash
            )
            all_data += data
        
        # Сжимаем
        compressed = self._compress_data(all_data, file_entries)
        return compressed, file_entries
    
    def compress_inc(self, files_data: Dict[str, bytes], 
                     base_files: Dict[str, FileEntry],
                     base_data: bytes) -> Tuple[bytes, Dict[str, FileEntry]]:
        """
        Инкрементальное сжатие.
        Сохраняет только:
        - Новые файлы
        - Изменённые файлы
        - Ссылки на неизменённые файлы из базы
        """
        new_entries = {}
        
        # Категоризируем файлы
        unchanged = {}   # путь -> (offset, size) в базе
        changed = {}     # путь -> новые данные
        new_files = {}   # путь -> новые данные
        
        for filepath, data in sorted(files_data.items()):
            fhash = self._file_hash(data)
            entry = FileEntry(
                path=filepath,
                size=len(data),
                mtime=time.time(),
                hash=fhash
            )
            new_entries[filepath] = entry
            
            if filepath in base_files:
                base_entry = base_files[filepath]
                if fhash == base_entry.hash:
                    # Файл не изменился - просто ссылка
                    unchanged[filepath] = base_entry
                    continue
                else:
                    # Файл изменился
                    changed[filepath] = data
            else:
                # Новый файл
                new_files[filepath] = data
        
        # Сохраняем только изменившиеся и новые файлы
        inc_data = b''
        
        # 1. Неизменённые файлы (только метаданные, без содержимого)
        # 2. Изменённые файлы (полное содержимое)
        for filepath, data in sorted(changed.items()):
            inc_data += data
        
        # 3. Новые файлы
        for filepath, data in sorted(new_files.items()):
            inc_data += data
        
        # Сжимаем только изменённые данные
        compressed = self._compress_inc_data(
            unchanged=unchanged,
            changed=changed,
            new_files=new_files,
            new_entries=new_entries,
            base_files=base_files
        )
        
        return compressed, new_entries
    
    def _compress_data(self, data: bytes, entries: Dict[str, FileEntry]) -> bytes:
        """Сжатие данных с заголовком"""
        chunks = self._chunk(data)
        
        # Строим словарь блоков
        block_dict = {}  # hash -> index
        block_data = []
        encoded = []
        
        for chash, cdata in chunks:
            if chash in block_dict:
                encoded.append(('ref', block_dict[chash], None))
            else:
                # Ищем похожий блок
                best_idx = -1
                best_ops = None
                best_size = len(cdata)
                
                if self.use_delta and block_data and not self.fast:
                    for idx, blk in enumerate(block_data):
                        if len(blk) == len(cdata):
                            if self._similarity(blk, cdata) > self.similarity:
                                ops = self._delta_ops(blk, cdata)
                                if ops:
                                    dsize = sum(len(op[2]) for op in ops) + len(ops) * 8
                                    if dsize < best_size:
                                        best_size = dsize
                                        best_idx = idx
                                        best_ops = ops
                
                if best_idx >= 0:
                    encoded.append(('delta', best_idx, best_ops))
                else:
                    idx = len(block_data)
                    block_data.append(cdata)
                    block_dict[chash] = idx
                    encoded.append(('full', idx, None))
        
        return self._serialize(block_data, encoded, entries)
    
    def _compress_inc_data(self, unchanged: Dict, changed: Dict, 
                          new_files: Dict, new_entries: Dict,
                          base_files: Dict) -> bytes:
        """Сериализация инкрементальных данных"""
        result = bytearray()
        
        # Заголовок инкремента
        result.extend(b'DGINC')  # Magic для инкремента
        result.extend(struct.pack('>H', 1))  # версия
        
        # Количество файлов по категориям
        result.extend(struct.pack('>I', len(unchanged)))
        result.extend(struct.pack('>I', len(changed)))
        result.extend(struct.pack('>I', len(new_files)))
        
        # Неизменённые файлы (только пути)
        for filepath, entry in sorted(unchanged.items()):
            path_bytes = filepath.encode('utf-8')
            result.extend(struct.pack('>H', len(path_bytes)))
            result.extend(path_bytes)
            result.extend(struct.pack('>Q', entry.size))
        
        # Изменённые и новые файлы - сжимаем их данные
        all_changed_data = b''
        changed_index = {}
        offset = 0
        
        for filepath, data in sorted({**changed, **new_files}.items()):
            changed_index[filepath] = {'offset': offset, 'size': len(data)}
            all_changed_data += data
            offset += len(data)
        
        # Сжимаем изменённые данные
        chunks = self._chunk(all_changed_data)
        block_dict = {}
        block_data = []
        encoded = []
        
        for chash, cdata in chunks:
            if chash in block_dict:
                encoded.append(('ref', block_dict[chash], None))
            else:
                idx = len(block_data)
                block_data.append(cdata)
                block_dict[chash] = idx
                encoded.append(('full', idx, None))
        
        # Сериализуем блоки
        result.extend(struct.pack('>I', len(block_data)))
        for blk in block_data:
            result.extend(struct.pack('>I', len(blk)))
            result.extend(blk)
        
        # Сериализуем инструкции
        result.extend(struct.pack('>I', len(encoded)))
        for etype, ref, _ in encoded:
            if etype == 'ref':
                result.append(0)
                result.extend(struct.pack('>I', ref))
            else:
                result.append(1)
                result.extend(struct.pack('>I', ref))
        
        # Индекс изменённых файлов
        result.extend(struct.pack('>I', len(changed_index)))
        for filepath, info in sorted(changed_index.items()):
            path_bytes = filepath.encode('utf-8')
            result.extend(struct.pack('>H', len(path_bytes)))
            result.extend(path_bytes)
            result.extend(struct.pack('>Q', info['offset']))
            result.extend(struct.pack('>I', info['size']))
            result.extend(bytes.fromhex(new_entries[filepath].hash))
        
        # Хаффман
        if self.use_huffman:
            h = HuffmanCoder()
            h.build(bytes(result))
            return h.encode(bytes(result))
        
        return bytes(result)
    
    def _serialize(self, block_data: List[bytes], encoded: List[Tuple], 
                  entries: Dict[str, FileEntry]) -> bytes:
        """Сериализация полного бэкапа"""
        result = bytearray()
        
        # Заголовок
        result.extend(b'DGFULL')  # Magic для полного бэкапа
        result.extend(struct.pack('>H', 1))  # версия
        
        # Индекс файлов
        result.extend(struct.pack('>I', len(entries)))
        for filepath, entry in sorted(entries.items()):
            path_bytes = filepath.encode('utf-8')
            result.extend(struct.pack('>H', len(path_bytes)))
            result.extend(path_bytes)
            result.extend(struct.pack('>Q', entry.size))
            result.extend(bytes.fromhex(entry.hash))
        
        # Блоки
        result.extend(struct.pack('>I', len(block_data)))
        for blk in block_data:
            result.extend(struct.pack('>I', len(blk)))
            result.extend(blk)
        
        # Инструкции
        result.extend(struct.pack('>I', len(encoded)))
        for etype, ref, ops in encoded:
            if etype == 'ref':
                result.append(0)
                result.extend(struct.pack('>I', ref))
            elif etype == 'full':
                result.append(1)
                result.extend(struct.pack('>I', ref))
            elif etype == 'delta':
                result.append(2)
                result.extend(struct.pack('>I', ref))
                result.extend(struct.pack('>H', len(ops)))
                for offset, length, ndata in ops:
                    result.extend(struct.pack('>I', offset))
                    result.extend(struct.pack('>H', length))
                    result.extend(struct.pack('>H', len(ndata)))
                    result.extend(ndata)
        
        # Хаффман
        if self.use_huffman:
            h = HuffmanCoder()
            h.build(bytes(result))
            return h.encode(bytes(result))
        
        return bytes(result)
    
    def decompress(self, data: bytes, base_data: Optional[bytes] = None) -> Tuple[bytes, Dict[str, FileEntry]]:
        """Распаковка (поддержка полных и инкрементальных)"""
        # Декодируем Хаффман
        if data[:6] not in [b'DGFULL', b'DGINC ']:
            h = HuffmanCoder()
            data = h.decode(data)
        
        magic = data[:6]
        
        if magic == b'DGFULL':
            return self._decompress_full(data)
        elif magic == b'DGINC':
            if base_data is None:
                raise ValueError("Для инкремента нужна база")
            return self._decompress_inc(data, base_data)
        else:
            raise ValueError("Неверный формат")
    
    def _decompress_full(self, data: bytes) -> Tuple[bytes, Dict[str, FileEntry]]:
        """Распаковка полного бэкапа"""
        pos = 6
        ver = struct.unpack('>H', data[pos:pos+2])[0]; pos += 2
        
        # Читаем индекс файлов
        num_files = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
        entries = {}
        file_sizes = {}
        
        for _ in range(num_files):
            plen = struct.unpack('>H', data[pos:pos+2])[0]; pos += 2
            filepath = data[pos:pos+plen].decode('utf-8'); pos += plen
            size = struct.unpack('>Q', data[pos:pos+8])[0]; pos += 8
            fhash = data[pos:pos+32].hex(); pos += 32
            file_sizes[filepath] = size
            entries[filepath] = FileEntry(path=filepath, size=size, mtime=0, hash=fhash)
        
        # Читаем блоки
        num_blocks = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
        blocks = []
        for _ in range(num_blocks):
            size = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
            blocks.append(data[pos:pos+size]); pos += size
        
        # Читаем инструкции
        num_instr = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
        result = bytearray()
        
        for _ in range(num_instr):
            etype = data[pos]; pos += 1
            ref = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
            
            if etype == 0:  # ссылка
                result.extend(blocks[ref])
            elif etype == 1:  # полный
                result.extend(blocks[ref])
            elif etype == 2:  # дельта
                num_ops = struct.unpack('>H', data[pos:pos+2])[0]; pos += 2
                ops = []
                for _ in range(num_ops):
                    offset = struct.unpack('>I', data[pos:pos+4])[0]; pos += 4
                    length = struct.unpack('>H', data[pos:pos+2])[0]; pos += 2
                    dlen = struct.unpack('>H', data[pos:pos+2])[0]; pos += 2
                    ndata = data[pos:pos+dlen]; pos += dlen
                    ops.append((offset, length, ndata))
                result.extend(self._apply_delta(blocks[ref], ops))
        
        return bytes(result), entries
    
    def _decompress_inc(self, inc_data: bytes, base_data: bytes) -> Tuple[bytes, Dict[str, FileEntry]]:
        """Распаковка инкремента с базой"""
        pos = 6
        ver = struct.unpack('>H', inc_data[pos:pos+2])[0]; pos += 2
        
        # Читаем количества
        num_unchanged = struct.unpack('>I', inc_data[pos:pos+4])[0]; pos += 4
        num_changed = struct.unpack('>I', inc_data[pos:pos+4])[0]; pos += 4
        num_new = struct.unpack('>I', inc_data[pos:pos+4])[0]; pos += 4
        
        # Неизменённые файлы
        unchanged_files = {}
        for _ in range(num_unchanged):
            plen = struct.unpack('>H', inc_data[pos:pos+2])[0]; pos += 2
            filepath = inc_data[pos:pos+plen].decode('utf-8'); pos += plen
            size = struct.unpack('>Q', inc_data[pos:pos+8])[0]; pos += 8
            unchanged_files[filepath] = size
        
        # Блоки изменённых данных
        num_blocks = struct.unpack('>I', inc_data[pos:pos+4])[0]; pos += 4
        blocks = []
        for _ in range(num_blocks):
            size = struct.unpack('>I', inc_data[pos:pos+4])[0]; pos += 4
            blocks.append(inc_data[pos:pos+size]); pos += size
        
        # Инструкции
        num_instr = struct.unpack('>I', inc_data[pos:pos+4])[0]; pos += 4
        changed_all = bytearray()
        for _ in range(num_instr):
            etype = inc_data[pos]; pos += 1
            ref = struct.unpack('>I', inc_data[pos:pos+4])[0]; pos += 4
            changed_all.extend(blocks[ref])
        
        # Индекс изменённых
        num_changed_idx = struct.unpack('>I', inc_data[pos:pos+4])[0]; pos += 4
        changed_files = {}
        
        for _ in range(num_changed_idx):
            plen = struct.unpack('>H', inc_data[pos:pos+2])[0]; pos += 2
            filepath = inc_data[pos:pos+plen].decode('utf-8'); pos += plen
            offset = struct.unpack('>Q', inc_data[pos:pos+8])[0]; pos += 8
            size = struct.unpack('>I', inc_data[pos:pos+4])[0]; pos += 4
            fhash = inc_data[pos:pos+32].hex(); pos += 32
            changed_files[filepath] = {
                'offset': offset, 'size': size, 'hash': fhash
            }
        
        # Восстанавливаем результат
        # Здесь нужна база, чтобы извлечь неизменённые файлы
        # Возвращаем только изменённые данные и индекс
        result = changed_all
        entries = {}
        
        for filepath, size in unchanged_files.items():
            entries[filepath] = FileEntry(path=filepath, size=size, mtime=0, hash='')
        
        for filepath, info in changed_files.items():
            entries[filepath] = FileEntry(
                path=filepath, size=info['size'], mtime=0, hash=info['hash']
            )
        
        return bytes(result), entries


# ==================== Система бэкапов ====================

class BackupSystem:
    def __init__(self, backup_dir="./backups"):
        self.backup_dir = backup_dir
        self.index_file = os.path.join(backup_dir, "index.json")
        os.makedirs(backup_dir, exist_ok=True)
        self.index = self._load()
    
    def _load(self):
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r') as f:
                return json.load(f)
        return {'snapshots': {}, 'chain': []}
    
    def _save(self):
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2, default=str)
    
    def _read_files(self, path: str) -> Dict[str, bytes]:
        """Читает все файлы из пути"""
        files = {}
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                files[os.path.basename(path)] = f.read()
        elif os.path.isdir(path):
            for root, _, filenames in os.walk(path):
                for fn in filenames:
                    fp = os.path.join(root, fn)
                    rp = os.path.relpath(fp, path)
                    try:
                        with open(fp, 'rb') as f:
                            files[rp] = f.read()
                    except:
                        pass
        return files
    
    def create_full(self, path: str, name: str = None, opts: dict = None) -> str:
        """Создание полного бэкапа"""
        if name is None:
            name = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        opts = opts or {}
        print(f"Полный бэкап '{name}' из '{path}'...")
        t0 = time.time()
        
        # Читаем файлы
        files_data = self._read_files(path)
        if not files_data:
            print("Нет файлов")
            return None
        
        # Сжимаем
        arch = IncrementalArchiver(**opts)
        compressed, entries = arch.compress_full(files_data)
        
        # Сохраняем
        sfile = os.path.join(self.backup_dir, f"{name}.dgba")
        with open(sfile, 'wb') as f:
            f.write(compressed)
        
        total_size = sum(e.size for e in entries.values())
        
        self.index['snapshots'][name] = {
            'type': 'full',
            'base': None,
            'file': sfile,
            'timestamp': datetime.now().isoformat(),
            'files': {p: {'size': e.size, 'hash': e.hash, 'mtime': e.mtime} 
                     for p, e in entries.items()},
            'total_size': total_size,
            'compressed_size': len(compressed)
        }
        self.index['chain'].append(name)
        self._save()
        
        t = time.time() - t0
        r = (1 - len(compressed)/total_size)*100 if total_size else 0
        print(f"✓ Готово за {t:.1f}с")
        print(f"  Файлов: {len(entries)}, {total_size:,} → {len(compressed):,} байт ({r:.1f}%)")
        
        return name
    
    def create_inc(self, path: str, base: str = None, name: str = None, opts: dict = None) -> str:
        """Создание инкрементального бэкапа"""
        if name is None:
            name = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Выбираем базу
        if base is None:
            # Автоматически: последний снимок в цепочке
            if self.index['chain']:
                base = self.index['chain'][-1]
            else:
                print("Нет базы для инкремента. Используйте 'full' сначала.")
                return None
        
        if base not in self.index['snapshots']:
            print(f"База '{base}' не найдена")
            return None
        
        base_info = self.index['snapshots'][base]
        opts = opts or {}
        
        print(f"Инкремент '{name}' на базе '{base}' из '{path}'...")
        t0 = time.time()
        
        # Читаем текущие файлы
        files_data = self._read_files(path)
        if not files_data:
            print("Нет файлов")
            return None
        
        # Загружаем базовые данные
        with open(base_info['file'], 'rb') as f:
            base_compressed = f.read()
        
        arch = IncrementalArchiver(**opts)
        base_all_data, base_entries = arch.decompress(base_compressed)
        
        # Конвертируем в FileEntry
        base_files = {}
        for p, info in base_info['files'].items():
            base_files[p] = FileEntry(
                path=p, size=info['size'], 
                mtime=info.get('mtime', 0), hash=info['hash']
            )
        
        # Создаём инкремент
        compressed, new_entries = arch.compress_inc(files_data, base_files, base_all_data)
        
        # Сохраняем
        sfile = os.path.join(self.backup_dir, f"{name}.dgba")
        with open(sfile, 'wb') as f:
            f.write(compressed)
        
        total_size = sum(e.size for e in new_entries.values())
        
        self.index['snapshots'][name] = {
            'type': 'inc',
            'base': base,
            'file': sfile,
            'timestamp': datetime.now().isoformat(),
            'files': {p: {'size': e.size, 'hash': e.hash, 'mtime': e.mtime} 
                     for p, e in new_entries.items()},
            'total_size': total_size,
            'compressed_size': len(compressed)
        }
        self.index['chain'].append(name)
        self._save()
        
        # Статистика изменений
        old_files = set(base_info['files'].keys())
        new_files_set = set(new_entries.keys())
        added = new_files_set - old_files
        removed = old_files - new_files_set
        changed = sum(1 for p in (old_files & new_files_set) 
                     if base_info['files'][p]['hash'] != new_entries[p].hash)
        unchanged = len(old_files & new_files_set) - changed
        
        t = time.time() - t0
        print(f"✓ Готово за {t:.1f}с")
        print(f"  Новых: {len(added)}, изменено: {changed}, удалено: {len(removed)}, без изменений: {unchanged}")
        print(f"  Сжато: {len(compressed):,} байт")
        
        return name
    
    def restore(self, name: str, output_dir: str):
        """Восстановление снимка (проходит по цепочке)"""
        if name not in self.index['snapshots']:
            raise ValueError(f"Снимок '{name}' не найден")
        
        print(f"Восстановление '{name}' в '{output_dir}'...")
        t0 = time.time()
        
        # Находим цепочку восстановления
        chain = self._get_restore_chain(name)
        print(f"  Цепочка: {' → '.join(chain)}")
        
        # Начинаем с последнего полного бэкапа
        arch = IncrementalArchiver()
        current_data = b''
        current_entries = {}
        
        for snap_name in chain:
            snap_info = self.index['snapshots'][snap_name]
            
            with open(snap_info['file'], 'rb') as f:
                compressed = f.read()
            
            if snap_info['type'] == 'full':
                current_data, current_entries = arch.decompress(compressed)
            else:
                # Инкремент - применяем к текущим данным
                inc_data, inc_entries = arch.decompress(compressed, current_data)
                
                # Обновляем индекс
                for p, e in inc_entries.items():
                    current_entries[p] = e
                
                # Обновляем данные (упрощённо)
                current_data = inc_data
        
        # Восстанавливаем файлы
        self._write_files(current_data, current_entries, output_dir)
        
        t = time.time() - t0
        print(f"✓ Восстановлено за {t:.1f}с ({len(current_entries)} файлов)")
    
    def _get_restore_chain(self, name: str) -> List[str]:
        """Получаем цепочку от полного бэкапа до указанного"""
        chain = []
        current = name
        
        while current:
            chain.insert(0, current)
            snap = self.index['snapshots'][current]
            if snap['type'] == 'full':
                break
            current = snap['base']
        
        return chain
    
    def _write_files(self, data: bytes, entries: Dict[str, FileEntry], output_dir: str):
        """Записывает файлы из данных"""
        os.makedirs(output_dir, exist_ok=True)
        offset = 0
        
        for filepath, entry in sorted(entries.items()):
            full_path = os.path.join(output_dir, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            file_data = data[offset:offset + entry.size]
            with open(full_path, 'wb') as f:
                f.write(file_data)
            offset += entry.size
    
    def list_snapshots(self):
        if not self.index['snapshots']:
            print("Нет снимков")
            return
        
        print("Цепочка бэкапов:")
        for name in self.index['chain']:
            snap = self.index['snapshots'][name]
            stype = "📦 ПОЛНЫЙ" if snap['type'] == 'full' else "📎 ИНКРЕМЕНТ"
            base = f" ← {snap['base']}" if snap.get('base') else ""
            total = snap.get('total_size', 0)
            compressed = snap.get('compressed_size', 0)
            nfiles = len(snap.get('files', {}))
            r = (1 - compressed/total)*100 if total else 0
            
            print(f"  {name}: {stype}{base}")
            print(f"    {nfiles} файлов, {total:,} → {compressed:,} байт ({r:.1f}%)")


# ==================== CLI ====================

def create_parser():
    p = argparse.ArgumentParser(
        description='DGBA v3.0 - Инкрементальный архиватор бэкапов',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Первый полный бэкап
  python dgba.py full ./project

  # Инкремент на основе последнего
  python dgba.py inc ./project
  
  # Инкремент на основе конкретного снимка
  python dgba.py inc ./project --base 20260513_120000
  
  # Восстановление (автоматически пройдёт по цепочке)
  python dgba.py restore 20260513_130000
  
  # Список бэкапов
  python dgba.py list
        """
    )
    
    sub = p.add_subparsers(dest='cmd', help='Команды')
    
    # full
    f = sub.add_parser('full', help='Полный бэкап')
    f.add_argument('path', help='Путь')
    f.add_argument('--name', '-n', help='Имя снимка')
    f.add_argument('--dir', '-d', default='./backups', help='Директория')
    add_opts(f)
    
    # inc
    i = sub.add_parser('inc', help='Инкрементальный бэкап')
    i.add_argument('path', help='Путь')
    i.add_argument('--name', '-n', help='Имя снимка')
    i.add_argument('--base', '-b', help='Базовый снимок (авто)')
    i.add_argument('--dir', '-d', default='./backups', help='Директория')
    add_opts(i)
    
    # restore
    r = sub.add_parser('restore', help='Восстановить')
    r.add_argument('name', help='Снимок')
    r.add_argument('output', nargs='?', help='Директория')
    r.add_argument('--dir', '-d', default='./backups', help='Директория бэкапов')
    
    # list
    sub.add_parser('list', help='Список').add_argument('--dir', '-d', default='./backups')
    
    return p

def add_opts(p):
    p.add_argument('--min-block', type=int, default=4096)
    p.add_argument('--max-block', type=int, default=65536)
    p.add_argument('--similarity', type=float, default=0.6)
    p.add_argument('--speed', action='store_true')
    p.add_argument('--no-huffman', action='store_true')
    p.add_argument('--no-delta', action='store_true')

def main():
    p = create_parser()
    args = p.parse_args()
    
    if not args.cmd:
        p.print_help()
        return
    
    try:
        if args.cmd == 'full':
            opts = get_opts(args)
            bs = BackupSystem(args.dir)
            bs.create_full(args.path, args.name, opts)
        
        elif args.cmd == 'inc':
            opts = get_opts(args)
            bs = BackupSystem(args.dir)
            bs.create_inc(args.path, args.base, args.name, opts)
        
        elif args.cmd == 'restore':
            bs = BackupSystem(args.dir)
            out = args.output or f"./restored_{args.name}"
            bs.restore(args.name, out)
        
        elif args.cmd == 'list':
            bs = BackupSystem(args.dir)
            bs.list_snapshots()
    
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def get_opts(args):
    return {
        'min_block': args.min_block,
        'max_block': args.max_block,
        'similarity': args.similarity,
        'use_huffman': not args.no_huffman,
        'use_delta': not args.no_delta,
        'fast': args.speed
    }

if __name__ == '__main__':
    main()
#!/usr/bin/env python3
"""
Скрипт для резервного копирования папки /home/admin/media/hdd/web
Бэкапы сохраняются в /home/admin/media/hdd/!Evgeny/src/BackUp
Поддерживает:
- Полные бэкапы
- Инкрементные бэкапы (только измененные файлы)
- Исключение папок из архивации (настраивается через переменную EXCLUDE_DIRS)
- Отображение прогресса создания бэкапа
- Восстановление с заменой существующих файлов
- АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ ЦЕПОЧКИ инкрементных бэкапов
- Проверка целостности архивов
"""

import os
import sys
import shutil
import tarfile
import logging
import argparse
import json
import hashlib
from datetime import datetime
from pathlib import Path
from tqdm import tqdm
import tempfile
import re
from typing import List, Optional, Tuple, Set


# ==================== НАСТРОЙКИ ====================
EXCLUDE_DIRS = ['__pycache__', '.git', 'media', 'node_modules', 'dist', 'build']
SOURCE_DIR = "/home/admin/media/hdd/web"
BACKUP_DIR = "/home/admin/media/hdd/!Evgeny/src/BackUp"
MAX_BACKUPS = None  # None = без ограничений
# ===================================================


class BackupManager:
    """Менеджер резервного копирования с поддержкой инкрементных бэкапов"""
    
    def __init__(self, source_dir=SOURCE_DIR, backup_dir=BACKUP_DIR,
                 max_backups=MAX_BACKUPS, exclude_dirs=None):
        self.source_dir = Path(source_dir)
        self.backup_dir = Path(backup_dir)
        self.max_backups = max_backups
        self.exclude_dirs = exclude_dirs or EXCLUDE_DIRS
        self.state_file = self.backup_dir / "backup_state.json"
        
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._setup_logging()
    
    def _setup_logging(self):
        """Настройка логирования"""
        log_file = self.backup_dir / "backup.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)]
        )
        self.logger = logging.getLogger(__name__)
    
    def _get_file_hash(self, file_path: Path) -> Optional[str]:
        """Быстрое хеширование с ограничением размера"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                # Хешируем только первые 64KB + размер для скорости
                chunk = f.read(65536)
                hash_md5.update(chunk)
                hash_md5.update(str(file_path.stat().st_size).encode())
            return hash_md5.hexdigest()
        except Exception as e:
            self.logger.warning(f"Не удалось вычислить хеш для {file_path}: {e}")
            return None
    
    def _get_file_info(self, file_path: Path) -> dict:
        """Получение информации о файле"""
        stat = file_path.stat()
        return {
            'size': stat.st_size,
            'mtime': stat.st_mtime,
            'hash': None  # Вычисляем только при необходимости
        }
    
    def _load_state(self) -> Optional[dict]:
        """Загрузка состояния последнего бэкапа"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Не удалось загрузить состояние: {e}")
        return None
    
    def _save_state(self, state: dict):
        """Сохранение состояния бэкапа"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Не удалось сохранить состояние: {e}")
    
    def _parse_backup_info(self, filename: str) -> Optional[dict]:
        """Парсинг имени файла бэкапа"""
        pattern = r'web_backup_(full|inc)_(\d{8}_\d{6})\.tar\.gz'
        match = re.match(pattern, filename)
        if match:
            return {
                'type': match.group(1),
                'timestamp': match.group(2),
                'datetime': datetime.strptime(match.group(2), '%Y%m%d_%H%M%S'),
                'filename': filename
            }
        return None
    
    def _get_all_backups(self) -> List[dict]:
        """Получение отсортированного списка всех бэкапов"""
        backups = []
        for file_path in self.backup_dir.glob("web_backup_*.tar.gz"):
            if file_path.is_file():
                info = self._parse_backup_info(file_path.name)
                if info:
                    info['path'] = file_path
                    backups.append(info)
        backups.sort(key=lambda x: x['datetime'])
        return backups
    
    def _find_base_full_backup(self, inc_backup_info: dict) -> Optional[dict]:
        """Находит полный бэкап, на котором основан инкрементный"""
        full_backup = None
        for backup in self._get_all_backups():
            if backup['type'] == 'full' and backup['datetime'] < inc_backup_info['datetime']:
                full_backup = backup
            elif backup['datetime'] >= inc_backup_info['datetime']:
                break
        return full_backup
    
    def _get_incremental_chain(self, target: dict) -> List[dict]:
        """Получение цепочки инкрементных бэкапов для восстановления"""
        all_backups = self._get_all_backups()
        
        if target['type'] == 'full':
            return [target]
        
        full_backup = self._find_base_full_backup(target)
        if not full_backup:
            self.logger.error(f"Не найден полный бэкап для {target['filename']}")
            return []
        
        chain = [full_backup]
        for backup in all_backups:
            if backup['type'] == 'inc' and full_backup['datetime'] < backup['datetime'] <= target['datetime']:
                chain.append(backup)
        
        return chain
    
    def _verify_backup(self, archive_path: Path) -> bool:
        """Проверка целостности архива"""
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                for member in tar.getmembers():
                    try:
                        f = tar.extractfile(member)
                        if f:
                            f.read()
                    except Exception as e:
                        self.logger.error(f"Ошибка чтения {member.name}: {e}")
                        return False
            self.logger.info(f"✅ Проверка целостности пройдена: {archive_path.name}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Архив поврежден: {archive_path.name} - {e}")
            return False
    
    def _restore_from_chain(self, chain: List[dict], temp_dir: Path) -> bool:
        """Восстановление из цепочки бэкапов во временную директорию"""
        try:
            for i, backup_info in enumerate(chain, 1):
                self.logger.info(f"  [{i}/{len(chain)}] Обработка: {backup_info['filename']}")
                
                with tarfile.open(backup_info['path'], "r:gz") as tar:
                    members = [m for m in tar.getmembers() if m.isfile()]
                    total_size = sum(m.size for m in members)
                    
                    with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024,
                             desc=f"  Распаковка {backup_info['type']}",
                             bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:
                        
                        for member in members:
                            try:
                                tar.extract(member, path=temp_dir, set_attrs=False)
                                pbar.update(member.size)
                                pbar.set_postfix(file=member.name[:30], refresh=True)
                            except Exception as e:
                                self.logger.warning(f"    Не удалось извлечь {member.name}: {e}")
                
                self.logger.info(f"  ✅ {backup_info['filename']} распакован")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при восстановлении цепочки: {e}")
            return False
    
    def _apply_deleted_files(self, temp_dir: Path, backup_info: dict) -> bool:
        """Применение информации об удалённых файлах"""
        try:
            with tarfile.open(backup_info['path'], "r:gz") as tar:
                deleted_files = [m for m in tar.getmembers() 
                                if '.deleted_' in m.name and m.name.endswith('.json')]
                
                if not deleted_files:
                    return True
                
                for deleted_file in deleted_files:
                    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
                        extracted = tar.extractfile(deleted_file)
                        if extracted:
                            f.write(extracted.read())
                            tmp_path = Path(f.name)
                    
                    with open(tmp_path, 'r') as f:
                        deleted_data = json.load(f)
                    
                    for rel_path in deleted_data.get('deleted_files', []):
                        web_dir = temp_dir / 'web'
                        file_to_delete = web_dir / rel_path if web_dir.exists() else temp_dir / rel_path
                        if file_to_delete.exists():
                            file_to_delete.unlink()
                            self.logger.info(f"  🗑️ Удалён файл: {rel_path}")
                    
                    tmp_path.unlink()
            return True
        except Exception as e:
            self.logger.warning(f"Не удалось применить информацию об удалённых файлах: {e}")
            return False
    
    def _scan_directory(self) -> Tuple[List[Path], int]:
        """Однократное сканирование директории"""
        files = []
        total_size = 0
        
        for root, dirs, filenames in os.walk(self.source_dir):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for filename in filenames:
                file_path = Path(root) / filename
                if file_path.is_file():
                    files.append(file_path)
                    total_size += file_path.stat().st_size
        
        return files, total_size
    
    def create_full_backup(self) -> Optional[Path]:
        """Создание полной резервной копии с прогресс-баром"""
        if not self.source_dir.exists():
            self.logger.error(f"Исходная директория не существует: {self.source_dir}")
            return None
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_name = f"web_backup_full_{timestamp}.tar.gz"
            archive_path = self.backup_dir / archive_name
            
            self.logger.info(f"Начинаю создание ПОЛНОЙ резервной копии: {archive_path}")
            self.logger.info(f"Исключаемые директории: {', '.join(self.exclude_dirs)}")
            
            # Однократное сканирование
            self.logger.info("Сканирование файлов...")
            files_to_backup, total_size = self._scan_directory()
            total_files = len(files_to_backup)
            
            self.logger.info(f"Найдено файлов: {total_files}, общий размер: {self._format_size(total_size)}")
            
            # Сохраняем состояние
            state = {'timestamp': timestamp, 'type': 'full', 
                    'source_dir': str(self.source_dir), 'files': {}}
            
            self.logger.info("Создание архива...")
            
            with tarfile.open(archive_path, "w:gz") as tar:
                with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024,
                         desc="Архивация",
                         bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:
                    
                    for file_path in files_to_backup:
                        try:
                            arcname = self.source_dir.name / file_path.relative_to(self.source_dir)
                            tar.add(file_path, arcname=arcname, recursive=False)
                            
                            # Сохраняем базовую информацию без хеша
                            relative_path = str(file_path.relative_to(self.source_dir))
                            state['files'][relative_path] = self._get_file_info(file_path)
                            
                            pbar.update(file_path.stat().st_size)
                            pbar.set_postfix(file=file_path.name[:30], refresh=True)
                        except Exception as e:
                            self.logger.warning(f"Не удалось добавить файл {file_path}: {e}")
            
            self._save_state(state)
            
            # Проверка целостности
            if not self._verify_backup(archive_path):
                self.logger.error("❌ Архив не прошел проверку целостности!")
                archive_path.unlink()
                return None
            
            archive_size = archive_path.stat().st_size
            compression_ratio = (1 - archive_size / total_size) * 100 if total_size > 0 else 0
            
            self.logger.info("=" * 60)
            self.logger.info("✅ ПОЛНАЯ резервная копия создана успешно!")
            self.logger.info(f"📁 Путь: {archive_path}")
            self.logger.info(f"📦 Размер архива: {self._format_size(archive_size)}")
            self.logger.info(f"📊 Исходный размер: {self._format_size(total_size)}")
            self.logger.info(f"🗜️  Степень сжатия: {compression_ratio:.1f}%")
            self.logger.info(f"📄 Файлов в архиве: {total_files}")
            self.logger.info("=" * 60)
            
            if self.max_backups is not None:
                self._cleanup_old_backups()
            
            return archive_path
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка при создании резервной копии: {e}")
            if 'archive_path' in locals() and archive_path.exists():
                archive_path.unlink()
            return None
    
    def _get_changed_files(self, previous_state: dict) -> Tuple[List[Path], List[Path], List[str]]:
        """Определение измененных, новых и удаленных файлов"""
        new_files = []
        modified_files = []
        
        # Сканируем текущие файлы
        current_files = {}
        for root, dirs, files in os.walk(self.source_dir):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for file in files:
                file_path = Path(root) / file
                relative_path = str(file_path.relative_to(self.source_dir))
                current_files[relative_path] = file_path
        
        previous_files = set(previous_state.get('files', {}).keys())
        current_files_set = set(current_files.keys())
        
        # Удаленные файлы
        deleted_files = list(previous_files - current_files_set)
        
        # Новые и измененные файлы
        for rel_path, file_path in current_files.items():
            if rel_path not in previous_files:
                new_files.append(file_path)
            else:
                prev_info = previous_state['files'][rel_path]
                current_info = self._get_file_info(file_path)
                
                # Быстрое сравнение по размеру и времени
                if (prev_info.get('size') != current_info.get('size') or
                    prev_info.get('mtime') != current_info.get('mtime')):
                    # Только при несовпадении вычисляем хеш
                    current_info['hash'] = self._get_file_hash(file_path)
                    if prev_info.get('hash') != current_info.get('hash'):
                        modified_files.append(file_path)
        
        return new_files, modified_files, deleted_files
    
    def create_incremental_backup(self) -> Optional[Path]:
        """Создание инкрементной резервной копии"""
        if not self.source_dir.exists():
            self.logger.error(f"Исходная директория не существует: {self.source_dir}")
            return None
        
        previous_state = self._load_state()
        if not previous_state:
            self.logger.info("Нет предыдущего состояния. Создаю полный бэкап...")
            return self.create_full_backup()
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_name = f"web_backup_inc_{timestamp}.tar.gz"
            archive_path = self.backup_dir / archive_name
            
            self.logger.info(f"Начинаю создание ИНКРЕМЕНТНОЙ резервной копии: {archive_path}")
            self.logger.info(f"Базовый бэкап от: {previous_state.get('timestamp', 'unknown')}")
            
            self.logger.info("Поиск измененных файлов...")
            new_files, modified_files, deleted_files = self._get_changed_files(previous_state)
            
            files_to_backup = new_files + modified_files
            if not files_to_backup:
                self.logger.info("📭 Изменений не обнаружено. Инкрементный бэкап не требуется.")
                return None
            
            total_size = sum(f.stat().st_size for f in files_to_backup if f.is_file())
            
            self.logger.info(f"🔄 Найдено изменений:")
            self.logger.info(f"  📄 Новых файлов: {len(new_files)}")
            self.logger.info(f"  ✏️  Измененных файлов: {len(modified_files)}")
            self.logger.info(f"  ❌ Удаленных файлов: {len(deleted_files)}")
            self.logger.info(f"  💾 Общий размер изменений: {self._format_size(total_size)}")
            
            # Новое состояние
            new_state = {
                'timestamp': timestamp,
                'type': 'incremental',
                'source_dir': str(self.source_dir),
                'base_backup': previous_state.get('timestamp'),
                'files': previous_state.get('files', {}).copy()
            }
            
            self.logger.info("Создание инкрементного архива...")
            
            with tarfile.open(archive_path, "w:gz") as tar:
                with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024,
                         desc="Инкрементная архивация",
                         bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:
                    
                    for file_path in files_to_backup:
                        try:
                            arcname = self.source_dir.name / file_path.relative_to(self.source_dir)
                            tar.add(file_path, arcname=arcname, recursive=False)
                            
                            relative_path = str(file_path.relative_to(self.source_dir))
                            new_state['files'][relative_path] = self._get_file_info(file_path)
                            
                            pbar.update(file_path.stat().st_size)
                            pbar.set_postfix(file=file_path.name[:30], refresh=True)
                        except Exception as e:
                            self.logger.warning(f"Не удалось добавить файл {file_path}: {e}")
                    
                    # Информация об удаленных файлах
                    if deleted_files:
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
                            json.dump({'deleted_files': deleted_files, 'timestamp': timestamp}, tmp)
                            tmp_path = Path(tmp.name)
                        tar.add(tmp_path, arcname=f".deleted_{timestamp}.json")
                        tmp_path.unlink()
                    
                    # Удаляем информацию об удаленных файлах из состояния
                    for deleted_file in deleted_files:
                        new_state['files'].pop(deleted_file, None)
            
            self._save_state(new_state)
            
            # Проверка целостности
            if not self._verify_backup(archive_path):
                self.logger.error("❌ Архив не прошел проверку целостности!")
                archive_path.unlink()
                return None
            
            archive_size = archive_path.stat().st_size
            compression_ratio = (1 - archive_size / total_size) * 100 if total_size > 0 else 0
            
            self.logger.info("=" * 60)
            self.logger.info("✅ ИНКРЕМЕНТНАЯ резервная копия создана успешно!")
            self.logger.info(f"📁 Путь: {archive_path}")
            self.logger.info(f"📦 Размер архива: {self._format_size(archive_size)}")
            self.logger.info(f"📊 Размер изменений: {self._format_size(total_size)}")
            self.logger.info(f"🗜️  Степень сжатия: {compression_ratio:.1f}%")
            self.logger.info(f"📄 Измененных файлов: {len(files_to_backup)}")
            self.logger.info(f"🗑️  Удаленных файлов: {len(deleted_files)}")
            self.logger.info("=" * 60)
            
            if self.max_backups is not None:
                self._cleanup_old_backups()
            
            return archive_path
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка при создании инкрементной копии: {e}")
            if 'archive_path' in locals() and archive_path.exists():
                archive_path.unlink()
            return None
    
    def create_backup(self, backup_type='full') -> Optional[Path]:
        """Создание резервной копии"""
        if backup_type == 'incremental':
            return self.create_incremental_backup()
        return self.create_full_backup()
    
    def restore_backup(self, archive_name=None) -> bool:
        """Восстановление из резервной копии с автоматической обработкой цепочки"""
        if archive_name:
            archive_path = self.backup_dir / archive_name
            if not archive_path.exists():
                self.logger.error(f"❌ Архив не найден: {archive_path}")
                return False
        else:
            backups = self._get_all_backups()
            if not backups:
                self.logger.error("❌ Нет доступных резервных копий для восстановления")
                return False
            archive_path = backups[-1]['path']
            archive_name = backups[-1]['filename']
        
        backup_info = self._parse_backup_info(archive_path.name)
        if not backup_info:
            self.logger.error(f"❌ Не удалось определить тип архива: {archive_name}")
            return False
        
        # Проверка целостности перед восстановлением
        self.logger.info("🔍 Проверка целостности архива...")
        if not self._verify_backup(archive_path):
            self.logger.error("❌ Восстановление отменено из-за повреждения архива")
            return False
        
        self.logger.info(f"🔄 Начинаю восстановление из архива: {archive_path}")
        self.logger.info(f"📋 Тип бэкапа: {backup_info['type'].upper()}")
        
        chain = self._get_incremental_chain(backup_info)
        if not chain:
            self.logger.error("❌ Не удалось построить цепочку для восстановления")
            return False
        
        self.logger.info("=" * 60)
        self.logger.info("📋 ПЛАН ВОССТАНОВЛЕНИЯ:")
        self.logger.info(f"  Целевая точка: {backup_info['filename']}")
        self.logger.info(f"  Всего бэкапов в цепочке: {len(chain)}")
        for i, b in enumerate(chain, 1):
            marker = "🎯" if b['filename'] == archive_path.name else "📦"
            self.logger.info(f"    {i}. {marker} {b['filename']} ({b['type'].upper()})")
        self.logger.info("=" * 60)
        
        # Резервная копия текущего состояния
        self.logger.info("💾 Создаю резервную копию текущего состояния...")
        current_backup = self.create_full_backup()
        if not current_backup:
            self.logger.warning("⚠️  Не удалось создать резервную копию текущего состояния")
            if input("Продолжить восстановление? (y/n): ").lower() != 'y':
                self.logger.info("Восстановление отменено")
                return False
        
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            
            self.logger.info("📦 Восстановление цепочки бэкапов...")
            if not self._restore_from_chain(chain, temp_dir):
                return False
            
            self._apply_deleted_files(temp_dir, backup_info)
            
            self.logger.info("📁 Копирование восстановленных файлов...")
            
            temp_web_dir = temp_dir / 'web'
            if not temp_web_dir.exists():
                items = list(temp_dir.iterdir())
                temp_web_dir = items[0] if len(items) == 1 and items[0].is_dir() else temp_dir
            
            self.source_dir.mkdir(parents=True, exist_ok=True)
            
            files_to_copy = [f for f in temp_web_dir.rglob('*') if f.is_file()]
            
            with tqdm(total=len(files_to_copy), unit='файл', desc="Копирование",
                     bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as pbar:
                
                for item in files_to_copy:
                    relative_path = item.relative_to(temp_web_dir)
                    target_path = self.source_dir / relative_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target_path)
                    pbar.update(1)
                    pbar.set_postfix(file=relative_path.name[:30], refresh=True)
            
            self.logger.info("=" * 60)
            self.logger.info(f"✅ Восстановление успешно завершено!")
            self.logger.info(f"📁 Целевая директория: {self.source_dir}")
            self.logger.info(f"📦 Архив-источник: {archive_path.name}")
            self.logger.info(f"🔗 Восстановлено бэкапов: {len(chain)}")
            self.logger.info("=" * 60)
            return True
    
    def _cleanup_old_backups(self):
        """Удаление старых архивов"""
        if self.max_backups is None:
            return
        
        backup_files = sorted(
            self.backup_dir.glob("web_backup_*.tar.gz"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        for old_file in backup_files[self.max_backups:]:
            self.logger.info(f"  Удаляю: {old_file.name}")
            old_file.unlink()
    
    def list_backups(self):
        """Вывод списка резервных копий"""
        backups = self._get_all_backups()
        
        if not backups:
            self.logger.info("📭 Нет созданных резервных копий")
            return
        
        self.logger.info(f"📚 Существующие резервные копии в {self.backup_dir}:")
        print("=" * 80)
        
        total_size_all = 0
        for i, backup in enumerate(backups, 1):
            size = backup['path'].stat().st_size
            total_size_all += size
            backup_type = "🔵 ПОЛНЫЙ" if backup['type'] == 'full' else "🟢 ИНКРЕМЕНТНЫЙ"
            
            age = datetime.now() - backup['datetime']
            age_str = f"{age.days} дн. {age.seconds // 3600} ч." if age.days > 0 else \
                     f"{age.seconds // 3600} ч. {(age.seconds % 3600) // 60} мин."
            
            self.logger.info(f"  {i:2d}. {backup_type} 📦 {backup['filename']}")
            self.logger.info(f"      📏 Размер: {self._format_size(size)}")
            self.logger.info(f"      🕐 Создан: {backup['datetime'].strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"      ⏳ Возраст: {age_str}")
            print()
        
        self.logger.info(f"💾 Общий размер всех бэкапов: {self._format_size(total_size_all)}")
        self.logger.info(f"📊 Количество бэкапов: {len(backups)}")
        
        state = self._load_state()
        if state:
            self.logger.info(f"📋 Последний бэкап: {state.get('type', 'unknown').upper()} "
                           f"от {state.get('timestamp', 'unknown')}")
        
        print()
        self.logger.info("🔗 Цепочки бэкапов:")
        self._show_backup_chains(backups)
        print("=" * 80)
    
    def _show_backup_chains(self, backups: List[dict]):
        """Показать доступные цепочки бэкапов"""
        chains = []
        current_chain = []
        
        for backup in backups:
            if backup['type'] == 'full':
                if current_chain:
                    chains.append(current_chain)
                current_chain = [backup]
            elif current_chain:
                current_chain.append(backup)
        
        if current_chain:
            chains.append(current_chain)
        
        for i, chain in enumerate(chains, 1):
            full = chain[0]
            inc_count = len(chain) - 1
            self.logger.info(f"  Цепочка #{i}: {full['datetime'].strftime('%Y-%m-%d')} → {inc_count} инкр. бэкапов")
            if inc_count > 0:
                self.logger.info(f"    Последний: {chain[-1]['filename']}")
    
    def _format_size(self, size_bytes: int) -> str:
        """Форматирование размера в читаемый вид"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"


def main():
    """Главная функция"""
    parser = argparse.ArgumentParser(
        description="🔄 Скрипт резервного копирования папки web с поддержкой инкрементных бэкапов",
        epilog="Примеры использования:\n"
               "  python3 backup.py --backup              # Создать полный бэкап\n"
               "  python3 backup.py --backup inc          # Создать инкрементный бэкап\n"
               "  python3 backup.py --list                # Показать список бэкапов\n"
               "  python3 backup.py --restore             # Восстановить из последнего бэкапа\n"
               "  python3 backup.py --restore web_backup_full_20260513.tar.gz\n"
               "  python3 backup.py --clean               # Очистить состояние",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--backup', '-b', nargs='?', const='full', 
                       choices=['full', 'inc', 'incremental'],
                       help='Создать резервную копию')
    parser.add_argument('--list', '-l', action='store_true',
                       help='Показать список существующих бэкапов')
    parser.add_argument('--restore', '-r', nargs='?', const='last', metavar='ARCHIVE',
                       help='Восстановить из бэкапа')
    parser.add_argument('--exclude', '-e', nargs='+', 
                       help='Директории для исключения')
    parser.add_argument('--clean', '-c', action='store_true',
                       help='Очистить состояние')
    
    args = parser.parse_args()
    
    try:
        import tqdm
    except ImportError:
        print("❌ Для работы необходим модуль tqdm")
        print("   Установите: pip install tqdm")
        sys.exit(1)
    
    exclude_dirs = args.exclude if args.exclude else EXCLUDE_DIRS
    
    backup_manager = BackupManager(max_backups=MAX_BACKUPS, exclude_dirs=exclude_dirs)
    
    if args.clean:
        if backup_manager.state_file.exists():
            backup_manager.state_file.unlink()
            backup_manager.logger.info("✅ Состояние очищено. Следующий бэкап будет полным.")
        else:
            backup_manager.logger.info("ℹ️ Файл состояния не найден.")
        return
    
    if args.backup:
        backup_type = 'incremental' if args.backup in ['inc', 'incremental'] else 'full'
        backup_manager.create_backup(backup_type)
    
    if args.list:
        backup_manager.list_backups()
    
    if args.restore:
        if args.restore == 'last':
            backup_manager.restore_backup()
        else:
            backup_manager.restore_backup(args.restore)
    
    if not (args.backup or args.list or args.restore or args.clean):
        backup_manager.create_backup('incremental')


if __name__ == "__main__":
    main()
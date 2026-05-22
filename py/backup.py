#!/usr/bin/env python3
"""
Скрипт для резервного копирования /home/admin/media/hdd/web
Бэкапы в /home/admin/media/hdd/!Evgeny/src/BackUp
"""

import os
import sys
import shutil
import tarfile
import logging
import argparse
import json
import hashlib
import tempfile
import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Optional

from rich.console import Console
from rich.progress import (
    Progress, BarColumn, TextColumn, FileSizeColumn,
    SpinnerColumn, TimeRemainingColumn
)
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.columns import Columns
from rich.box import SIMPLE, ROUNDED, HEAVY


EXCLUDE_DIRS = ['__pycache__', '.git', '.venv', '.vscode', 'media', 'node_modules', 'dist', 'build']
SOURCE_DIR = "/home/admin/media/hdd/web"
BACKUP_DIR = "/home/admin/media/hdd/!Evgeny/src/BackUp"
MAX_BACKUPS = None


# ═══════════════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ═══════════════════════════════════════════════════════════════════════════════

def format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_ext(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return ext if ext else "(нет)"


def parse_backup_info(filename: str) -> Optional[dict]:
    match = re.match(r'web_backup_(full|inc)_(\d{8}_\d{6})\.tar\.gz', filename)
    if match:
        return {
            'type': match.group(1),
            'timestamp': match.group(2),
            'datetime': datetime.strptime(match.group(2), '%Y%m%d_%H%M%S'),
            'filename': filename
        }
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# BackupManager
# ═══════════════════════════════════════════════════════════════════════════════

class BackupManager:
    def __init__(self, source_dir=SOURCE_DIR, backup_dir=BACKUP_DIR,
                 max_backups=MAX_BACKUPS, exclude_dirs=None, skip_symlink_check=False):
        self.source_dir = Path(source_dir)
        self.backup_dir = Path(backup_dir)
        self.max_backups = max_backups
        self.exclude_dirs = exclude_dirs or EXCLUDE_DIRS
        self.state_file = self.backup_dir / "backup_state.json"
        self.console = Console()
        self.skip_symlink_check = skip_symlink_check
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._setup_logging()

    def _setup_logging(self):
        log_file = self.backup_dir / "backup.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        rich_handler = logging.StreamHandler()
        rich_handler.setFormatter(logging.Formatter('%(message)s'))
        logging.basicConfig(level=logging.INFO, handlers=[rich_handler, file_handler])
        self.logger = logging.getLogger("backup")

    def _load_state(self) -> Optional[dict]:
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _save_state(self, state: dict):
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception:
            pass

    def _get_file_info(self, file_path: Path) -> dict:
        stat = file_path.stat()
        return {'size': stat.st_size, 'mtime': stat.st_mtime, 'hash': None}

    def _get_file_hash(self, file_path: Path) -> Optional[str]:
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                hash_md5.update(f.read(65536))
                hash_md5.update(str(file_path.stat().st_size).encode())
            return hash_md5.hexdigest()
        except Exception:
            return None

    def _walk_source_dir(self) -> dict:
        files = {}
        for root, dirs, filenames in os.walk(self.source_dir):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for filename in filenames:
                file_path = Path(root) / filename
                if file_path.is_file() or file_path.is_symlink():
                    rel_path = str(file_path.relative_to(self.source_dir)).replace('\\', '/')
                    files[rel_path] = file_path
        return files

    def _get_all_backups(self) -> list:
        backups = []
        for file_path in self.backup_dir.glob("web_backup_*.tar.gz"):
            if file_path.is_file():
                info = parse_backup_info(file_path.name)
                if info:
                    info['path'] = file_path
                    backups.append(info)
        return sorted(backups, key=lambda x: x['datetime'])

    def _get_incremental_chain(self, target: dict) -> list:
        all_backups = self._get_all_backups()
        if target['type'] == 'full':
            return [target]

        full_backup = None
        for backup in all_backups:
            if backup['type'] == 'full' and backup['datetime'] < target['datetime']:
                full_backup = backup
            elif backup['datetime'] >= target['datetime']:
                break

        if not full_backup:
            return []

        chain = [full_backup]
        for backup in all_backups:
            if backup['type'] == 'inc' and full_backup['datetime'] < backup['datetime'] <= target['datetime']:
                chain.append(backup)
        return chain

    def _cleanup_old_backups(self):
        if not self.max_backups:
            return
        backup_files = sorted(
            self.backup_dir.glob("web_backup_*.tar.gz"),
            key=lambda x: x.stat().st_mtime, reverse=True
        )
        for old_file in backup_files[self.max_backups:]:
            old_file.unlink()

    def _print_header(self, title: str, subtitle: str = None):
        self.console.print()
        self.console.print(Panel(
            f"[bold white]{title}[/bold white]",
            box=HEAVY, border_style="cyan", padding=(1, 2)
        ))
        if subtitle:
            self.console.print(f"  [dim]{subtitle}[/dim]")
        self.console.print()

    def _print_step(self, step_num: int, total_steps: int, description: str):
        self.console.print(f"[bold cyan]▸ Шаг {step_num}/{total_steps}:[/bold cyan] {description}")
        self.console.print()

    # ═══════════════════════════════════════════════════════════════════════
    # Создание бэкапа
    # ═══════════════════════════════════════════════════════════════════════

    def create_backup(self, backup_type='full') -> Optional[Path]:
        if not self.source_dir.exists():
            self.console.print(Panel.fit("[red]Директория не существует[/red]", border_style="red"))
            return None

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            type_str = 'full' if backup_type == 'full' else 'inc'
            archive_name = f"web_backup_{type_str}_{timestamp}.tar.gz"
            archive_path = self.backup_dir / archive_name

            title = "📦 ПОЛНЫЙ БЭКАП" if backup_type == 'full' else "📦 ИНКРЕМЕНТАЛЬНЫЙ БЭКАП"
            subtitle = f"Исключения: {', '.join(self.exclude_dirs)}"
            self._print_header(title, subtitle)

            # ── Шаг 1: Сканирование ──
            self._print_step(1, 3, "Сканирование файлов")

            if backup_type == 'full':
                files_to_backup, deleted_files, total_size, state = self._scan_full(timestamp)
            else:
                result = self._scan_incremental(timestamp)
                if result is None:
                    return None
                files_to_backup, deleted_files, total_size, state = result

            total_files = len(files_to_backup)
            if total_files == 0:
                self.console.print("[yellow]Нет файлов для архивации[/yellow]")
                return None

            # ── Шаг 2: Архивация ──
            self._print_step(2, 3, f"Создание архива: {archive_name}")
            ext_stats = self._create_archive(archive_path, files_to_backup, total_size,
                                             state, backup_type, deleted_files, timestamp)

            # ── Шаг 3: Проверка ──
            self._print_step(3, 3, "Проверка целостности архива")
            success, errors = self._verify_backup(archive_path)

            # ── Итоги ──
            self._print_summary(archive_path, archive_name, total_files, ext_stats, success, errors)

            self._save_state(state)
            if self.max_backups:
                self._cleanup_old_backups()

            return archive_path

        except Exception as e:
            self.console.print(Panel.fit(f"[red]✗ Ошибка: {e}[/red]", border_style="red"))
            self.logger.exception("Ошибка при создании бэкапа")
            return None

    def _scan_full(self, timestamp: str) -> tuple:
        current_files = self._walk_source_dir()
        files_to_backup = list(current_files.values())

        with Progress(
            TextColumn("[bold]{task.percentage:>3.0f}%"),
            BarColumn(bar_width=None),
            TextColumn("[cyan]{task.description}[/cyan]"),
            console=self.console
        ) as progress:
            task = progress.add_task("Сканирование", total=len(files_to_backup) or 1)

            for _ in files_to_backup:
                progress.advance(task)

            total_size = sum(f.stat().st_size for f in files_to_backup
                           if f.is_file() and not f.is_symlink())

            progress.update(task,
                          description=f"[green]✓ Найдено: {len(files_to_backup):,} файлов "
                                      f"({format_size(total_size)})[/green]")

        self.console.print()
        state = {'timestamp': timestamp, 'type': 'full', 'source_dir': str(self.source_dir), 'files': {}}
        return files_to_backup, [], total_size, state

    def _scan_incremental(self, timestamp: str) -> Optional[tuple]:
        previous_state = self._load_state()
        if not previous_state:
            self.console.print("[yellow]Нет предыдущего состояния. Создаю полный бэкап...[/yellow]")
            self.console.print()
            return self._scan_full(timestamp)

        current_files = self._walk_source_dir()
        prev_files = set(previous_state.get('files', {}).keys())
        curr_files = set(current_files.keys())

        deleted_files = list(prev_files - curr_files)
        new_files = [current_files[f] for f in (curr_files - prev_files) if f in current_files]
        modified_files = []

        common_files = list(prev_files & curr_files)

        with Progress(
            TextColumn("[bold]{task.percentage:>3.0f}%"),
            BarColumn(bar_width=None),
            TextColumn("[cyan]{task.description}[/cyan]"),
            console=self.console
        ) as progress:
            task = progress.add_task("Сравнение", total=len(common_files) or 1)

            for f in common_files:
                file_path = current_files[f]
                prev_info = previous_state['files'][f]
                curr_info = self._get_file_info(file_path)

                if (prev_info.get('size') != curr_info.get('size') or
                    prev_info.get('mtime') != curr_info.get('mtime')):
                    curr_info['hash'] = self._get_file_hash(file_path)
                    if prev_info.get('hash') != curr_info.get('hash'):
                        modified_files.append(file_path)

                progress.advance(task)

            files_to_backup = new_files + modified_files

            if not files_to_backup and not deleted_files:
                progress.update(task, description="[yellow]Изменений не обнаружено[/yellow]")
                self.console.print()
                return None

            progress.update(task,
                          description=f"[green]✓ Новых: {len(new_files):,}, "
                                      f"измененных: {len(modified_files):,}, "
                                      f"удаленных: {len(deleted_files):,}[/green]")

        self.console.print()

        total_size = sum(f.stat().st_size for f in files_to_backup
                       if f.is_file() and not f.is_symlink())

        state = previous_state.copy()
        state.update({'timestamp': timestamp, 'type': 'incremental', 'base_backup': previous_state.get('timestamp')})

        stats_table = Table(box=SIMPLE, show_header=False, padding=(0, 4))
        stats_table.add_column(style="cyan", width=15)
        stats_table.add_column(style="white", justify="right")
        stats_table.add_row("🆕 Новых файлов", str(len(new_files)))
        stats_table.add_row("✏️  Измененных", str(len(modified_files)))
        stats_table.add_row("🗑️  Удаленных", str(len(deleted_files)))
        stats_table.add_row("💾 Общий размер", format_size(total_size))
        self.console.print(stats_table)
        self.console.print()

        return files_to_backup, deleted_files, total_size, state

    def _create_archive(self, archive_path: Path, files_to_backup: list,
                        total_size: int, state: dict, backup_type: str,
                        deleted_files: list, timestamp: str) -> dict:
        ext_stats = defaultdict(lambda: {'total': 0, 'raw_size': 0})

        files_with_size = []
        for f in files_to_backup:
            if f.is_file() and not f.is_symlink():
                size = f.stat().st_size
            else:
                size = 0
            files_with_size.append((f, size))

        if total_size == 0:
            total_size = len(files_to_backup) or 1

        with Progress(
            TextColumn("[bold]{task.percentage:>3.0f}%"),
            BarColumn(bar_width=None, complete_style="green"),
            FileSizeColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=self.console,
            expand=True
        ) as progress:
            task = progress.add_task("[cyan]Архивация", total=total_size)

            with tarfile.open(archive_path, "w:gz") as tar:
                for file_path, file_size in files_with_size:
                    rel_path = str(file_path.relative_to(self.source_dir))

                    try:
                        arcname = str(self.source_dir.name / file_path.relative_to(self.source_dir))

                        if file_path.is_symlink():
                            tarinfo = tarfile.TarInfo(name=arcname)
                            tarinfo.type = tarfile.SYMTYPE
                            tarinfo.linkname = os.readlink(file_path)
                            tarinfo.mode = file_path.stat().st_mode
                            tarinfo.mtime = file_path.stat().st_mtime
                            tar.addfile(tarinfo)
                        else:
                            tar.add(file_path, arcname=arcname, recursive=False)
                            state['files'][rel_path] = self._get_file_info(file_path)
                            ext = get_ext(rel_path)
                            ext_stats[ext]['total'] += 1
                            ext_stats[ext]['raw_size'] += file_size

                        progress.update(task, advance=file_size)

                    except Exception:
                        pass

        self.console.print()

        if backup_type == 'incremental' and deleted_files:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
                json.dump({'deleted_files': deleted_files, 'timestamp': timestamp}, tmp)
                tmp_path = Path(tmp.name)
            with tarfile.open(archive_path, "a:gz") as tar:
                tar.add(tmp_path, arcname=f".deleted_{timestamp}.json")
            tmp_path.unlink()
            for f in deleted_files:
                state['files'].pop(f, None)

        return ext_stats

    def _verify_backup(self, archive_path: Path) -> tuple:
        errors = []
        warnings = []

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getmembers()
                total_members = len(members)

                with Progress(
                    TextColumn("[bold]{task.percentage:>3.0f}%"),
                    BarColumn(bar_width=None, complete_style="yellow"),
                    TextColumn("[yellow]{task.description}[/yellow]"),
                    console=self.console
                ) as progress:
                    task = progress.add_task("Проверка", total=total_members)

                    for member in members:
                        progress.advance(task)

                        try:
                            if member.issym():
                                if self.skip_symlink_check:
                                    continue
                                if not member.linkname:
                                    errors.append(f"Поврежденный symlink: {member.name}")
                                elif member.linkname.startswith('/') and not self.skip_symlink_check:
                                    warnings.append(f"Абсолютный symlink: {member.name} -> {member.linkname}")
                                continue

                            if member.isfile():
                                f = tar.extractfile(member)
                                if f:
                                    try:
                                        f.read()
                                    except Exception as e:
                                        errors.append(f"Ошибка чтения {member.name}: {e}")
                        except Exception as e:
                            errors.append(f"Ошибка обработки {member.name}: {e}")

                    if errors:
                        progress.update(task, description=f"[red]✗ Найдено ошибок: {len(errors)}[/red]")
                    elif warnings:
                        progress.update(task, description=f"[yellow]⚠ Проверка пройдена "
                                                          f"(предупреждений: {len(warnings)})[/yellow]")
                    else:
                        progress.update(task, description="[green]✓ Проверка пройдена успешно[/green]")

            self.console.print()

            if errors:
                self.console.print(Panel(
                    "\n".join(f"[red]• {e}[/red]" for e in errors[:10]) +
                    (f"\n[dim]... и ещё {len(errors) - 10}[/dim]" if len(errors) > 10 else ""),
                    title="[red]ОШИБКИ[/red]", border_style="red"
                ))

            if warnings:
                self.console.print(Panel(
                    "\n".join(f"[yellow]• {w}[/yellow]" for w in warnings[:10]) +
                    (f"\n[dim]... и ещё {len(warnings) - 10}[/dim]" if len(warnings) > 10 else ""),
                    title="[yellow]ПРЕДУПРЕЖДЕНИЯ[/yellow]", border_style="yellow"
                ))

            return len(errors) == 0, errors

        except Exception as e:
            self.console.print(f"  [red]✗ Критическая ошибка: {e}[/red]")
            return False, [str(e)]

    def _print_summary(self, archive_path: Path, archive_name: str,
                       total_files: int, ext_stats: dict,
                       success: bool, errors: list):
        archive_size = archive_path.stat().st_size
        total_raw = sum(s['raw_size'] for s in ext_stats.values())
        ratio = (1 - archive_size / total_raw) * 100 if total_raw > 0 else 0

        # Таблица по расширениям
        if ext_stats:
            table = Table(box=SIMPLE, show_header=True, header_style="bold cyan")
            table.add_column("Расширение", style="cyan", width=10)
            table.add_column("Файлов", justify="right", width=8)
            table.add_column("Размер", justify="right", width=12)

            sorted_exts = sorted(ext_stats.items(), key=lambda x: x[1]['raw_size'], reverse=True)[:10]
            for ext, stats in sorted_exts:
                if stats['total'] > 0:
                    table.add_row(ext, str(stats['total']), format_size(stats['raw_size']))

            total_ext_files = sum(s['total'] for s in ext_stats.values())
            if total_ext_files > 0:
                table.add_section()
                table.add_row("[bold]ИТОГО[/bold]", f"[bold]{total_ext_files}[/bold]",
                             f"[bold]{format_size(total_raw)}[/bold]")

            self.console.print(table)
            self.console.print()

        # Итоговая таблица
        status_title = "✓ БЭКАП СОЗДАН" if success else "⚠ БЭКАП СОЗДАН (с ошибками)"
        status_style = "bold green" if success else "bold yellow"
        border_style = "green" if success else "yellow"

        result_table = Table(
            title=f"[bold]{status_title}[/bold]",
            title_style=status_style,
            box=ROUNDED, border_style=border_style, padding=(0, 2)
        )
        result_table.add_column("Параметр", style="cyan", justify="right")
        result_table.add_column("Значение", style="white")
        result_table.add_row("", "")
        result_table.add_row("📁 Файлов в архиве", f"{total_files:,}")
        result_table.add_row("💾 Исходный размер", format_size(total_raw))
        result_table.add_row("📦 Размер архива", f"[bold green]{format_size(archive_size)}[/bold green]")
        result_table.add_row("🗜️  Сжатие", f"[bold]{ratio:.1f}%[/bold]")
        result_table.add_row("", "")
        result_table.add_row("📄 Имя файла", f"[bold blue]{archive_name}[/bold blue]")
        result_table.add_row("📍 Путь", f"[dim]{archive_path}[/dim]")

        self.console.print(result_table)
        self.console.print()

        if not success:
            self.console.print("[yellow]Архив может быть поврежден. Рекомендуется создать новый.[/yellow]")

    # ═══════════════════════════════════════════════════════════════════════
    # Восстановление
    # ═══════════════════════════════════════════════════════════════════════

    def restore_backup(self, archive_name=None, create_backup_before=True) -> bool:
        if archive_name:
            archive_path = self.backup_dir / archive_name
            if not archive_path.exists():
                self.console.print(Panel.fit("[red]Архив не найден[/red]", border_style="red"))
                return False
        else:
            backups = self._get_all_backups()
            if not backups:
                self.console.print(Panel.fit("[red]Нет доступных бэкапов[/red]", border_style="red"))
                return False
            archive_path = backups[-1]['path']
            archive_name = backups[-1]['filename']

        backup_info = parse_backup_info(archive_path.name)
        if not backup_info:
            self.console.print(Panel.fit("[red]Неизвестный формат[/red]", border_style="red"))
            return False

        backup_info['path'] = archive_path

        self._print_header("🔄 ВОССТАНОВЛЕНИЕ ИЗ БЭКАПА", f"Архив: {archive_name}")

        # Шаг 1: Цепочка
        self._print_step(1, 5, "Анализ цепочки бэкапов")

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                    console=self.console) as progress:
            task = progress.add_task("[cyan]Построение цепочки восстановления...", total=None)
            chain = self._get_incremental_chain(backup_info)
            if not chain:
                progress.update(task, description="[red]✗ Не удалось построить цепочку[/red]")
                return False
            progress.update(task, description=f"[green]✓ Цепочка построена: {len(chain)} бэкапов[/green]")

        self.console.print()

        tree = Tree("🔗 [bold]План восстановления[/bold]")
        for i, b in enumerate(chain, 1):
            if b['filename'] == archive_path.name:
                tree.add(f"[bold green]► {i}. {b['filename']} (целевой)[/bold green]")
            else:
                tree.add(f"[dim]  {i}. {b['filename']}[/dim]")
        self.console.print(Panel(tree, border_style="blue"))
        self.console.print()

        # Шаг 2: Предварительный бэкап текущего состояния
        self._print_step(2, 5, "Предварительный бэкап текущего состояния")
        if create_backup_before:
            if self.create_backup('full'):
                self.console.print("[green]✓ Текущее состояние сохранено[/green]")
            else:
                self.console.print("[yellow]⚠ Не удалось создать предварительный бэкап[/yellow]")
        else:
            self.console.print("[dim]Пропущен (флаг -nb)[/dim]")
        self.console.print()

        # Шаг 3: Распаковка во временную директорию
        self._print_step(3, 5, "Распаковка архива во временную директорию")

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)

            with Progress(
                TextColumn("[bold]{task.percentage:>3.0f}%"),
                BarColumn(bar_width=None, complete_style="cyan"),
                TextColumn("[cyan]{task.description}[/cyan]"),
                console=self.console
            ) as progress:
                task = progress.add_task("Извлечение", total=len(chain))

                for i, backup_info_chain in enumerate(chain, 1):
                    progress.update(task, description=f"Извлечение [{i}/{len(chain)}] "
                                                    f"{backup_info_chain['filename']}")

                    with tarfile.open(backup_info_chain['path'], "r:gz") as tar:
                        members = tar.getmembers()
                        file_members = [m for m in members if m.isfile() or m.issym()]

                        for member in file_members:
                            try:
                                tar.extract(member, path=temp_dir, filter='data')
                            except Exception:
                                pass

                    progress.advance(task)

            self.console.print()

            # Обработка удаленных файлов
            for backup_info_chain in chain:
                try:
                    with tarfile.open(backup_info_chain['path'], "r:gz") as tar:
                        for member in tar.getmembers():
                            if '.deleted_' in member.name and member.name.endswith('.json'):
                                with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
                                    extracted = tar.extractfile(member)
                                    if extracted:
                                        f.write(extracted.read())
                                        tmp_path = Path(f.name)

                                with open(tmp_path, 'r') as f:
                                    deleted_data = json.load(f)

                                for rel_path in deleted_data.get('deleted_files', []):
                                    for d in temp_dir.rglob('*'):
                                        try:
                                            if d.relative_to(temp_dir) == Path(rel_path) and d.exists():
                                                d.unlink()
                                        except ValueError:
                                            pass
                                tmp_path.unlink()
                except Exception:
                    pass

            # Шаг 4: Проверка распакованных файлов
            self._print_step(4, 5, "Проверка распакованных данных")
            
            temp_web_dir = temp_dir / 'web'
            if not temp_web_dir.exists():
                items = list(temp_dir.iterdir())
                temp_web_dir = items[0] if len(items) == 1 and items[0].is_dir() else temp_dir

            all_items = list(temp_web_dir.rglob('*'))
            files_only = [i for i in all_items if i.is_file() or i.is_symlink()]
            
            if not files_only:
                self.console.print("[red]✗ В архиве нет файлов для восстановления![/red]")
                self.console.print("[yellow]Целевая директория НЕ изменена.[/yellow]")
                return False
                
            self.console.print(f"[green]✓ Найдено {len(files_only):,} файлов для восстановления[/green]")
            self.console.print()

            # Шаг 5: Безопасное копирование с предварительным бэкапом в памяти
            self._print_step(5, 5, "Копирование файлов в целевую директорию")

            # Создаём бэкап текущих файлов во временную директорию
            backup_of_current = temp_dir / "_current_backup"
            if self.source_dir.exists():
                try:
                    shutil.copytree(self.source_dir, backup_of_current, symlinks=True)
                    self.console.print("[dim]Создана резервная копия текущих файлов[/dim]")
                except Exception as e:
                    self.console.print(f"[yellow]⚠ Не удалось создать резервную копию: {e}[/yellow]")

            with Progress(
                TextColumn("[bold]{task.percentage:>3.0f}%"),
                BarColumn(bar_width=None, complete_style="green"),
                TextColumn("[cyan]{task.description}[/cyan]"),
                console=self.console
            ) as progress:
                task = progress.add_task("Копирование", total=len(files_only))

                errors_count = 0
                for item in files_only:
                    try:
                        rel_path = item.relative_to(temp_web_dir)
                        target_path = self.source_dir / rel_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        # Удаляем только конкретный файл, если он существует
                        if target_path.exists() or target_path.is_symlink():
                            target_path.unlink()

                        if item.is_symlink():
                            target_path.symlink_to(os.readlink(item))
                        else:
                            shutil.copy2(item, target_path)

                        progress.advance(task)
                    except Exception as e:
                        errors_count += 1
                        if errors_count <= 5:  # Показываем только первые 5 ошибок
                            self.logger.error(f"Ошибка копирования {rel_path}: {e}")

                if errors_count > 0:
                    progress.update(task, 
                        description=f"[yellow]⚠ Копирование завершено с {errors_count} ошибками[/yellow]")
                else:
                    progress.update(task, description="[green]✓ Копирование завершено[/green]")

            self.console.print()
            
            # Удаляем файлы, которых нет в бэкапе (опционально)
            if self.source_dir.exists():
                backup_files_set = {str(item.relative_to(temp_web_dir)).replace('\\', '/') 
                                for item in files_only}
                current_files = set()
                for root, _, files in os.walk(self.source_dir):
                    for file in files:
                        file_path = Path(root) / file
                        try:
                            rel = str(file_path.relative_to(self.source_dir)).replace('\\', '/')
                            current_files.add(rel)
                        except ValueError:
                            pass
                
                files_to_remove = current_files - backup_files_set
                if files_to_remove:
                    self.console.print(f"[yellow]⚠ Найдено {len(files_to_remove)} файлов, "
                                    f"которых нет в бэкапе[/yellow]")
                    self.console.print("[dim]Эти файлы не будут удалены для безопасности[/dim]")
                    self.console.print()

            result_table = Table(
                title="[bold]✓ ВОССТАНОВЛЕНИЕ ЗАВЕРШЕНО[/bold]",
                title_style="bold green",
                box=ROUNDED, border_style="green", padding=(0, 2)
            )
            result_table.add_column("Параметр", style="cyan", justify="right")
            result_table.add_column("Значение", style="white")
            result_table.add_row("", "")
            result_table.add_row("📁 Целевая директория", str(self.source_dir))
            result_table.add_row("📦 Архив-источник", archive_name)
            result_table.add_row("🔗 Бэкапов в цепочке", str(len(chain)))
            result_table.add_row("📄 Восстановлено файлов", f"{len(files_only):,}")
            
            if errors_count > 0:
                result_table.add_row("❌ Ошибок при копировании", str(errors_count))

            self.console.print(result_table)
            self.console.print()

            self.logger.info("Восстановлено из: %s", archive_path.name)
            return True

    # ═══════════════════════════════════════════════════════════════════════
    # Список бэкапов
    # ═══════════════════════════════════════════════════════════════════════

    def list_backups(self):
        backups = self._get_all_backups()

        if not backups:
            self.console.print(Panel.fit("[yellow]Нет созданных бэкапов[/yellow]", border_style="yellow"))
            return

        self._print_header("📚 СПИСОК БЭКАПОВ")

        table = Table(box=ROUNDED, border_style="blue", padding=(0, 2))
        table.add_column("#", style="dim", width=3, justify="right")
        table.add_column("Тип", style="cyan", width=10)
        table.add_column("Имя файла", style="blue")
        table.add_column("Размер", style="green", width=12, justify="right")
        table.add_column("Создан", style="yellow", width=20)
        table.add_column("Возраст", style="magenta", width=15)

        total_size = 0
        for i, backup in enumerate(backups, 1):
            size = backup['path'].stat().st_size
            total_size += size
            backup_type = "🔵 Полный" if backup['type'] == 'full' else "🟢 Инкрем."

            age = datetime.now() - backup['datetime']
            if age.days > 0:
                age_str = f"{age.days} дн. {age.seconds // 3600} ч."
            else:
                age_str = f"{age.seconds // 3600} ч. {(age.seconds % 3600) // 60} мин."

            table.add_row(
                str(i), backup_type, backup['filename'],
                format_size(size),
                backup['datetime'].strftime('%Y-%m-%d %H:%M:%S'),
                age_str
            )

        self.console.print(table)
        self.console.print()

        stats = Columns([
            Panel(f"[green]💾 Общий размер\n{format_size(total_size)}[/green]", box=SIMPLE),
            Panel(f"[cyan]📊 Всего бэкапов\n{len(backups)}[/cyan]", box=SIMPLE)
        ])
        self.console.print(stats)
        self.console.print()

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

        if chains:
            tree = Tree("🔗 [bold]Цепочки бэкапов[/bold]")
            for i, chain in enumerate(chains, 1):
                full = chain[0]
                inc_count = len(chain) - 1
                branch = tree.add(
                    f"[cyan]Цепочка #{i}: {full['datetime'].strftime('%Y-%m-%d')} "
                    f"→ {inc_count} инкрементальных[/cyan]"
                )
                if inc_count > 0:
                    branch.add(f"[dim]└─ Последний: {chain[-1]['filename']}[/dim]")

            self.console.print(Panel(tree, border_style="blue"))
            self.console.print()


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Резервное копирование с инкрементальными бэкапами",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Примеры:\n"
               "  %(prog)s -b           # Полный бэкап\n"
               "  %(prog)s -b inc       # Инкрементальный\n"
               "  %(prog)s -l           # Список\n"
               "  %(prog)s -r           # Восстановить последний\n"
               "  %(prog)s -r file -nb  # Без предв. бэкапа\n"
               "  %(prog)s -r -nb -ns   # Без проверки symlinks")

    parser.add_argument('--backup', '-b', nargs='?', const='full',
                       choices=['full', 'inc', 'incremental'])
    parser.add_argument('--list', '-l', action='store_true')
    parser.add_argument('--restore', '-r', nargs='?', const='last', metavar='ARCHIVE')
    parser.add_argument('--no-backup-before', '-nb', action='store_true')
    parser.add_argument('--no-symlink-check', '-ns', action='store_true')
    parser.add_argument('--exclude', '-e', nargs='+')
    parser.add_argument('--clean', '-c', action='store_true')

    args = parser.parse_args()

    try:
        import rich
    except ImportError:
        print("pip install rich")
        sys.exit(1)

    manager = BackupManager(
        max_backups=MAX_BACKUPS,
        exclude_dirs=args.exclude if args.exclude else EXCLUDE_DIRS,
        skip_symlink_check=args.no_symlink_check
    )

    if args.clean:
        if manager.state_file.exists():
            manager.state_file.unlink()
            manager.console.print("[green]✓ Состояние очищено[/green]")
        return

    if args.backup:
        backup_type = 'incremental' if args.backup in ['inc', 'incremental'] else 'full'
        manager.create_backup(backup_type)

    if args.list:
        manager.list_backups()

    if args.restore:
        create_backup_before = not args.no_backup_before
        if args.restore == 'last':
            manager.restore_backup(create_backup_before=create_backup_before)
        else:
            manager.restore_backup(args.restore, create_backup_before)

    if not (args.backup or args.list or args.restore or args.clean):
        manager.create_backup('incremental')


if __name__ == "__main__":
    main()
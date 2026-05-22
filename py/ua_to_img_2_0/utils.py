# utils.py

import os
import json
import numpy as np
from pathlib import Path


def ensure_dir(directory: str):
    """Создаёт директорию, если её нет."""
    Path(directory).mkdir(parents=True, exist_ok=True)


def file_size_kb(path: str) -> float:
    """Размер файла в килобайтах."""
    return os.path.getsize(path) / 1024.0


def file_size_mb(path: str) -> float:
    """Размер файла в мегабайтах."""
    return os.path.getsize(path) / (1024.0 * 1024.0)


def clean_temp_files(*paths: str):
    """Удаляет временные файлы."""
    for path in paths:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                print(f"   Ошибка при удалении {path}: {e}")


def mm_to_pixels(mm: float, dpi: int = 300) -> int:
    """Переводит миллиметры в пиксели для заданного DPI."""
    return int(round(mm * dpi / 25.4))


def pixels_to_mm(px: int, dpi: int = 300) -> float:
    """Переводит пиксели в миллиметры для заданного DPI."""
    return px * 25.4 / dpi
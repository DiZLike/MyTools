# calibration.py — полный файл

import numpy as np
from scipy.interpolate import interp1d


# 16 ступеней от чёрного до белого
CALIBRATION_STEPS = 16
CALIBRATION_VALUES = np.array([
    0, 17, 34, 51, 68, 85, 102, 119, 
    136, 153, 170, 187, 204, 221, 238, 255
], dtype=np.uint8)


def generate_calibration_strip(step_width_px: int = 20, step_height_px: int = 20) -> np.ndarray:
    """
    Создаёт калибровочную полосу: 16 прямоугольников.
    
    Returns:
        grayscale изображение (step_height_px, 16 * step_width_px)
    """
    total_width = step_width_px * CALIBRATION_STEPS
    strip = np.zeros((step_height_px, total_width), dtype=np.uint8)
    
    for i, value in enumerate(CALIBRATION_VALUES):
        x_start = i * step_width_px
        x_end = (i + 1) * step_width_px
        strip[:, x_start:x_end] = value
    
    return strip


def measure_calibration_steps(strip_image: np.ndarray) -> np.ndarray:
    """
    Измеряет реальную яркость каждой ступени.
    
    Args:
        strip_image: вырезанная полоса (grayscale)
    
    Returns:
        Массив из 16 измеренных значений
    """
    step_width = strip_image.shape[1] // CALIBRATION_STEPS
    
    measured = np.zeros(CALIBRATION_STEPS, dtype=np.float32)
    
    for i in range(CALIBRATION_STEPS):
        x_start = i * step_width
        x_end = (i + 1) * step_width
        
        # Центральная область (отступ 20% от краёв)
        margin = max(1, int(step_width * 0.2))
        center_region = strip_image[:, x_start + margin : x_end - margin]
        
        measured[i] = np.mean(center_region)
    
    return measured


def is_original_print(measured: np.ndarray, reference: np.ndarray = None) -> bool:
    """
    Проверяет, является ли изображение оригиналом (не сканом).
    Если измеренные значения близки к эталонным — это оригинал.
    
    Args:
        measured: измеренные значения 16 ступеней
        reference: эталонные значения (по умолчанию CALIBRATION_VALUES)
    
    Returns:
        True если это оригинал, False если скан
    """
    if reference is None:
        reference = CALIBRATION_VALUES.astype(np.float32)
    else:
        reference = np.array(reference, dtype=np.float32)
    
    measured = np.array(measured, dtype=np.float32)
    
    # Среднее абсолютное отклонение от эталона
    deviation = np.mean(np.abs(measured - reference))
    return deviation < 5.0  # меньше 5 единиц — оригинал


def validate_calibration(measured: np.ndarray, 
                         reference: np.ndarray = None) -> bool:
    """
    Проверяет качество калибровочной шкалы.
    
    Args:
        measured: измеренные значения 16 ступеней
        reference: эталонные значения
    
    Returns:
        True если шкала пригодна для коррекции
    """
    if reference is None:
        reference = CALIBRATION_VALUES
    
    # Нестрогая монотонность (допускаем небольшой шум до 1 единицы)
    diffs = np.diff(measured)
    if np.any(diffs < -1.0):
        problem_steps = np.where(diffs < -1.0)[0]
        print(f"   ⚠️ Шкала не монотонна! Проблемные ступени: {problem_steps}")
        return False
    
    # Динамический диапазон
    dynamic_range = measured[-1] - measured[0]
    if dynamic_range < 50:
        print(f"   ⚠️ Недостаточный динамический диапазон: {dynamic_range:.0f}")
        return False
    
    print(f"   ✓ Калибровочная шкала: OK (диапазон {dynamic_range:.0f})")
    return True


def build_correction_lut(measured: np.ndarray, 
                         reference: np.ndarray = None) -> np.ndarray:
    """
    Строит LUT для коррекции яркости по 16 точкам.
    
    Args:
        measured: измеренные значения 16 ступеней
        reference: эталонные значения
    
    Returns:
        Массив из 256 значений (0-255)
    """
    if reference is None:
        reference = CALIBRATION_VALUES.astype(np.float32)
    else:
        reference = np.array(reference, dtype=np.float32)
    
    measured = np.array(measured, dtype=np.float32)
    
    # Добавляем крайние точки для устойчивости
    m = np.concatenate([[0.0], measured, [255.0]])
    r = np.concatenate([[0.0], reference, [255.0]])
    
    # Убираем дубликаты для интерполяции
    unique_idx = np.concatenate([[True], np.diff(m) > 0.1])
    m = m[unique_idx]
    r = r[unique_idx]
    
    # Кубическая интерполяция
    f = interp1d(m, r, kind='cubic', bounds_error=False, fill_value='extrapolate')
    
    # Строим LUT
    lut = f(np.arange(256))
    lut = np.clip(lut, 0, 255).astype(np.uint8)
    
    return lut


def correct_spectrogram(spectrogram: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """
    Применяет коррекцию яркости к спектрограмме.
    
    Args:
        spectrogram: 2D массив значений 0-255
        lut: таблица коррекции (256 элементов)
    
    Returns:
        Скорректированная спектрограмма
    """
    if spectrogram.dtype == np.uint8:
        return lut[spectrogram]
    else:
        # Приводим к 0-255, если float
        clipped = np.clip(spectrogram, 0, 255).astype(np.uint8)
        return lut[clipped].astype(spectrogram.dtype)


def normalize_by_range(channel: np.ndarray) -> np.ndarray:
    """
    Нормализация по диапазону (fallback, если нет шкалы).
    Линейно растягивает до 0-255.
    
    Args:
        channel: 2D массив
    
    Returns:
        Нормализованный массив uint8
    """
    ch_min = np.min(channel)
    ch_max = np.max(channel)
    
    if ch_max > ch_min:
        normalized = (channel - ch_min) / (ch_max - ch_min) * 255
    else:
        normalized = channel
    
    return np.clip(normalized, 0, 255).astype(np.uint8)
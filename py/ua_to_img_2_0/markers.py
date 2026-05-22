# markers.py

import numpy as np
import cv2


def generate_marker(size_px: int = 40) -> np.ndarray:
    """
    Создаёт маркер: концентрические квадраты с крестом.
    Легко детектируется, устойчив к размытию.
    
    Возвращает grayscale изображение size_px × size_px.
    """
    marker = np.zeros((size_px, size_px), dtype=np.uint8)
    
    # Параметры (в долях от размера)
    outer_margin = int(size_px * 0.1)    # 10% от края
    inner_margin = int(size_px * 0.25)   # 25% от края
    cross_half = int(size_px * 0.08)     # толщина креста
    
    # Внешняя белая рамка
    marker[outer_margin:size_px-outer_margin, outer_margin:size_px-outer_margin] = 255
    
    # Внутренний чёрный квадрат
    marker[inner_margin:size_px-inner_margin, inner_margin:size_px-inner_margin] = 0
    
    # Белый крест в центре
    center = size_px // 2
    marker[center-cross_half:center+cross_half, inner_margin:size_px-inner_margin] = 255
    marker[inner_margin:size_px-inner_margin, center-cross_half:center+cross_half] = 255
    
    return marker


def generate_all_markers(marker_size_px: int = 40) -> dict:
    """
    Создаёт 4 одинаковых маркера для углов.
    Возвращает словарь с позициями.
    """
    marker = generate_marker(marker_size_px)
    return {
        'tl': marker.copy(),  # top-left
        'tr': marker.copy(),  # top-right
        'bl': marker.copy(),  # bottom-left
        'br': marker.copy(),  # bottom-right
    }


def _is_square_contour(contour, tolerance: float = 0.15) -> bool:
    """Проверяет, является ли контур приблизительно квадратным."""
    peri = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.04 * peri, True)
    
    if len(approx) != 4:
        return False
    
    # Проверяем соотношение сторон
    (x, y, w, h) = cv2.boundingRect(approx)
    aspect_ratio = float(w) / h if h > 0 else 0
    return 1.0 - tolerance <= aspect_ratio <= 1.0 + tolerance


def _has_inner_structure(region: np.ndarray) -> bool:
    """
    Проверяет наличие внутренней структуры маркера:
    чередование чёрного и белого.
    """
    h, w = region.shape
    center_row = region[h//2, :]
    center_col = region[:, w//2]
    
    # Считаем переходы яркости (должно быть несколько)
    row_transitions = np.sum(np.abs(np.diff(center_row.astype(np.int32))) > 50)
    col_transitions = np.sum(np.abs(np.diff(center_col.astype(np.int32))) > 50)
    
    return row_transitions >= 4 and col_transitions >= 4


def find_markers(image: np.ndarray, marker_size_hint: int = 40) -> list:
    """
    Ищет 4 маркера на изображении.
    
    Args:
        image: grayscale изображение
        marker_size_hint: примерный размер маркера в пикселях
    
    Returns:
        Список из 4 точек (x, y) в порядке: TL, TR, BL, BR
        или None, если не найдено ровно 4 маркера
    """
    # Бинаризация
    if image.dtype != np.uint8:
        image = (image * 255).astype(np.uint8) if image.max() <= 1.0 else image.astype(np.uint8)
    
    binary = cv2.adaptiveThreshold(
        image, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=11,
        C=2
    )
    
    # Поиск контуров
    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    candidates = []
    min_size = marker_size_hint * 0.5
    max_size = marker_size_hint * 2.0
    
    for contour in contours:
        (x, y, w, h) = cv2.boundingRect(contour)
        
        # Фильтр по размеру
        if w < min_size or h < min_size or w > max_size or h > max_size:
            continue
        
        # Проверка на квадратность
        if not _is_square_contour(contour):
            continue
        
        # Проверка внутренней структуры
        roi = binary[y:y+h, x:x+w]
        if _has_inner_structure(roi):
            cx, cy = x + w // 2, y + h // 2
            candidates.append((cx, cy, w))
    
    if len(candidates) < 4:
        return None
    
    # Сортируем: сначала 4 самых крупных
    candidates.sort(key=lambda c: c[2], reverse=True)
    candidates = candidates[:4]
    
    # Сортируем по позиции: верхние-левые, верхние-правые, нижние-левые, нижние-правые
    points = [(c[0], c[1]) for c in candidates]
    
    # Сортировка по y (верхние первые)
    points.sort(key=lambda p: p[1])
    
    # Верхние два сортируем по x
    top_two = sorted(points[:2], key=lambda p: p[0])
    # Нижние два сортируем по x
    bottom_two = sorted(points[2:], key=lambda p: p[0])
    
    return [top_two[0], top_two[1], bottom_two[0], bottom_two[1]]


def correct_perspective(image: np.ndarray, markers: list, 
                        target_width: int, target_height: int) -> np.ndarray:
    """
    Исправляет перспективу изображения по 4 маркерам.
    
    Args:
        image: исходное изображение
        markers: 4 точки [TL, TR, BL, BR]
        target_width, target_height: целевые размеры
    
    Returns:
        Исправленное изображение
    """
    src_points = np.array(markers, dtype=np.float32)
    
    dst_points = np.array([
        [0, 0],
        [target_width - 1, 0],
        [0, target_height - 1],
        [target_width - 1, target_height - 1],
    ], dtype=np.float32)
    
    M = cv2.getPerspectiveTransform(src_points, dst_points)
    corrected = cv2.warpPerspective(image, M, (target_width, target_height))
    
    return corrected
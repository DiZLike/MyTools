# layout.py — макет для цветной Cyan/Magenta стерео-спектрограммы

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import platform

from config import PAPER_SIZES, LAYOUT
from utils import mm_to_pixels


def calculate_layout(config: dict):
    """
    Вычисляет все координаты макета листа в пикселях.
    Одна область для стерео-спектрограммы (Cyan/Magenta).
    """
    dpi = config.get('dpi', 300)
    paper = PAPER_SIZES[config.get('paper_size', 'A4')]
    
    page_w = mm_to_pixels(paper['width_mm'], dpi)
    page_h = mm_to_pixels(paper['height_mm'], dpi)
    
    margin = mm_to_pixels(LAYOUT['margin_mm'], dpi)
    marker_inset = mm_to_pixels(LAYOUT['marker_inset_mm'], dpi)
    marker_size = mm_to_pixels(config.get('marker_size_mm', 5), dpi)
    calib_height = mm_to_pixels(LAYOUT['calibration_strip_height_mm'], dpi)
    calib_margin = mm_to_pixels(LAYOUT['calibration_margin_mm'], dpi)
    metadata_height = mm_to_pixels(LAYOUT['metadata_height_mm'], dpi)
    
    markers = {
        'tl': (margin, margin),
        'tr': (page_w - margin, margin),
        'bl': (margin, page_h - margin),
        'br': (page_w - margin, page_h - margin),
    }
    
    content_x = margin + marker_inset + marker_size
    content_y = margin + marker_inset + marker_size
    content_w = page_w - 2 * (margin + marker_inset + marker_size)
    content_h = page_h - 2 * (margin + marker_inset + marker_size)
    
    bottom_reserved = 0
    if config.get('calibration_enabled', True):
        bottom_reserved += calib_height + calib_margin
    bottom_reserved += metadata_height
    
    spectrogram_h = content_h - bottom_reserved
    
    # Одна область спектрограммы на всю высоту
    spectrogram = {
        'x': content_x,
        'y': content_y,
        'w': content_w,
        'h': spectrogram_h,
    }
    
    calib_y = content_y + spectrogram_h + calib_margin
    calibration = {
        'x': content_x,
        'y': calib_y,
        'w': content_w,
        'h': calib_height,
    }
    
    metadata_y = calib_y + calib_height + 2 if config.get('calibration_enabled', True) else content_y + spectrogram_h + 2
    metadata_region = {
        'x': content_x,
        'y': metadata_y,
        'w': content_w,
        'h': metadata_height,
    }
    
    return {
        'page_w': page_w,
        'page_h': page_h,
        'dpi': dpi,
        'markers': markers,
        'marker_size': marker_size,
        'spectrogram': spectrogram,
        'calibration': calibration,
        'metadata_region': metadata_region,
        'frames_per_page': content_w,
    }


def calculate_pages(n_frames: int, frames_per_page: int) -> int:
    """Вычисляет количество страниц."""
    import math
    return max(1, math.ceil(n_frames / frames_per_page))
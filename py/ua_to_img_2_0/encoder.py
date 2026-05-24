# encoder.py — Grayscale кодирование аудио в страницы для печати
# Два канала друг над другом, одна калибровочная шкала, QR отдельно

import time
import numpy as np
import librosa
from pathlib import Path
from PIL import Image, ImageDraw
import io

from config import PRESETS, PAPER_SIZES
from calibration import generate_calibration_strip, CALIBRATION_STEPS
from metadata_sheet import encode_metadata_text
from utils import mm_to_pixels


def _generate_qr_page(metadata: dict, config: dict, output_path: str):
    """Создаёт отдельную страницу с QR-кодом метаданных."""
    dpi = config.get('dpi', 300)
    paper = PAPER_SIZES[config.get('paper_size', 'A4')]
    page_w = mm_to_pixels(paper['width_mm'], dpi)
    page_h = mm_to_pixels(paper['height_mm'], dpi)
    
    # Белая страница
    page = np.full((page_h, page_w), 255, dtype=np.uint8)
    metadata_text = encode_metadata_text(metadata)
    
    print(f"   QR содержит {len(metadata_text)} символов")
    
    try:
        import segno
        qr = segno.make(metadata_text, micro=False)
        # Квадратный QR, занимает ~60% меньшей стороны листа
        target_size = int(min(page_w, page_h) * 0.7)
        module_size = max(1, target_size // qr.symbol_size()[0])
        
        buf = io.BytesIO()
        qr.save(buf, kind='png', scale=module_size, dark='black', light='white', border=1)
        buf.seek(0)
        
        qr_img = np.array(Image.open(buf).convert('L'), dtype=np.uint8)
        # Инвертируем: QR чёрный на белом (стандарт)
        qr_h, qr_w = qr_img.shape
        
        # Центрируем
        qr_x = (page_w - qr_w) // 2
        qr_y = (page_h - qr_h) // 2
        
        page[qr_y:qr_y+qr_h, qr_x:qr_x+qr_w] = qr_img
        print(f"   QR: {qr_w}×{qr_h} px")
    except ImportError:
        print("   ⚠️ segno не установлен! Установите: pip install segno")
    
    Image.fromarray(page).save(output_path, 'PNG', compress_level=0)
    print(f"   QR-страница: {Path(output_path).name}")


# encoder.py — assemble_page (полная замена)

# encoder.py — assemble_page (адаптивная рамка)

def assemble_page(left_channel: np.ndarray, right_channel: np.ndarray, config: dict) -> np.ndarray:
    """
    Собирает страницу:
    - Левый канал
    - Правый канал (впритык)
    - Калибровочная шкала
    - Чёрная рамка вокруг всего
    
    Толщина рамки адаптивная: 1% от меньшей стороны, но не менее 4px.
    """
    n_freqs, n_frames = left_channel.shape
    
    calib_h = 30
    
    # Размеры контента
    content_w = n_frames
    content_h = n_freqs + n_freqs + calib_h
    
    # Адаптивная рамка: 1% от меньшей стороны, минимум 4px
    min_dim = min(content_w, content_h)
    border = max(4, int(min_dim * 0.01))
    
    # Страница = контент + рамка
    page_w = content_w + 2 * border
    page_h = content_h + 2 * border
    
    # Белая страница
    page = np.full((page_h, page_w), 255, dtype=np.uint8)
    
    # Левый канал
    y_left = border
    page[y_left:y_left + n_freqs, border:border + n_frames] = left_channel
    
    # Правый канал
    y_right = y_left + n_freqs
    page[y_right:y_right + n_freqs, border:border + n_frames] = right_channel
    
    # Калибровочная шкала
    y_calib = y_right + n_freqs
    calib_strip = generate_calibration_strip(
        step_width_px=max(1, n_frames // CALIBRATION_STEPS),
        step_height_px=calib_h
    )
    if calib_strip.shape[1] != n_frames:
        calib_strip = np.array(Image.fromarray(calib_strip).resize(
            (n_frames, calib_h), Image.LANCZOS))
    page[y_calib:y_calib + calib_h, border:border + n_frames] = calib_strip
    
    # Чёрная рамка
    page[0:border, :] = 0                          # верх
    page[page_h - border:page_h, :] = 0            # низ
    page[:, 0:border] = 0                          # лево
    page[:, page_w - border:page_w] = 0            # право
    
    print(f"   Страница: {page_w}×{page_h} px (рамка {border}px)")
    print(f"   Левый канал:    y={y_left},  {n_freqs}×{n_frames}")
    print(f"   Правый канал:   y={y_right}, {n_freqs}×{n_frames}")
    print(f"   Калибр. шкала:  y={y_calib}, {calib_h}×{n_frames}")
    
    return page


def audio_to_pages(wav_path: str, output_base: str, config: dict):
    """Кодирует аудио в страницы для печати."""
    preset = PRESETS[config["active_preset"]]
    n_fft = preset["N_FFT"]
    hop_length = preset["HOP_LENGTH"]
    target_sr = 44100
    
    print(f"\n=== КОДИРОВАНИЕ АУДИО (GRAYSCALE) ===")
    print(f"Пресет: {config['active_preset']} (FFT={n_fft}, HOP={hop_length})")
    
    # Загрузка
    y, sr = librosa.load(wav_path, sr=target_sr, mono=False)
    if y.ndim == 1:
        y = np.vstack([y, y.copy()])
    print(f"   Аудио: {y.shape}, {sr} Гц, {y.shape[1]/sr:.1f} сек")
    
    # Обрезка
    if config.get("trim_enabled", False):
        t0 = int(config["trim_start"] * sr)
        t1 = int(config["trim_end"] * sr) if config["trim_end"] > 0 else y.shape[1]
        if t1 > t0:
            y = y[:, t0:t1]
            print(f"   Обрезано: {t0/sr:.1f}s - {t1/sr:.1f}s")
    
    # STFT
    print("   Вычисление STFT...")
    D_left = librosa.stft(y[0], n_fft=n_fft, hop_length=hop_length, window='hann')
    D_right = librosa.stft(y[1], n_fft=n_fft, hop_length=hop_length, window='hann')
    
    n_freqs, n_frames = D_left.shape  # n_freqs = n_fft // 2 + 1
    print(f"   Спектрограмма: {n_freqs} частот × {n_frames} кадров")
    
    # Магнитуда в dB
    mag_left = np.abs(D_left)
    mag_right = np.abs(D_right)
    
    ref_left = float(np.max(mag_left)) or 1.0
    ref_right = float(np.max(mag_right)) or 1.0
    
    db_left = librosa.amplitude_to_db(mag_left, ref=ref_left)
    db_right = librosa.amplitude_to_db(mag_right, ref=ref_right)
    
    mag_min = float(np.floor(min(db_left.min(), db_right.min())))
    print(f"   dB диапазон: [{mag_min:.0f}, 0]")
    print(f"   ref: L={ref_left:.4f}, R={ref_right:.4f}")
    
    # dB -> 0..255 (0 = тихо/чёрный, 255 = громко/белый)
    # Но для печати на белой бумаге инвертируем: 0 = громко/чёрный
    db_left = np.clip(db_left, mag_min, 0)
    db_right = np.clip(db_right, mag_min, 0)
    
    # Линейное отображение dB -> [0, 255]
    left_img = ((db_left - mag_min) / (-mag_min) * 255).astype(np.uint8)
    right_img = ((db_right - mag_min) / (-mag_min) * 255).astype(np.uint8)
    
    # Инвертируем для печати: громкие частоты = тёмные
    #left_img = 255 - left_img
    #right_img = 255 - right_img
    
    print(f"   Яркость: L [{left_img.min()},{left_img.max()}], R [{right_img.min()},{right_img.max()}]")
    
    # Метаданные
    metadata = {
        'n_fft': n_fft,
        'hop_length': hop_length,
        'original_length': len(y[0]),
        'n_freqs': n_freqs,
        'sr': target_sr,
        'ref_left': ref_left,
        'ref_right': ref_right,
        'mag_min': mag_min,
        'total_frames': n_frames,
        'total_pages': 1,
        'encoding': 'grayscale_stacked',
        'phase_generate_iterations': config.get("phase_generate_iterations", 5000),
        'phase_generate_random_seed': config.get("phase_generate_random_seed", 454),
        'griffin_lim_mode': config.get("griffin_lim_mode", "fast"),
        'griffin_lim_parallel': config.get("griffin_lim_parallel", True),
        'early_stop_enabled': config.get("early_stop_enabled", True),
        'early_stop_threshold': config.get("early_stop_threshold", 0.0001),
        'early_stop_patience': config.get("early_stop_patience", 10),
    }
    
    output_dir = str(Path(output_base).parent) if Path(output_base).parent != Path('.') else '.'
    stem = Path(output_base).stem
    saved = []
    
    # Собираем страницу спектрограммы
    page = assemble_page(left_img, right_img, config)
    spec_path = str(Path(output_dir) / f"{stem}_spectrum.png")
    Image.fromarray(page).save(spec_path, 'PNG', compress_level=0)
    saved.append(spec_path)
    size_mb = Path(spec_path).stat().st_size / (1024 * 1024)
    print(f"   ✓ {Path(spec_path).name} ({size_mb:.1f} MB)")
    
    # QR-страница
    qr_path = str(Path(output_dir) / f"{stem}_qr.png")
    _generate_qr_page(metadata, config, qr_path)
    saved.append(qr_path)
    
    print(f"\n   Готово: {len(saved)} файла")
    return saved, metadata
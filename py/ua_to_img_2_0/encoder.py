# encoder.py

import time
import io
import numpy as np
import librosa
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import platform

from config import PRESETS, PAPER_SIZES
from layout import calculate_layout, calculate_pages
from calibration import generate_calibration_strip
from metadata_sheet import encode_metadata_text
from utils import mm_to_pixels


def _find_high_cut_auto(mag_left_db: np.ndarray, mag_right_db: np.ndarray, 
                        freqs: np.ndarray, threshold_db: float = -80, 
                        freq_min: float = 8000, margin_db: float = 10):
    """Автоматически находит частоту среза высоких частот по спаду энергии."""
    mean_mag = np.maximum(np.mean(mag_left_db, axis=1), np.mean(mag_right_db, axis=1))
    
    from scipy.ndimage import uniform_filter1d
    smooth_size = max(3, len(mean_mag) // 20)
    mean_mag_smooth = uniform_filter1d(mean_mag, size=smooth_size)
    
    effective_threshold = threshold_db + margin_db
    below_threshold = mean_mag_smooth < effective_threshold
    min_idx = np.searchsorted(freqs, freq_min)
    
    cut_bin = len(freqs) - 1
    for i in range(min_idx, len(freqs) - 5):
        if np.all(below_threshold[i:i+5]):
            cut_bin = max(min_idx, i)
            break
    
    print(f"   Автосрез ВЧ: порог {effective_threshold:.0f} dB, частота среза {freqs[cut_bin]:.0f} Гц")
    return cut_bin


def _generate_qr_page(global_metadata: dict, config: dict, output_path: str):
    """Создаёт отдельную страницу с QR-кодом."""
    dpi = config.get('dpi', 300)
    paper = PAPER_SIZES[config.get('paper_size', 'A4')]
    
    page_w = mm_to_pixels(paper['width_mm'], dpi)
    page_h = mm_to_pixels(paper['height_mm'], dpi)
    
    page = np.full((page_h, page_w), 255, dtype=np.uint8)
    metadata_text = encode_metadata_text(global_metadata)
    
    print(f"   Длина метаданных: {len(metadata_text)} символов")
    
    target_qr_size = int(min(page_w, page_h) * 0.70)
    
    try:
        import segno
        
        qr = segno.make(metadata_text, micro=False)
        matrix_size = qr.symbol_size()[0]
        module_size = max(1, target_qr_size // matrix_size)
        
        buf = io.BytesIO()
        qr.save(buf, kind='png', scale=module_size, dark='black', light='white', border=0)
        buf.seek(0)
        
        qr_img = np.array(Image.open(buf).convert('L'), dtype=np.uint8)
        
        qr_h, qr_w = qr_img.shape
        qr_x = max(0, (page_w - qr_w) // 2)
        qr_y = max(0, (page_h - qr_h) // 2 - 80)
        
        qr_x_end = min(page_w, qr_x + qr_w)
        qr_y_end = min(page_h, qr_y + qr_h)
        
        page[qr_y:qr_y_end, qr_x:qr_x_end] = qr_img[:qr_y_end-qr_y, :qr_x_end-qr_x]
        
        print(f"   QR: {qr_w}×{qr_h} px (module_size={module_size}, "
              f"занимает {qr_w*100/page_w:.0f}% ширины листа)")
        
        img = Image.fromarray(page, mode='L')
        draw = ImageDraw.Draw(img)
        
        font = None
        small_font = None
        font_paths = []
        
        if platform.system() == 'Windows':
            font_paths = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/consola.ttf"]
        elif platform.system() == 'Darwin':
            font_paths = ["/System/Library/Fonts/Helvetica.ttc"]
        else:
            font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        
        for fp in font_paths:
            try:
                font = ImageFont.truetype(fp, 24)
                small_font = ImageFont.truetype(fp, 14)
                break
            except (IOError, OSError):
                continue
        
        if font is None:
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        title = "AudioPrint v2 — метаданные аудиофайла (Cyan/Magenta stereo)"
        bbox = draw.textbbox((0, 0), title, font=font)
        text_w = bbox[2] - bbox[0]
        text_x = (page_w - text_w) // 2
        text_y = qr_y + qr_h + 30
        
        draw.text((text_x, text_y), title, fill=0, font=font)
        
        duration = global_metadata['original_length'] / global_metadata['sr']
        info_lines = [
            f"N_FFT={global_metadata['n_fft']} | HOP={global_metadata['hop_length']} | SR={global_metadata['sr']} Гц",
            f"Частот: {global_metadata['n_freqs']} | Кадров: {global_metadata['total_frames']} | Страниц: {global_metadata['total_pages']}",
            f"Длительность: {duration:.1f} сек | Griffin-Lim: {global_metadata['griffin_lim_mode']}, {global_metadata['phase_generate_iterations']} итераций",
            f"ref_left={global_metadata['ref_left']:.2f} | ref_right={global_metadata['ref_right']:.2f} | mag_min={global_metadata['mag_min']} dB",
            f"Cyan = левый канал | Magenta = правый канал",
        ]
        
        for i, line in enumerate(info_lines):
            bbox = draw.textbbox((0, 0), line, font=small_font)
            line_w = bbox[2] - bbox[0]
            draw.text(((page_w - line_w) // 2, text_y + 40 + i * 22), line, fill=100, font=small_font)
        
        page = np.array(img, dtype=np.uint8)
        
    except ImportError:
        print("   ⚠️ segno не установлен: pip install segno")
        img = Image.fromarray(page, mode='L')
        draw = ImageDraw.Draw(img)
        draw.text((50, 50), metadata_text, fill=0)
        page = np.array(img, dtype=np.uint8)
    
    img = Image.fromarray(page, mode='L')
    img.save(output_path, 'PNG', compress_level=6)
    
    file_size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    print(f"   QR-страница: {Path(output_path).name} ({file_size_mb:.2f} MB)")
    
    return output_path


def _render_text_rgb(page: np.ndarray, text: str, region: dict):
    """Рендерит текст на RGB изображении."""
    img = Image.fromarray(page, mode='RGB')
    draw = ImageDraw.Draw(img)
    
    font = None
    font_size = 12
    font_paths = []
    
    if platform.system() == 'Windows':
        font_paths = ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/arial.ttf"]
    elif platform.system() == 'Darwin':
        font_paths = ["/System/Library/Fonts/Menlo.ttc"]
    else:
        font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
    
    loaded_font_path = None
    for font_path in font_paths:
        try:
            font = ImageFont.truetype(font_path, font_size)
            loaded_font_path = font_path
            break
        except (IOError, OSError):
            continue
    
    if font is None:
        font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    if text_w > region['w'] * 0.9 and loaded_font_path is not None:
        scale = region['w'] / text_w * 0.9
        new_size = max(8, int(font_size * scale))
        try:
            font = ImageFont.truetype(loaded_font_path, new_size)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except (IOError, OSError):
            pass
    
    x = region['x'] + max(0, (region['w'] - text_w) // 2)
    y = region['y'] + max(0, (region['h'] - text_h) // 2)
    
    draw.text((x, y), text, fill=(100, 100, 100), font=font)
    
    result = np.array(img, dtype=np.uint8)
    np.copyto(page, result)


def assemble_page_stereo(spec_left: np.ndarray, spec_right: np.ndarray,
                         layout: dict, page_metadata: dict, config: dict) -> np.ndarray:
    """
    Собирает страницу с цветной стерео-спектрограммой.
    Спектрограмма НЕ МАСШТАБИРУЕТСЯ по ширине — каждый кадр = 1 пиксель.
    Центрируется на странице с белыми полями.
    """
    import cv2
    from markers import generate_marker
    
    page_w = layout['page_w']
    page_h = layout['page_h']
    marker_size = layout['marker_size']
    
    # Белый лист RGB
    page = np.full((page_h, page_w, 3), 255, dtype=np.uint8)
    
    # --- Маркеры (чёрные) ---
    marker_gray = generate_marker(marker_size)
    marker_rgb = np.stack([marker_gray, marker_gray, marker_gray], axis=-1)
    
    for pos_name, (cx, cy) in layout['markers'].items():
        x = cx - marker_size // 2
        y = cy - marker_size // 2
        
        x_start = max(0, x)
        y_start = max(0, y)
        x_end = min(page_w, x + marker_size)
        y_end = min(page_h, y + marker_size)
        
        m_x_start = max(0, -x)
        m_y_start = max(0, -y)
        m_x_end = marker_size - max(0, (x + marker_size) - page_w)
        m_y_end = marker_size - max(0, (y + marker_size) - page_h)
        
        page[y_start:y_end, x_start:x_end] = marker_rgb[m_y_start:m_y_end, m_x_start:m_x_end]
    
    # --- Цветная спектрограмма ---
    spec_region = layout['spectrogram']
    max_w = spec_region['w']
    max_h = spec_region['h']
    
    n_freqs, n_frames = spec_left.shape
    
    # Масштабируем ТОЛЬКО по высоте до max_h
    if n_freqs != max_h:
        left_scaled = cv2.resize(spec_left.astype(np.float32), (n_frames, max_h), interpolation=cv2.INTER_LINEAR)
        right_scaled = cv2.resize(spec_right.astype(np.float32), (n_frames, max_h), interpolation=cv2.INTER_LINEAR)
    else:
        left_scaled = spec_left.astype(np.float32)
        right_scaled = spec_right.astype(np.float32)
    
    actual_h = max_h
    
    # По ширине: НЕ МАСШТАБИРУЕМ! Каждый кадр = 1 пиксель.
    # Если кадров меньше чем ширина области — центрируем с белыми полями.
    # Если больше — это ошибка, но на всякий случай обрежем.
    if n_frames > max_w:
        left_scaled = left_scaled[:, :max_w]
        right_scaled = right_scaled[:, :max_w]
        actual_w = max_w
    else:
        actual_w = n_frames
    
    # Центрируем по ширине
    x_offset = spec_region['x'] + (max_w - actual_w) // 2
    y_offset = spec_region['y']
    
    # Цветовое кодирование на белом фоне
    r_channel = np.clip(255.0 - left_scaled[:, :actual_w], 0, 255).astype(np.uint8)
    g_channel = np.clip(255.0 - right_scaled[:, :actual_w], 0, 255).astype(np.uint8)
    b_channel = np.full((actual_h, actual_w), 255, dtype=np.uint8)
    
    color_spec = np.stack([r_channel, g_channel, b_channel], axis=-1)
    
    # Размещаем на странице
    page[y_offset:y_offset+actual_h, x_offset:x_offset+actual_w] = color_spec
    
    # --- Калибровочная шкала ---
    if config.get('calibration_enabled', True):
        calib = layout['calibration']
        if calib['w'] > 0 and calib['h'] > 0:
            step_w = max(10, calib['w'] // 16)
            strip = generate_calibration_strip(step_width_px=step_w, step_height_px=calib['h'])
            if strip.shape[1] > calib['w']:
                strip = strip[:, :calib['w']]
            
            y_start = calib['y']
            y_end = min(calib['y'] + calib['h'], page_h)
            x_center = calib['x'] + max(0, (calib['w'] - strip.shape[1]) // 2)
            x_end = min(x_center + strip.shape[1], page_w)
            
            strip_rgb = np.stack([strip, strip, strip], axis=-1)
            page[y_start:y_end, x_center:x_end] = strip_rgb[:y_end-y_start, :x_end-x_center]
    
    # --- Номер страницы ---
    meta_region = layout['metadata_region']
    page_num = page_metadata.get('page', 1)
    total_pages = page_metadata.get('total_pages', 1)
    page_info = f"стр. {page_num} из {total_pages}  |  Cyan=L  Magenta=R"
    _render_text_rgb(page, page_info, meta_region)
    
    return page


def audio_to_pages(wav_path: str, output_base: str, config: dict):
    """Кодирует аудио в набор страниц A4 для печати."""
    preset = PRESETS[config["active_preset"]]
    n_fft = preset["N_FFT"]
    hop_length = preset["HOP_LENGTH"]
    target_sr = 44100
    
    print(f"\n=== КОДИРОВАНИЕ АУДИО В СТРАНИЦЫ (Cyan/Magenta) ===")
    print(f"Пресет: {config['active_preset']} (FFT={n_fft}, HOP={hop_length})")
    
    # --- Загрузка аудио ---
    y, sr = librosa.load(wav_path, sr=target_sr, mono=False)
    
    if y.ndim == 1:
        y = np.vstack([y, y.copy()])
    
    print(f"   Аудио загружено: {y.shape}, {sr} Гц")
    
    # --- Обрезка ---
    if config.get("trim_enabled", False):
        trim_start = config.get("trim_start", 0.0)
        trim_end = config.get("trim_end", 0.0)
        
        start_sample = int(trim_start * sr)
        end_sample = int(trim_end * sr) if trim_end > 0 else y.shape[1]
        
        start_sample = max(0, min(start_sample, y.shape[1]))
        end_sample = max(start_sample, min(end_sample, y.shape[1]))
        
        y = y[:, start_sample:end_sample]
        duration = y.shape[1] / sr
        
        print(f"   Аудио обрезано: {trim_start:.2f}s - {trim_end if trim_end > 0 else duration:.2f}s")
        print(f"   Длительность фрагмента: {duration:.2f} сек")
    
    # --- Каналы ---
    left = y[0]
    right = y[1]
    
    # --- STFT ---
    print("   Вычисление STFT...")
    D_left = librosa.stft(left, n_fft=n_fft, hop_length=hop_length, window='hann')
    D_right = librosa.stft(right, n_fft=n_fft, hop_length=hop_length, window='hann')
    
    n_freqs_orig, n_frames_total = D_left.shape
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    
    print(f"   Спектрограмма: {n_freqs_orig} частот × {n_frames_total} кадров")
    
    # --- Опорные уровни ---
    mag_left = np.abs(D_left)
    mag_right = np.abs(D_right)
    ref_left = float(np.max(mag_left))
    ref_right = float(np.max(mag_right))
    
    if ref_left == 0:
        ref_left = 1.0
    if ref_right == 0:
        ref_right = 1.0
    
    print(f"   ref_left: {ref_left:.4f}, ref_right: {ref_right:.4f}")
    
    # --- Частотная обрезка ---
    low_cut_bin = 0
    if config.get("low_cut_enabled", False) and config.get("low_cut_freq", 0) > 0:
        low_cut_bin = int(np.searchsorted(freqs, config["low_cut_freq"]))
        print(f"   Обрезка низких частот: {config['low_cut_freq']} Гц ({low_cut_bin} бинов)")
    
    high_cut_bin = len(freqs)
    high_cut_bins_removed = 0
    if config.get("high_cut_enabled", False):
        if config.get("high_cut_mode", "auto") == "auto":
            mag_left_db = librosa.amplitude_to_db(mag_left, ref=ref_left)
            mag_right_db = librosa.amplitude_to_db(mag_right, ref=ref_right)
            high_cut_bin = _find_high_cut_auto(
                mag_left_db, mag_right_db, freqs,
                config.get("high_cut_auto_threshold_db", -80),
                config.get("high_cut_auto_freq_min", 8000),
                config.get("high_cut_auto_margin_db", 10)
            )
        else:
            high_cut_bin = int(np.searchsorted(freqs, config.get("high_cut_freq", 16000)))
        
        D_left = D_left[low_cut_bin:high_cut_bin, :]
        D_right = D_right[low_cut_bin:high_cut_bin, :]
        high_cut_bins_removed = n_freqs_orig - high_cut_bin
        print(f"   Обрезка высоких частот: выше {freqs[high_cut_bin-1]:.0f} Гц ({high_cut_bins_removed} бинов)")
    else:
        D_left = D_left[low_cut_bin:, :]
        D_right = D_right[low_cut_bin:, :]
    
    n_freqs = D_left.shape[0]
    
    # --- Конвертация в яркость (0-255) ---
    mag_left = np.abs(D_left)
    mag_right = np.abs(D_right)
    mag_min = -120
    
    mag_left_db = librosa.amplitude_to_db(mag_left, ref=ref_left)
    mag_right_db = librosa.amplitude_to_db(mag_right, ref=ref_right)
    
    print(f"   DEBUG ENCODE:")
    print(f"   mag_left_db: [{mag_left_db.min():.2f}, {mag_left_db.max():.2f}], mean={mag_left_db.mean():.2f}")
    print(f"   mag_right_db: [{mag_right_db.min():.2f}, {mag_right_db.max():.2f}], mean={mag_right_db.mean():.2f}")
    
    mag_left_norm = np.clip((mag_left_db - mag_min) / (-mag_min) * 255, 0, 255).astype(np.uint8)
    mag_right_norm = np.clip((mag_right_db - mag_min) / (-mag_min) * 255, 0, 255).astype(np.uint8)
    
    print(f"   Яркость: left [{mag_left_norm.min()}, {mag_left_norm.max()}], "
          f"right [{mag_right_norm.min()}, {mag_right_norm.max()}]")
    
    # --- Расчёт страниц ---
    layout = calculate_layout(config)
    frames_per_page = layout['frames_per_page']
    n_pages = calculate_pages(n_frames_total, frames_per_page)
    
    print(f"\n   Разбиение на страницы:")
    print(f"   Всего кадров: {n_frames_total}")
    print(f"   Кадров на страницу: {frames_per_page}")
    print(f"   Страниц спектрограмм: {n_pages}")
    print(f"   + 1 страница с QR-кодом")
    
    # --- Глобальные метаданные ---
    global_metadata = {
        'n_fft': n_fft,
        'hop_length': hop_length,
        'original_length': len(left),
        'n_freqs': n_freqs,
        'n_freqs_original': n_freqs_orig,
        'sr': target_sr,
        'ref_left': ref_left,
        'ref_right': ref_right,
        'low_cut_bin': low_cut_bin,
        'high_cut_bins_removed': high_cut_bins_removed,
        'mag_min': mag_min,
        'total_frames': n_frames_total,
        'total_pages': n_pages,
        'frames_per_page': frames_per_page,
        'encoding': 'cyan_magenta',
        'phase_generate_iterations': config.get("phase_generate_iterations", 5000),
        'phase_generate_random_seed': config.get("phase_generate_random_seed", 454),
        'griffin_lim_mode': config.get("griffin_lim_mode", "fast"),
        'griffin_lim_parallel': config.get("griffin_lim_parallel", True),
        'early_stop_enabled': config.get("early_stop_enabled", True),
        'early_stop_threshold': config.get("early_stop_threshold", 0.0001),
        'early_stop_patience': config.get("early_stop_patience", 10),
    }
    
    # --- Генерация страниц ---
    saved_files = []
    output_dir = str(Path(output_base).parent) if Path(output_base).parent != Path('.') else '.'
    output_stem = Path(output_base).stem
    
    print(f"\n   Генерация страниц спектрограмм:")
    
    for page_num in range(n_pages):
        start_frame = page_num * frames_per_page
        end_frame = min((page_num + 1) * frames_per_page, n_frames_total)
        
        left_slice = mag_left_norm[:, start_frame:end_frame]
        right_slice = mag_right_norm[:, start_frame:end_frame]
        
        page_metadata = {
            **global_metadata,
            'page': page_num + 1,
            'start_frame': start_frame,
            'n_frames': end_frame - start_frame,
        }
        
        page_img = assemble_page_stereo(left_slice, right_slice, layout, page_metadata, config)
        
        if n_pages == 1:
            filename = f"{output_stem}.png"
        else:
            filename = f"{output_stem}_page{page_num+1}of{n_pages}.png"
        
        filepath = str(Path(output_dir) / filename)
        
        img = Image.fromarray(page_img, mode='RGB')
        img.save(filepath, 'PNG', compress_level=6)
        
        file_size_mb = Path(filepath).stat().st_size / (1024 * 1024)
        print(f"   Страница {page_num+1}/{n_pages}: {filename} ({file_size_mb:.1f} MB) "
              f"[кадры {start_frame}-{end_frame}]")
        
        saved_files.append(filepath)
    
    # --- QR-страница ---
    print(f"\n   Генерация QR-страницы:")
    qr_filename = f"{output_stem}_qr.png"
    qr_filepath = str(Path(output_dir) / qr_filename)
    _generate_qr_page(global_metadata, config, qr_filepath)
    saved_files.append(qr_filepath)
    
    print(f"\n   ✓ Создано страниц: {len(saved_files)} (включая QR-страницу)")
    print(f"   Кодирование: Cyan = левый канал, Magenta = правый канал")
    print(f"   Параметры Griffin-Lim: {config.get('griffin_lim_mode')}, "
          f"{config.get('phase_generate_iterations')} итераций")
    
    return saved_files, global_metadata
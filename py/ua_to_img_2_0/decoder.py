# decoder.py — Grayscale декодер: два канала друг над другом, калибровка, QR

import time
import numpy as np
import librosa
import soundfile as sf
from PIL import Image
from pathlib import Path
from typing import List, Optional, Tuple
import cv2

from calibration import (
    measure_calibration_steps, validate_calibration, 
    build_correction_lut, correct_spectrogram
)
from metadata_sheet import decode_metadata_text


def decode_page(image_path: str, n_freqs: int, n_frames: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Декодирует страницу спектрограммы после сканирования.
    """
    print(f"\n   Сканирование: {Path(image_path).name}")
    
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Не удалось загрузить: {image_path}")
    
    print(f"   Размер скана: {img.shape[1]}×{img.shape[0]}")
    
    calib_h = 30
    total_h = n_freqs * 2 + calib_h
    calib_ratio = calib_h / total_h
    
    expected_w = n_frames
    expected_h_channels = n_freqs * 2
    
    # Шаг 1: найти тёмную область
    binary = cv2.adaptiveThreshold(
        img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, blockSize=21, C=4
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        print(f"   ⚠️ Область не найдена, используется всё изображение")
        page = img
        calib_region = None
    else:
        largest = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest)
        
        margin = max(10, int(min(w, h) * 0.02))
        x += margin
        y += margin
        w -= 2 * margin
        h -= 2 * margin
        
        if w <= 0 or h <= 0:
            print(f"   ⚠️ Отступ слишком большой, использую без отступа")
            x, y, w, h = cv2.boundingRect(largest)
        
        print(f"   Спектрограмма: x={x}, y={y}, {w}×{h} px (отступ {margin}px)")
        
        calib_h_scan = max(10, int(h * calib_ratio))
        calib_y_scan = y + h - calib_h_scan
        calib_region = img[calib_y_scan:calib_y_scan+calib_h_scan, x:x+w]
        
        channels_h_scan = h - calib_h_scan
        page = img[y:y+channels_h_scan, x:x+w]
        
        print(f"   Каналы в скане: {w}×{channels_h_scan} px, шкала: {w}×{calib_h_scan} px")
    
    # Шаг 2: масштабируем каналы
    if page.shape[1] != expected_w or page.shape[0] != expected_h_channels:
        print(f"   Масштабирование каналов: {page.shape[1]}×{page.shape[0]} → {expected_w}×{expected_h_channels}")
        page = cv2.resize(page, (expected_w, expected_h_channels), interpolation=cv2.INTER_LANCZOS4)
    
    # Шаг 3: разделяем на левый и правый
    half = page.shape[0] // 2
    left_ch = page[0:half, :]
    right_ch = page[half:half*2, :]
    
    # Калибровка отключена
    measured_calib = None
    
    if measured_calib is not None:
        lut = build_correction_lut(measured_calib)
        left_ch = correct_spectrogram(left_ch.astype(np.uint8), lut).astype(np.float32)
        right_ch = correct_spectrogram(right_ch.astype(np.uint8), lut).astype(np.float32)
        print(f"   Коррекция яркости применена")
    else:
        left_ch = left_ch.astype(np.float32)
        right_ch = right_ch.astype(np.float32)
        print(f"   Без коррекции яркости")
    
    print(f"   Каналы: {left_ch.shape[0]}×{left_ch.shape[1]}, L [{left_ch.min():.0f}, {left_ch.max():.0f}]")
    
    return left_ch, right_ch


def decode_qr_page(image_path: str) -> dict:
    """Декодирует QR-страницу и возвращает метаданные."""
    print(f"\n   Чтение QR: {Path(image_path).name}")
    
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Не удалось загрузить: {image_path}")
    
    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(img)
    
    if not data:
        data, points, _ = detector.detectAndDecode(255 - img)
    
    if not data:
        raise ValueError("QR-код не найден на странице!")
    
    print(f"   QR прочитан успешно")
    metadata = decode_metadata_text(data)
    
    metadata.setdefault('sr', 44100)
    metadata.setdefault('mag_min', -120.0)
    metadata.setdefault('ref_left', 1.0)
    metadata.setdefault('ref_right', 1.0)
    metadata.setdefault('phase_generate_iterations', 5000)
    metadata.setdefault('phase_generate_random_seed', 454)
    metadata.setdefault('griffin_lim_mode', 'fast')
    metadata.setdefault('griffin_lim_parallel', True)
    metadata.setdefault('early_stop_enabled', True)
    metadata.setdefault('early_stop_threshold', 0.0001)
    metadata.setdefault('early_stop_patience', 10)
    
    return metadata


def decode_pages(image_paths: List[str], config: dict, output_wav_path: str):
    """Декодирует страницы и восстанавливает аудио."""
    print(f"\n{'='*60}")
    print(f"ДЕКОДИРОВАНИЕ (GRAYSCALE STACKED)")
    print(f"{'='*60}")
    
    # Собираем все файлы
    all_files = []
    for p in image_paths:
        path = Path(p)
        if path.is_dir():
            all_files.extend(sorted(path.glob("*.png")))
            all_files.extend(sorted(path.glob("*.jpg")))
            all_files.extend(sorted(path.glob("*.jpeg")))
        elif '*' in str(p) or '?' in str(p):
            import glob
            all_files.extend([Path(x) for x in sorted(glob.glob(str(p)))])
        else:
            all_files.append(path)
    
    all_files = [str(f) for f in all_files if f.is_file()]
    
    if not all_files:
        raise ValueError("Не найдены файлы для декодирования")
    
    qr_path = None
    spectrum_paths = []
    
    for f in all_files:
        name = Path(f).name.lower()
        if '_qr' in name:
            qr_path = f
        else:
            spectrum_paths.append(f)
    
    if qr_path is None:
        raise ValueError("QR-страница не найдена! Имя файла должно содержать '_qr'")
    
    if not spectrum_paths:
        raise ValueError("Не найдены страницы со спектрограммами")
    
    print(f"\n   Найдено файлов: QR — 1, спектрограмм — {len(spectrum_paths)}")
    
    meta = decode_qr_page(qr_path)
    
    n_freqs = meta['n_freqs']
    n_frames = meta['total_frames']
    n_fft = meta['n_fft']
    hop_length = meta['hop_length']
    sr = meta['sr']
    original_length = meta['original_length']
    mag_min = meta['mag_min']
    
    print(f"\n   Параметры из QR:")
    print(f"   N_FFT: {n_fft}, HOP: {hop_length}, SR: {sr}")
    print(f"   Частот: {n_freqs}, Кадров: {n_frames}")
    print(f"   Длительность: {original_length / sr:.1f} сек")
    print(f"   Динамический диапазон: {mag_min:.0f} dB")
    
    all_left = []
    all_right = []
    
    for spec_path in spectrum_paths:
        left_ch, right_ch = decode_page(spec_path, n_freqs, n_frames)
        all_left.append(left_ch)
        all_right.append(right_ch)
    
    mag_left = all_left[0]
    mag_right = all_right[0]
    
    # Обрезаем края
    margin_frames = 3
    if n_frames > margin_frames * 2:
        mag_left = mag_left[:, margin_frames:-margin_frames]
        mag_right = mag_right[:, margin_frames:-margin_frames]
        n_frames_used = mag_left.shape[1]
        original_length = int(original_length * n_frames_used / n_frames)
        print(f"   Обрезано {margin_frames} кадров по краям ({n_frames} → {n_frames_used})")
    
    # Нормализация яркости: растягиваем до 0-255
    def normalize_channel(ch):
        ch_min = ch.min()
        ch_max = ch.max()
        if ch_max > ch_min:
            return (ch - ch_min) / (ch_max - ch_min) * 255.0
        return ch
    
    mag_left = normalize_channel(mag_left)
    mag_right = normalize_channel(mag_right)
    print(f"   После нормализации яркости: L [{mag_left.min():.0f}, {mag_left.max():.0f}]")
    
    # Яркость → dB
    db_left = (mag_left / 255.0) * (-mag_min) + mag_min
    db_right = (mag_right / 255.0) * (-mag_min) + mag_min
    
    # dB → амплитуда (НЕ нормализуем — оставляем реальные значения)
    amp_left = librosa.db_to_amplitude(db_left, ref=1.0)
    amp_right = librosa.db_to_amplitude(db_right, ref=1.0)
    
    print(f"\n   Амплитуда L: [{amp_left.min():.6f}, {amp_left.max():.4f}], mean={amp_left.mean():.6f}")
    print(f"   Амплитуда R: [{amp_right.min():.6f}, {amp_right.max():.4f}], mean={amp_right.mean():.6f}")
    
    # Griffin-Lim
    iterations = meta.get('phase_generate_iterations', 5000)
    random_seed = meta.get('phase_generate_random_seed', 454)
    if random_seed == -1:
        random_seed = None
    
    gl_mode = meta.get('griffin_lim_mode', 'fast')
    parallel = meta.get('griffin_lim_parallel', True)
    early_stop_enabled = meta.get('early_stop_enabled', True)
    early_stop_threshold = meta.get('early_stop_threshold', 0.0001)
    early_stop_patience = meta.get('early_stop_patience', 10)
    
    from phase_generator import griffin_lim_fast, griffin_lim_stereo_parallel
    
    t_start = time.time()
    print(f"\n   Восстановление фазы (Griffin-Lim {gl_mode}, {iterations} итераций)...")
    
    if parallel:
        phase_left, phase_right = griffin_lim_stereo_parallel(
            amp_left, amp_right, n_fft, hop_length,
            iterations=iterations, random_seed=random_seed, mode=gl_mode,
            early_stop_threshold=early_stop_threshold if early_stop_enabled else None,
            early_stop_patience=early_stop_patience, num_workers=2, verbose=True
        )
    else:
        seed_r = random_seed + 1 if random_seed is not None else None
        phase_left = griffin_lim_fast(
            amp_left, n_fft, hop_length, iterations, random_seed=random_seed,
            early_stop_threshold=early_stop_threshold if early_stop_enabled else None,
            early_stop_patience=early_stop_patience
        )
        phase_right = griffin_lim_fast(
            amp_right, n_fft, hop_length, iterations, random_seed=seed_r,
            early_stop_threshold=early_stop_threshold if early_stop_enabled else None,
            early_stop_patience=early_stop_patience
        )
    
    for name, ph in [("L", phase_left), ("R", phase_right)]:
        if np.any(np.isnan(ph)):
            np.nan_to_num(ph, copy=False, nan=0.0)
            print(f"   ⚠️ NaN в фазе {name} — заменены на 0")
    
    print("   Обратное STFT...")
    D_left = amp_left * np.exp(1j * phase_left)
    D_right = amp_right * np.exp(1j * phase_right)
    
    y_left = librosa.istft(D_left, hop_length=hop_length, length=original_length, window='hann')
    y_right = librosa.istft(D_right, hop_length=hop_length, length=original_length, window='hann')
    
    print(f"   y_left: min={y_left.min():.6f}, max={y_left.max():.6f}, std={y_left.std():.6f}")
    print(f"   y_right: min={y_right.min():.6f}, max={y_right.max():.6f}, std={y_right.std():.6f}")
    
    min_len = min(len(y_left), len(y_right))
    y_stereo = np.stack([y_left[:min_len], y_right[:min_len]], axis=1)
    
    # Нормализация громкости: всегда усиливаем до 0.95
    max_val = np.max(np.abs(y_stereo))
    if max_val > 0:
        print(f"   Пиковое значение: {max_val:.6f}")
        if max_val > 1.0:
            y_stereo /= max_val * 0.95
            print(f"   Сигнал ослаблен до 0.95")
        else:
            y_stereo = y_stereo / max_val * 0.95
            print(f"   Сигнал усилен до 0.95 (коэфф. {0.95/max_val:.1f}x)")
    
    y_16 = (y_stereo * 32767).clip(-32768, 32767).astype(np.int16)
    sf.write(output_wav_path, y_16, sr, subtype='PCM_16')
    
    duration = min_len / sr
    elapsed = time.time() - t_start
    size_mb = Path(output_wav_path).stat().st_size / (1024 * 1024)
    
    print(f"\n{'='*60}")
    print(f"ГОТОВО!")
    print(f"   Файл: {output_wav_path} ({size_mb:.1f} MB)")
    print(f"   Длительность: {duration:.1f} сек")
    print(f"   Время декодирования: {elapsed:.1f} сек")
    print(f"{'='*60}")
    
    return y_stereo
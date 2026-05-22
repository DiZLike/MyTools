# decoder.py — цветное стерео декодирование (Cyan/Magenta)

import time
import numpy as np
import librosa
import soundfile as sf
from PIL import Image
from pathlib import Path
from typing import List, Optional

from markers import find_markers, correct_perspective
from calibration import (measure_calibration_steps, validate_calibration,
                         build_correction_lut, correct_spectrogram, normalize_by_range,
                         is_original_print, CALIBRATION_VALUES)
from metadata_sheet import decode_metadata_text
from layout import calculate_layout
from phase_generator import griffin_lim, griffin_lim_fast, griffin_lim_stereo_parallel


def _pad_spectrum(data: np.ndarray, low_pad: int, high_pad: int) -> np.ndarray:
    """Дополняет спектр нулями сверху и снизу."""
    if low_pad > 0:
        data = np.vstack([np.zeros((low_pad, data.shape[1]), dtype=data.dtype), data])
    if high_pad > 0:
        data = np.vstack([data, np.zeros((high_pad, data.shape[1]), dtype=data.dtype)])
    return data


def correct_perspective_color(image: np.ndarray, markers: list,
                              target_width: int, target_height: int) -> np.ndarray:
    """Исправляет перспективу цветного изображения по 4 маркерам."""
    import cv2
    
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


def decode_qr_page(image_path: str) -> dict:
    """Декодирует отдельную страницу с QR-кодом."""
    import cv2
    
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Не удалось загрузить QR-страницу: {image_path}")
    
    print(f"\n   QR-страница загружена: {img.shape[1]}×{img.shape[0]}")
    
    detector = cv2.QRCodeDetector()
    
    # 1. Прямой поиск
    data, bbox, _ = detector.detectAndDecode(img)
    if data:
        print(f"   ✓ QR прочитан (прямой): {data[:100]}...")
        return decode_metadata_text(data)
    
    # 2. Инвертированный
    data, bbox, _ = detector.detectAndDecode(255 - img)
    if data:
        print(f"   ✓ QR прочитан (inverted): {data[:100]}...")
        return decode_metadata_text(data)
    
    # 3. Разные масштабы
    h, w = img.shape
    for scale in [0.5, 0.75, 1.25, 1.5, 2.0]:
        new_w, new_h = int(w * scale), int(h * scale)
        if new_w < 100 or new_h < 100 or new_w > 5000 or new_h > 5000:
            continue
        
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        data, _, _ = detector.detectAndDecode(resized)
        if data:
            print(f"   ✓ QR прочитан (scale={scale}): {data[:100]}...")
            return decode_metadata_text(data)
        
        data, _, _ = detector.detectAndDecode(255 - resized)
        if data:
            print(f"   ✓ QR прочитан (inverted scale={scale}): {data[:100]}...")
            return decode_metadata_text(data)
    
    # 4. Поиск окнами
    print(f"   Поиск окнами...")
    for win_pct in [0.4, 0.5, 0.6, 0.7, 0.8]:
        win_size = int(min(w, h) * win_pct)
        if win_size > w or win_size > h:
            continue
        step = max(1, win_size // 4)
        
        for y in range(0, h - win_size + 1, step):
            for x in range(0, w - win_size + 1, step):
                window = img[y:y + win_size, x:x + win_size]
                try:
                    data, _, _ = detector.detectAndDecode(window)
                    if data:
                        print(f"   ✓ QR прочитан (окно {win_size}px): {data[:100]}...")
                        return decode_metadata_text(data)
                except:
                    pass
                try:
                    data, _, _ = detector.detectAndDecode(255 - window)
                    if data:
                        print(f"   ✓ QR прочитан (inverted окно): {data[:100]}...")
                        return decode_metadata_text(data)
                except:
                    pass
    
    raise ValueError(f"QR-код не найден на странице: {image_path}")


def decode_single_page_color(image_path: str, global_metadata: dict,
                             config: dict, page_num: int) -> dict:
    """
    Декодирует страницу с цветной Cyan/Magenta спектрограммой.
    Находит спектрограмму внутри области, убирает белые поля.
    """
    import cv2
    
    img_bgr = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError(f"Не удалось загрузить: {image_path}")
    
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    
    print(f"\n   Скан загружен: {img_rgb.shape[1]}×{img_rgb.shape[0]}, RGB")
    
    # --- Коррекция перспективы ---
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    layout = calculate_layout(config)
    target_w = layout['page_w']
    target_h = layout['page_h']
    
    markers = find_markers(gray, marker_size_hint=layout['marker_size'])
    
    if markers is not None and len(markers) == 4:
        print(f"   Маркеры найдены, коррекция перспективы...")
        img_rgb = correct_perspective_color(img_rgb, markers, target_w, target_h)
    else:
        print(f"   ⚠️ Маркеры не найдены, масштабирование до {target_w}x{target_h}")
        img_rgb = cv2.resize(img_rgb, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
    
    # --- Извлекаем область спектрограммы ---
    spec_region = layout['spectrogram']
    sx = max(0, spec_region['x'])
    sy = max(0, spec_region['y'])
    sw = min(spec_region['w'], img_rgb.shape[1] - sx)
    sh = min(spec_region['h'], img_rgb.shape[0] - sy)
    
    color_spec = img_rgb[sy:sy+sh, sx:sx+sw, :]
    
    # --- Цветоделение с белого фона ---
    R = color_spec[:, :, 0].astype(np.float32)
    G = color_spec[:, :, 1].astype(np.float32)
    
    left_raw = np.clip(255.0 - R, 0, 255)
    right_raw = np.clip(255.0 - G, 0, 255)
    
    print(f"   Извлечено: {left_raw.shape[1]}×{left_raw.shape[0]}")
    
    # --- Получаем размеры из метаданных ---
    n_freqs = global_metadata.get('n_freqs', 2049)
    total_frames = global_metadata.get('total_frames', 0)
    total_pages = global_metadata.get('total_pages', 1)
    
    frames_per_page_original = int(np.ceil(total_frames / total_pages))
    start_frame = (page_num - 1) * frames_per_page_original
    end_frame = min(page_num * frames_per_page_original, total_frames)
    expected_frames = end_frame - start_frame
    
    print(f"   Ожидаемые размеры для страницы {page_num}: {expected_frames}×{n_freqs}")
    
    # --- Находим спектрограмму (убираем белые поля слева/справа) ---
    # Ищем столбцы, где ЕСТЬ сигнал (не чисто белый)
    col_max = np.max(left_raw, axis=0)
    signal_cols = col_max > 5  # столбцы где есть хоть какой-то сигнал
    
    if np.any(signal_cols):
        signal_indices = np.where(signal_cols)[0]
        spec_start = signal_indices[0]
        spec_end = signal_indices[-1] + 1
        spec_width = spec_end - spec_start
        
        print(f"   Найдена спектрограмма: столбцы [{spec_start}, {spec_end}], ширина={spec_width}")
        
        # Вырезаем только спектрограмму
        left_trimmed = left_raw[:, spec_start:spec_end]
        right_trimmed = right_raw[:, spec_start:spec_end]
    else:
        left_trimmed = left_raw
        right_trimmed = right_raw
        spec_width = left_raw.shape[1]
    
    # --- Масштабируем к ожидаемым размерам ---
    actual_h = left_trimmed.shape[0]
    
    if actual_h != n_freqs or spec_width != expected_frames:
        print(f"   Масштабирование: {spec_width}×{actual_h} -> {expected_frames}×{n_freqs}")
        left_scaled = cv2.resize(left_trimmed, (expected_frames, n_freqs), interpolation=cv2.INTER_LINEAR)
        right_scaled = cv2.resize(right_trimmed, (expected_frames, n_freqs), interpolation=cv2.INTER_LINEAR)
    else:
        left_scaled = left_trimmed
        right_scaled = right_trimmed
    
    # Не переворачиваем
    left_spec = left_scaled.astype(np.float32)
    right_spec = right_scaled.astype(np.float32)
    
    print(f"   Итог: left={left_spec.shape}, right={right_spec.shape}")
    print(f"   DEBUG left final: [{left_spec.min():.1f}, {left_spec.max():.1f}], mean={left_spec.mean():.1f}")
    
    return {
        'mag_left': left_spec,
        'mag_right': right_spec,
        'n_frames': expected_frames,
    }


def decode_multipage(page_paths: List[str], qr_path: str, config: dict, output_wav_path: str) -> np.ndarray:
    """Декодирует QR-страницу и страницы спектрограмм, собирает аудио."""
    print(f"\n{'='*60}")
    print(f"ДЕКОДИРОВАНИЕ СТРАНИЦ (Cyan/Magenta)")
    print(f"{'='*60}")
    
    # --- QR-страница ---
    print(f"\n--- QR-страница: {Path(qr_path).name} ---")
    global_metadata = decode_qr_page(qr_path)
    
    print(f"\n   Метаданные:")
    print(f"   N_FFT: {global_metadata['n_fft']}")
    print(f"   HOP_LENGTH: {global_metadata['hop_length']}")
    print(f"   Частот: {global_metadata['n_freqs']}")
    print(f"   Всего кадров: {global_metadata.get('total_frames', 'НЕТ')}")
    print(f"   Страниц: {global_metadata.get('total_pages', 'НЕТ')}")
    print(f"   Длительность: {global_metadata['original_length'] / global_metadata.get('sr', 44100):.2f} сек")
    print(f"   ref_left: {global_metadata.get('ref_left', 'НЕТ')}")
    print(f"   ref_right: {global_metadata.get('ref_right', 'НЕТ')}")
    print(f"   mag_min: {global_metadata.get('mag_min', 'НЕТ')} dB")
    
    # --- Декодируем страницы ---
    print(f"\nНайдено страниц спектрограмм: {len(page_paths)}")
    
    pages = []
    for i, path in enumerate(page_paths):
        print(f"\n--- Страница {i+1}/{len(page_paths)}: {Path(path).name} ---")
        try:
            page_data = decode_single_page_color(path, global_metadata, config, page_num=i+1)
            pages.append(page_data)
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    # Склеиваем
    all_left, all_right = [], []
    for page in pages:
        all_left.append(page['mag_left'])
        all_right.append(page['mag_right'])
    
    mag_left_full = np.hstack(all_left)
    mag_right_full = np.hstack(all_right)
    
    print(f"\n   Полная спектрограмма: {mag_left_full.shape}")
    
    # Проверяем размер
    total_frames_expected = global_metadata.get('total_frames', 0)
    if total_frames_expected > 0 and mag_left_full.shape[1] != total_frames_expected:
        print(f"   ⚠️ Кадров: {mag_left_full.shape[1]}, ожидалось {total_frames_expected}")
        if mag_left_full.shape[1] > total_frames_expected:
            mag_left_full = mag_left_full[:, :total_frames_expected]
            mag_right_full = mag_right_full[:, :total_frames_expected]
    
    # --- Восстановление магнитуды ---
    mag_min = global_metadata.get('mag_min', -120)
    ref_left = global_metadata.get('ref_left', 1.0)
    ref_right = global_metadata.get('ref_right', 1.0)
    
    print(f"\n   Восстановление магнитуды:")
    print(f"   mag_min={mag_min}, ref_left={ref_left:.6f}, ref_right={ref_right:.6f}")
    print(f"   mag_left_full: [{mag_left_full.min():.1f}, {mag_left_full.max():.1f}], mean={mag_left_full.mean():.1f}")
    print(f"   mag_right_full: [{mag_right_full.min():.1f}, {mag_right_full.max():.1f}], mean={mag_right_full.mean():.1f}")
    
    # Шаг 1: Яркость (0-255) -> dB (правильное обратное преобразование)
    mag_left_db = (mag_left_full / 255.0) * (-mag_min) + mag_min
    mag_right_db = (mag_right_full / 255.0) * (-mag_min) + mag_min
    
    print(f"   dB left: [{mag_left_db.min():.1f}, {mag_left_db.max():.1f}], mean={mag_left_db.mean():.1f}")
    print(f"   dB right: [{mag_right_db.min():.1f}, {mag_right_db.max():.1f}], mean={mag_right_db.mean():.1f}")
    
    if mag_left_db.max() < -10:
        print(f"   ⚠️ ПРЕДУПРЕЖДЕНИЕ: Максимум dB левого канала = {mag_left_db.max():.1f} (ожидается ~0)")
    if mag_right_db.max() < -10:
        print(f"   ⚠️ ПРЕДУПРЕЖДЕНИЕ: Максимум dB правого канала = {mag_right_db.max():.1f} (ожидается ~0)")
    
    # Шаг 2: dB -> линейная амплитуда с ПРАВИЛЬНЫМ ref
    # ref должен быть исходной амплитудой, которая была max() при кодировании
    mag_left = librosa.db_to_amplitude(mag_left_db, ref=ref_left)
    mag_right = librosa.db_to_amplitude(mag_right_db, ref=ref_right)
    
    print(f"   Амплитуда left: [{mag_left.min():.6f}, {mag_left.max():.6f}], mean={mag_left.mean():.6f}")
    print(f"   Амплитуда right: [{mag_right.min():.6f}, {mag_right.max():.6f}], mean={mag_right.mean():.6f}")
    
    # Дополняем обрезанные частоты
    mag_left = _pad_spectrum(mag_left, global_metadata.get('low_cut_bin', 0),
                            global_metadata.get('high_cut_bins_removed', 0))
    mag_right = _pad_spectrum(mag_right, global_metadata.get('low_cut_bin', 0),
                             global_metadata.get('high_cut_bins_removed', 0))
    
    # --- Генерация фазы ---
    n_fft = global_metadata['n_fft']
    hop_length = global_metadata['hop_length']
    original_length = global_metadata['original_length']
    sr = global_metadata.get('sr', 44100)
    
    iterations = global_metadata.get('phase_generate_iterations', 5000)
    random_seed = global_metadata.get('phase_generate_random_seed', 454)
    if random_seed == -1:
        random_seed = None
    
    gl_mode = global_metadata.get('griffin_lim_mode', 'fast')
    parallel = global_metadata.get('griffin_lim_parallel', True)
    early_stop_enabled = global_metadata.get('early_stop_enabled', True)
    early_stop_threshold = global_metadata.get('early_stop_threshold', 0.0001)
    early_stop_patience = global_metadata.get('early_stop_patience', 10)
    
    t_start = time.time()
    
    print(f"\n   Генерация фазы: Griffin-Lim ({gl_mode}, {iterations} итераций)...")
    
    if parallel:
        phase_left, phase_right = griffin_lim_stereo_parallel(
            mag_left, mag_right, n_fft, hop_length,
            iterations=iterations, random_seed=random_seed, mode=gl_mode,
            scale_factor=None, coarse_iterations=None, fine_iterations=None,
            early_stop_threshold=early_stop_threshold if early_stop_enabled else None,
            early_stop_patience=early_stop_patience, num_workers=2, verbose=True
        )
    else:
        if gl_mode == 'fast':
            phase_left = griffin_lim_fast(mag_left, n_fft, hop_length, iterations,
                                          random_seed=random_seed,
                                          early_stop_threshold=early_stop_threshold if early_stop_enabled else None,
                                          early_stop_patience=early_stop_patience)
            phase_right = griffin_lim_fast(mag_right, n_fft, hop_length, iterations,
                                           random_seed=random_seed + 1 if random_seed else None,
                                           early_stop_threshold=early_stop_threshold if early_stop_enabled else None,
                                           early_stop_patience=early_stop_patience)
        else:
            phase_left = griffin_lim(mag_left, n_fft, hop_length, iterations,
                                     random_seed=random_seed,
                                     early_stop_threshold=early_stop_threshold if early_stop_enabled else None,
                                     early_stop_patience=early_stop_patience)
            phase_right = griffin_lim(mag_right, n_fft, hop_length, iterations,
                                      random_seed=random_seed + 1 if random_seed else None,
                                      early_stop_threshold=early_stop_threshold if early_stop_enabled else None,
                                      early_stop_patience=early_stop_patience)
    
    # Проверка NaN в фазе
    for name, ph in [("Left", phase_left), ("Right", phase_right)]:
        if np.any(np.isnan(ph)):
            print(f"   ⚠️ NaN в фазе {name}, замена на 0")
            np.nan_to_num(ph, copy=False, nan=0.0)
        if np.abs(ph).max() > np.pi * 1.1:
            np.clip(ph, -np.pi, np.pi, out=ph)
    
    # --- Восстановление аудио ---
    print("   Восстановление комплексных спектров...")
    D_left = mag_left.astype(np.complex64) * np.exp(1j * phase_left.astype(np.float32))
    D_right = mag_right.astype(np.complex64) * np.exp(1j * phase_right.astype(np.float32))
    
    print("   Обратное STFT...")
    y_left = librosa.istft(D_left, hop_length=hop_length, length=original_length, window='hann')
    y_right = librosa.istft(D_right, hop_length=hop_length, length=original_length, window='hann')
    
    print(f"   y_left: [{y_left.min():.4f}, {y_left.max():.4f}], max_abs={np.max(np.abs(y_left)):.4f}")
    print(f"   y_right: [{y_right.min():.4f}, {y_right.max():.4f}], max_abs={np.max(np.abs(y_right)):.4f}")
    
    min_len = min(len(y_left), len(y_right))
    y_recovered = np.stack([y_left[:min_len], y_right[:min_len]], axis=1)
    
    # Нормализация
    max_val = np.max(np.abs(y_recovered))
    if max_val > 1.0:
        print(f"   Нормализация: деление на {max_val:.4f}")
        y_recovered = y_recovered / max_val * 0.95
    
    duration = y_recovered.shape[0] / sr
    elapsed = time.time() - t_start
    
    print(f"\n   Сохранение: {output_wav_path}")
    print(f"   Длительность: {duration:.2f} сек")
    print(f"   Время: {elapsed:.1f} сек")
    
    y_16bit = (y_recovered * 32767).clip(-32768, 32767).astype(np.int16)
    sf.write(output_wav_path, y_16bit, sr, subtype='PCM_16')
    
    return y_recovered


def decode_pages(image_paths: List[str], config: dict, output_wav_path: str) -> np.ndarray:
    """Точка входа для декодирования."""
    if len(image_paths) == 0:
        raise ValueError("Не указаны файлы для декодирования")
    
    if len(image_paths) == 1:
        path = image_paths[0]
        if Path(path).is_dir():
            import glob
            png_files = sorted(glob.glob(str(Path(path) / "*.png")))
            jpg_files = sorted(glob.glob(str(Path(path) / "*.jpg")))
            jpeg_files = sorted(glob.glob(str(Path(path) / "*.jpeg")))
            image_paths = png_files + jpg_files + jpeg_files
            
            if not image_paths:
                raise ValueError(f"В директории {path} не найдены изображения")
    
    valid_paths = [p for p in image_paths if Path(p).is_file()]
    
    if not valid_paths:
        raise ValueError("Нет доступных файлов")
    
    # Отделяем QR
    qr_path = None
    spec_paths = []
    
    for p in valid_paths:
        name = Path(p).name.lower()
        if '_qr' in name or 'qr.' in name:
            qr_path = p
        else:
            spec_paths.append(p)
    
    if qr_path is None:
        raise ValueError("QR-страница не найдена! Ожидается файл с '_qr' в имени.")
    
    if not spec_paths:
        raise ValueError("Не найдены страницы спектрограмм!")
    
    def extract_page_num(path):
        import re
        match = re.search(r'page(\d+)of', Path(path).name)
        return int(match.group(1)) if match else 1
    
    spec_paths.sort(key=extract_page_num)
    
    print(f"   QR-страница: {Path(qr_path).name}")
    print(f"   Страницы: {[Path(p).name for p in spec_paths]}")
    
    return decode_multipage(spec_paths, qr_path, config, output_wav_path)

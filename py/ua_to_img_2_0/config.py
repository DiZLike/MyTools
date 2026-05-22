# config.py

PRESETS = {
    # --- СТАНДАРТНЫЕ ПРЕСЕТЫ ---
    "75p_n512":   {"N_FFT": 512,  "HOP_LENGTH": 128},
    "75p_n1024":  {"N_FFT": 1024, "HOP_LENGTH": 256},
    "75p_n2048":  {"N_FFT": 2048, "HOP_LENGTH": 512},
    "75p_n4096":  {"N_FFT": 4096, "HOP_LENGTH": 1024},
    "75p_n8192":  {"N_FFT": 8192, "HOP_LENGTH": 2048},

    # 87.5% перекрытие
    "87p_n256":   {"N_FFT": 256,  "HOP_LENGTH": 32},
    "87p_n512":   {"N_FFT": 512,  "HOP_LENGTH": 64},
    "87p_n1024":  {"N_FFT": 1024, "HOP_LENGTH": 128},
    "87p_n2048":  {"N_FFT": 2048, "HOP_LENGTH": 256},
    "87p_n4096":  {"N_FFT": 4096, "HOP_LENGTH": 512},

    # --- ПРЕСЕТЫ ДЛЯ JPEG-СЖАТИЯ ---
    "jpeg_n256_75p":  {"N_FFT": 256,  "HOP_LENGTH": 64},
    "jpeg_n512_75p":  {"N_FFT": 512,  "HOP_LENGTH": 128},
    "jpeg_n512_87p":  {"N_FFT": 512,  "HOP_LENGTH": 64},
    "jpeg_n1024_87p": {"N_FFT": 1024, "HOP_LENGTH": 128},

    # --- ПРЕСЕТЫ ДЛЯ WebP-СЖАТИЯ ---
    "webp_n128_75p":  {"N_FFT": 128,  "HOP_LENGTH": 32},
    "webp_n128_87p":  {"N_FFT": 128,  "HOP_LENGTH": 16},
    "webp_n256_75p":  {"N_FFT": 256,  "HOP_LENGTH": 64},
    "webp_n256_87p":  {"N_FFT": 256,  "HOP_LENGTH": 32},
    "webp_n512_87p":  {"N_FFT": 512,  "HOP_LENGTH": 64},

    # --- ПРЕСЕТЫ ДЛЯ AVIF-СЖАТИЯ ---
    "avif_n128_75p":  {"N_FFT": 128,  "HOP_LENGTH": 32},
    "avif_n128_87p":  {"N_FFT": 128,  "HOP_LENGTH": 16},
    "avif_n256_75p":  {"N_FFT": 256,  "HOP_LENGTH": 64},
    "avif_n256_87p":  {"N_FFT": 256,  "HOP_LENGTH": 32},
    "avif_n512_87p":  {"N_FFT": 512,  "HOP_LENGTH": 64},

    # --- ПРЕСЕТЫ ДЛЯ ВИДЕО-СЖАТИЯ ---
    "video_n1024_87p": {"N_FFT": 1024, "HOP_LENGTH": 128},
    "video_n2048_87p": {"N_FFT": 2048, "HOP_LENGTH": 256},
    "video_n4096_87p": {"N_FFT": 4096, "HOP_LENGTH": 512},
    "video_n1024_93p": {"N_FFT": 1024, "HOP_LENGTH": 64},
    "video_n2048_93p": {"N_FFT": 2048, "HOP_LENGTH": 128},

    "custom":  {"N_FFT": 4096, "HOP_LENGTH": 2048},
}

DEFAULT_CONFIG = {
    # --- ФАЙЛЫ ---
    "mp3_file": "track.mp3",
    "active_preset": "75p_n4096",
    
    # --- ДИАПАЗОН ОБРАБОТКИ ---
    "trim_enabled": False,
    "trim_start": 0.0,
    "trim_end": 0.0,
    
    # --- ПАРАМЕТРЫ ЛИСТА ---
    "dpi": 300,
    "paper_size": "A4",
    "calibration_enabled": True,
    "marker_size_mm": 5,
    
    # --- МАСШТАБИРОВАНИЕ СПЕКТРОГРАММЫ ---
    "scale_enabled": False,
    "scale_x": 1,
    "scale_y": 1,
    "scale_method": "lanczos",
    
    # --- ОБРЕЗКА НИЗКИХ ЧАСТОТ ---
    "low_cut_enabled": False,
    "low_cut_freq": 20,
    
    # --- ОБРЕЗКА ВЫСОКИХ ЧАСТОТ ---
    "high_cut_enabled": False,
    "high_cut_mode": "auto",
    "high_cut_freq": 16000,
    "high_cut_auto_threshold_db": -80,
    "high_cut_auto_freq_min": 8000,
    "high_cut_auto_margin_db": 10,
    
    # --- ПАРАМЕТРЫ ГЕНЕРАЦИИ ФАЗЫ (Griffin-Lim) ---
    "phase_generate_iterations": 5000,
    "phase_generate_random_seed": 454,
    "griffin_lim_mode": "fast",
    "griffin_lim_parallel": True,
    
    # --- РАННЯЯ ОСТАНОВКА (early stopping) ---
    "early_stop_enabled": True,
    "early_stop_threshold": 0.0001,
    "early_stop_patience": 10,
    
    # --- МЕТАДАННЫЕ НА ЛИСТЕ ---
    "metadata_format": "qr_page",
    
    # --- ПАПКИ ---
    "data_dir": "data",
}

# Физические размеры бумаги в мм (альбомная ориентация)
PAPER_SIZES = {
    "A4":     {"width_mm": 297, "height_mm": 210},
    "A3":     {"width_mm": 420, "height_mm": 297},
    "letter": {"width_mm": 279.4, "height_mm": 215.9},
}

# Параметры макета (отступы в мм)
LAYOUT = {
    "margin_mm": 5,
    "marker_inset_mm": 3,
    "channel_gap_mm": 0,
    "calibration_strip_height_mm": 3,
    "metadata_height_mm": 8,
    "calibration_margin_mm": 1,
}
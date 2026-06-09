# config.py — пресеты STFT

PRESETS = {
    "75p_n512":   {"N_FFT": 512,  "HOP_LENGTH": 128},
    "75p_n1024":  {"N_FFT": 1024, "HOP_LENGTH": 256},
    "75p_n2048":  {"N_FFT": 2048, "HOP_LENGTH": 512},
    "75p_n4096":  {"N_FFT": 4096, "HOP_LENGTH": 1024},
    "75p_n8192":  {"N_FFT": 8192, "HOP_LENGTH": 2048},
    "87p_n256":   {"N_FFT": 256,  "HOP_LENGTH": 32},
    "87p_n512":   {"N_FFT": 512,  "HOP_LENGTH": 64},
    "87p_n1024":  {"N_FFT": 1024, "HOP_LENGTH": 128},
    "87p_n2048":  {"N_FFT": 2048, "HOP_LENGTH": 256},
    "87p_n4096":  {"N_FFT": 4096, "HOP_LENGTH": 512},
}

DEFAULT_CONFIG = {
    "active_preset": "87p_n2048",
    "sr": 44100,
    "duration": 5.0,                # секунд, по умолчанию
    "stereo_width_gain": 2.5,       # усиление Side (1.0 = норма, 3.0 = очень широко)
    "stereo_noise_floor": 0.05,     # ниже — Side зануляется
    "griffin_lim_iterations": 500,
    "griffin_lim_mode": "fast",     # "standard", "fast", "multi_scale"
    "griffin_lim_seed": 42,         # -1 = случайный
    "early_stop_threshold": 0.0001,
    "early_stop_patience": 15,
}
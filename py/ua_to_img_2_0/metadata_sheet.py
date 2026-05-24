# metadata_sheet.py

import numpy as np
from typing import Dict, Optional
from PIL import Image
import io


def encode_metadata_text(metadata: dict) -> str:
    """Кодирует метаданные в компактную текстовую строку."""
    parts = [
        f"N:{metadata['n_fft']}",
        f"H:{metadata['hop_length']}",
        f"L:{metadata['original_length']}",
        f"NF:{metadata['n_freqs']}",
        f"RL:{metadata['ref_left']:.6f}",
        f"RR:{metadata['ref_right']:.6f}",
        f"SR:{metadata.get('sr', 44100)}",
        f"MM:{metadata.get('mag_min', -120):.1f}",  # Форматируем как float с 1 знаком
        f"TF:{metadata.get('total_frames', 0)}",
        f"TP:{metadata.get('total_pages', 1)}",
        f"FPG:{metadata.get('frames_per_page', 0)}",
        f"EN:{metadata.get('encoding', 'rgb_stereo')}",
        f"GI:{metadata.get('phase_generate_iterations', 5000)}",
        f"GS:{metadata.get('phase_generate_random_seed', 454)}",
        f"GM:{metadata.get('griffin_lim_mode', 'fast')}",
        f"GP:{1 if metadata.get('griffin_lim_parallel', True) else 0}",
        f"ES:{1 if metadata.get('early_stop_enabled', True) else 0}",
        f"ET:{metadata.get('early_stop_threshold', 0.0001)}",
        f"EP:{metadata.get('early_stop_patience', 10)}",
    ]
    
    if metadata.get('low_cut_bin', 0) > 0:
        parts.append(f"LC:{metadata['low_cut_bin']}")
    if metadata.get('high_cut_bins_removed', 0) > 0:
        parts.append(f"HC:{metadata['high_cut_bins_removed']}")
    
    if 'page' in metadata:
        parts.append(f"PG:{metadata['page']}")
        parts.append(f"SF:{metadata['start_frame']}")
        parts.append(f"FP:{metadata['n_frames']}")
    
    return " ".join(parts)


def decode_metadata_text(text: str) -> dict:
    """Декодирует текстовую строку метаданных."""
    metadata = {}
    mapping = {
        'N': 'n_fft', 
        'H': 'hop_length', 
        'L': 'original_length',
        'NF': 'n_freqs', 
        'RL': 'ref_left', 
        'RR': 'ref_right', 
        'SR': 'sr',
        'LC': 'low_cut_bin', 
        'HC': 'high_cut_bins_removed',
        'PG': 'page', 
        'TP': 'total_pages', 
        'SF': 'start_frame', 
        'FP': 'n_frames',
        'MM': 'mag_min',
        'TF': 'total_frames',
        'FPG': 'frames_per_page',
        'EN': 'encoding',
        'GI': 'phase_generate_iterations',
        'GS': 'phase_generate_random_seed',
        'GM': 'griffin_lim_mode',
        'GP': 'griffin_lim_parallel',
        'ES': 'early_stop_enabled',
        'ET': 'early_stop_threshold',
        'EP': 'early_stop_patience',
    }
    
    # Ключи, которые должны быть float
    float_keys = {'RL', 'RR', 'ET', 'MM'}
    
    # Ключи, которые должны быть bool
    bool_keys = {'GP', 'ES'}
    
    # Ключи, которые должны быть str
    str_keys = {'GM', 'EN'}
    
    parts = text.strip().split()
    for part in parts:
        if ':' in part:
            key, value = part.split(':', 1)
            if key in mapping:
                if key in float_keys:
                    metadata[mapping[key]] = float(value)
                elif key in bool_keys:
                    metadata[mapping[key]] = bool(int(value))
                elif key in str_keys:
                    metadata[mapping[key]] = value
                else:
                    metadata[mapping[key]] = int(value)
    
    metadata.setdefault('low_cut_bin', 0)
    metadata.setdefault('high_cut_bins_removed', 0)
    metadata.setdefault('sr', 44100)
    metadata.setdefault('mag_min', -120)
    metadata.setdefault('total_frames', 0)
    metadata.setdefault('total_pages', 1)
    metadata.setdefault('frames_per_page', 0)
    metadata.setdefault('encoding', 'rgb_stereo')
    metadata.setdefault('phase_generate_iterations', 5000)
    metadata.setdefault('phase_generate_random_seed', 454)
    metadata.setdefault('griffin_lim_mode', 'fast')
    metadata.setdefault('griffin_lim_parallel', True)
    metadata.setdefault('early_stop_enabled', True)
    metadata.setdefault('early_stop_threshold', 0.0001)
    metadata.setdefault('early_stop_patience', 10)
    
    return metadata
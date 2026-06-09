# transforms.py
import numpy as np

def lr_to_ms(left: np.ndarray, right: np.ndarray):
    """Left/Right -> Mid/Side."""
    mid = (left + right) * 0.5
    side = (left - right) * 0.5
    return mid, side

def ms_to_lr(mid: np.ndarray, side: np.ndarray):
    """Mid/Side -> Left/Right."""
    left = mid + side
    right = mid - side
    return left, right
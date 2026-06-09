# decoder.py — Image to Ambient Audio (SPECTRAL TILT)
import argparse
import time
import numpy as np
import librosa
import soundfile as sf
from PIL import Image, ImageOps
from scipy.ndimage import gaussian_filter


def griffin_lim_fast(magnitude, n_fft, hop_length, iterations=500, random_seed=42,
                     early_stop_threshold=0.0001, early_stop_patience=20):
    """Griffin-Lim с ранней остановкой."""
    mag = np.ascontiguousarray(magnitude.astype(np.float32))
    
    rng = np.random.RandomState(random_seed)
    angles = rng.uniform(-np.pi, np.pi, mag.shape).astype(np.float32)
    
    best_error = float('inf')
    best_angles = None
    patience_counter = 0
    
    for i in range(iterations):
        D = mag * np.exp(1j * angles)
        y = librosa.istft(D, hop_length=hop_length, n_fft=n_fft, window='hann')
        D_new = librosa.stft(y, n_fft=n_fft, hop_length=hop_length, window='hann')
        angles = np.angle(D_new).astype(np.float32)
        
        error = np.mean(np.abs(np.abs(D_new) - mag))
        
        if error < best_error:
            improvement = best_error - error
            best_error = error
            best_angles = angles.copy()
            
            if improvement < early_stop_threshold:
                patience_counter += 1
            else:
                patience_counter = 0
        else:
            patience_counter += 1
        
        if i % 100 == 0 or i == iterations - 1:
            print(f"   GL {i}/{iterations}, error={best_error:.6f}")
        
        if patience_counter >= early_stop_patience:
            print(f"   Ранняя остановка на итерации {i+1} (error={best_error:.6f})")
            return best_angles
    
    return best_angles if best_angles is not None else angles


def spectral_tilt(n_freqs, n_frames, sr, tilt_db_per_octave=-6.0, cutoff_freq=200):
    """
    Естественный спад высоких частот.
    
    - Ниже cutoff_freq: без изменений
    - Выше cutoff_freq: спад tilt_db_per_octave дБ/октаву
    
    -6 дБ/октава = естественный спад (как в природе, коричневый шум)
    -3 дБ/октава = лёгкий спад (розовый шум)
    0 дБ/октава = без изменений (белый шум)
    """
    freqs = np.linspace(0, sr/2, n_freqs)
    
    tilt = np.ones(n_freqs, dtype=np.float32)
    
    above_cutoff = freqs > cutoff_freq
    octaves_above = np.log2(freqs[above_cutoff] / cutoff_freq)
    tilt[above_cutoff] = 10 ** (tilt_db_per_octave * octaves_above / 20)
    
    # Расширяем до [n_freqs, n_frames]
    tilt = tilt[:, np.newaxis] * np.ones(n_frames, dtype=np.float32)
    
    return tilt


def apply_contrast(arr, amount):
    """Усиление контраста."""
    mean = arr.mean()
    return np.clip((arr - mean) * amount + mean, 0.0, 1.0)


def image_to_audio_ambient(
    image_path: str,
    output_path: str,
    duration: float = 10.0,
    sr: int = 44100,
    n_fft: int = 2048,
    hop_length: int = 256,
    smoothing: float = 2.0,
    gl_iterations: int = 500,
    contrast: float = 2.0,
    tilt_db: float = -6.0,
    tilt_cutoff: float = 200,
):
    """
    Картинка → эмбиент аудио.
    
    - Спектральный наклон: высокие частоты тише (естественно для слуха)
    - tilt_db: крутизна спада (-3 = мягко, -6 = естественно, -12 = темно)
    - tilt_cutoff: частота начала спада (Гц)
    """
    print(f"🎨 Загрузка: {image_path}")
    img_original = Image.open(image_path).convert('RGB')
    orig_w, orig_h = img_original.size
    
    # Инверсия Y
    img_original = ImageOps.flip(img_original)
    
    n_freqs = n_fft // 2 + 1
    target_frames = max(1, int(duration * sr / hop_length))
    
    print(f"   {n_freqs}×{target_frames} кадров, {duration} сек")
    print(f"   Спектральный наклон: {tilt_db} дБ/октава (срез от {tilt_cutoff} Гц)")
    
    # Ресайз
    base_w = int(orig_w * n_freqs / orig_h)
    img = img_original.resize((base_w, n_freqs), Image.LANCZOS)
    img = img.resize((target_frames, n_freqs), Image.LANCZOS)
    arr = np.array(img, dtype=np.float64)
    
    t_start = time.time()
    
    # Каналы
    r = arr[:, :, 0] / 255.0
    g = arr[:, :, 1] / 255.0
    b = arr[:, :, 2] / 255.0
    
    # Mid = яркость
    mag_mid = 0.299 * r + 0.587 * g + 0.114 * b
    mag_mid = apply_contrast(mag_mid, contrast)
    
    # Side = насыщенность × разница R-B
    max_rgb = np.maximum(np.maximum(r, g), b)
    min_rgb = np.minimum(np.minimum(r, g), b)
    delta = max_rgb - min_rgb
    safe_max = np.maximum(max_rgb, 1e-6)
    sat = np.where(max_rgb > 1e-6, delta / safe_max, 0.0)
    mag_side = sat * np.abs(r - b) * 2.0
    
    # Сглаживание
    mag_mid = gaussian_filter(mag_mid, sigma=(smoothing*0.5, smoothing))
    mag_side = gaussian_filter(mag_side, sigma=(smoothing*0.5, smoothing))
    
    # Клиппинг и нормализация
    mag_mid = np.clip(mag_mid, 0.0, 1.0)
    mag_side = np.clip(mag_side, 0.0, 1.0)
    
    mid_max = mag_mid.max()
    if mid_max > 0:
        mag_mid /= mid_max
    side_max = mag_side.max()
    if side_max > 0:
        mag_side /= side_max
    
    # Спектральный наклон (естественный спад высоких)
    tilt = spectral_tilt(n_freqs, target_frames, sr, tilt_db, tilt_cutoff)
    mag_mid = mag_mid * tilt
    mag_side = mag_side * tilt
    
    print(f"\n🔄 Griffin-Lim (max {gl_iterations} итер):")
    
    phase_mid = griffin_lim_fast(mag_mid, n_fft, hop_length, gl_iterations, random_seed=42)
    phase_side = griffin_lim_fast(mag_side, n_fft, hop_length, gl_iterations, random_seed=43)
    
    # Istft
    print("\n🔊 Синтез...")
    D_mid = (mag_mid.astype(np.complex64) * np.exp(1j * phase_mid))
    D_side = (mag_side.astype(np.complex64) * np.exp(1j * phase_side))
    
    y_mid = librosa.istft(D_mid, hop_length=hop_length, n_fft=n_fft, window='hann')
    y_side = librosa.istft(D_side, hop_length=hop_length, n_fft=n_fft, window='hann')
    
    y_left = y_mid + y_side
    y_right = y_mid - y_side
    y_stereo = np.stack([y_left, y_right], axis=1)
    
    max_val = np.max(np.abs(y_stereo))
    if max_val > 0:
        y_stereo = y_stereo / max_val * 0.9
    
    # Плавный fade out на конце
    fade_len = min(int(sr * 0.3), len(y_stereo) // 3)
    if fade_len > 0:
        fade = np.cos(np.linspace(0, np.pi/2, fade_len)) ** 2
        y_stereo[-fade_len:, :] *= fade[:, np.newaxis]
    
    elapsed = time.time() - t_start
    print(f"\n💾 {output_path}")
    print(f"   {y_stereo.shape[0]/sr:.1f} сек | пик {np.max(np.abs(y_stereo)):.3f} | {elapsed:.1f} сек")
    
    sf.write(output_path, y_stereo, sr)
    return y_stereo


def main():
    parser = argparse.ArgumentParser(
        description="🎨 Image to Ambient Audio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python decoder.py photo.jpg
  python decoder.py art.png -d 30 --tilt -3   (мягкий спад)
  python decoder.py img.jpg -d 60 --tilt -9   (тёмный звук)
  python decoder.py img.jpg -d 20 --tilt 0    (без спада, ярко)
        """
    )
    parser.add_argument("image", type=str)
    parser.add_argument("output", type=str, nargs="?", default="output.wav")
    parser.add_argument("--duration", "-d", type=float, default=10.0)
    parser.add_argument("--fft", type=int, default=2048)
    parser.add_argument("--smooth", "-s", type=float, default=2.0)
    parser.add_argument("--gl", type=int, default=500)
    parser.add_argument("--contrast", "-c", type=float, default=2.0)
    parser.add_argument("--tilt", type=float, default=-6.0,
                       help="Спад высоких частот (0=ровно, -3=мягко, -6=естественно, -12=темно)")
    parser.add_argument("--cutoff", type=float, default=200,
                       help="Частота начала спада (Гц)")
    
    args = parser.parse_args()
    
    print(f"╔══════════════════════════════════╗")
    print(f"║  Image → Ambient Audio        ║")
    print(f"╚══════════════════════════════════╝")
    print()
    
    image_to_audio_ambient(
        image_path=args.image,
        output_path=args.output,
        duration=args.duration,
        sr=44100,
        n_fft=args.fft,
        hop_length=256,
        smoothing=args.smooth,
        gl_iterations=args.gl,
        contrast=args.contrast,
        tilt_db=args.tilt,
        tilt_cutoff=args.cutoff,
    )


if __name__ == "__main__":
    main()
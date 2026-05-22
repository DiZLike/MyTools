# phase_generator.py
import numpy as np
import librosa
from concurrent.futures import ThreadPoolExecutor
import threading
import sys


def griffin_lim(magnitude: np.ndarray,
                n_fft: int,
                hop_length: int,
                iterations: int = 50,
                window: str = 'hann',
                random_seed: int = None,
                verbose: bool = True,
                early_stop_threshold: float = 0.0001,
                early_stop_patience: int = 15) -> np.ndarray:
    
    thread_name = threading.current_thread().name
    prefix = f"[{thread_name}] " if thread_name != "MainThread" else ""
    
    if verbose:
        print(f"   {prefix}Griffin-Lim (standard): {iterations} итераций")
        if random_seed is not None:
            print(f"   {prefix}Random seed: {random_seed}")

    window_array = librosa.filters.get_window(window, n_fft, fftbins=True)
    magnitude_f32 = magnitude.astype(np.float32)
    
    rng = np.random.RandomState(random_seed)
    angles = rng.uniform(-np.pi, np.pi, magnitude.shape).astype(np.float32)
    
    complex_spec = np.zeros(magnitude.shape, dtype=np.complex64)
    
    best_error = float('inf')
    best_angles = None
    patience_counter = 0

    for i in range(iterations):
        np.multiply(magnitude_f32, 
                     np.exp(1j * angles, dtype=np.complex64), 
                     out=complex_spec)

        y_est = librosa.istft(complex_spec, 
                              hop_length=hop_length, 
                              window=window_array)

        D_new = librosa.stft(y_est, 
                             n_fft=n_fft, 
                             hop_length=hop_length, 
                             window=window_array)

        angles = np.angle(D_new).astype(np.float32)
        
        current_error = np.mean(np.abs(np.abs(D_new) - magnitude))
        
        if current_error < best_error:
            improvement = best_error - current_error
            best_error = current_error
            best_angles = angles.copy()
            
            if improvement < early_stop_threshold and best_error < float('inf'):
                patience_counter += 1
            else:
                patience_counter = 0
        else:
            patience_counter += 1

        if verbose and (i + 1) % 10 == 0:
            print(f"   {prefix}Итерация {i+1}/{iterations}, ошибка: {current_error:.6f}")

        if early_stop_patience > 0 and patience_counter >= early_stop_patience:
            if verbose:
                print(f"   {prefix}Ранняя остановка на итерации {i+1}")
                print(f"   {prefix}Финальная ошибка: {best_error:.6f}")
            return best_angles

    return best_angles if best_angles is not None else angles


def griffin_lim_fast(magnitude: np.ndarray,
                     n_fft: int,
                     hop_length: int,
                     iterations: int = 50,
                     window: str = 'hann',
                     random_seed: int = None,
                     verbose: bool = True,
                     early_stop_threshold: float = 0.0001,
                     early_stop_patience: int = 15) -> np.ndarray:
    
    thread_name = threading.current_thread().name
    prefix = f"[{thread_name}] " if thread_name != "MainThread" else ""
    
    if verbose:
        print(f"   {prefix}Griffin-Lim (fast): {iterations} итераций")

    magnitude_f32 = np.ascontiguousarray(magnitude, dtype=np.float32)
    window_array = librosa.filters.get_window(window, n_fft, fftbins=True)
    window_array = np.ascontiguousarray(window_array, dtype=np.float32)
    
    rng = np.random.RandomState(random_seed)
    angles = rng.uniform(-np.pi, np.pi, magnitude_f32.shape).astype(np.float32)
    angles = np.ascontiguousarray(angles)
    
    best_error = float('inf')
    best_angles = None
    patience_counter = 0
    
    for i in range(iterations):
        stft_matrix = magnitude_f32 * np.exp(1j * angles, dtype=np.complex64)
        stft_matrix = np.ascontiguousarray(stft_matrix)
        
        y = librosa.istft(stft_matrix, 
                          hop_length=hop_length, 
                          window=window_array)
        y = np.ascontiguousarray(y, dtype=np.float32)
        
        D_new = librosa.stft(y, 
                             n_fft=n_fft, 
                             hop_length=hop_length, 
                             window=window_array)
        
        angles = np.angle(D_new).astype(np.float32)
        angles = np.ascontiguousarray(angles)
        
        current_error = np.mean(np.abs(np.abs(D_new) - magnitude))
        
        if current_error < best_error:
            improvement = best_error - current_error
            best_error = current_error
            best_angles = angles.copy()
            
            if improvement < early_stop_threshold and best_error < float('inf'):
                patience_counter += 1
            else:
                patience_counter = 0
        else:
            patience_counter += 1

        if verbose and (i + 1) % 10 == 0:
            print(f"   {prefix}Итерация {i+1}/{iterations}, ошибка: {current_error:.6f}")

        if early_stop_patience > 0 and patience_counter >= early_stop_patience:
            if verbose:
                print(f"   {prefix}Ранняя остановка на итерации {i+1}")
                print(f"   {prefix}Финальная ошибка: {best_error:.6f}")
            return best_angles

    return best_angles if best_angles is not None else angles


def griffin_lim_multi_scale(magnitude: np.ndarray,
                            n_fft: int,
                            hop_length: int,
                            iterations: int = 50,
                            window: str = 'hann',
                            random_seed: int = None,
                            verbose: bool = True,
                            scale_factor: int = 4,
                            coarse_iterations: int = None,
                            fine_iterations: int = None,
                            early_stop_threshold: float = 0.0001,
                            early_stop_patience: int = 15) -> np.ndarray:
    
    thread_name = threading.current_thread().name
    prefix = f"[{thread_name}] " if thread_name != "MainThread" else ""
    
    if coarse_iterations is None:
        coarse_iterations = iterations
    if fine_iterations is None:
        fine_iterations = max(1, iterations // 2)
    
    if verbose:
        print(f"   {prefix}Griffin-Lim (multi-scale): Масштаб={scale_factor}, "
              f"coarse={coarse_iterations} iter, fine={fine_iterations} iter")

    if n_fft % scale_factor != 0 or hop_length % scale_factor != 0:
        if verbose:
            print(f"   {prefix}Внимание: n_fft или hop_length не кратны {scale_factor}, "
                  f"переключаюсь на стандартный режим")
        return griffin_lim(magnitude, n_fft, hop_length, iterations, 
                          window, random_seed, verbose,
                          early_stop_threshold, early_stop_patience)

    window_array = librosa.filters.get_window(window, n_fft, fftbins=True)
    
    if verbose:
        print(f"   {prefix}Этап 1 (грубый): {coarse_iterations} итераций на 1/{scale_factor} разрешении")
    
    coarse_n_fft = n_fft // scale_factor
    coarse_hop = hop_length // scale_factor
    
    coarse_mag = magnitude[::scale_factor, ::scale_factor].copy()
    coarse_mag = np.ascontiguousarray(coarse_mag, dtype=np.float32)
    
    coarse_window = window_array[:coarse_n_fft] if len(window_array) > coarse_n_fft else window_array
    coarse_window = np.ascontiguousarray(coarse_window, dtype=np.float32)
    
    rng = np.random.RandomState(random_seed)
    angles_coarse = rng.uniform(-np.pi, np.pi, coarse_mag.shape).astype(np.float32)
    angles_coarse = np.ascontiguousarray(angles_coarse)
    
    complex_buffer = np.zeros(coarse_mag.shape, dtype=np.complex64)
    
    best_error_coarse = float('inf')
    best_angles_coarse = None
    
    for i in range(coarse_iterations):
        np.multiply(coarse_mag, 
                     np.exp(1j * angles_coarse, dtype=np.complex64), 
                     out=complex_buffer)
        
        y = librosa.istft(complex_buffer, 
                          hop_length=coarse_hop, 
                          n_fft=coarse_n_fft,
                          window=coarse_window)
        y = np.ascontiguousarray(y, dtype=np.float32)
        
        D_new = librosa.stft(y, 
                             n_fft=coarse_n_fft, 
                             hop_length=coarse_hop,
                             window=coarse_window)
        
        angles_coarse = np.angle(D_new).astype(np.float32)
        angles_coarse = np.ascontiguousarray(angles_coarse)
        
        current_error = np.mean(np.abs(np.abs(D_new) - coarse_mag))
        
        if current_error < best_error_coarse:
            best_error_coarse = current_error
            best_angles_coarse = angles_coarse.copy()
        
        log_interval = max(1, coarse_iterations // 10)
        if verbose and (i + 1) % log_interval == 0:
            print(f"   {prefix}Этап 1, итерация {i+1}/{coarse_iterations}, ошибка: {current_error:.6f}")
    
    if best_angles_coarse is not None:
        angles_coarse = best_angles_coarse
    
    if fine_iterations > 0:
        if verbose:
            print(f"   {prefix}Этап 2 (точный): {fine_iterations} итераций на полном разрешении")
        
        from scipy.ndimage import zoom
        
        zoom_factors = (scale_factor, scale_factor)
        angles = zoom(angles_coarse, zoom_factors, order=1).astype(np.float32)
        angles = angles[:magnitude.shape[0], :magnitude.shape[1]]
        angles = np.ascontiguousarray(angles)
        
        magnitude_f32 = np.ascontiguousarray(magnitude, dtype=np.float32)
        window_array = np.ascontiguousarray(window_array, dtype=np.float32)
        complex_buffer_full = np.zeros(magnitude.shape, dtype=np.complex64)
        
        np.multiply(magnitude_f32, 
                     np.exp(1j * angles, dtype=np.complex64), 
                     out=complex_buffer_full)
        
        y_init = librosa.istft(complex_buffer_full, 
                               hop_length=hop_length, 
                               window=window_array)
        D_init = librosa.stft(y_init, 
                              n_fft=n_fft, 
                              hop_length=hop_length, 
                              window=window_array)
        init_error = np.mean(np.abs(np.abs(D_init) - magnitude))
        
        if verbose:
            print(f"   {prefix}Начальная ошибка после интерполяции: {init_error:.6f}")
        
        best_error_fine = init_error
        best_angles_fine = angles.copy()
        patience_counter_fine = 0
        
        for i in range(fine_iterations):
            np.multiply(magnitude_f32, 
                         np.exp(1j * angles, dtype=np.complex64), 
                         out=complex_buffer_full)
            
            y = librosa.istft(complex_buffer_full, 
                              hop_length=hop_length, 
                              window=window_array)
            y = np.ascontiguousarray(y, dtype=np.float32)
            
            D_new = librosa.stft(y, 
                                 n_fft=n_fft, 
                                 hop_length=hop_length, 
                                 window=window_array)
            
            angles = np.angle(D_new).astype(np.float32)
            angles = np.ascontiguousarray(angles)
            
            current_error = np.mean(np.abs(np.abs(D_new) - magnitude))
            
            if current_error < best_error_fine:
                improvement = best_error_fine - current_error
                best_error_fine = current_error
                best_angles_fine = angles.copy()
                
                if improvement < early_stop_threshold and best_error_fine < float('inf'):
                    patience_counter_fine += 1
                else:
                    patience_counter_fine = 0
            else:
                patience_counter_fine += 1
            
            log_interval = max(1, fine_iterations // 5)
            if verbose and (i + 1) % log_interval == 0:
                print(f"   {prefix}Этап 2, итерация {i+1}/{fine_iterations}, ошибка: {current_error:.6f}")

            if early_stop_patience > 0 and patience_counter_fine >= early_stop_patience:
                if verbose:
                    print(f"   {prefix}Ранняя остановка на итерации {i+1}")
                    print(f"   {prefix}Финальная ошибка: {best_error_fine:.6f}")
                return best_angles_fine
        
        if verbose:
            print(f"   {prefix}Завершено")
        return best_angles_fine if best_angles_fine is not None else angles
    else:
        if verbose:
            print(f"   {prefix}Этап 2 отключён (0 итераций), возврат интерполированной фазы")
        
        from scipy.ndimage import zoom
        
        zoom_factors = (scale_factor, scale_factor)
        angles = zoom(angles_coarse, zoom_factors, order=1).astype(np.float32)
        angles = angles[:magnitude.shape[0], :magnitude.shape[1]]
        return np.ascontiguousarray(angles)


def griffin_lim_stereo_parallel(mag_mid: np.ndarray,
                                mag_side: np.ndarray,
                                n_fft: int,
                                hop_length: int,
                                iterations: int = 50,
                                window: str = 'hann',
                                random_seed: int = None,
                                verbose: bool = True,
                                mode: str = 'standard',
                                scale_factor: int = 4,
                                coarse_iterations: int = None,
                                fine_iterations: int = None,
                                early_stop_threshold: float = 0.0001,
                                early_stop_patience: int = 15,
                                num_workers: int = 2) -> tuple:
    
    seeds = [random_seed, random_seed if random_seed is not None else None]
    print_lock = threading.Lock()
    
    def process_channel(mag, seed, channel_name):
        threading.current_thread().name = channel_name
        
        with print_lock:
            print(f"[{channel_name}] Запуск генерации фазы (seed={seed})")
            sys.stdout.flush()
        
        if mode == 'fast':
            result = griffin_lim_fast(mag, n_fft, hop_length, iterations, 
                                     window, seed, verbose=True,
                                     early_stop_threshold=early_stop_threshold,
                                     early_stop_patience=early_stop_patience)
        elif mode == 'multi_scale':
            result = griffin_lim_multi_scale(mag, n_fft, hop_length, iterations,
                                            window, seed, verbose=True,
                                            scale_factor=scale_factor,
                                            coarse_iterations=coarse_iterations,
                                            fine_iterations=fine_iterations,
                                            early_stop_threshold=early_stop_threshold,
                                            early_stop_patience=early_stop_patience)
        else:
            result = griffin_lim(mag, n_fft, hop_length, iterations,
                                window, seed, verbose=True,
                                early_stop_threshold=early_stop_threshold,
                                early_stop_patience=early_stop_patience)
        
        with print_lock:
            print(f"[{channel_name}] Завершено")
            sys.stdout.flush()
        
        return result
    
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_mid = executor.submit(process_channel, mag_mid, seeds[0], "Left")
        future_side = executor.submit(process_channel, mag_side, seeds[1], "Right")
        
        phase_mid = future_mid.result()
        phase_side = future_side.result()
    
    return phase_mid, phase_side
# check_freqs.py
import numpy as np
import soundfile as sf

y, sr = sf.read('data/recovered.wav')
print(f"SR: {sr}, длительность: {len(y)/sr:.2f} сек")
print(f"max L: {np.abs(y[:,0]).max():.4f}, max R: {np.abs(y[:,1]).max():.4f}")

# FFT для проверки частот
n = len(y)
freqs = np.fft.rfftfreq(n, 1/sr)

fft_left = np.abs(np.fft.rfft(y[:,0]))
fft_right = np.abs(np.fft.rfft(y[:,1]))

# Находим пики (пропускаем DC)
peak_idx_l = np.argmax(fft_left[1:]) + 1
peak_idx_r = np.argmax(fft_right[1:]) + 1

print(f"Пик L: {freqs[peak_idx_l]:.1f} Гц (ожидалось 440 Гц)")
print(f"Пик R: {freqs[peak_idx_r]:.1f} Гц (ожидалось 880 Гц)")
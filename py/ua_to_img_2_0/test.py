# create_test.py
import numpy as np
import soundfile as sf

sr = 44100
duration = 10.0  # 10 секунд
t = np.linspace(0, duration, int(sr * duration), endpoint=False)

# Стерео: левый канал = 440 Гц, правый = 880 Гц
left = 0.5 * np.sin(2 * np.pi * 440 * t)
right = 0.5 * np.sin(2 * np.pi * 880 * t)

stereo = np.stack([left, right], axis=1)

sf.write('test_tone.wav', stereo, sr)
print(f"Создан test_tone.wav: {duration} сек, {sr} Гц, стерео")
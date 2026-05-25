import librosa
import numpy as np
import matplotlib.pyplot as plt

# Создадим простой звук: 440 Гц (нота Ля), 2 секунды
sr = 22050  # частота дискретизации
t = np.linspace(0, 2, sr * 2)
audio = np.sin(2 * np.pi * 440 * t)

# Построим мел-спектрограмму
mel = librosa.feature.melspectrogram(y=audio, sr=sr, n_mels=128)
mel_db = librosa.power_to_db(mel, ref=np.max)

# Покажем картинку
plt.figure(figsize=(10, 4))
librosa.display.specshow(mel_db, sr=sr, x_axis='time', y_axis='mel')
plt.colorbar(format='%+2.0f dB')
plt.title('Мел-спектрограмма')
plt.show()
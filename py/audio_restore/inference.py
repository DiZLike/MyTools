"""
Inference — удаление шума из аудиофайла
"""
import torch
import numpy as np
import soundfile as sf
import librosa
from pathlib import Path
import argparse

from train import ComplexDenoiser, N_FFT, HOP_LENGTH, SR, FREQ_BINS, DEVICE

@torch.no_grad()
def denoise_file(input_path, output_path, model_path, global_max=None):
    """Удаляет шум из аудиофайла"""
    
    # Загрузка модели
    model = ComplexDenoiser().to(DEVICE)
    ckpt = torch.load(model_path, map_location=DEVICE)
    # Поддержка разных форматов чекпоинта
    if 'model_state' in ckpt:
        model.load_state_dict(ckpt['model_state'])
    else:
        model.load_state_dict(ckpt)
    model.eval()
    
    # Загрузка аудио
    audio, sr = sf.read(input_path)
    if sr != SR:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SR)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    
    # STFT
    stft = librosa.stft(audio, n_fft=N_FFT, hop_length=HOP_LENGTH)
    
    # Нормализация
    if global_max is None:
        global_max = np.abs(stft).max()
    stft_norm = stft / global_max
    
    # Подготовка входа [1, 2, F, T]
    x = np.stack([np.real(stft_norm), np.imag(stft_norm)], axis=0)
    x = torch.from_numpy(x.astype(np.float32)).unsqueeze(0).to(DEVICE)
    
    # Инференс
    pred = model(x)  # [1, 2, F, T]
    pred = pred.cpu().numpy()[0]
    
    # Обратно в комплексный спектр
    pred_complex = (pred[0] + 1j * pred[1]) * global_max
    
    # Обратное STFT
    denoised = librosa.istft(pred_complex, hop_length=HOP_LENGTH, length=len(audio))
    
    # Сохранение
    sf.write(output_path, denoised, SR)
    print(f"✅ Сохранено: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Входной WAV-файл')
    parser.add_argument('output', help='Выходной WAV-файл')
    parser.add_argument('--model', default='checkpoints_denoiser_v1/best_model.pt')
    args = parser.parse_args()
    
    denoise_file(args.input, args.output, args.model)
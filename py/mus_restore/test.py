"""
Инференс AudioUNet MEL-1024
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import librosa
import numpy as np
from pathlib import Path
import soundfile as sf
import random

# ======================== КОНФИГ ========================
N_FFT = 2048
HOP_LENGTH = 512
SR = 44100
N_MELS = 1024
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

BEST_MODEL = Path("checkpoints_mel1024/best_model.pt")
DATASET_DIR = Path("E:/AI_RESTORE/dataset_audio_sr")
LOW_RES_DIR = DATASET_DIR / "low_res"
HIGH_RES_DIR = DATASET_DIR / "high_res"
OUTPUT_DIR = Path("restored_mel1024")
OUTPUT_DIR.mkdir(exist_ok=True)

# ======================== МОДЕЛЬ ========================
class AudioUNet_Mel1024(nn.Module):
    def __init__(self):
        super().__init__()
        
        def conv_block(in_ch, out_ch):
            return nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 3, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True),
                nn.Conv2d(out_ch, out_ch, 3, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True)
            )

        self.enc1 = conv_block(1, 32)
        self.enc2 = conv_block(32, 64)
        self.enc3 = conv_block(64, 128)
        self.enc4 = conv_block(128, 256)
        self.pool = nn.MaxPool2d(2, 2)
        self.bottleneck = conv_block(256, 512)
        
        self.up4 = nn.ConvTranspose2d(512, 256, kernel_size=2, stride=2)
        self.dec4 = conv_block(512, 256)
        self.up3 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.dec3 = conv_block(256, 128)
        self.up2 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.dec2 = conv_block(128, 64)
        self.up1 = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
        self.dec1 = conv_block(64, 32)
        
        self.output_conv = nn.Sequential(
            nn.Conv2d(32, 32, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 1, kernel_size=1)
        )

    def _pad_to_match(self, x, target):
        _, _, h_target, w_target = target.shape
        _, _, h_x, w_x = x.shape
        pad_h = max(0, h_target - h_x)
        pad_w = max(0, w_target - w_x)
        if pad_h > 0 or pad_w > 0:
            x = F.pad(x, [0, pad_w, 0, pad_h])
        if x.shape[2] > h_target: x = x[:, :, :h_target, :]
        if x.shape[3] > w_target: x = x[:, :, :, :w_target]
        return x

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        e4 = self.enc4(self.pool(e3))
        b = self.bottleneck(self.pool(e4))
        
        d4 = self.up4(b); d4 = self._pad_to_match(d4, e4)
        d4 = self.dec4(torch.cat([d4, e4], dim=1))
        d3 = self.up3(d4); d3 = self._pad_to_match(d3, e3)
        d3 = self.dec3(torch.cat([d3, e3], dim=1))
        d2 = self.up2(d3); d2 = self._pad_to_match(d2, e2)
        d2 = self.dec2(torch.cat([d2, e2], dim=1))
        d1 = self.up1(d2); d1 = self._pad_to_match(d1, e1)
        d1 = self.dec1(torch.cat([d1, e1], dim=1))
        
        return self.output_conv(d1)


def audio_to_logmel(audio):
    """Конвертирует аудио в log-mel спектрограмму"""
    mel = librosa.feature.melspectrogram(y=audio, sr=SR, n_fft=N_FFT,
                                         hop_length=HOP_LENGTH, n_mels=N_MELS)
    mel = mel / (mel.max() + 1e-8)
    log_mel = np.log10(np.maximum(mel, 1e-5))
    log_mel = (log_mel + 5) / 5
    log_mel = np.clip(log_mel, 0, 1)
    return log_mel.astype(np.float32)


def logmel_to_audio(log_mel, low_audio, reference_rms=None):
    """Конвертирует log-mel обратно в аудио с фазой low_res"""
    mel = 10 ** (log_mel * 5 - 5)
    
    # Инвертируем mel → магнитуду
    mel_basis = librosa.filters.mel(sr=SR, n_fft=N_FFT, n_mels=N_MELS)
    mel_basis_pinv = np.linalg.pinv(mel_basis)
    pred_mag = np.abs(mel_basis_pinv @ mel)
    
    # Берём фазу из low_res
    low_stft = librosa.stft(low_audio, n_fft=N_FFT, hop_length=HOP_LENGTH)
    low_phase = np.angle(low_stft)
    
    min_frames = min(pred_mag.shape[1], low_phase.shape[1])
    pred_mag = pred_mag[:, :min_frames]
    low_phase = low_phase[:, :min_frames]
    
    # Комбинируем
    pred_stft = pred_mag * np.exp(1j * low_phase)
    audio = librosa.istft(pred_stft, hop_length=HOP_LENGTH)
    
    if reference_rms is not None:
        current_rms = np.sqrt(np.mean(audio**2))
        if current_rms > 1e-8:
            audio = audio * (reference_rms / current_rms)
    
    return np.clip(audio, -1.0, 1.0)


def main():
    print("=" * 60)
    print("ИНФЕРЕНС MEL-1024")
    print("=" * 60)
    
    if not BEST_MODEL.exists():
        print(f"❌ Модель не найдена: {BEST_MODEL}")
        return
    
    print(f"\n📦 Загрузка модели...")
    model = AudioUNet_Mel1024().to(DEVICE)
    model.load_state_dict(torch.load(BEST_MODEL, map_location=DEVICE))
    model.eval()
    
    low_files = sorted(LOW_RES_DIR.glob("*.wav"))
    if not low_files:
        print("❌ Нет файлов!")
        return
    
    idx = random.randint(0, len(low_files) - 1)
    low_file = low_files[idx]
    high_file = HIGH_RES_DIR / low_file.name
    
    print(f"\n🎵 Файл: {low_file.name}")
    
    low_audio, _ = librosa.load(low_file, sr=SR)
    low_rms = np.sqrt(np.mean(low_audio**2))
    
    high_audio = None
    if high_file.exists():
        high_audio, _ = librosa.load(high_file, sr=SR)
    
    # Инференс
    low_mel = audio_to_logmel(low_audio)
    with torch.no_grad():
        x = torch.from_numpy(low_mel).unsqueeze(0).unsqueeze(0).to(DEVICE)
        pred_mel = model(x).squeeze().cpu().numpy()
    
    restored_audio = logmel_to_audio(pred_mel, low_audio, reference_rms=low_rms)
    
    # Обрезаем
    min_len = min(len(low_audio), len(restored_audio))
    low_audio = low_audio[:min_len]
    restored_audio = restored_audio[:min_len]
    if high_audio is not None:
        high_audio = high_audio[:min_len]
    
    # Сохраняем
    base_name = low_file.stem
    sf.write(OUTPUT_DIR / f"{base_name}_low.wav", low_audio, SR)
    sf.write(OUTPUT_DIR / f"{base_name}_restored.wav", restored_audio, SR)
    if high_audio is not None:
        sf.write(OUTPUT_DIR / f"{base_name}_high.wav", high_audio, SR)
    
    # Статистика
    if high_audio is not None:
        low_spec = np.abs(librosa.stft(low_audio, n_fft=N_FFT, hop_length=HOP_LENGTH))
        high_spec = np.abs(librosa.stft(high_audio, n_fft=N_FFT, hop_length=HOP_LENGTH))
        restored_spec = np.abs(librosa.stft(restored_audio, n_fft=N_FFT, hop_length=HOP_LENGTH))
        
        min_frames = min(low_spec.shape[1], high_spec.shape[1], restored_spec.shape[1])
        low_spec = low_spec[:, :min_frames]
        high_spec = high_spec[:, :min_frames]
        restored_spec = restored_spec[:, :min_frames]
        
        print(f"\n📊 Энергия по частотам:")
        for name, f_range in [
            ("НЧ (0-300 Hz)", (0, int(300*N_FFT/SR))),
            ("СЧ (0.3-4 kHz)", (int(300*N_FFT/SR), int(4000*N_FFT/SR))),
            ("ВЧ (4-10 kHz)", (int(4000*N_FFT/SR), int(10000*N_FFT/SR))),
            ("УВЧ (10-22 kHz)", (int(10000*N_FFT/SR), N_FFT//2+1))
        ]:
            l_e = np.mean(low_spec[f_range[0]:f_range[1], :])
            r_e = np.mean(restored_spec[f_range[0]:f_range[1], :])
            h_e = np.mean(high_spec[f_range[0]:f_range[1], :])
            print(f"   {name}:")
            print(f"      Low: {l_e:.4f} | Restored: {r_e:.4f} | High: {h_e:.4f}")
    
    print(f"\n💾 Сохранено в {OUTPUT_DIR}/")
    print(f"✅ Готово!")


if __name__ == "__main__":
    main()
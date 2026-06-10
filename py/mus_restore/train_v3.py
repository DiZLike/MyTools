"""
MP3 Restorer v3 — GAN + Frequency Attention + Multi-Resolution STFT
Вход: магнитуда MP3-спектра [B, 1, F, T] (log10, [0,1])
Выход: магнитуда lossless-спектра [B, 1, F, T]
Особенности:
- U-Net с Frequency Attention (гармоническая структура)
- Multi-Scale Discriminator (GAN)
- Multi-resolution STFT loss
- L1 в линейной магнитуде + adversarial + feature matching + texture
- Расширенный дашборд: best/median/worst + error maps + SNR
- Сохранение pred WAV каждую эпоху
"""
import os
import sys
import gc
import json
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import numpy as np
import soundfile as sf
import librosa
from pathlib import Path
from tqdm import tqdm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import warnings
warnings.filterwarnings('ignore')

torch.backends.cudnn.benchmark = True
torch.backends.cudnn.deterministic = False

# ======================== КОНФИГ ========================
DATASET_DIR = Path("E:/AI_RESTORE/dataset_audio_mp3_128")
LOW_RES_DIR = DATASET_DIR / "low_res"
HIGH_RES_DIR = DATASET_DIR / "high_res"
CACHE_DIR = DATASET_DIR / "cache_mp3_v3"
CHECKPOINT_DIR = Path("checkpoints_mp3_v3")
REPORTS_DIR = Path("reports_mp3_v3")
AUDIO_SAMPLES_DIR = REPORTS_DIR / "audio_samples"

BATCH_SIZE = 4
EPOCHS = 120
LEARNING_RATE_G = 5e-5
LEARNING_RATE_D = 2e-5
N_FFT = 2048
HOP_LENGTH = 512
SR = 44100
FREQ_BINS = N_FFT // 2 + 1
VAL_SPLIT = 0.1
NUM_WORKERS = 2
GRADIENT_CLIP = 1.0
EARLY_STOP_PATIENCE = 40

# Веса лоссов
LAMBDA_L1 = 1.0        # L1 в линейной магнитуде
LAMBDA_ADV = 0.0       # Adversarial
LAMBDA_FM = 0.0        # Feature matching
LAMBDA_TEX = 0.3       # Texture (variance)

# GAN параметры
LABEL_SMOOTHING_REAL = 0.9
LABEL_SMOOTHING_FAKE = 0.1
NOISE_STD_D = 0.05

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CHECKPOINT_FILE = CHECKPOINT_DIR / "checkpoint_latest.pt"
BEST_MODEL_FILE_G = CHECKPOINT_DIR / "best_generator.pt"
BEST_MODEL_FILE_D = CHECKPOINT_DIR / "best_discriminator.pt"
HISTORY_FILE = REPORTS_DIR / "training_history.json"

# ======================== FREQUENCY ATTENTION ========================

class FrequencyAttention(nn.Module):
    """
    Self-attention вдоль оси частот.
    Помогает ловить гармоники и переносить high-frequency информацию.
    """
    def __init__(self, channels):
        super().__init__()
        self.ch_att = max(channels // 8, 8)
        self.query = nn.Conv1d(channels, self.ch_att, 1, bias=False)
        self.key = nn.Conv1d(channels, self.ch_att, 1, bias=False)
        self.value = nn.Conv1d(channels, channels, 1, bias=False)
        self.gamma = nn.Parameter(torch.zeros(1))
        
    def forward(self, x):
        B, C, F, T = x.shape
        x_flat = x.permute(0, 3, 1, 2).reshape(B * T, C, F)
        
        Q = self.query(x_flat)
        K = self.key(x_flat)
        V = self.value(x_flat)
        
        scale = self.ch_att ** 0.5
        attn = torch.softmax(torch.bmm(Q.transpose(1, 2), K) / scale, dim=-1)
        out = torch.bmm(V, attn.transpose(1, 2))
        out = out.reshape(B, T, C, F).permute(0, 2, 3, 1)
        
        return x + self.gamma * out


# ======================== ДИСКРИМИНАТОР (Multi-Scale) ========================

class MultiScaleDiscriminator(nn.Module):
    def __init__(self):
        super().__init__()
        def make_disc():
            return nn.Sequential(
                nn.Conv2d(1, 64, 4, 2, 1), nn.LeakyReLU(0.2),
                nn.Conv2d(64, 128, 4, 2, 1), nn.BatchNorm2d(128), nn.LeakyReLU(0.2),
                nn.Conv2d(128, 256, 4, 2, 1), nn.BatchNorm2d(256), nn.LeakyReLU(0.2),
                nn.Conv2d(256, 512, 4, 2, 1), nn.BatchNorm2d(512), nn.LeakyReLU(0.2),
                nn.Conv2d(512, 1, 4, 1, 0)
            )
        self.d1 = make_disc()
        self.d2 = make_disc()
        self.d3 = make_disc()
        self.downsample = nn.AvgPool2d(2, 2)

    def forward(self, x):
        if self.training and NOISE_STD_D > 0:
            x = x + torch.randn_like(x) * NOISE_STD_D
        return [self.d1(x), self.d2(self.downsample(x)), self.d3(self.downsample(self.downsample(x)))]


# ======================== ГЕНЕРАТОР (U-Net + Frequency Attention) ========================

class DoubleConv(nn.Module):
    def __init__(self, in_ch, out_ch, dropout=0.0):
        super().__init__()
        layers = [
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.LeakyReLU(0.2, inplace=True),
        ]
        if dropout > 0:
            layers.append(nn.Dropout2d(dropout))
        layers += [
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.LeakyReLU(0.2, inplace=True),
        ]
        self.conv = nn.Sequential(*layers)
    
    def forward(self, x):
        return self.conv(x)


class MP3RestorerV3(nn.Module):
    """
    U-Net для магнитуды спектра.
    Вход: [B, 1, F, T] — log-магнитуда MP3
    Выход: [B, 1, F, T] — log-магнитуда lossless
    """
    def __init__(self, freq_bins=FREQ_BINS):
        super().__init__()
        
        self.enc1 = DoubleConv(1, 48)
        self.enc2 = DoubleConv(48, 96)
        self.enc3 = DoubleConv(96, 192)
        self.enc4 = DoubleConv(192, 384)
        self.enc5 = DoubleConv(384, 768, dropout=0.1)
        self.pool = nn.MaxPool2d((2, 2))
        
        self.freq_attn = FrequencyAttention(768)
        
        self.bottleneck = nn.Sequential(
            DoubleConv(768, 1024, dropout=0.2),
            DoubleConv(1024, 768, dropout=0.1),
        )
        
        self.up5 = nn.ConvTranspose2d(768, 768, kernel_size=2, stride=2)
        self.dec5 = DoubleConv(768 + 768, 384)
        self.up4 = nn.ConvTranspose2d(384, 384, kernel_size=2, stride=2)
        self.dec4 = DoubleConv(384 + 384, 192)
        self.up3 = nn.ConvTranspose2d(192, 192, kernel_size=2, stride=2)
        self.dec3 = DoubleConv(192 + 192, 96)
        self.up2 = nn.ConvTranspose2d(96, 96, kernel_size=2, stride=2)
        self.dec2 = DoubleConv(96 + 96, 48)
        self.up1 = nn.ConvTranspose2d(48, 48, kernel_size=2, stride=2)
        self.dec1 = DoubleConv(48 + 48, 24)
        
        self.output = nn.Sequential(
            nn.Conv2d(24, 24, 3, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(24, 1, 3, padding=1),
            nn.Sigmoid(),
        )
        
        self._init_weights()
    
    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, (nn.Conv2d, nn.ConvTranspose2d)):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='leaky_relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
    
    def _crop(self, x, target):
        _, _, h_t, w_t = target.shape
        _, _, h_x, w_x = x.shape
        if h_x > h_t:
            x = x[:, :, :h_t, :]
        if w_x > w_t:
            x = x[:, :, :, :w_t]
        if h_x < h_t:
            x = F.pad(x, [0, 0, 0, h_t - h_x])
        if w_x < w_t:
            x = F.pad(x, [0, w_t - w_x, 0, 0])
        return x
    
    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        e4 = self.enc4(self.pool(e3))
        e5 = self.enc5(self.pool(e4))
        
        e5 = self.freq_attn(e5)
        b = self.bottleneck(e5)
        
        d5 = self.up5(b); d5 = self._crop(d5, e5)
        d5 = self.dec5(torch.cat([d5, e5], dim=1))
        
        d4 = self.up4(d5); d4 = self._crop(d4, e4)
        d4 = self.dec4(torch.cat([d4, e4], dim=1))
        
        d3 = self.up3(d4); d3 = self._crop(d3, e3)
        d3 = self.dec3(torch.cat([d3, e3], dim=1))
        
        d2 = self.up2(d3); d2 = self._crop(d2, e2)
        d2 = self.dec2(torch.cat([d2, e2], dim=1))
        
        d1 = self.up1(d2); d1 = self._crop(d1, e1)
        d1 = self.dec1(torch.cat([d1, e1], dim=1))
        
        return self.output(d1)


# ======================== ДАТАСЕТ ========================
class MP3DatasetV3(Dataset):
    def __init__(self, low_res_dir, high_res_dir):
        self.low_files = sorted(Path(low_res_dir).glob("*.wav"))
        self.high_files = sorted(Path(high_res_dir).glob("*.wav"))
        assert len(self.low_files) == len(self.high_files), "Mismatch!"
        
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.chunk_files = sorted(CACHE_DIR.glob("chunk_*.pt"))
        self._all_X = None
        self._all_Y = None
        
        if self.chunk_files:
            print(f"📦 Загрузка из кэша: {CACHE_DIR}")
            all_X, all_Y = [], []
            for cf in tqdm(self.chunk_files, desc="   Загрузка", unit="чанк"):
                chunk = torch.load(cf, map_location='cpu', weights_only=True)
                X = chunk['X']
                Y = chunk['Y']
                # Гарантируем [N, 1, F, T]
                if X.dim() == 3:
                    X = X.unsqueeze(1)
                if Y.dim() == 3:
                    Y = Y.unsqueeze(1)
                all_X.append(X)
                all_Y.append(Y)
            self._all_X = torch.cat(all_X, dim=0)
            self._all_Y = torch.cat(all_Y, dim=0)
            self.n_samples = len(self._all_X)
        else:
            print(f"🔨 Создание кэша ({len(self.low_files)} файлов)...")
            n_files = len(self.low_files)
            
            print("   Вычисление статистики...")
            global_max = 0
            step = max(1, n_files // 10)
            for i in tqdm(range(0, n_files, step), desc="   Статистика"):
                low, _ = librosa.load(self.low_files[i], sr=SR)
                high, _ = librosa.load(self.high_files[i], sr=SR)
                low_mag = np.abs(librosa.stft(low, n_fft=N_FFT, hop_length=HOP_LENGTH))
                high_mag = np.abs(librosa.stft(high, n_fft=N_FFT, hop_length=HOP_LENGTH))
                global_max = max(global_max, low_mag.max(), high_mag.max())
            
            self.global_max = global_max
            print(f"   Global max: {global_max:.2f}")
            
            chunk_size = 200
            all_X, all_Y = [], []
            
            for start in tqdm(range(0, n_files, chunk_size), desc="   Запись чанков"):
                chunk_X, chunk_Y = [], []
                for i in range(start, min(start + chunk_size, n_files)):
                    low, _ = librosa.load(self.low_files[i], sr=SR)
                    high, _ = librosa.load(self.high_files[i], sr=SR)
                    
                    low_mag = np.abs(librosa.stft(low, n_fft=N_FFT, hop_length=HOP_LENGTH))
                    high_mag = np.abs(librosa.stft(high, n_fft=N_FFT, hop_length=HOP_LENGTH))
                    
                    low_mag /= global_max
                    high_mag /= global_max
                    
                    log_low = (np.log10(np.maximum(low_mag, 1e-6)) + 6) / 6
                    log_high = (np.log10(np.maximum(high_mag, 1e-6)) + 6) / 6
                    
                    x = torch.from_numpy(log_low.astype(np.float16))
                    y = torch.from_numpy(log_high.astype(np.float16))
                    # Принудительно [1, F, T]
                    if x.dim() == 2:
                        x = x.unsqueeze(0)
                    elif x.dim() == 3 and x.shape[0] > 1:
                        x = x[0:1]
                    if y.dim() == 2:
                        y = y.unsqueeze(0)
                    elif y.dim() == 3 and y.shape[0] > 1:
                        y = y[0:1]
                    
                    chunk_X.append(x)
                    chunk_Y.append(y)
                
                chunk_X = torch.cat(chunk_X, dim=0)
                chunk_Y = torch.cat(chunk_Y, dim=0)
                # Гарантируем [N, 1, F, T]
                if chunk_X.dim() == 3:
                    chunk_X = chunk_X.unsqueeze(1)
                if chunk_Y.dim() == 3:
                    chunk_Y = chunk_Y.unsqueeze(1)
                
                print(f"   Чанк {len(all_X)}: X={chunk_X.shape}")
                
                torch.save({'X': chunk_X, 'Y': chunk_Y}, CACHE_DIR / f"chunk_{len(all_X):04d}.pt")
                all_X.append(chunk_X)
                all_Y.append(chunk_Y)
            
            self.chunk_files = sorted(CACHE_DIR.glob("chunk_*.pt"))
            self._all_X = torch.cat(all_X, dim=0)
            self._all_Y = torch.cat(all_Y, dim=0)
            self.n_samples = n_files
            
            with open(CACHE_DIR / "cache_info.txt", 'w') as f:
                f.write(f"MP3v3_GMAX={global_max:.2f}\n")
        
        self.global_max = 1.0
        info_file = CACHE_DIR / "cache_info.txt"
        if info_file.exists():
            with open(info_file) as f:
                for line in f:
                    if 'GMAX=' in line:
                        self.global_max = float(line.split('GMAX=')[1])
                        break
        
        print(f"   ✓ {self.n_samples:,} пар (X={self._all_X.shape}, global_max={self.global_max:.2f})")
    
    def __len__(self):
        return self.n_samples
    
    def __getitem__(self, idx):
        return self._all_X[idx].float(), self._all_Y[idx].float()


# ======================== ПРЕОБРАЗОВАНИЯ ========================

def log_mag_to_linear(log_mag):
    return 10 ** (log_mag * 6 - 6)


def linear_to_log_mag(linear_mag):
    return (torch.log10(linear_mag.clamp(min=1e-6)) + 6) / 6


# ======================== ЛОСС-ФУНКЦИИ ========================

def multi_resolution_stft_loss(pred_linear, target_linear, resolutions=[2048, 1024, 512]):
    """
    Multi-resolution magnitude loss.
    pred_linear, target_linear: магнитуды в линейном масштабе [B, 1, F, T]
    """
    loss = 0.0
    count = 0
    
    for res in resolutions:
        if res == N_FFT:
            pred_mag = pred_linear
            target_mag = target_linear
        elif res < N_FFT:
            scale = N_FFT // res
            pred_mag = F.avg_pool2d(pred_linear, kernel_size=(scale, 1), stride=(scale, 1))
            target_mag = F.avg_pool2d(target_linear, kernel_size=(scale, 1), stride=(scale, 1))
        else:
            continue
        
        loss += F.l1_loss(
            torch.log10(pred_mag + 1e-6),
            torch.log10(target_mag + 1e-6)
        )
        count += 1
    
    return loss / max(count, 1)


# ======================== SNR МЕТРИКА ========================

def compute_snr(clean_linear, noisy_linear):
    noise = noisy_linear - clean_linear
    signal_power = (clean_linear**2).sum()
    noise_power = (noise**2).sum() + 1e-8
    return 10 * torch.log10(signal_power / noise_power)


# ======================== ОБУЧЕНИЕ ========================

def train_epoch(generator, discriminator, loader, opt_g, opt_d, device):
    generator.train()
    
    total_g_loss = 0.0
    total_l1 = 0.0
    
    freq_weights = torch.linspace(1.0, 4.0, FREQ_BINS, device=device).view(1, 1, -1, 1)
    hf_cutoff = int(FREQ_BINS * 0.75)
    
    pbar = tqdm(loader, desc="Train", leave=False)
    for x, y_log in pbar:
        x = x.to(device)
        y_log = y_log.to(device)
        
        # === ГЕНЕРАТОР (без GAN) ===
        opt_g.zero_grad()
        pred_log = generator(x)
        
        pred_linear = log_mag_to_linear(pred_log)
        y_linear = log_mag_to_linear(y_log)
        
        l1_loss = F.l1_loss(pred_linear, y_linear)
        weighted_l1 = (torch.abs(pred_linear - y_linear) * freq_weights).mean()
        hf_loss = F.l1_loss(pred_linear[:, :, hf_cutoff:, :], y_linear[:, :, hf_cutoff:, :])
        mr_loss = multi_resolution_stft_loss(pred_linear, y_linear)
        
        std_pred = pred_linear.std(dim=3)
        std_real = y_linear.std(dim=3)
        tex_loss = (std_pred - std_real).abs().mean()
        
        g_loss = (LAMBDA_L1 * l1_loss +
                  0.5 * weighted_l1 +
                  0.3 * hf_loss +
                  LAMBDA_TEX * tex_loss +
                  0.5 * mr_loss)
        
        g_loss.backward()
        torch.nn.utils.clip_grad_norm_(generator.parameters(), GRADIENT_CLIP)
        opt_g.step()
        
        total_g_loss += g_loss.item()
        total_l1 += l1_loss.item()
        
        pbar.set_postfix(
            g=f'{total_g_loss/(pbar.n+1):.3f}',
            l1=f'{total_l1/(pbar.n+1):.4f}',
        )
    
    n = len(loader)
    return total_g_loss / n, 0.0, total_l1 / n


@torch.no_grad()
def validate(generator, loader, device):
    generator.eval()
    total_l1 = 0.0
    
    pbar = tqdm(loader, desc="Val", leave=False)
    for x, y_log in pbar:
        x = x.to(device)
        y_log = y_log.to(device)
        
        pred_log = generator(x)
        
        pred_linear = log_mag_to_linear(pred_log)
        y_linear = log_mag_to_linear(y_log)
        l1_loss = F.l1_loss(pred_linear, y_linear)
        total_l1 += l1_loss.item()
        
        pbar.set_postfix(l1=f'{total_l1/(pbar.n+1):.6f}')
    
    return total_l1 / len(loader)


@torch.no_grad()
def get_samples_for_viz(generator, dataset, device, num_check=60):
    generator.eval()
    all_errors = []
    all_data = []
    
    n_to_check = min(num_check, len(dataset))
    indices = np.random.choice(len(dataset), n_to_check, replace=False)
    
    for idx in indices:
        x, y_log = dataset[idx]
        x_dev = x.unsqueeze(0).to(device)
        pred_log = generator(x_dev).cpu()
        
        pred_linear = log_mag_to_linear(pred_log)
        y_linear = log_mag_to_linear(y_log.unsqueeze(0))
        error = F.l1_loss(pred_linear, y_linear).item()
        
        all_errors.append(error)
        all_data.append({
            'input': x.unsqueeze(0),
            'target_log': y_log.unsqueeze(0),
            'pred_log': pred_log,
        })
    
    sorted_idx = np.argsort(all_errors)
    
    result = []
    labels = ['BEST', 'MEDIAN', 'WORST']
    picks = [sorted_idx[0], sorted_idx[len(sorted_idx)//2], sorted_idx[-1]]
    
    for label, pick in zip(labels, picks):
        result.append({
            'label': label,
            'data': all_data[pick],
            'error': all_errors[pick],
        })
    
    return result


def save_prediction_wavs(samples, epoch, save_dir, global_max=1.0):
    """
    Сохраняет WAV предсказаний для best, median, worst.
    Восстанавливает аудио через фазу от MP3 (input).
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    
    for s in samples:
        label = s['label'].lower()
        data = s['data']
        
        # Берём фазу от MP3 (input)
        # У нас нет комплексного спектра — используем Griffin-Lim
        pred_log = data['pred_log'][0, 0].numpy()  # [F, T]
        pred_linear = 10 ** (pred_log * 6 - 6) * global_max
        
        # Griffin-Lim для восстановления фазы
        pred_stft = librosa.griffinlim(
            pred_linear, n_iter=32,
            hop_length=HOP_LENGTH, n_fft=N_FFT
        )
        
        peak = np.max(np.abs(pred_stft))
        if peak > 0.99:
            pred_stft /= peak * 1.01
        
        sf.write(save_dir / f"epoch_{epoch+1:03d}_{label}_pred.wav", pred_stft, SR)


# ======================== ВИЗУАЛИЗАЦИЯ ========================

def plot_dashboard(epoch,
                   g_losses, d_losses, val_l1s, lrs,
                   samples, save_dir):
    if not samples:
        return
    
    fig = plt.figure(figsize=(30, 24))
    gs = GridSpec(5, 4, figure=fig, hspace=0.4, wspace=0.35)
    
    colors = {
        'best': '#4CAF50', 'median': '#FF9800', 'worst': '#F44336',
    }
    
    # ===== РЯД 1: КРИВЫЕ ОБУЧЕНИЯ =====
    
    ax = fig.add_subplot(gs[0, 0])
    ax.plot(g_losses, 'b-', alpha=0.7, label='G Loss')
    ax.set_title('Generator Loss', fontsize=11, fontweight='bold')
    ax.legend(fontsize=7); ax.grid(alpha=0.3)
    
    ax = fig.add_subplot(gs[0, 1])
    ax.plot(d_losses, 'r-', alpha=0.7, label='D Loss')
    ax.set_title('Discriminator Loss', fontsize=11, fontweight='bold')
    ax.legend(fontsize=7); ax.grid(alpha=0.3)
    
    ax = fig.add_subplot(gs[0, 2])
    ax.plot(val_l1s, 'g-', alpha=0.7, label='Val L1 (linear)')
    ax.set_title('Validation L1 (linear mag)', fontsize=11, fontweight='bold')
    ax.legend(fontsize=7); ax.grid(alpha=0.3)
    best_epoch = val_l1s.index(min(val_l1s))
    ax.axvline(x=best_epoch + 1, color='green', linestyle='--', alpha=0.5)
    
    ax = fig.add_subplot(gs[0, 3])
    ax.semilogy(lrs, 'purple', linewidth=2)
    ax.set_title('Learning Rate (G)', fontsize=11, fontweight='bold')
    ax.grid(alpha=0.3)
    
    # ===== РЯД 2: МЕТРИКИ =====
    
    ax_metrics = fig.add_subplot(gs[1, :2])
    ax_metrics.axis('off')
    
    metrics_lines = []
    metrics_lines.append("═" * 50)
    metrics_lines.append(f"  EPOCH {epoch+1}  |  LR: {lrs[-1]:.2e}")
    metrics_lines.append("═" * 50)
    metrics_lines.append("")
    metrics_lines.append(f"  G Loss:    {g_losses[-1]:.4f}")
    metrics_lines.append(f"  D Loss:    {d_losses[-1]:.4f}")
    metrics_lines.append(f"  Val L1:    {val_l1s[-1]:.6f}")
    metrics_lines.append(f"  Best L1:   {min(val_l1s):.6f}  (epoch {best_epoch+1})")
    metrics_lines.append("")
    
    for s in samples:
        label = s['label']
        data = s['data']
        
        input_linear = log_mag_to_linear(data['input'][0, 0])
        target_linear = log_mag_to_linear(data['target_log'][0, 0])
        pred_linear = log_mag_to_linear(data['pred_log'][0, 0])
        
        snr_before = compute_snr(target_linear, input_linear).item()
        snr_after = compute_snr(target_linear, pred_linear).item()
        
        metrics_lines.append(
            f"  [{label}]  SNR: {snr_before:5.1f} → {snr_after:5.1f} dB  "
            f"(Δ={snr_after-snr_before:+.1f} dB)"
        )
    
    metrics_lines.append("")
    metrics_lines.append(f"  Device: {DEVICE}")
    metrics_lines.append("═" * 50)
    
    ax_metrics.text(0.05, 0.98, '\n'.join(metrics_lines),
                    transform=ax_metrics.transAxes,
                    fontsize=8.5, fontfamily='monospace',
                    verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='#FFF8E1',
                             edgecolor='#CC9900', alpha=0.95))
    
    # SNR bar chart
    ax_snr = fig.add_subplot(gs[1, 2:])
    labels_snr = []
    improvements = []
    colors_bar = []
    
    for s in samples:
        label = s['label']
        data = s['data']
        
        input_linear = log_mag_to_linear(data['input'][0, 0])
        target_linear = log_mag_to_linear(data['target_log'][0, 0])
        pred_linear = log_mag_to_linear(data['pred_log'][0, 0])
        
        snr_before = compute_snr(target_linear, input_linear).item()
        snr_after = compute_snr(target_linear, pred_linear).item()
        
        labels_snr.append(f"{label}\n{snr_before:.0f}→{snr_after:.0f}")
        improvements.append(snr_after - snr_before)
        colors_bar.append(colors[label.lower()])
    
    bars = ax_snr.bar(range(len(improvements)), improvements, color=colors_bar,
                      edgecolor='black', linewidth=0.5)
    ax_snr.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax_snr.set_xticks(range(len(improvements)))
    ax_snr.set_xticklabels(labels_snr, fontsize=8)
    ax_snr.set_title('SNR Improvement (Δ dB)', fontsize=11, fontweight='bold')
    ax_snr.grid(axis='y', alpha=0.3, linestyle='--')
    
    for bar, imp in zip(bars, improvements):
        ax_snr.text(bar.get_x() + bar.get_width()/2,
                   bar.get_height() + 0.1,
                   f'{imp:+.1f}',
                   ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    # ===== РЯДЫ 3-5: СПЕКТРОГРАММЫ =====
    
    for s_idx, s in enumerate(samples):
        label = s['label']
        data = s['data']
        row = 2 + s_idx
        
        input_log = data['input'][0, 0]  # [F, T]
        target_log = data['target_log'][0, 0]
        pred_log = data['pred_log'][0, 0]
        
        T = input_log.shape[1]
        t_start = max(0, T // 4)
        t_end = min(T, 3 * T // 4)
        
        input_db = (input_log[:, t_start:t_end] * 6 - 6).numpy()
        target_db = (target_log[:, t_start:t_end] * 6 - 6).numpy()
        pred_db = (pred_log[:, t_start:t_end] * 6 - 6).numpy()
        
        input_lin = log_mag_to_linear(input_log[:, t_start:t_end])
        target_lin = log_mag_to_linear(target_log[:, t_start:t_end])
        pred_lin = log_mag_to_linear(pred_log[:, t_start:t_end])
        error_after = torch.abs(pred_lin - target_lin).numpy()
        
        vmin_db = -6
        vmax_db = 0.5
        vmax_err = min(0.15, error_after.max() * 1.1)
        
        spec_configs = [
            (input_db, f'[{label}] MP3 Input (dB)', 'viridis', vmin_db, vmax_db),
            (pred_db, f'[{label}] Predicted (dB)', 'viridis', vmin_db, vmax_db),
            (target_db, f'[{label}] Lossless Target (dB)', 'viridis', vmin_db, vmax_db),
            (error_after, f'[{label}] Error |Pred-Target|', 'hot', 0, vmax_err),
        ]
        
        for col, (img_data, title, cmap, vmin, vmax) in enumerate(spec_configs):
            ax = fig.add_subplot(gs[row, col])
            im = ax.imshow(img_data, aspect='auto', origin='lower',
                          cmap=cmap, vmin=vmin, vmax=vmax)
            ax.set_title(title, fontsize=9, fontweight='bold')
            
            if col == 0:
                ax.set_ylabel('Freq bin')
            if s_idx == 2:
                ax.set_xlabel('Time frame')
            
            plt.colorbar(im, ax=ax, fraction=0.046)
    
    fig.suptitle(f'MP3 Restorer v3 — Epoch {epoch+1}/{EPOCHS}  |  '
                 f'Best Val L1: {min(val_l1s):.6f}',
                 fontsize=14, fontweight='bold', y=1.01)
    
    plt.savefig(save_dir / f"dashboard_epoch_{epoch+1:03d}.png",
                dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"   📊 Дашборд сохранён: dashboard_epoch_{epoch+1:03d}.png")


# ======================== СОХРАНЕНИЕ/ЗАГРУЗКА ========================

def save_checkpoint(epoch, g, d, opt_g, opt_d, best_l1, path):
    torch.save({
        'epoch': epoch,
        'g_state': g.state_dict(),
        'd_state': d.state_dict(),
        'opt_g': opt_g.state_dict(),
        'opt_d': opt_d.state_dict(),
        'best_l1': best_l1,
    }, path)


def load_checkpoint(path, g, d, opt_g, opt_d, device):
    ckpt = torch.load(path, map_location=device)
    g.load_state_dict(ckpt['g_state'])
    d.load_state_dict(ckpt['d_state'])
    opt_g.load_state_dict(ckpt['opt_g'])
    opt_d.load_state_dict(ckpt['opt_d'])
    return ckpt.get('epoch', 0), ckpt.get('best_l1', float('inf'))


def save_history(history, path):
    with open(path, 'w') as f:
        json.dump(history, f, indent=2)


# ======================== MAIN ========================
if __name__ == "__main__":
    for d in [CHECKPOINT_DIR, REPORTS_DIR, AUDIO_SAMPLES_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    
    print("╔══════════════════════════════════════════════╗")
    print("║  MP3 Restorer v3 — GAN + Freq Attention     ║")
    print("║  Magnitude only + Multi-Res STFT Loss       ║")
    print("╚══════════════════════════════════════════════╝")
    print()
    print(f"  Device:      {DEVICE}")
    if DEVICE.type == "cuda":
        print(f"  GPU:         {torch.cuda.get_device_name(0)}")
        print(f"  VRAM:        {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    print(f"  N_FFT:       {N_FFT}")
    print(f"  Hop length:  {HOP_LENGTH}")
    print(f"  Freq bins:   {FREQ_BINS}")
    print()
    
    # ======================== ДАТАСЕТ ========================
    print("📦 Загрузка датасета...")
    full_dataset = MP3DatasetV3(LOW_RES_DIR, HIGH_RES_DIR)
    
    val_size = int(len(full_dataset) * VAL_SPLIT)
    train_size = len(full_dataset) - val_size
    indices = torch.randperm(len(full_dataset),
                             generator=torch.Generator().manual_seed(42)).tolist()
    
    train_ds = torch.utils.data.Subset(full_dataset, indices[:train_size])
    val_ds = torch.utils.data.Subset(full_dataset, indices[train_size:])
    
    train_loader = DataLoader(train_ds, BATCH_SIZE, shuffle=True,
                              num_workers=NUM_WORKERS, pin_memory=True,
                              drop_last=True)
    val_loader = DataLoader(val_ds, BATCH_SIZE, shuffle=False,
                            num_workers=NUM_WORKERS, pin_memory=True)
    
    print(f"   Train: {train_size:,}  |  Val: {val_size:,}")
    print(f"   Batches per epoch: {len(train_loader)} train  |  {len(val_loader)} val")
    
    # ======================== МОДЕЛИ ========================
    generator = MP3RestorerV3().to(DEVICE)
    discriminator = MultiScaleDiscriminator().to(DEVICE)
    
    n_params_g = sum(p.numel() for p in generator.parameters())
    n_params_d = sum(p.numel() for p in discriminator.parameters())
    
    print(f"\n🔧 Модели:")
    print(f"   Generator:     {n_params_g:,} параметров")
    print(f"   Discriminator: {n_params_d:,} параметров")
    print(f"   Frequency Attention:  ✓")
    print(f"   Multi-Res STFT Loss:  ✓")
    
    # ======================== ОПТИМИЗАТОРЫ ========================
    opt_g = torch.optim.AdamW(generator.parameters(), lr=LEARNING_RATE_G,
                              betas=(0.5, 0.999))
    opt_d = torch.optim.AdamW(discriminator.parameters(), lr=LEARNING_RATE_D,
                              betas=(0.5, 0.999))
    sched_g = torch.optim.lr_scheduler.CosineAnnealingLR(opt_g, T_max=EPOCHS, eta_min=1e-6)
    sched_d = torch.optim.lr_scheduler.CosineAnnealingLR(opt_d, T_max=EPOCHS, eta_min=1e-6)
    
    # ======================== ЗАГРУЗКА ЧЕКПОИНТА ========================
    start_epoch = 0
    best_l1 = float('inf')
    
    if os.path.exists(CHECKPOINT_FILE):
        start_epoch, best_l1 = load_checkpoint(CHECKPOINT_FILE, generator, discriminator,
                                                opt_g, opt_d, DEVICE)
        # Принудительно ставим LR из конфига
        for param_group in opt_g.param_groups:
            param_group['lr'] = LEARNING_RATE_G
        for param_group in opt_d.param_groups:
            param_group['lr'] = LEARNING_RATE_D
        print(f"\n📂 Чекпоинт загружен: эпоха {start_epoch}, best L1 {best_l1:.6f}")
        print(f"   LR принудительно: G={LEARNING_RATE_G:.1e}, D={LEARNING_RATE_D:.1e}")
    else:
        print("\n🆕 Обучение с нуля")
    
    # ======================== ИСТОРИЯ ========================
    history = {
        'g_loss': [], 'd_loss': [], 'val_l1': [], 'lr': [],
        'snr_improvements': [],
    }
    
    no_improve = 0
    
    print(f"\n{'='*60}")
    print(f"  LR G: {LEARNING_RATE_G:.0e}  |  LR D: {LEARNING_RATE_D:.0e}")
    print(f"  λ_L1={LAMBDA_L1}  λ_ADV={LAMBDA_ADV}  λ_FM={LAMBDA_FM}  λ_TEX={LAMBDA_TEX}")
    print(f"  Label smooth: {LABEL_SMOOTHING_REAL}/{LABEL_SMOOTHING_FAKE}")
    print(f"  Noise D: {NOISE_STD_D}")
    print(f"  Early stop patience: {EARLY_STOP_PATIENCE}")
    print(f"{'='*60}\n")
    
    # ======================== ЦИКЛ ОБУЧЕНИЯ ========================
    for epoch in range(start_epoch, EPOCHS):
        print(f"\n{'─'*50}")
        print(f"  EPOCH {epoch+1}/{EPOCHS}")
        print(f"{'─'*50}")
        
        g_loss, d_loss, train_l1 = train_epoch(
            generator, discriminator, train_loader, opt_g, opt_d, DEVICE
        )
        val_l1 = validate(generator, val_loader, DEVICE)
        
        sched_g.step()
        sched_d.step()
        current_lr = opt_g.param_groups[0]['lr']
        
        history['g_loss'].append(g_loss)
        history['d_loss'].append(d_loss)
        history['val_l1'].append(val_l1)
        history['lr'].append(current_lr)
        
        print(f"   G: {g_loss:.4f}  |  D: {d_loss:.4f}  |  Train L1: {train_l1:.6f}")
        print(f"   Val L1: {val_l1:.6f}  |  LR: {current_lr:.2e}  |  Best: {best_l1:.6f}")
        
        if val_l1 < best_l1:
            best_l1 = val_l1
            no_improve = 0
            torch.save(generator.state_dict(), BEST_MODEL_FILE_G)
            torch.save(discriminator.state_dict(), BEST_MODEL_FILE_D)
            print(f"   ✓ НОВАЯ ЛУЧШАЯ МОДЕЛЬ (val_l1={best_l1:.6f})")
        else:
            no_improve += 1
            print(f"   · Нет улучшения: {no_improve}/{EARLY_STOP_PATIENCE}")
        
        save_checkpoint(epoch + 1, generator, discriminator, opt_g, opt_d, best_l1, CHECKPOINT_FILE)
        
        # Дашборд + WAV каждую эпоху
        print(f"   🎨 Генерация дашборда...")
        samples = get_samples_for_viz(generator, val_ds, DEVICE)
        save_prediction_wavs(samples, epoch, AUDIO_SAMPLES_DIR,
                            global_max=full_dataset.global_max)
        
        # SNR для истории
        snr_imps = []
        for s in samples:
            data = s['data']
            input_linear = log_mag_to_linear(data['input'][0, 0])
            target_linear = log_mag_to_linear(data['target_log'][0, 0])
            pred_linear = log_mag_to_linear(data['pred_log'][0, 0])
            snr_before = compute_snr(target_linear, input_linear).item()
            snr_after = compute_snr(target_linear, pred_linear).item()
            snr_imps.append({
                'label': s['label'],
                'snr_before': snr_before,
                'snr_after': snr_after,
                'improvement': snr_after - snr_before,
            })
        history['snr_improvements'].append(snr_imps)
        
        plot_dashboard(epoch, history['g_loss'], history['d_loss'],
                      history['val_l1'], history['lr'],
                      samples, REPORTS_DIR)
        
        save_history(history, HISTORY_FILE)
        
        if no_improve >= EARLY_STOP_PATIENCE:
            print(f"\n⏹️  Ранняя остановка на эпохе {epoch+1}")
            break
        
        if DEVICE.type == "cuda" and (epoch + 1) % 10 == 0:
            torch.cuda.empty_cache()
            gc.collect()
    
    print(f"\n{'='*60}")
    print(f"🏁 ОБУЧЕНИЕ ЗАВЕРШЕНО")
    print(f"   Лучшая Val L1:  {best_l1:.6f}")
    print(f"   Генератор:      {BEST_MODEL_FILE_G}")
    print(f"   Дискриминатор:  {BEST_MODEL_FILE_D}")
    print(f"   Дашборды:       {REPORTS_DIR}")
    print(f"   WAV предсказаний: {AUDIO_SAMPLES_DIR}")
    print(f"   История:        {HISTORY_FILE}")
    print(f"\n✅ Готово!")
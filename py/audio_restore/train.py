"""
ComplexUNet — Noise Remover (50Hz Hum + Noise)
Вход: комплексный спектр зашумлённого сигнала [B, 2, F, T]
Выход: комплексный спектр чистого сигнала [B, 2, F, T]
Особенности:
- Complex U-Net с частотным attention
- Лосс: магнитудный (log-L1) + фазовый (cos distance)
- Multi-resolution STFT loss
- Расширенный дашборд: best/median/worst + error maps + SNR
- FIXED: громкость WAV-предсказаний восстановлена через global_max
- Сохраняются pred WAV для best, median, worst
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
DATASET_DIR = Path("E:/AI_RESTORE/dataset_noise_50hz")
NOISY_DIR = DATASET_DIR / "noisy"
CLEAN_DIR = DATASET_DIR / "clean"
CACHE_DIR = DATASET_DIR / "cache_complex_v1"
CHECKPOINT_DIR = Path("checkpoints_denoiser_v1")
REPORTS_DIR = Path("reports_denoiser_v1")
AUDIO_SAMPLES_DIR = REPORTS_DIR / "audio_samples"

BATCH_SIZE = 4
EPOCHS = 120
LEARNING_RATE = 2e-4
N_FFT = 2048
HOP_LENGTH = 1024
SR = 44100
FREQ_BINS = N_FFT // 2 + 1
VAL_SPLIT = 0.1
NUM_WORKERS = 2
GRADIENT_CLIP = 1.0
EARLY_STOP_PATIENCE = 50

# Веса лоссов
LAMBDA_MAG = 1.0       # L1 на log-магнитуде
LAMBDA_PHASE = 0.2     # cos distance на фазе
LAMBDA_MR = 0.5        # Multi-resolution STFT loss

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CHECKPOINT_FILE = CHECKPOINT_DIR / "checkpoint_latest.pt"
BEST_MODEL_FILE = CHECKPOINT_DIR / "best_model.pt"
HISTORY_FILE = REPORTS_DIR / "training_history.json"

# ======================== ЧАСТОТНЫЙ ATTENTION ========================

class FrequencyAttention(nn.Module):
    """
    Self-attention вдоль оси частот.
    Позволяет сети улавливать гармоническую структуру гула (50, 100, 150... Гц).
    """
    def __init__(self, channels):
        super().__init__()
        self.ch_in = channels
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


# ======================== COMPLEX U-NET ========================

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


class ComplexDenoiser(nn.Module):
    """
    U-Net для комплексного спектра.
    Вход: [B, 2, F, T] — (Re, Im) зашумлённого
    Выход: [B, 2, F, T] — очищенный спектр (residual connection)
    """
    def __init__(self, freq_bins=FREQ_BINS):
        super().__init__()
        
        self.enc1 = DoubleConv(2, 64)
        self.enc2 = DoubleConv(64, 128)
        self.enc3 = DoubleConv(128, 256)
        self.enc4 = DoubleConv(256, 512)
        self.enc5 = DoubleConv(512, 768, dropout=0.1)
        self.pool = nn.MaxPool2d((2, 2))
        
        self.freq_attn = FrequencyAttention(768)
        
        self.bottleneck = nn.Sequential(
            DoubleConv(768, 1024, dropout=0.2),
            DoubleConv(1024, 768, dropout=0.1),
        )
        
        self.up5 = nn.ConvTranspose2d(768, 768, kernel_size=2, stride=2)
        self.dec5 = DoubleConv(768 + 768, 512)
        self.up4 = nn.ConvTranspose2d(512, 512, kernel_size=2, stride=2)
        self.dec4 = DoubleConv(512 + 512, 256)
        self.up3 = nn.ConvTranspose2d(256, 256, kernel_size=2, stride=2)
        self.dec3 = DoubleConv(256 + 256, 128)
        self.up2 = nn.ConvTranspose2d(128, 128, kernel_size=2, stride=2)
        self.dec2 = DoubleConv(128 + 128, 64)
        self.up1 = nn.ConvTranspose2d(64, 64, kernel_size=2, stride=2)
        self.dec1 = DoubleConv(64 + 64, 32)
        
        self.output = nn.Sequential(
            nn.Conv2d(32, 32, 3, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(32, 2, 3, padding=1),
            nn.Tanh(),
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
        
        residual = self.output(d1)
        residual = self._crop(residual, x)
        
        return x + 0.3 * residual


# ======================== ДАТАСЕТ ========================

class ComplexNoiseDataset(Dataset):
    """
    Датасет, возвращающий комплексные спектры.
    Кэширует в оперативную память.
    """
    def __init__(self, noisy_dir, clean_dir):
        self.noisy_files = sorted(Path(noisy_dir).glob("*.wav"))
        self.clean_files = sorted(Path(clean_dir).glob("*.wav"))
        assert len(self.noisy_files) == len(self.clean_files), \
            f"Mismatch: {len(self.noisy_files)} noisy vs {len(self.clean_files)} clean"
        
        print(f"📦 Загрузка датасета ({len(self.noisy_files)} файлов)...")
        self.data = []
        
        global_max = 0.01
        for i in tqdm(range(len(self.noisy_files)), desc="   Анализ"):
            n, _ = sf.read(self.noisy_files[i])
            n_stft = librosa.stft(n, n_fft=N_FFT, hop_length=HOP_LENGTH)
            global_max = max(global_max, np.abs(n_stft).max())
        
        self.global_max = global_max
        print(f"   Global max: {global_max:.4f}")
        
        for i in tqdm(range(len(self.noisy_files)), desc="   Загрузка"):
            noisy, _ = sf.read(self.noisy_files[i])
            clean, _ = sf.read(self.clean_files[i])
            
            noisy_stft = librosa.stft(noisy, n_fft=N_FFT, hop_length=HOP_LENGTH)
            clean_stft = librosa.stft(clean, n_fft=N_FFT, hop_length=HOP_LENGTH)
            
            noisy_stft /= global_max
            clean_stft /= global_max
            
            noisy_real = np.real(noisy_stft).astype(np.float32)
            noisy_imag = np.imag(noisy_stft).astype(np.float32)
            clean_real = np.real(clean_stft).astype(np.float32)
            clean_imag = np.imag(clean_stft).astype(np.float32)
            
            x = np.stack([noisy_real, noisy_imag], axis=0)
            y = np.stack([clean_real, clean_imag], axis=0)
            
            self.data.append((torch.from_numpy(x), torch.from_numpy(y)))
        
        print(f"   ✓ {len(self.data)} пар загружено в память")
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        return self.data[idx]


# ======================== ЛОСС-ФУНКЦИИ ========================

def mag_phase_loss(pred, target):
    pred_mag = torch.sqrt(pred[:, 0:1]**2 + pred[:, 1:2]**2 + 1e-8)
    target_mag = torch.sqrt(target[:, 0:1]**2 + target[:, 1:2]**2 + 1e-8)
    
    log_pred = torch.log10(pred_mag + 1e-6)
    log_target = torch.log10(target_mag + 1e-6)
    mag_loss = F.l1_loss(log_pred, log_target)
    
    pred_phase = torch.atan2(pred[:, 1:2], pred[:, 0:1])
    target_phase = torch.atan2(target[:, 1:2], target[:, 0:1])
    phase_diff = pred_phase - target_phase
    phase_loss = torch.mean(1.0 - torch.cos(phase_diff))
    
    return mag_loss, phase_loss


def multi_resolution_stft_loss(pred_stft, target_stft, resolutions=[2048, 1024, 512]):
    loss = 0.0
    count = 0
    
    for res in resolutions:
        if res == N_FFT:
            pred_mag = torch.sqrt(pred_stft[:, 0:1]**2 + pred_stft[:, 1:2]**2 + 1e-8)
            target_mag = torch.sqrt(target_stft[:, 0:1]**2 + target_stft[:, 1:2]**2 + 1e-8)
        elif res < N_FFT:
            scale = N_FFT // res
            pred_mag = F.avg_pool2d(
                torch.sqrt(pred_stft[:, 0:1]**2 + pred_stft[:, 1:2]**2 + 1e-8),
                kernel_size=(scale, 1), stride=(scale, 1)
            )
            target_mag = F.avg_pool2d(
                torch.sqrt(target_stft[:, 0:1]**2 + target_stft[:, 1:2]**2 + 1e-8),
                kernel_size=(scale, 1), stride=(scale, 1)
            )
        else:
            continue
        
        loss += F.l1_loss(
            torch.log10(pred_mag + 1e-6),
            torch.log10(target_mag + 1e-6)
        )
        count += 1
    
    return loss / max(count, 1)


def total_loss_fn(pred, target):
    mag_loss, phase_loss = mag_phase_loss(pred, target)
    mr_loss = multi_resolution_stft_loss(pred, target)
    
    loss = (LAMBDA_MAG * mag_loss +
            LAMBDA_PHASE * phase_loss +
            LAMBDA_MR * mr_loss)
    
    return loss, mag_loss, phase_loss, mr_loss


# ======================== SNR МЕТРИКА ========================

def compute_snr(clean_mag, noisy_mag):
    noise = noisy_mag - clean_mag
    signal_power = (clean_mag**2).sum()
    noise_power = (noise**2).sum() + 1e-8
    return 10 * torch.log10(signal_power / noise_power)


# ======================== ОБУЧЕНИЕ ========================

def train_epoch(model, loader, optimizer, device):
    model.train()
    total_loss = 0.0
    total_mag = 0.0
    total_phase = 0.0
    total_mr = 0.0
    
    pbar = tqdm(loader, desc="Train", leave=False)
    for x, y in pbar:
        x = x.to(device)
        y = y.to(device)
        
        optimizer.zero_grad()
        pred = model(x)
        
        loss, mag_loss, phase_loss, mr_loss = total_loss_fn(pred, y)
        
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), GRADIENT_CLIP)
        optimizer.step()
        
        total_loss += loss.item()
        total_mag += mag_loss.item()
        total_phase += phase_loss.item()
        total_mr += mr_loss.item()
        
        pbar.set_postfix(
            loss=f'{total_loss/(pbar.n+1):.4f}',
            mag=f'{total_mag/(pbar.n+1):.4f}',
            ph=f'{total_phase/(pbar.n+1):.4f}',
        )
    
    n = len(loader)
    return total_loss / n, total_mag / n, total_phase / n, total_mr / n


@torch.no_grad()
def validate(model, loader, device):
    model.eval()
    total_loss = 0.0
    total_mag = 0.0
    total_phase = 0.0
    total_mr = 0.0
    
    pbar = tqdm(loader, desc="Val", leave=False)
    for x, y in pbar:
        x = x.to(device)
        y = y.to(device)
        
        pred = model(x)
        loss, mag_loss, phase_loss, mr_loss = total_loss_fn(pred, y)
        
        total_loss += loss.item()
        total_mag += mag_loss.item()
        total_phase += phase_loss.item()
        total_mr += mr_loss.item()
        
        pbar.set_postfix(loss=f'{total_loss/(pbar.n+1):.4f}')
    
    n = len(loader)
    return total_loss / n, total_mag / n, total_phase / n, total_mr / n


@torch.no_grad()
def get_samples_for_viz(model, dataset, device, num_check=60):
    model.eval()
    all_errors = []
    all_data = []
    
    n_to_check = min(num_check, len(dataset))
    indices = np.random.choice(len(dataset), n_to_check, replace=False)
    
    for idx in indices:
        x, y = dataset[idx]
        x_dev = x.unsqueeze(0).to(device)
        pred = model(x_dev).cpu()
        
        pred_mag = torch.sqrt(pred[0, 0]**2 + pred[0, 1]**2 + 1e-8)
        y_mag = torch.sqrt(y[0]**2 + y[1]**2 + 1e-8)
        error = F.l1_loss(pred_mag, y_mag).item()
        
        all_errors.append(error)
        all_data.append({
            'noisy': x.unsqueeze(0),
            'clean': y.unsqueeze(0),
            'pred': pred,
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
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    
    for s in samples:
        label = s['label'].lower()
        data = s['data']
        
        pred_stft = (data['pred'][0, 0].numpy() + 1j * data['pred'][0, 1].numpy())
        pred_stft = pred_stft * global_max
        
        pred_wav = librosa.istft(pred_stft, hop_length=HOP_LENGTH)
        
        peak = np.max(np.abs(pred_wav))
        if peak > 0.99:
            pred_wav /= peak * 1.01
        
        sf.write(save_dir / f"epoch_{epoch+1:03d}_{label}_pred.wav", pred_wav, SR)


# ======================== ВИЗУАЛИЗАЦИЯ ========================

def plot_dashboard(epoch, 
                   train_losses, val_losses,
                   train_mags, val_mags,
                   train_phases, val_phases,
                   train_mrs, val_mrs,
                   lrs, samples, save_dir):
    if not samples:
        return
    
    fig = plt.figure(figsize=(30, 24))
    gs = GridSpec(5, 4, figure=fig, hspace=0.4, wspace=0.35)
    
    colors = {
        'train': '#2196F3', 'val': '#FF5722',
        'best': '#4CAF50', 'median': '#FF9800', 'worst': '#F44336',
    }
    
    # ===== РЯД 1: КРИВЫЕ ОБУЧЕНИЯ =====
    loss_configs = [
        ('Total Loss', train_losses, val_losses, 0),
        ('Magnitude Loss (log L1)', train_mags, val_mags, 1),
        ('Phase Loss (cos dist)', train_phases, val_phases, 2),
        ('Multi-Res STFT Loss', train_mrs, val_mrs, 3),
    ]
    
    for title, train_data, val_data, col in loss_configs:
        ax = fig.add_subplot(gs[0, col])
        epochs_x = range(1, len(train_data) + 1)
        ax.plot(epochs_x, train_data, color=colors['train'], alpha=0.8, 
                linewidth=1.5, label='Train')
        ax.plot(epochs_x, val_data, color=colors['val'], alpha=0.8, 
                linewidth=1.5, label='Val')
        ax.set_title(title, fontsize=11, fontweight='bold')
        ax.legend(fontsize=7, loc='upper right')
        ax.grid(alpha=0.3)
        ax.set_xlabel('Epoch')
        if 'Total' in title:
            best_epoch = val_data.index(min(val_data))
            ax.axvline(x=best_epoch + 1, color='green', linestyle='--', 
                      alpha=0.5, linewidth=0.8)
    
    # ===== РЯД 2: МЕТРИКИ И SNR =====
    ax_metrics = fig.add_subplot(gs[1, :2])
    ax_metrics.axis('off')
    
    metrics_lines = []
    metrics_lines.append("═" * 50)
    metrics_lines.append(f"  EPOCH {epoch+1}  |  LR: {lrs[-1]:.2e}")
    metrics_lines.append("═" * 50)
    metrics_lines.append("")
    metrics_lines.append(f"  Total Loss:     T {train_losses[-1]:.4f}  |  V {val_losses[-1]:.4f}")
    metrics_lines.append(f"  Magnitude Loss: T {train_mags[-1]:.4f}  |  V {val_mags[-1]:.4f}")
    metrics_lines.append(f"  Phase Loss:     T {train_phases[-1]:.4f}  |  V {val_phases[-1]:.4f}")
    metrics_lines.append(f"  MR STFT Loss:   T {train_mrs[-1]:.4f}  |  V {val_mrs[-1]:.4f}")
    metrics_lines.append("")
    
    best_epoch_idx = val_losses.index(min(val_losses))
    metrics_lines.append(f"  Best Val Loss:  {min(val_losses):.4f}  (epoch {best_epoch_idx+1})")
    metrics_lines.append(f"  Patience:       {EARLY_STOP_PATIENCE}")
    metrics_lines.append("")
    
    for s in samples:
        label = s['label']
        data = s['data']
        
        noisy_mag = torch.sqrt(data['noisy'][0, 0]**2 + data['noisy'][0, 1]**2 + 1e-8)
        clean_mag = torch.sqrt(data['clean'][0, 0]**2 + data['clean'][0, 1]**2 + 1e-8)
        pred_mag = torch.sqrt(data['pred'][0, 0]**2 + data['pred'][0, 1]**2 + 1e-8)
        
        snr_before = compute_snr(clean_mag, noisy_mag).item()
        snr_after = compute_snr(clean_mag, pred_mag).item()
        improvement = snr_after - snr_before
        
        metrics_lines.append(
            f"  [{label}]  SNR: {snr_before:5.1f} → {snr_after:5.1f} dB  "
            f"(Δ={improvement:+.1f} dB)"
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
    
    # SNR Improvement bar chart
    ax_snr = fig.add_subplot(gs[1, 2:])
    
    labels_snr = []
    improvements = []
    colors_bar = []
    
    for s in samples:
        label = s['label']
        data = s['data']
        
        noisy_mag = torch.sqrt(data['noisy'][0, 0]**2 + data['noisy'][0, 1]**2 + 1e-8)
        clean_mag = torch.sqrt(data['clean'][0, 0]**2 + data['clean'][0, 1]**2 + 1e-8)
        pred_mag = torch.sqrt(data['pred'][0, 0]**2 + data['pred'][0, 1]**2 + 1e-8)
        
        snr_before = compute_snr(clean_mag, noisy_mag).item()
        snr_after = compute_snr(clean_mag, pred_mag).item()
        
        labels_snr.append(f"{label}\n{snr_before:.0f}→{snr_after:.0f}")
        improvements.append(snr_after - snr_before)
        colors_bar.append(colors[label.lower()])
    
    bars = ax_snr.bar(range(len(improvements)), improvements, color=colors_bar, 
                      edgecolor='black', linewidth=0.5)
    ax_snr.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax_snr.set_xticks(range(len(improvements)))
    ax_snr.set_xticklabels(labels_snr, fontsize=8)
    ax_snr.set_title('SNR Improvement (Δ dB)', fontsize=11, fontweight='bold')
    ax_snr.set_ylabel('Δ SNR (dB)')
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
        
        noisy_mag = torch.sqrt(data['noisy'][0, 0]**2 + data['noisy'][0, 1]**2 + 1e-8)
        clean_mag = torch.sqrt(data['clean'][0, 0]**2 + data['clean'][0, 1]**2 + 1e-8)
        pred_mag = torch.sqrt(data['pred'][0, 0]**2 + data['pred'][0, 1]**2 + 1e-8)
        
        T = noisy_mag.shape[1]
        t_start = max(0, T // 4)
        t_end = min(T, 3 * T // 4)
        
        noisy_db = torch.log10(noisy_mag[:, t_start:t_end] + 1e-6).numpy()
        clean_db = torch.log10(clean_mag[:, t_start:t_end] + 1e-6).numpy()
        pred_db = torch.log10(pred_mag[:, t_start:t_end] + 1e-6).numpy()
        error_after = torch.abs(pred_mag[:, t_start:t_end] - clean_mag[:, t_start:t_end]).numpy()
        
        vmin_db = -6
        vmax_db = 0.5
        vmax_err = min(0.2, error_after.max() * 1.1)
        
        spec_configs = [
            (noisy_db, f'[{label}] Noisy Input', 'viridis', vmin_db, vmax_db),
            (pred_db, f'[{label}] Predicted', 'viridis', vmin_db, vmax_db),
            (clean_db, f'[{label}] Clean Target', 'viridis', vmin_db, vmax_db),
            (error_after, f'[{label}] Error |Pred-Clean|', 'hot', 0, vmax_err),
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
            
            if 'Error' not in title:
                for h in [1, 2, 3, 4, 5, 6]:
                    freq_hz = 50 * h
                    bin_idx = int(freq_hz * N_FFT / SR)
                    if bin_idx < img_data.shape[0]:
                        ax.axhline(y=bin_idx, color='red', linestyle=':', 
                                  linewidth=0.4, alpha=0.5)
            
            plt.colorbar(im, ax=ax, fraction=0.046)
    
    fig.suptitle(f'ComplexUNet Denoiser — Epoch {epoch+1}/{EPOCHS}  |  '
                 f'Best Val Loss: {min(val_losses):.4f}',
                 fontsize=14, fontweight='bold', y=1.01)
    
    plt.savefig(save_dir / f"dashboard_epoch_{epoch+1:03d}.png", 
                dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"   📊 Дашборд сохранён: dashboard_epoch_{epoch+1:03d}.png")


# ======================== СОХРАНЕНИЕ/ЗАГРУЗКА ========================

def save_checkpoint(epoch, model, optimizer, best_loss, path):
    torch.save({
        'epoch': epoch,
        'model_state': model.state_dict(),
        'optimizer_state': optimizer.state_dict(),
        'best_loss': best_loss,
    }, path)


def load_checkpoint(path, model, optimizer, device):
    ckpt = torch.load(path, map_location=device)
    model.load_state_dict(ckpt['model_state'])
    optimizer.load_state_dict(ckpt['optimizer_state'])
    return ckpt.get('epoch', 0), ckpt.get('best_loss', float('inf'))


def save_history(history, path):
    with open(path, 'w') as f:
        json.dump(history, f, indent=2)


# ======================== MAIN ========================
if __name__ == "__main__":
    for d in [CHECKPOINT_DIR, REPORTS_DIR, AUDIO_SAMPLES_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    
    print("╔══════════════════════════════════════════════╗")
    print("║  ComplexUNet — Noise Remover v2              ║")
    print("║  50Hz Hum + Pink Noise + Brown Noise        ║")
    print("║  Complex spectrum + Frequency Attention     ║")
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
    full_dataset = ComplexNoiseDataset(NOISY_DIR, CLEAN_DIR)
    
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
    
    # ======================== МОДЕЛЬ ========================
    model = ComplexDenoiser().to(DEVICE)
    n_params = sum(p.numel() for p in model.parameters())
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    
    print(f"\n🔧 Модель ComplexUNet:")
    print(f"   Всего параметров:     {n_params:,}")
    print(f"   Обучаемых:            {n_trainable:,}")
    print(f"   Frequency Attention:  ✓")
    print(f"   Dropout:              ✓")
    
    # ======================== ОПТИМИЗАТОР ========================
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, 
                                  betas=(0.9, 0.999), weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=10, min_lr=1e-6
    )
    
    # ======================== ЗАГРУЗКА ЧЕКПОИНТА ========================
    start_epoch = 0
    best_loss = float('inf')
    
    if os.path.exists(CHECKPOINT_FILE):
        start_epoch, best_loss = load_checkpoint(CHECKPOINT_FILE, model, optimizer, DEVICE)
        print(f"\n📂 Чекпоинт загружен: эпоха {start_epoch}, best loss {best_loss:.4f}")
    else:
        print("\n🆕 Обучение с нуля")
    
    # ======================== ИСТОРИЯ ========================
    history = {
        'train_loss': [], 'val_loss': [],
        'train_mag': [], 'val_mag': [],
        'train_phase': [], 'val_phase': [],
        'train_mr': [], 'val_mr': [],
        'lr': [],
        'snr_improvements': [],
    }
    
    no_improve = 0
    
    print(f"\n{'='*60}")
    print(f"  LR: {LEARNING_RATE:.0e}  |  Batch: {BATCH_SIZE}")
    print(f"  λ_mag={LAMBDA_MAG}  λ_phase={LAMBDA_PHASE}  λ_mr={LAMBDA_MR}")
    print(f"  Early stop patience: {EARLY_STOP_PATIENCE}")
    print(f"  Gradient clip: {GRADIENT_CLIP}")
    print(f"{'='*60}\n")
    
    # ======================== ЦИКЛ ОБУЧЕНИЯ ========================
    for epoch in range(start_epoch, EPOCHS):
        print(f"\n{'─'*50}")
        print(f"  EPOCH {epoch+1}/{EPOCHS}")
        print(f"{'─'*50}")
        
        t_loss, t_mag, t_phase, t_mr = train_epoch(model, train_loader, optimizer, DEVICE)
        v_loss, v_mag, v_phase, v_mr = validate(model, val_loader, DEVICE)
        
        old_lr = optimizer.param_groups[0]['lr']
        scheduler.step(v_loss)
        current_lr = optimizer.param_groups[0]['lr']
        if current_lr < old_lr:
            print(f"   🔻 LR снижен: {old_lr:.2e} → {current_lr:.2e}")
        
        history['train_loss'].append(t_loss)
        history['val_loss'].append(v_loss)
        history['train_mag'].append(t_mag)
        history['val_mag'].append(v_mag)
        history['train_phase'].append(t_phase)
        history['val_phase'].append(v_phase)
        history['train_mr'].append(t_mr)
        history['val_mr'].append(v_mr)
        history['lr'].append(current_lr)
        
        print(f"   Train │ Loss: {t_loss:.4f}  Mag: {t_mag:.4f}  "
              f"Phase: {t_phase:.4f}  MR: {t_mr:.4f}")
        print(f"   Val   │ Loss: {v_loss:.4f}  Mag: {v_mag:.4f}  "
              f"Phase: {v_phase:.4f}  MR: {v_mr:.4f}")
        print(f"   LR: {current_lr:.2e}  |  Best Val: {best_loss:.4f}")
        
        if v_loss < best_loss:
            best_loss = v_loss
            no_improve = 0
            torch.save(model.state_dict(), BEST_MODEL_FILE)
            print(f"   ✓ НОВАЯ ЛУЧШАЯ МОДЕЛЬ (val_loss={best_loss:.4f})")
        else:
            no_improve += 1
            print(f"   · Нет улучшения: {no_improve}/{EARLY_STOP_PATIENCE}")
        
        save_checkpoint(epoch + 1, model, optimizer, best_loss, CHECKPOINT_FILE)
        
        # ===== ДАШБОРД + WAV КАЖДУЮ ЭПОХУ =====
        print(f"   🎨 Генерация дашборда...")
        samples = get_samples_for_viz(model, val_ds, DEVICE)
        
        # Сохраняем pred WAV (best, median, worst) с правильной громкостью
        save_prediction_wavs(samples, epoch, AUDIO_SAMPLES_DIR, 
                            global_max=full_dataset.global_max)
        
        # SNR для истории
        snr_imps = []
        for s in samples:
            data = s['data']
            noisy_mag = torch.sqrt(data['noisy'][0, 0]**2 + data['noisy'][0, 1]**2 + 1e-8)
            clean_mag = torch.sqrt(data['clean'][0, 0]**2 + data['clean'][0, 1]**2 + 1e-8)
            pred_mag = torch.sqrt(data['pred'][0, 0]**2 + data['pred'][0, 1]**2 + 1e-8)
            snr_before = compute_snr(clean_mag, noisy_mag).item()
            snr_after = compute_snr(clean_mag, pred_mag).item()
            snr_imps.append({
                'label': s['label'],
                'snr_before': snr_before,
                'snr_after': snr_after,
                'improvement': snr_after - snr_before,
            })
        history['snr_improvements'].append(snr_imps)
        
        plot_dashboard(
            epoch,
            history['train_loss'], history['val_loss'],
            history['train_mag'], history['val_mag'],
            history['train_phase'], history['val_phase'],
            history['train_mr'], history['val_mr'],
            history['lr'],
            samples,
            REPORTS_DIR,
        )
        
        save_history(history, HISTORY_FILE)
        
        if no_improve >= EARLY_STOP_PATIENCE:
            print(f"\n⏹️  Ранняя остановка на эпохе {epoch+1}")
            break
        
        if DEVICE.type == "cuda" and (epoch + 1) % 10 == 0:
            torch.cuda.empty_cache()
            gc.collect()
    
    # ======================== ФИНАЛ ========================
    print(f"\n{'='*60}")
    print(f"🏁 ОБУЧЕНИЕ ЗАВЕРШЕНО")
    print(f"{'='*60}")
    print(f"   Лучшая Val Loss:     {best_loss:.4f}")
    print(f"   Лучшая модель:       {BEST_MODEL_FILE}")
    print(f"   Чекпоинт:            {CHECKPOINT_FILE}")
    print(f"   Дашборды:            {REPORTS_DIR}")
    print(f"   WAV предсказаний:    {AUDIO_SAMPLES_DIR}")
    print(f"   История (JSON):      {HISTORY_FILE}")
    
    print(f"\n✅ Готово!")
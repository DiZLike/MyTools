"""
AudioUNet — MP3 RESTORER v2 (Hi-Res Direct) [FIXED v2]
- Восстановление после MP3 128 kbps
- Вход: 1 канал (спектр MP3, 0-22k)
- Выход: полный high_res спектр
- Генератор предсказывает сразу lossless
- Дискриминатор сравнивает pred с real high_res
- FIXED: линейная магнитуда для лосса, баланс G/D, label smoothing, аугментации
- FIXED v2: broadcast ошибка в дискриминаторе, total_memory, совместимость .pt cache
"""
import os
import sys
import gc
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import librosa
import numpy as np
from pathlib import Path
from tqdm import tqdm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

torch.backends.cudnn.benchmark = True
torch.backends.cudnn.deterministic = False

# ======================== КОНФИГ ========================
DATASET_DIR = Path("E:/AI_RESTORE/dataset_audio_mp3_128")
LOW_RES_DIR = DATASET_DIR / "low_res"
HIGH_RES_DIR = DATASET_DIR / "high_res"
CACHE_DIR = DATASET_DIR / "cache_mp3_128_v2_fixed"
CHECKPOINT_DIR = Path("checkpoints_mp3_128_v2_fixed")
REPORTS_DIR = Path("reports_mp3_128_v2_fixed")

BATCH_SIZE = 4
EPOCHS = 100
LEARNING_RATE_G = 1e-4
LEARNING_RATE_D = 5e-5
N_FFT = 2048
HOP_LENGTH = 512
SR = 44100
FREQ_BINS = N_FFT // 2 + 1
VAL_SPLIT = 0.1
NUM_WORKERS = 2
GRADIENT_CLIP = 1.0
EARLY_STOP_PATIENCE = 40

LAMBDA_MSE = 1.0
LAMBDA_ADV = 2.5
LAMBDA_FM = 2.0
LAMBDA_TEX = 0.3

PRE_EMPHASIS_COEF = 0.90

LABEL_SMOOTHING_REAL = 0.9
LABEL_SMOOTHING_FAKE = 0.1
NOISE_STD_D = 0.03

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CHECKPOINT_FILE = CHECKPOINT_DIR / "checkpoint_latest.pt"
BEST_MODEL_FILE = CHECKPOINT_DIR / "best_generator.pt"

# ======================== ДИСКРИМИНАТОР ========================
class MultiScaleDiscriminator(nn.Module):
    def __init__(self):
        super().__init__()
        def make_discriminator():
            return nn.Sequential(
                nn.Conv2d(1, 64, 4, 2, 1), nn.LeakyReLU(0.2),
                nn.Conv2d(64, 128, 4, 2, 1), nn.BatchNorm2d(128), nn.LeakyReLU(0.2),
                nn.Conv2d(128, 256, 4, 2, 1), nn.BatchNorm2d(256), nn.LeakyReLU(0.2),
                nn.Conv2d(256, 512, 4, 2, 1), nn.BatchNorm2d(512), nn.LeakyReLU(0.2),
                nn.Conv2d(512, 1, 4, 1, 0)
            )
        self.d1 = make_discriminator()
        self.d2 = make_discriminator()
        self.d3 = make_discriminator()
        self.downsample = nn.AvgPool2d(2, 2)

    def forward(self, x):
        if self.training and NOISE_STD_D > 0:
            x = x + torch.randn_like(x) * NOISE_STD_D
        return [self.d1(x), self.d2(self.downsample(x)), self.d3(self.downsample(self.downsample(x)))]

# ======================== ГЕНЕРАТОР ========================
class SelfAttention(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.ch_att = nn.Sequential(
            nn.AdaptiveAvgPool2d(1), nn.Conv2d(channels, channels // 8, 1),
            nn.ReLU(), nn.Conv2d(channels // 8, channels, 1), nn.Sigmoid()
        )
        self.sp_att = nn.Sequential(nn.Conv2d(channels, 1, 1), nn.Sigmoid())
    def forward(self, x): return x * self.ch_att(x) * self.sp_att(x)

class MP3RestorerV2(nn.Module):
    def __init__(self):
        super().__init__()
        def conv_block(in_ch, out_ch):
            return nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(out_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.LeakyReLU(0.2, inplace=True)
            )
        self.enc1 = conv_block(1, 48)
        self.enc2 = conv_block(48, 96)
        self.enc3 = conv_block(96, 192)
        self.enc4 = conv_block(192, 384)
        self.pool = nn.MaxPool2d(2, 2)
        self.bottleneck = nn.Sequential(conv_block(384, 768), SelfAttention(768))
        self.up4 = nn.ConvTranspose2d(768, 384, kernel_size=2, stride=2)
        self.dec4 = conv_block(768, 192)
        self.up3 = nn.ConvTranspose2d(192, 192, kernel_size=2, stride=2)
        self.dec3 = conv_block(384, 96)
        self.up2 = nn.ConvTranspose2d(96, 96, kernel_size=2, stride=2)
        self.dec2 = conv_block(192, 48)
        self.up1 = nn.ConvTranspose2d(48, 48, kernel_size=2, stride=2)
        self.dec1 = conv_block(96, 24)
        self.output_conv = nn.Sequential(
            nn.Conv2d(24, 24, kernel_size=1), nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(24, 1, kernel_size=1),
            nn.Sigmoid()
        )
        for m in self.modules():
            if isinstance(m, (nn.Conv2d, nn.ConvTranspose2d)):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='leaky_relu')
                if m.bias is not None: nn.init.constant_(m.bias, 0)

    def _pad_to_match(self, x, target):
        _, _, h_target, w_target = target.shape
        _, _, h_x, w_x = x.shape
        pad_h = max(0, h_target - h_x); pad_w = max(0, w_target - w_x)
        if pad_h > 0 or pad_w > 0: x = F.pad(x, [0, pad_w, 0, pad_h])
        if x.shape[2] > h_target: x = x[:, :, :h_target, :]
        if x.shape[3] > w_target: x = x[:, :, :, :w_target]
        return x

    def forward(self, x_input):
        e1 = self.enc1(x_input)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        e4 = self.enc4(self.pool(e3))
        b = self.bottleneck(self.pool(e4))
        d4 = self.up4(b); d4 = self._pad_to_match(d4, e4); d4 = self.dec4(torch.cat([d4, e4], dim=1))
        d3 = self.up3(d4); d3 = self._pad_to_match(d3, e3); d3 = self.dec3(torch.cat([d3, e3], dim=1))
        d2 = self.up2(d3); d2 = self._pad_to_match(d2, e2); d2 = self.dec2(torch.cat([d2, e2], dim=1))
        d1 = self.up1(d2); d1 = self._pad_to_match(d1, e1); d1 = self.dec1(torch.cat([d1, e1], dim=1))
        output = self.output_conv(d1)
        if output.shape[2] != x_input.shape[2]:
            output = F.pad(output, [0, 0, 0, max(0, x_input.shape[2] - output.shape[2])])
        if output.shape[3] != x_input.shape[3]:
            output = F.pad(output, [0, max(0, x_input.shape[3] - output.shape[3]), 0, 0])
        output = output[:, :, :x_input.shape[2], :x_input.shape[3]]
        return output

# ======================== ДАТАСЕТ ========================
class MP3DatasetV2(Dataset):
    def __init__(self, low_res_dir, high_res_dir):
        self.low_files = sorted(Path(low_res_dir).glob("*.wav"))
        self.high_files = sorted(Path(high_res_dir).glob("*.wav"))
        assert len(self.low_files) == len(self.high_files), "Mismatch!"
        self.chunk_files = sorted(CACHE_DIR.glob("chunk_*.pt"))
        self._all_X = None; self._all_Y = None
        self._load_or_create_cache()

    def _load_or_create_cache(self):
        if self.chunk_files:
            print(f"📦 Загрузка чанков MP3 v2...")
            all_X, all_Y = [], []
            for cf in tqdm(self.chunk_files, desc="   Загрузка", unit="чанк"):
                chunk = torch.load(cf, map_location='cpu', weights_only=True)
                all_X.append(chunk['X']); all_Y.append(chunk['Y'])
            self._all_X = torch.cat(all_X, dim=0); self._all_Y = torch.cat(all_Y, dim=0)
            self.n_samples = len(self._all_X)
        else:
            print(f"🔨 Создание чанков MP3 v2...")
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            n_files = len(self.low_files)
            print("   Вычисление глобальной статистики...")
            global_max = 0
            for i in tqdm(range(0, n_files, max(1, n_files // 10)), desc="   Статистика"):
                low, _ = librosa.load(self.low_files[i], sr=SR); high, _ = librosa.load(self.high_files[i], sr=SR)
                low = np.append(low[0], low[1:] - PRE_EMPHASIS_COEF * low[:-1])
                high = np.append(high[0], high[1:] - PRE_EMPHASIS_COEF * high[:-1])
                global_max = max(global_max, np.abs(librosa.stft(low, n_fft=N_FFT, hop_length=HOP_LENGTH)).max(),
                                           np.abs(librosa.stft(high, n_fft=N_FFT, hop_length=HOP_LENGTH)).max())
            print(f"   Global max: {global_max:.2f}")
            chunk_size = 200; all_X, all_Y = [], []
            for start in tqdm(range(0, n_files, chunk_size), desc="   Запись чанков"):
                chunk_X, chunk_Y = [], []
                for i in range(start, min(start + chunk_size, n_files)):
                    x, y = self._compute_stft(i, global_max)
                    chunk_X.append(x.unsqueeze(0)); chunk_Y.append(y.unsqueeze(0))
                chunk_X = torch.cat(chunk_X, dim=0).half(); chunk_Y = torch.cat(chunk_Y, dim=0).half()
                torch.save({'X': chunk_X, 'Y': chunk_Y}, CACHE_DIR / f"chunk_{len(all_X):04d}.pt")
                all_X.append(chunk_X); all_Y.append(chunk_Y)
            self.chunk_files = sorted(CACHE_DIR.glob("chunk_*.pt"))
            self._all_X = torch.cat(all_X, dim=0); self._all_Y = torch.cat(all_Y, dim=0)
            self.n_samples = n_files
            with open(CACHE_DIR / "cache_info.txt", 'w') as f: f.write(f"MP3v2_GMAX={global_max:.2f}")
        print(f"   ✓ {self.n_samples:,} пар")

    def _compute_stft(self, idx, global_max):
        low, _ = librosa.load(self.low_files[idx], sr=SR); high, _ = librosa.load(self.high_files[idx], sr=SR)
        low = np.append(low[0], low[1:] - PRE_EMPHASIS_COEF * low[:-1])
        high = np.append(high[0], high[1:] - PRE_EMPHASIS_COEF * high[:-1])
        low_mag = np.abs(librosa.stft(low, n_fft=N_FFT, hop_length=HOP_LENGTH))
        high_mag = np.abs(librosa.stft(high, n_fft=N_FFT, hop_length=HOP_LENGTH))
        low_mag /= global_max; high_mag /= global_max
        log_low = (np.log10(np.maximum(low_mag, 1e-6)) + 6) / 6
        log_high = (np.log10(np.maximum(high_mag, 1e-6)) + 6) / 6
        x = log_low; y = log_high
        x = torch.from_numpy(x.astype(np.float16)).unsqueeze(0)
        y = torch.from_numpy(y.astype(np.float16)).unsqueeze(0)
        return x, y

    def __len__(self): return self.n_samples
    def __getitem__(self, idx): return self._all_X[idx], self._all_Y[idx]

# ======================== AUGMENTED SUBSET ========================
class AugmentedSubsetV2(Dataset):
    def __init__(self, dataset, indices, augment=True):
        self.dataset = dataset; self.indices = indices; self.augment = augment
    def __len__(self): return len(self.indices)
    def __getitem__(self, idx):
        x, y = self.dataset[self.indices[idx]]
        if self.augment:
            x = x.float(); y = y.float()
            if torch.rand(1) > 0.5:
                noise_level = torch.rand(1) * 0.02
                x = x + torch.randn_like(x) * noise_level
            if torch.rand(1) > 0.5:
                freq_cutoff = torch.randint(128, FREQ_BINS, (1,)).item()
                x[:, freq_cutoff:, :] *= 0.8 + 0.2 * torch.rand(1)
            if torch.rand(1) > 0.5:
                x *= 0.9 + 0.2 * torch.rand(1)
                y *= 0.9 + 0.2 * torch.rand(1)
            x = x.clamp(0, 1); y = y.clamp(0, 1)
            x = x.half(); y = y.half()
        return x, y

# ======================== ВИЗУАЛИЗАЦИЯ ========================
class VisualizationDatasetV2(Dataset):
    def __init__(self, low_res_dir, high_res_dir):
        self.low_files = sorted(Path(low_res_dir).glob("*.wav"))
        self.high_files = sorted(Path(high_res_dir).glob("*.wav"))
        self.global_max = 1.0
        cache_info = CACHE_DIR / "cache_info.txt"
        if cache_info.exists():
            with open(cache_info) as f:
                info = f.read()
                if 'GMAX=' in info:
                    self.global_max = float(info.split('GMAX=')[1])
    def __len__(self): return len(self.low_files)
    def __getitem__(self, idx):
        low, _ = librosa.load(self.low_files[idx], sr=SR)
        high, _ = librosa.load(self.high_files[idx], sr=SR)
        low = np.append(low[0], low[1:] - PRE_EMPHASIS_COEF * low[:-1])
        high = np.append(high[0], high[1:] - PRE_EMPHASIS_COEF * high[:-1])
        low_mag = np.abs(librosa.stft(low, n_fft=N_FFT, hop_length=HOP_LENGTH))
        high_mag = np.abs(librosa.stft(high, n_fft=N_FFT, hop_length=HOP_LENGTH))
        low_mag /= self.global_max; high_mag /= self.global_max
        log_low = (np.log10(np.maximum(low_mag, 1e-6)) + 6) / 6
        log_high = (np.log10(np.maximum(high_mag, 1e-6)) + 6) / 6
        x = torch.from_numpy(log_low.astype(np.float16)).unsqueeze(0)
        y = torch.from_numpy(log_high.astype(np.float16)).unsqueeze(0)
        return x, y

# ======================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ========================
def log_mag_to_linear(log_mag):
    return 10 ** (log_mag * 6 - 6)

def linear_to_log_mag(linear_mag):
    return (torch.log10(linear_mag.clamp(min=1e-6)) + 6) / 6

# ======================== ОБУЧЕНИЕ ========================
def train_epoch(generator, discriminator, loader, opt_g, opt_d, device):
    generator.train(); discriminator.train()
    total_g_loss = 0; total_d_loss = 0
    total_mse_linear = 0

    pbar = tqdm(loader, desc="Train", leave=False)
    for x, y_real_log in pbar:
        x = x.to(device, dtype=torch.float32)
        y_real_log = y_real_log.to(device, dtype=torch.float32)

        # --- Дискриминатор ---
        opt_d.zero_grad()
        with torch.no_grad():
            y_fake_log = generator(x)

        real_preds = discriminator(y_real_log)
        fake_preds = discriminator(y_fake_log)

        d_loss = 0.0
        for rp, fp in zip(real_preds, fake_preds):
            real_target = torch.ones_like(rp) * LABEL_SMOOTHING_REAL
            fake_target = torch.ones_like(fp) * LABEL_SMOOTHING_FAKE
            d_loss += F.mse_loss(rp, real_target) + F.mse_loss(fp, fake_target)

        d_loss.backward()
        torch.nn.utils.clip_grad_norm_(discriminator.parameters(), GRADIENT_CLIP)
        opt_d.step()

        # --- Генератор ---
        opt_g.zero_grad()
        y_fake_log = generator(x)

        fake_preds = discriminator(y_fake_log)
        adv_loss = sum(F.mse_loss(fp, torch.ones_like(fp)) for fp in fake_preds)

        with torch.no_grad():
            real_preds_detached = discriminator(y_real_log)
        fm_loss = sum(F.l1_loss(fp, rp) for fp, rp in zip(fake_preds, real_preds_detached))

        y_fake_linear = log_mag_to_linear(y_fake_log)
        y_real_linear = log_mag_to_linear(y_real_log)

        mse_loss = F.l1_loss(y_fake_linear, y_real_linear)

        std_fake = y_fake_linear.std(dim=3)
        std_real = y_real_linear.std(dim=3)
        tex_loss = (std_fake - std_real).abs().mean()

        g_loss = (LAMBDA_MSE * mse_loss +
                  LAMBDA_ADV * adv_loss +
                  LAMBDA_FM * fm_loss +
                  LAMBDA_TEX * tex_loss)

        g_loss.backward()
        torch.nn.utils.clip_grad_norm_(generator.parameters(), GRADIENT_CLIP)
        opt_g.step()

        total_g_loss += g_loss.item()
        total_d_loss += d_loss.item()
        total_mse_linear += mse_loss.item()

        pbar.set_postfix(
            g=f'{total_g_loss/(pbar.n+1):.3f}',
            d=f'{total_d_loss/(pbar.n+1):.3f}',
            mse_lin=f'{total_mse_linear/(pbar.n+1):.4f}',
            adv=f'{adv_loss.item():.3f}'
        )

    n = len(loader)
    return total_g_loss / n, total_d_loss / n, total_mse_linear / n

@torch.no_grad()
def validate(generator, loader, vis_loader, device):
    generator.eval()
    total_mse_linear = 0
    sample_data = None

    pbar = tqdm(loader, desc="Val", leave=False)
    for i, (x, y_log) in enumerate(pbar):
        x = x.to(device, dtype=torch.float32)
        y_log = y_log.to(device, dtype=torch.float32)

        pred_log = generator(x)

        pred_linear = log_mag_to_linear(pred_log)
        y_linear = log_mag_to_linear(y_log)
        mse = F.mse_loss(pred_linear, y_linear)
        total_mse_linear += mse.item()

        pbar.set_postfix(mse_lin=f'{total_mse_linear/(i+1):.6f}')

    vis_loader_small = DataLoader(vis_loader, batch_size=min(BATCH_SIZE, len(vis_loader)), shuffle=False)
    vis_data = next(iter(vis_loader_small))
    x_vis, y_vis_log = vis_data
    x_vis = x_vis.to(device, dtype=torch.float32)
    pred_vis_log = generator(x_vis).cpu()

    if pred_vis_log.shape[0] >= 3:
        y_vis_linear = log_mag_to_linear(y_vis_log)
        pred_vis_linear = log_mag_to_linear(pred_vis_log)
        err = (pred_vis_linear - y_vis_linear).abs().mean(dim=[1,2,3])
        idx = err.argsort()
        sample_data = (
            x_vis[idx[[0, len(idx)//2, -1]]].cpu(),
            y_vis_log[idx[[0, len(idx)//2, -1]]].cpu(),
            pred_vis_log[idx[[0, len(idx)//2, -1]]].cpu()
        )

    return total_mse_linear / len(loader), sample_data

def save_checkpoint(epoch, g, d, opt_g, opt_d, best_loss, path):
    torch.save({
        'epoch': epoch,
        'g_state_dict': g.state_dict(),
        'd_state_dict': d.state_dict(),
        'opt_g': opt_g.state_dict(),
        'opt_d': opt_d.state_dict(),
        'best_loss': best_loss
    }, path)

def load_checkpoint(path, g, d, opt_g, opt_d, device):
    ckpt = torch.load(path, map_location=device, weights_only=False)
    g.load_state_dict(ckpt['g_state_dict']); d.load_state_dict(ckpt['d_state_dict'])
    opt_g.load_state_dict(ckpt['opt_g']); opt_d.load_state_dict(ckpt['opt_d'])
    return ckpt.get('epoch', 0), ckpt.get('best_loss', float('inf'))

# ======================== ВИЗУАЛИЗАЦИЯ ========================
def plot_dashboard(epoch, g_losses, d_losses, val_mses, lr_history, sample_data, save_dir):
    if sample_data is None: return
    inp, full_high_log, pred_log = sample_data
    num = min(inp.shape[0], 2)
    fig = plt.figure(figsize=(24, 16))

    for i, (label, data) in enumerate([
        ('G Loss', g_losses), ('D Loss', d_losses), ('Val MSE (linear)', val_mses), ('Info', None)
    ]):
        ax = plt.subplot(4, 4, i+1)
        if i < 3:
            ax.plot(data, 'o-', markersize=3)
            ax.set_title(label)
            ax.grid(alpha=0.3)
        else:
            ax.axis('off')
            ax.text(0.1, 0.9,
                    f"Epoch: {epoch+1}\n"
                    f"G: {g_losses[-1]:.3f}\n"
                    f"D: {d_losses[-1]:.3f}\n"
                    f"Val MSE lin: {val_mses[-1]:.6f}\n"
                    f"LR: {lr_history[-1]:.2e}\n"
                    f"MP3 128 → Lossless",
                    fontsize=8, fontfamily='monospace', verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    names = ['BEST', 'MEDIAN']
    for s in range(num):
        inp_lin = log_mag_to_linear(inp[s, 0])
        full_high_lin = log_mag_to_linear(full_high_log[s, 0])
        pred_lin = log_mag_to_linear(pred_log[s, 0])

        min_t = min(inp_lin.shape[1], full_high_lin.shape[1], pred_lin.shape[1])
        inp_np = inp_lin[:, :min_t].numpy()
        full_high_np = full_high_lin[:, :min_t].numpy()
        pred_np = pred_lin[:, :min_t].numpy()

        inp_display = np.log10(np.maximum(inp_np, 1e-6))
        full_high_display = np.log10(np.maximum(full_high_np, 1e-6))
        pred_display = np.log10(np.maximum(pred_np, 1e-6))
        diff_display = np.abs(pred_np - full_high_np)

        base_idx = 4 * (s + 2)
        vmin, vmax = -6, 0

        for col, (data, title, cmap, vmin_c, vmax_c) in enumerate([
            (inp_display, f'[{names[s]}] MP3 Input (dB)', 'viridis', vmin, vmax),
            (full_high_display, 'Target Lossless (dB)', 'viridis', vmin, vmax),
            (pred_display, 'Predicted (dB)', 'viridis', vmin, vmax),
            (diff_display, 'Error (linear)', 'hot', 0, 0.1)
        ]):
            ax = plt.subplot(4, 4, base_idx + col + 1)
            im = ax.imshow(data, aspect='auto', origin='lower', cmap=cmap,
                          vmin=vmin_c, vmax=vmax_c)
            ax.set_title(title, fontsize=7)
            plt.colorbar(im, ax=ax, fraction=0.046)

    plt.tight_layout()
    plt.savefig(save_dir / f"dashboard_epoch_{epoch+1:03d}.png", dpi=150)
    plt.savefig(save_dir / "dashboard_latest.png", dpi=150)
    plt.close()

# ======================== MAIN ========================
if __name__ == "__main__":
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)

    print(f"╔══════════════════════════════════════╗")
    print(f"║  MP3 Restorer v2 — FIXED           ║")
    print(f"║  Direct Hi-Res with Linear Loss    ║")
    print(f"╚══════════════════════════════════════╝")
    print(f"   Вход: спектр MP3 128kbps (0-22k)")
    print(f"   Выход: lossless спектр")
    print(f"   Лосс: L1 в линейной магнитуде")
    print()

    print(f"→ Device: {DEVICE}")
    if DEVICE.type == "cuda":
        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    print("\n📦 Загрузка датасета...")
    full_dataset = MP3DatasetV2(LOW_RES_DIR, HIGH_RES_DIR)
    vis_dataset = VisualizationDatasetV2(LOW_RES_DIR, HIGH_RES_DIR)

    val_size = int(len(full_dataset) * VAL_SPLIT)
    train_size = len(full_dataset) - val_size
    indices = torch.randperm(len(full_dataset), generator=torch.Generator().manual_seed(42)).tolist()

    train_ds = AugmentedSubsetV2(full_dataset, indices[:train_size])
    val_ds = AugmentedSubsetV2(full_dataset, indices[train_size:], augment=False)
    train_loader = DataLoader(train_ds, BATCH_SIZE, shuffle=True, num_workers=NUM_WORKERS,
                             pin_memory=True, drop_last=True)
    val_loader = DataLoader(val_ds, BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS,
                           pin_memory=True)
    print(f"   Train: {train_size} | Val: {val_size}")
    print(f"   Batches: {len(train_loader)} train | {len(val_loader)} val")

    generator = MP3RestorerV2().to(DEVICE)
    discriminator = MultiScaleDiscriminator().to(DEVICE)
    print(f"\n🔧 Модели:")
    print(f"   Generator: {sum(p.numel() for p in generator.parameters()):,} params")
    print(f"   Discriminator: {sum(p.numel() for p in discriminator.parameters()):,} params")

    opt_g = torch.optim.AdamW(generator.parameters(), lr=LEARNING_RATE_G, betas=(0.5, 0.999))
    opt_d = torch.optim.AdamW(discriminator.parameters(), lr=LEARNING_RATE_D, betas=(0.5, 0.999))
    sched_g = torch.optim.lr_scheduler.CosineAnnealingLR(opt_g, T_max=EPOCHS, eta_min=1e-6)
    sched_d = torch.optim.lr_scheduler.CosineAnnealingLR(opt_d, T_max=EPOCHS, eta_min=1e-6)

    start_epoch, best_loss = 0, float('inf')
    if os.path.exists(CHECKPOINT_FILE):
        start_epoch, best_loss = load_checkpoint(CHECKPOINT_FILE, generator, discriminator,
                                                 opt_g, opt_d, DEVICE)
        print(f"\n📂 Загрузка чекпоинта: эпоха {start_epoch}, best MSE {best_loss:.6f}")
    else:
        print("\n🆕 Обучение с нуля")

    print(f"\n⚙️  Параметры обучения:")
    print(f"   LR G: {LEARNING_RATE_G:.0e} | LR D: {LEARNING_RATE_D:.0e}")
    print(f"   LAMBDA_MSE: {LAMBDA_MSE} | LAMBDA_ADV: {LAMBDA_ADV}")
    print(f"   LAMBDA_FM: {LAMBDA_FM} | LAMBDA_TEX: {LAMBDA_TEX}")
    print(f"   Label Smoothing: {LABEL_SMOOTHING_REAL}/{LABEL_SMOOTHING_FAKE}")
    print(f"   Noise D: {NOISE_STD_D}")
    print(f"\n{'='*60}")

    g_losses, d_losses, val_mses, lr_history = [], [], [], []
    no_improve = 0

    for epoch in range(start_epoch, EPOCHS):
        print(f"\n--- Epoch {epoch+1}/{EPOCHS} ---")

        g_loss, d_loss, train_mse_linear = train_epoch(
            generator, discriminator, train_loader, opt_g, opt_d, DEVICE
        )
        val_mse_linear, sample_data = validate(
            generator, val_loader, vis_dataset, DEVICE
        )

        sched_g.step()
        sched_d.step()

        g_losses.append(g_loss)
        d_losses.append(d_loss)
        val_mses.append(val_mse_linear)
        lr_history.append(opt_g.param_groups[0]['lr'])

        print(f"   G: {g_loss:.3f} | D: {d_loss:.3f}")
        print(f"   Train MSE (linear): {train_mse_linear:.6f}")
        print(f"   Val MSE (linear):   {val_mse_linear:.6f} | LR: {opt_g.param_groups[0]['lr']:.2e}")

        if val_mse_linear < best_loss:
            best_loss = val_mse_linear
            no_improve = 0
            torch.save(generator.state_dict(), BEST_MODEL_FILE)
            print(f"   ✓ Лучшая модель (Val MSE={best_loss:.6f})")
        else:
            no_improve += 1
            print(f"   · Нет улучшения ({no_improve}/{EARLY_STOP_PATIENCE})")

        save_checkpoint(epoch+1, generator, discriminator, opt_g, opt_d, best_loss, CHECKPOINT_FILE)

        plot_dashboard(epoch, g_losses, d_losses, val_mses, lr_history, 
                    sample_data, REPORTS_DIR)

        if no_improve >= EARLY_STOP_PATIENCE:
            print(f"\n⏹️  Ранняя остановка на эпохе {epoch+1}")
            break

        if DEVICE.type == "cuda" and (epoch + 1) % 10 == 0:
            torch.cuda.empty_cache()
            gc.collect()

    print(f"\n{'='*60}")
    print(f"🏁 Обучение завершено!")
    print(f"   Лучшая Val MSE (linear): {best_loss:.6f}")
    print(f"   Модель сохранена: {BEST_MODEL_FILE}")
    print(f"   Дашборды: {REPORTS_DIR}")

    if sample_data is not None:
        plot_dashboard(EPOCHS-1, g_losses, d_losses, val_mses, lr_history,
                      sample_data, REPORTS_DIR)
        print(f"   Финальный дашборд сохранён")
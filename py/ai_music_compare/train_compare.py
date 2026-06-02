"""
train_compare.py
Обучение AudioCompareNet с регрессией (предсказание similarity 0..1).
Поддерживает обучение с нуля и дообучение на разных датасетах.
С EWC (Elastic Weight Consolidation) для сохранения знаний при дообучении.
С кешированием датасета в .pt для быстрой загрузки.

Использование:
  python train_compare.py --dataset spectrograms_mp3
  python train_compare.py --dataset spectrograms_aac --pretrained compare_model.pth
"""

import os
import sys
import argparse
import pickle
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
from tqdm import tqdm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import torchaudio
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
import warnings
warnings.filterwarnings('ignore')

# ========== НАСТРОЙКИ ==========
BATCH_SIZE = 128
EPOCHS = 14
LEARNING_RATE = 0.001
WEIGHT_DECAY = 1e-4
VAL_SPLIT = 0.15
EARLY_STOPPING_PATIENCE = 20

# EWC
EWC_LAMBDA = 5000

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
NUM_WORKERS = 2


# ========== ДАТАСЕТ ==========
class PairDataset(Dataset):
    def __init__(self, specs_a, specs_b, labels, augment=False):
        self.specs_a = specs_a
        self.specs_b = specs_b
        self.labels = labels  # непрерывные similarity 0..1
        self.augment = augment
    
    def __len__(self):
        return len(self.specs_a)
    
    def __getitem__(self, idx):
        spec_a = self.specs_a[idx]
        spec_b = self.specs_b[idx]
        label = self.labels[idx]
        
        if self.augment:
            if torch.rand(1) > 0.5:
                spec_a = torchaudio.transforms.FrequencyMasking(16)(spec_a)
            if torch.rand(1) > 0.5:
                spec_b = torchaudio.transforms.FrequencyMasking(16)(spec_b)
            if torch.rand(1) > 0.7:
                spec_a += torch.randn_like(spec_a) * 0.01
                spec_b += torch.randn_like(spec_b) * 0.01
        
        return spec_a, spec_b, label


# ========== МОДЕЛЬ ==========
class SEBlock(nn.Module):
    def __init__(self, channels, reduction=16):
        super().__init__()
        self.fc = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(channels, channels // reduction),
            nn.ReLU(),
            nn.Linear(channels // reduction, channels),
            nn.Sigmoid()
        )
    
    def forward(self, x):
        b, c, _, _ = x.shape
        return x * self.fc(x).view(b, c, 1, 1)


class AudioEncoder(nn.Module):
    def __init__(self, in_channels=1):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(in_channels, 32, 3, padding=1),
            nn.BatchNorm2d(32), nn.ReLU(), SEBlock(32),
            nn.MaxPool2d(2), nn.Dropout2d(0.1),
            
            nn.Conv2d(32, 64, 3, padding=1),
            nn.BatchNorm2d(64), nn.ReLU(), SEBlock(64),
            nn.MaxPool2d(2), nn.Dropout2d(0.2),
            
            nn.Conv2d(64, 128, 3, padding=1),
            nn.BatchNorm2d(128), nn.ReLU(), SEBlock(128),
            nn.MaxPool2d(2), nn.Dropout2d(0.3),
            
            nn.Conv2d(128, 256, 3, padding=1),
            nn.BatchNorm2d(256), nn.ReLU(), SEBlock(256),
            nn.AdaptiveAvgPool2d((4, 4)),
        )
        self.embedding_dim = 256 * 4 * 4
    
    def forward(self, x):
        return self.features(x)


class AudioCompareNet(nn.Module):
    """Регрессия: предсказывает similarity 0..1."""
    def __init__(self, in_channels=1):
        super().__init__()
        self.encoder = AudioEncoder(in_channels)
        embed_dim = self.encoder.embedding_dim
        
        self.regressor = nn.Sequential(
            nn.Linear(embed_dim * 3, 512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid()
        )
    
    def forward(self, spec_a, spec_b):
        emb_a = self.encoder(spec_a).flatten(1)
        emb_b = self.encoder(spec_b).flatten(1)
        diff = torch.abs(emb_a - emb_b)
        combined = torch.cat([emb_a, emb_b, diff], dim=1)
        return self.regressor(combined)


# ========== ЗАГРУЗКА ДАННЫХ ==========
def load_dataset(dataset_dir):
    """Загружает датасет, используя .pt кеш для ускорения."""
    cache_path = os.path.join(dataset_dir, 'cached_dataset.pt')
    
    if os.path.exists(cache_path):
        print("  Загрузка из кеша (.pt)...")
        cached = torch.load(cache_path, map_location='cpu', weights_only=False)
        specs_a = cached['specs_a']
        specs_b = cached['specs_b']
        labels = cached['labels']
        meta = cached['meta']
        # Убедимся, что labels имеет правильную форму (N, 1)
        if labels.dim() == 1:
            labels = labels.unsqueeze(1)
        print(f"  ✓ Загружено за {cached.get('load_time', '?')} сек")
    else:
        print("  Загрузка из .npy и создание кеша...")
        import time
        t_start = time.time()
        
        specs_a_np = np.load(os.path.join(dataset_dir, 'specs_a.npy'), mmap_mode='r')
        specs_b_np = np.load(os.path.join(dataset_dir, 'specs_b.npy'), mmap_mode='r')
        similarities_np = np.load(os.path.join(dataset_dir, 'similarities.npy'), mmap_mode='r')
        
        with open(os.path.join(dataset_dir, 'meta.pkl'), 'rb') as f:
            meta = pickle.load(f)
        
        specs_a = torch.from_numpy(specs_a_np.copy()).float()
        del specs_a_np
        
        specs_b = torch.from_numpy(specs_b_np.copy()).float()
        del specs_b_np
        
        # Важно: форма (N, 1) для совместимости с MSELoss
        labels = torch.from_numpy(similarities_np.copy()).float().unsqueeze(1)
        del similarities_np
        
        load_time = time.time() - t_start
        
        print(f"  Сохранение кеша ({specs_a.nbytes / 1024**3:.1f} + {specs_b.nbytes / 1024**3:.1f} ГБ)...")
        torch.save({
            'specs_a': specs_a,
            'specs_b': specs_b,
            'labels': labels,
            'meta': meta,
            'load_time': f"{load_time:.1f}",
        }, cache_path)
        print(f"  ✓ Кеш сохранён: {cache_path} ({load_time:.1f} сек)")
    
    return specs_a, specs_b, labels, meta


# ========== ОБУЧЕНИЕ ==========
def train_epoch(model, loader, criterion, optimizer, device, 
                pretrained_weights=None, ewc_lambda=0):
    model.train()
    total_loss = 0
    
    for spec_a, spec_b, labels in tqdm(loader, desc="Train", leave=False):
        spec_a = spec_a.to(device, non_blocking=True)
        spec_b = spec_b.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        
        optimizer.zero_grad()
        outputs = model(spec_a, spec_b)
        loss = criterion(outputs, labels)
        
        # EWC-штраф
        if pretrained_weights is not None and ewc_lambda > 0:
            ewc_loss = 0
            for name, param in model.named_parameters():
                if name in pretrained_weights:
                    ewc_loss += torch.sum((param - pretrained_weights[name]) ** 2)
            loss = loss + ewc_lambda * ewc_loss
        
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item()
    
    return total_loss / len(loader)


@torch.no_grad()
def validate(model, loader, criterion, device):
    model.eval()
    total_loss = 0
    all_preds = []
    all_labels = []
    
    for spec_a, spec_b, labels in loader:
        spec_a = spec_a.to(device, non_blocking=True)
        spec_b = spec_b.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        
        outputs = model(spec_a, spec_b)
        loss = criterion(outputs, labels)
        total_loss += loss.item()
        
        # outputs и labels имеют форму (batch, 1)
        # Преобразуем в 1D для метрик
        all_preds.append(outputs.cpu().numpy())
        all_labels.append(labels.cpu().numpy())
    
    # Конкатенируем батчи
    all_preds = np.concatenate(all_preds).flatten()
    all_labels = np.concatenate(all_labels).flatten()
    
    mse = mean_squared_error(all_labels, all_preds)
    mae = mean_absolute_error(all_labels, all_preds)
    r2 = r2_score(all_labels, all_preds)
    
    return total_loss / len(loader), mse, mae, r2, all_preds, all_labels


def save_checkpoint(epoch, model, optimizer, scheduler, best_loss, 
                    pretrained_weights, ewc_lambda, path):
    torch.save({
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict() if scheduler else {},
        'best_loss': best_loss,
        'pretrained_weights': pretrained_weights,
        'ewc_lambda': ewc_lambda,
    }, path)


def load_checkpoint(path, model, optimizer, scheduler, device):
    ckpt = torch.load(path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt['model_state_dict'])
    optimizer.load_state_dict(ckpt['optimizer_state_dict'])
    if scheduler and 'scheduler_state_dict' in ckpt and ckpt['scheduler_state_dict']:
        scheduler.load_state_dict(ckpt['scheduler_state_dict'])
    pretrained_weights = ckpt.get('pretrained_weights', None)
    ewc_lambda = ckpt.get('ewc_lambda', 0)
    return ckpt['epoch'], ckpt['best_loss'], pretrained_weights, ewc_lambda


# ========== ВИЗУАЛИЗАЦИЯ ==========
def save_epoch_plot(epoch, all_preds, all_labels, mse, mae, r2, 
                    train_loss, val_loss, lr, save_path, dataset_name=""):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    # Scatter plot
    ax1.scatter(all_labels, all_preds, alpha=0.3, s=1, c='blue', label='Predictions')
    ax1.plot([0, 1], [0, 1], 'r--', linewidth=2, label='Идеал')
    ax1.set_xlabel('Real similarity')
    ax1.set_ylabel('Predicted similarity')
    ax1.set_title(f'Epoch {epoch} | R²={r2:.4f} | MAE={mae:.4f}',
                  fontsize=12, fontweight='bold')
    ax1.legend()
    ax1.set_xlim(0, 1)
    ax1.set_ylim(0, 1)
    ax1.grid(True, alpha=0.3)
    
    # Распределение ошибок
    errors = all_preds - all_labels
    ax2.hist(errors, bins=50, color='steelblue', edgecolor='white', alpha=0.8)
    ax2.axvline(0, color='red', linestyle='--', linewidth=2)
    ax2.set_xlabel('Ошибка (pred - real)')
    ax2.set_ylabel('Количество')
    ax2.set_title(f'Распределение ошибок | MSE={mse:.4f}',
                  fontsize=12, fontweight='bold')
    
    info = (
        f"{dataset_name} — Epoch {epoch}\n"
        f"{'─'*30}\n"
        f"Train Loss:  {train_loss:.4f}\n"
        f"Val Loss:    {val_loss:.4f}\n"
        f"Val MSE:     {mse:.4f}\n"
        f"Val MAE:     {mae:.4f}\n"
        f"Val R²:      {r2:.4f}\n"
        f"LR:          {lr:.6f}\n"
    )
    
    ax2.text(0.02, 0.98, info, transform=ax2.transAxes,
            fontsize=9, verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='#F5F5F5', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=120, bbox_inches='tight')
    plt.close()


def save_training_curves(history, save_path, dataset_name=""):
    epochs = range(1, len(history['train_loss']) + 1)
    
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 4))
    
    ax1.plot(epochs, history['train_loss'], 'b-', label='Train', linewidth=1.5)
    ax1.plot(epochs, history['val_loss'], 'r-', label='Val', linewidth=1.5)
    ax1.set_xlabel('Epoch')
    ax1.set_ylabel('MSE Loss')
    ax1.set_title(f'Loss — {dataset_name}', fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    if len(history['val_loss']) > 0:
        best_epoch = np.argmin(history['val_loss']) + 1
        best_loss = history['val_loss'][best_epoch - 1]
        ax1.plot(best_epoch, best_loss, 'r*', markersize=12, label=f'Best: {best_loss:.4f}')
        ax1.legend()
    
    ax2.plot(epochs, history['val_r2'], 'g-', label='Val R²', linewidth=1.5)
    ax2.plot(epochs, history['val_mae'], 'orange', label='Val MAE', linewidth=1.5)
    ax2.set_xlabel('Epoch')
    ax2.set_ylabel('Score')
    ax2.set_title(f'Metrics — {dataset_name}', fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    ax3.plot(epochs, history['lr'], 'g-', linewidth=2)
    ax3.set_xlabel('Epoch')
    ax3.set_ylabel('LR')
    ax3.set_title('Learning Rate', fontweight='bold')
    ax3.set_yscale('log')
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=120, bbox_inches='tight')
    plt.close()


# ========== ГЛАВНАЯ ==========
def main():
    parser = argparse.ArgumentParser(description="Train AudioCompareNet (Regression)")
    parser.add_argument("--dataset", type=str, required=True,
                        help="Path to dataset directory (e.g. spectrograms_mp3)")
    parser.add_argument("--pretrained", type=str, default=None,
                        help="Path to pretrained model for fine-tuning with EWC")
    parser.add_argument("--ewc-lambda", type=float, default=EWC_LAMBDA,
                        help=f"EWC regularization strength (default: {EWC_LAMBDA})")
    parser.add_argument("--no-cache", action="store_true",
                        help="Force recreate cache from .npy files")
    args = parser.parse_args()
    
    dataset_dir = args.dataset
    pretrained_path = args.pretrained
    is_finetune = pretrained_path is not None
    ewc_lambda = args.ewc_lambda if is_finetune else 0
    
    dataset_name = os.path.basename(dataset_dir)
    checkpoint_file = f"checkpoint_{dataset_name}.pth"
    best_model_file = "compare_model.pth"
    
    if args.no_cache:
        cache_path = os.path.join(dataset_dir, 'cached_dataset.pt')
        if os.path.exists(cache_path):
            os.remove(cache_path)
            print(f"  Кеш удалён: {cache_path}")
    
    print("=" * 60)
    print(f"TRAIN — AudioCompareNet Regression ({dataset_name})")
    if is_finetune:
        print(f"  Дообучение из: {pretrained_path}")
        print(f"  EWC lambda: {ewc_lambda}")
    print("=" * 60)
    print(f"  Device: {DEVICE}")
    if DEVICE.type == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
        print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} ГБ")
    
    print(f"\n→ Загрузка данных из '{dataset_dir}'...")
    specs_a, specs_b, labels, meta = load_dataset(dataset_dir)
    
    print(f"  Кодек: {meta.get('codec', 'unknown')}")
    print(f"  Классов: {len(meta['class_names'])}")
    print(f"  Сегментов: {len(specs_a):,}")
    print(f"  Размер в RAM: ~{(specs_a.nbytes + specs_b.nbytes + labels.nbytes) / 1024**3:.1f} ГБ")
    
    print(f"\n  Статистика similarity:")
    sims = labels.numpy().flatten()
    print(f"    Min: {sims.min():.3f}")
    print(f"    Max: {sims.max():.3f}")
    print(f"    Mean: {sims.mean():.3f}")
    print(f"    Median: {np.median(sims):.3f}")
    print(f"    Std: {sims.std():.3f}")
    
    print("\n→ Создание датасетов...")
    dataset = PairDataset(specs_a, specs_b, labels)
    
    total_len = len(dataset)
    val_len = int(total_len * VAL_SPLIT)
    test_len = val_len
    train_len = total_len - val_len - test_len
    
    train_ds, val_ds, test_ds = random_split(
        dataset, [train_len, val_len, test_len],
        generator=torch.Generator().manual_seed(42)
    )
    
    print(f"  Train: {train_len:,}, Val: {val_len:,}, Test: {test_len:,}")
    
    train_loader = DataLoader(train_ds, BATCH_SIZE, shuffle=True, num_workers=NUM_WORKERS, pin_memory=True)
    val_loader = DataLoader(val_ds, BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS, pin_memory=True)
    test_loader = DataLoader(test_ds, BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS, pin_memory=True)
    
    print("\n→ Создание модели...")
    in_channels = meta.get('channels', 1)
    model = AudioCompareNet(in_channels=in_channels).to(DEVICE)
    
    pretrained_weights = None
    
    if is_finetune:
        print(f"  Загрузка весов из {pretrained_path}...")
        model.load_state_dict(torch.load(pretrained_path, map_location=DEVICE, weights_only=False))
        
        pretrained_weights = {}
        for name, param in model.named_parameters():
            pretrained_weights[name] = param.data.clone().to(DEVICE)
        print(f"  EWC: сохранено {len(pretrained_weights)} параметров")
    
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  Всего параметров: {total_params:,}")
    print(f"  Обучаемых: {trainable_params:,}")
    
    criterion = nn.MSELoss()
    
    lr = LEARNING_RATE
    if is_finetune:
        lr = LEARNING_RATE * 0.1
    
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=WEIGHT_DECAY)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', patience=5, factor=0.5)
    
    start_epoch = 0
    best_loss = float('inf')
    patience_counter = 0
    
    if os.path.exists(checkpoint_file):
        print(f"\n→ Найден чекпойнт: {checkpoint_file}")
        start_epoch, best_loss, saved_weights, saved_ewc = load_checkpoint(
            checkpoint_file, model, optimizer, scheduler, DEVICE
        )
        if saved_weights is not None:
            pretrained_weights = saved_weights
        if saved_ewc > 0:
            ewc_lambda = saved_ewc
        print(f"  Восстановлен с эпохи {start_epoch}, best_loss: {best_loss:.6f}")
    else:
        print(f"\n→ Обучение {'с нуля' if not is_finetune else '(дообучение с EWC)'}")
    
    plots_dir = f"epoch_plots_{dataset_name}"
    os.makedirs(plots_dir, exist_ok=True)
    
    history = {
        'train_loss': [],
        'val_loss': [],
        'val_mse': [],
        'val_mae': [],
        'val_r2': [],
        'lr': []
    }
    
    print(f"\n→ Обучение: {start_epoch + 1}–{EPOCHS} эпох (LR={lr}, EWC={ewc_lambda})")
    print(f"{'Epoch':<8} {'Train Loss':<12} {'Val Loss':<12} {'Val MAE':<10} {'Val R²':<10} {'LR':<10} {'Best':<10}")
    print("-" * 72)
    
    for epoch in range(start_epoch, EPOCHS):
        train_ds.dataset.augment = True
        train_loss = train_epoch(
            model, train_loader, criterion, optimizer, DEVICE,
            pretrained_weights, ewc_lambda
        )
        train_ds.dataset.augment = False
        
        val_loss, val_mse, val_mae, val_r2, val_preds, val_labels = validate(
            model, val_loader, criterion, DEVICE
        )
        
        scheduler.step(val_loss)
        current_lr = optimizer.param_groups[0]['lr']
        
        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        history['val_mse'].append(val_mse)
        history['val_mae'].append(val_mae)
        history['val_r2'].append(val_r2)
        history['lr'].append(current_lr)
        
        improved = "✓" if val_loss < best_loss else ""
        
        print(f"{epoch+1:<8} {train_loss:<12.4f} {val_loss:<12.4f} {val_mae:<10.4f} {val_r2:<10.4f} {current_lr:<10.6f} {improved:<10}")
        
        if val_loss < best_loss:
            best_loss = val_loss
            patience_counter = 0
            torch.save(model.state_dict(), best_model_file)
            
            plot_path = os.path.join(plots_dir, f"best_epoch_{epoch+1:03d}.png")
            save_epoch_plot(
                epoch + 1, val_preds, val_labels, val_mse, val_mae, val_r2,
                train_loss, val_loss, current_lr,
                plot_path, dataset_name
            )
        else:
            patience_counter += 1
        
        save_checkpoint(epoch + 1, model, optimizer, scheduler, best_loss,
                       pretrained_weights, ewc_lambda, checkpoint_file)
        
        if patience_counter >= EARLY_STOPPING_PATIENCE:
            print(f"\n  Early stopping после {EARLY_STOPPING_PATIENCE} эпох без улучшений")
            break
    
    print(f"\n→ Сохранение кривых обучения...")
    curves_path = os.path.join(plots_dir, "learning_curves_final.png")
    save_training_curves(history, curves_path, dataset_name)
    print(f"  ✓ {curves_path}")
    
    # ===== ТЕСТ =====
    print(f"\n{'='*60}")
    print(f"ФИНАЛЬНЫЙ ТЕСТ — {dataset_name}")
    print("=" * 60)
    
    model.load_state_dict(torch.load(best_model_file, map_location=DEVICE, weights_only=False))
    model.eval()
    
    all_preds = []
    all_labels = []
    test_loss = 0
    
    for spec_a, spec_b, labels in tqdm(test_loader, desc="Test"):
        spec_a = spec_a.to(DEVICE, non_blocking=True)
        spec_b = spec_b.to(DEVICE, non_blocking=True)
        labels = labels.to(DEVICE, non_blocking=True)
        
        with torch.no_grad():
            outputs = model(spec_a, spec_b)
            loss = criterion(outputs, labels)
            test_loss += loss.item()
        
        all_preds.extend(outputs.cpu().numpy().flatten())
        all_labels.extend(labels.cpu().numpy().flatten())
    
    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    
    test_mse = mean_squared_error(all_labels, all_preds)
    test_mae = mean_absolute_error(all_labels, all_preds)
    test_r2 = r2_score(all_labels, all_preds)
    
    print(f"\nTest MSE: {test_mse:.6f}")
    print(f"Test MAE: {test_mae:.4f}")
    print(f"Test R²: {test_r2:.4f}")
    
    # Сохраняем отчёт
    report_path = f'test_report_{dataset_name}.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"TEST REPORT — {dataset_name}\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"Test MSE: {test_mse:.6f}\n")
        f.write(f"Test MAE: {test_mae:.4f}\n")
        f.write(f"Test R²: {test_r2:.4f}\n\n")
        f.write(f"Model: {best_model_file}\n")
        f.write(f"Total params: {total_params:,}\n")
    
    print(f"\n  ✓ {report_path} сохранён")
    print(f"\n✓ Модель сохранена: {best_model_file}")
    print(f"  Чекпойнт: {checkpoint_file}")
    print(f"  Кривые обучения: {curves_path}")
    print("Готово!")


if __name__ == "__main__":
    main()
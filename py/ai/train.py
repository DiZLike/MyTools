import os
import numpy as np
import pickle
import torch
import torch.nn as nn
import torch.optim as optim
import torchaudio
from torch.utils.data import Dataset, DataLoader, random_split
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

print("→ Импорты OK")

# ========== 1. Датасет со SpecAugment ==========
class SpecDataset(Dataset):
    def __init__(self, specs, labels, augment=False):
        self.specs = torch.FloatTensor(specs).unsqueeze(1)
        self.labels = torch.LongTensor(labels)
        self.augment = augment

    def __len__(self):
        return len(self.specs)

    def __getitem__(self, idx):
        spec = self.specs[idx]
        label = self.labels[idx]

        if self.augment:
            if torch.rand(1) > 0.5:
                spec = torchaudio.transforms.FrequencyMasking(16)(spec)
            if torch.rand(1) > 0.5:
                spec = torchaudio.transforms.TimeMasking(32)(spec)
            if torch.rand(1) > 0.7:
                spec += torch.randn_like(spec) * 0.01
            if torch.rand(1) > 0.7:
                shift = torch.randint(-15, 15, (1,)).item()
                spec = torch.roll(spec, shifts=shift, dims=-1)

        return spec, label


# ========== 2. SE-блок ==========
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


# ========== 3. Модель ==========
class DualHeadCNN(nn.Module):
    def __init__(self, num_lossy):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1),
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
        self.head_lossless = nn.Sequential(
            nn.Flatten(), nn.Linear(4096, 128), nn.ReLU(), nn.Dropout(0.3), nn.Linear(128, 2)
        )
        self.head_codec = nn.Sequential(
            nn.Flatten(), nn.Linear(4096, 256), nn.ReLU(), nn.Dropout(0.4),
            nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.3), nn.Linear(128, num_lossy)
        )

    def forward(self, x):
        f = self.features(x)
        return self.head_lossless(f), self.head_codec(f)


# ========== 4. Утилиты ==========
def convert_labels(labels, device):
    bin_lbl = (labels == 0).long()
    codec_lbl = labels.clone() - 1
    codec_lbl[labels == 0] = -1
    return bin_lbl.to(device), codec_lbl.to(device)


def train_epoch(model, loader, crit_bin, crit_codec, opt, device, alpha=0.2):
    model.train()
    total_loss = corr_bin = corr_codec = total_bin = total_codec = 0
    for specs, labels in tqdm(loader, desc="Train", leave=False):
        specs = specs.to(device)
        bin_lbl, codec_lbl = convert_labels(labels, device)

        opt.zero_grad()
        out_bin, out_codec = model(specs)
        loss_bin = crit_bin(out_bin, bin_lbl)

        mask = codec_lbl >= 0
        loss_codec = crit_codec(out_codec[mask], codec_lbl[mask]) if mask.any() else torch.tensor(0.0, device=device)
        (alpha * loss_bin + (1 - alpha) * loss_codec).backward()
        opt.step()

        total_loss += loss_bin.item() * alpha + (loss_codec.item() if mask.any() else 0) * (1 - alpha)
        pred_bin = out_bin.argmax(1)
        corr_bin += pred_bin.eq(bin_lbl).sum().item()
        total_bin += bin_lbl.size(0)
        if mask.any():
            corr_codec += out_codec[mask].argmax(1).eq(codec_lbl[mask]).sum().item()
            total_codec += mask.sum().item()

    return total_loss / len(loader), 100 * corr_bin / total_bin, 100 * corr_codec / total_codec if total_codec else 0


@torch.no_grad()
def validate(model, loader, crit_bin, crit_codec, device, alpha=0.2):
    model.eval()
    total_loss = corr_bin = corr_codec = total_bin = total_codec = 0
    all_preds, all_labels = [], []
    for specs, labels in loader:
        specs = specs.to(device)
        bin_lbl, codec_lbl = convert_labels(labels, device)
        out_bin, out_codec = model(specs)
        loss_bin = crit_bin(out_bin, bin_lbl)
        mask = codec_lbl >= 0
        loss_codec = crit_codec(out_codec[mask], codec_lbl[mask]) if mask.any() else torch.tensor(0.0, device=device)
        total_loss += loss_bin.item() * alpha + (loss_codec.item() if mask.any() else 0) * (1 - alpha)

        pred_bin = out_bin.argmax(1)
        corr_bin += pred_bin.eq(bin_lbl).sum().item()
        total_bin += bin_lbl.size(0)
        if mask.any():
            corr_codec += out_codec[mask].argmax(1).eq(codec_lbl[mask]).sum().item()
            total_codec += mask.sum().item()

        final = torch.zeros_like(labels, device=device)
        final[pred_bin == 1] = 0
        lossy_mask = pred_bin == 0
        if lossy_mask.any():
            final[lossy_mask] = out_codec[lossy_mask].argmax(1) + 1
        all_preds.extend(final.cpu().numpy())
        all_labels.extend(labels.cpu().numpy())

    return total_loss / len(loader), 100 * corr_bin / total_bin, 100 * corr_codec / total_codec if total_codec else 0, all_preds, all_labels


def save_checkpoint(epoch, model, opt, sched, best_acc, path):
    torch.save({
        'epoch': epoch, 'model_state_dict': model.state_dict(),
        'optimizer_state_dict': opt.state_dict(),
        'scheduler_state_dict': sched.state_dict(), 'best_acc': best_acc
    }, path)


def load_checkpoint(path, model, opt, sched, device):
    ckpt = torch.load(path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt['model_state_dict'])
    opt.load_state_dict(ckpt['optimizer_state_dict'])
    sched.load_state_dict(ckpt['scheduler_state_dict'])
    return ckpt['epoch'], ckpt['best_acc']


# ========== 5. Запуск ==========
if __name__ == "__main__":
    EPOCHS = 60
    CHECKPOINT_FILE = "checkpoint_latest.pth"
    BEST_MODEL_FILE = "best_model.pth"

    lossy_names = [
        "mp3_32", "mp3_64", "mp3_128", "mp3_high",
        "aac_64", "aac_high",
        "opus_32", "opus_64", "opus_96", "opus_high"
    ]
    all_names = ["lossless"] + lossy_names
    num_lossy = len(lossy_names)

    print("→ Загружаю данные...")
    specs = np.load("spectrograms/spectrograms.npy")
    labels = np.load("spectrograms/labels.npy")
    print(f"  Спектрограмм: {specs.shape[0]:,}, классов: {len(all_names)}")

    print("→ Создаю датасеты...")
    dataset = SpecDataset(specs, labels)
    train_size = int(0.7 * len(dataset))
    val_size = int(0.15 * len(dataset))
    test_size = len(dataset) - train_size - val_size
    train_ds, val_ds, test_ds = random_split(
        dataset, [train_size, val_size, test_size],
        generator=torch.Generator().manual_seed(42)
    )

    BATCH = 128
    train_loader = DataLoader(train_ds, BATCH, shuffle=True, num_workers=0, pin_memory=True)
    val_loader = DataLoader(val_ds, BATCH, shuffle=False, num_workers=0, pin_memory=True)
    test_loader = DataLoader(test_ds, BATCH, shuffle=False, num_workers=0, pin_memory=True)
    print(f"  Train: {len(train_ds):,}, Val: {len(val_ds):,}, Test: {len(test_ds):,}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"→ Device: {device}")
    if device.type == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")

    model = DualHeadCNN(num_lossy).to(device)
    print(f"  Параметров: {sum(p.numel() for p in model.parameters()):,}")

    crit_bin = nn.CrossEntropyLoss(weight=torch.FloatTensor([0.45, 0.55]).to(device))
    crit_codec = nn.CrossEntropyLoss()
    opt = optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-4)
    sched = optim.lr_scheduler.ReduceLROnPlateau(opt, mode='min', patience=4, factor=0.5)

    start_epoch, best_acc = 0, 0
    if os.path.exists(CHECKPOINT_FILE):
        print(f"→ Найден чекпойнт: {CHECKPOINT_FILE}")
        start_epoch, best_acc = load_checkpoint(CHECKPOINT_FILE, model, opt, sched, device)
        print(f"  Восстановлен с эпохи {start_epoch}, best_acc: {best_acc:.2f}%")
    else:
        print("→ Обучение с нуля")

    print(f"→ Эпохи: {start_epoch + 1}–{EPOCHS}\n")

    for epoch in range(start_epoch, EPOCHS):
        print(f"--- Epoch {epoch+1}/{EPOCHS} ---")
        train_ds.dataset.augment = True
        train_loss, train_bin, train_codec = train_epoch(model, train_loader, crit_bin, crit_codec, opt, device)
        train_ds.dataset.augment = False
        val_loss, val_bin, val_codec, val_preds, val_labels = validate(model, val_loader, crit_bin, crit_codec, device)
        sched.step(val_loss)

        val_acc = 100 * (np.array(val_preds) == np.array(val_labels)).sum() / len(val_labels)
        print(f"  Train Loss: {train_loss:.4f} | Bin: {train_bin:.1f}% | Codec: {train_codec:.1f}%")
        print(f"  Val   Loss: {val_loss:.4f} | Bin: {val_bin:.1f}% | Codec: {val_codec:.1f}% | Total: {val_acc:.2f}%")

        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(model.state_dict(), BEST_MODEL_FILE)
            print(f"  ✓ Лучшая модель ({best_acc:.2f}%)")
        save_checkpoint(epoch + 1, model, opt, sched, best_acc, CHECKPOINT_FILE)

    print(f"\n{'='*50}\nФинальный тест...")
    model.load_state_dict(torch.load(BEST_MODEL_FILE, map_location=device, weights_only=False))
    test_loss, test_bin, test_codec, test_preds, test_labels = validate(model, test_loader, crit_bin, crit_codec, device)
    test_acc = 100 * (np.array(test_preds) == np.array(test_labels)).sum() / len(test_labels)
    print(f"\nTest Accuracy ({len(all_names)} классов): {test_acc:.2f}%")
    print(f"  Бинарная: {test_bin:.1f}% | Кодек: {test_codec:.1f}%")
    print("\n" + classification_report(test_labels, test_preds, target_names=all_names))

    cm = confusion_matrix(test_labels, test_preds)
    plt.figure(figsize=(12, 10))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=all_names, yticklabels=all_names)
    plt.title(f'Confusion Matrix (Test Acc: {test_acc:.1f}%)')
    plt.xticks(rotation=45, ha='right'); plt.yticks(rotation=0)
    plt.tight_layout(); plt.savefig('confusion_matrix.png', dpi=150)
    print("✓ Матрица ошибок сохранена: confusion_matrix.png")
    print("\nГотово! Нажми Enter для выхода..."); input()
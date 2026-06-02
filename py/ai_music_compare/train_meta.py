"""
train_meta.py
Обучение мета-модели поверх ансамбля из 4 кодек-моделей.
Мета-модель учится комбинировать выходы ансамбля в одну оценку.

Использование:
  python train_meta.py --datasets spectrograms_mp3,spectrograms_aac,spectrograms_opus,spectrograms_vorbis
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
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
import warnings
warnings.filterwarnings('ignore')

# ========== НАСТРОЙКИ ==========
BATCH_SIZE = 4096
EPOCHS = 100
LEARNING_RATE = 0.001
VAL_SPLIT = 0.15
EARLY_STOPPING_PATIENCE = 20

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Модели ансамбля
MODEL_PATHS = {
    'mp3': 'compare_model_mp3.pth',
    'aac': 'compare_model_aac.pth',
    'opus': 'compare_model_opus.pth',
    'vorbis': 'compare_model_vorbis.pth',
}

# ========== ОСНОВНАЯ МОДЕЛЬ (та же архитектура что в train_compare.py) ==========
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


# ========== МЕТА-МОДЕЛЬ ==========
class MetaEnsemble(nn.Module):
    """
    Мета-модель поверх ансамбля.
    Вход: 4 предсказания similarity от 4 моделей
    Выход: итоговая similarity + уверенность
    """
    def __init__(self, num_models=4, hidden_dim=32):
        super().__init__()
        
        # Обучаемые веса для взвешенного среднего
        self.weights = nn.Parameter(torch.ones(num_models) / num_models)
        
        # Нелинейная коррекция
        self.correction = nn.Sequential(
            nn.Linear(num_models, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim // 2, 1),
            nn.Tanh()  # поправка -1..+1
        )
        
        # Предсказание уверенности
        self.confidence = nn.Sequential(
            nn.Linear(num_models, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid()
        )
    
    def forward(self, x):
        # x: (batch, 4) — выходы 4 моделей
        
        # Взвешенное среднее
        weighted_avg = (x * self.weights.softmax(0)).sum(dim=1, keepdim=True)
        
        # Коррекция
        correction = self.correction(x) * 0.1  # масштабируем коррекцию
        
        # Итоговая оценка
        similarity = weighted_avg + correction
        similarity = torch.clamp(similarity, 0, 1)
        
        # Уверенность
        conf = self.confidence(x)
        
        return similarity, conf


# ========== ЗАГРУЗКА АНСАМБЛЯ ==========
def load_ensemble_models():
    """Загружает 4 модели ансамбля."""
    models = {}
    for name, path in MODEL_PATHS.items():
        if not os.path.exists(path):
            print(f"  ⚠ Модель {name} не найдена: {path}")
            continue
        
        model = AudioCompareNet(in_channels=1).to(DEVICE)
        model.load_state_dict(torch.load(path, map_location=DEVICE, weights_only=False))
        model.eval()
        models[name] = model
        print(f"  ✓ {name}: {path}")
    
    return models


# ========== СБОР ДАННЫХ ДЛЯ МЕТА-МОДЕЛИ ==========
def collect_ensemble_predictions(models, dataset_dirs, max_samples_per_dataset=None):
    """
    Прогоняет все датасеты через ансамбль и собирает:
    X: выходы 4 моделей (N, 4)
    y: реальная similarity (N, 1)
    """
    all_X = []
    all_y = []
    
    for ds_dir in dataset_dirs:
        ds_name = os.path.basename(ds_dir)
        print(f"\n  Обработка {ds_name}...")
        
        # Загружаем спектрограммы
        specs_a = np.load(os.path.join(ds_dir, 'specs_a.npy'), mmap_mode='r')
        specs_b = np.load(os.path.join(ds_dir, 'specs_b.npy'), mmap_mode='r')
        similarities = np.load(os.path.join(ds_dir, 'similarities.npy'), mmap_mode='r')
        
        total = len(similarities)
        if max_samples_per_dataset:
            total = min(total, max_samples_per_dataset)
        
        X_chunk = np.zeros((total, len(models)), dtype=np.float32)
        y_chunk = similarities[:total].copy()
        
        # Батчами прогоняем через все модели
        batch_size = 256
        for start in tqdm(range(0, total, batch_size), desc=f"  {ds_name}"):
            end = min(start + batch_size, total)
            
            batch_a = torch.FloatTensor(specs_a[start:end]).to(DEVICE)
            batch_b = torch.FloatTensor(specs_b[start:end]).to(DEVICE)
            
            with torch.no_grad():
                for j, (name, model) in enumerate(models.items()):
                    preds = model(batch_a, batch_b).cpu().numpy().flatten()
                    X_chunk[start:end, j] = preds
        
        all_X.append(X_chunk)
        all_y.append(y_chunk)
        
        print(f"    Собрано: {total:,} примеров")
    
    X = np.concatenate(all_X)
    y = np.concatenate(all_y)
    
    # Перемешиваем
    indices = np.random.permutation(len(X))
    X = X[indices]
    y = y[indices]
    
    print(f"\n  Всего примеров: {len(X):,}")
    print(f"  Размер X: {X.nbytes / 1024**2:.1f} МБ")
    
    return X, y


# ========== ОБУЧЕНИЕ МЕТА-МОДЕЛИ ==========
def train_meta_model(model, X_train, y_train, X_val, y_val):
    """Обучает мета-модель."""
    
    # Конвертируем в тензоры
    X_train_t = torch.FloatTensor(X_train).to(DEVICE)
    y_train_t = torch.FloatTensor(y_train).unsqueeze(1).to(DEVICE)
    X_val_t = torch.FloatTensor(X_val).to(DEVICE)
    y_val_t = torch.FloatTensor(y_val).unsqueeze(1).to(DEVICE)
    
    # DataLoader
    train_ds = torch.utils.data.TensorDataset(X_train_t, y_train_t)
    val_ds = torch.utils.data.TensorDataset(X_val_t, y_val_t)
    train_loader = DataLoader(train_ds, BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, BATCH_SIZE, shuffle=False)
    
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', patience=10, factor=0.5)
    
    best_loss = float('inf')
    patience_counter = 0
    
    history = {'train_loss': [], 'val_loss': [], 'val_mae': [], 'val_r2': []}
    
    print(f"\n→ Обучение мета-модели ({EPOCHS} эпох)...")
    print(f"{'Epoch':<8} {'Train Loss':<12} {'Val Loss':<12} {'Val MAE':<10} {'Val R²':<10} {'Best':<10}")
    print("-" * 62)
    
    for epoch in range(EPOCHS):
        # Train
        model.train()
        train_loss = 0
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            pred, _ = model(X_batch)
            loss = criterion(pred, y_batch)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
        train_loss /= len(train_loader)
        
        # Validate
        model.eval()
        val_loss = 0
        all_preds = []
        all_labels = []
        
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                pred, _ = model(X_batch)
                loss = criterion(pred, y_batch)
                val_loss += loss.item()
                all_preds.append(pred.cpu().numpy())
                all_labels.append(y_batch.cpu().numpy())
        
        val_loss /= len(val_loader)
        all_preds = np.concatenate(all_preds).flatten()
        all_labels = np.concatenate(all_labels).flatten()
        
        val_mae = mean_absolute_error(all_labels, all_preds)
        val_r2 = r2_score(all_labels, all_preds)
        
        scheduler.step(val_loss)
        
        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        history['val_mae'].append(val_mae)
        history['val_r2'].append(val_r2)
        
        improved = "✓" if val_loss < best_loss else ""
        
        print(f"{epoch+1:<8} {train_loss:<12.6f} {val_loss:<12.6f} {val_mae:<10.4f} {val_r2:<10.4f} {improved:<10}")
        
        if val_loss < best_loss:
            best_loss = val_loss
            patience_counter = 0
            torch.save(model.state_dict(), 'meta_model.pth')
        else:
            patience_counter += 1
        
        if patience_counter >= EARLY_STOPPING_PATIENCE:
            print(f"\n  Early stopping после {EARLY_STOPPING_PATIENCE} эпох")
            break
    
    return history


# ========== ГЛАВНАЯ ==========
def main():
    parser = argparse.ArgumentParser(description="Train Meta-Ensemble Model")
    parser.add_argument("--datasets", type=str, required=True,
                        help="Comma-separated dataset directories")
    parser.add_argument("--max-samples", type=int, default=100000,
                        help="Max samples per dataset (default: 100k)")
    parser.add_argument("--models", type=str, default=None,
                        help="Comma-separated model paths (default: auto)")
    args = parser.parse_args()
    
    dataset_dirs = [d.strip() for d in args.datasets.split(",")]
    
    # Проверяем наличие датасетов
    for ds in dataset_dirs:
        if not os.path.exists(ds):
            print(f"✗ Датасет не найден: {ds}")
            sys.exit(1)
    
    print("=" * 60)
    print("TRAIN META-ENSEMBLE MODEL")
    print("=" * 60)
    print(f"  Device: {DEVICE}")
    print(f"  Датасетов: {len(dataset_dirs)}")
    
    # Загружаем модели ансамбля
    print(f"\n→ Загрузка моделей ансамбля...")
    if args.models:
        model_paths_list = [p.strip() for p in args.models.split(",")]
        # Временно заменяем MODEL_PATHS
        global MODEL_PATHS
        MODEL_PATHS = {f"model_{i}": p for i, p in enumerate(model_paths_list)}
    
    models = load_ensemble_models()
    
    if len(models) < 2:
        print("✗ Нужно минимум 2 модели для ансамбля!")
        sys.exit(1)
    
    # Собираем данные
    print(f"\n→ Сбор предсказаний ансамбля...")
    X, y = collect_ensemble_predictions(models, dataset_dirs, args.max_samples)
    
    # Разделяем на train/val
    val_size = int(len(X) * VAL_SPLIT)
    X_train, X_val = X[:-val_size], X[-val_size:]
    y_train, y_val = y[:-val_size], y[-val_size:]
    
    print(f"\n  Train: {len(X_train):,}, Val: {len(X_val):,}")
    
    # Обучаем мета-модель
    print(f"\n→ Создание мета-модели...")
    meta_model = MetaEnsemble(num_models=len(models)).to(DEVICE)
    
    total_params = sum(p.numel() for p in meta_model.parameters())
    print(f"  Параметров: {total_params:,}")
    
    history = train_meta_model(meta_model, X_train, y_train, X_val, y_val)
    
    # Финальный тест
    print(f"\n{'='*60}")
    print("ФИНАЛЬНЫЙ ТЕСТ")
    print("=" * 60)
    
    meta_model.load_state_dict(torch.load('meta_model.pth', map_location=DEVICE))
    meta_model.eval()
    
    X_test_t = torch.FloatTensor(X_val[:10000]).to(DEVICE)
    y_test_t = torch.FloatTensor(y_val[:10000]).unsqueeze(1).to(DEVICE)
    
    with torch.no_grad():
        pred, conf = meta_model(X_test_t)
    
    y_test = y_test_t.cpu().numpy().flatten()
    pred = pred.cpu().numpy().flatten()
    conf = conf.cpu().numpy().flatten()
    
    test_mse = mean_squared_error(y_test, pred)
    test_mae = mean_absolute_error(y_test, pred)
    test_r2 = r2_score(y_test, pred)
    
    print(f"Test MSE: {test_mse:.6f}")
    print(f"Test MAE: {test_mae:.4f}")
    print(f"Test R²: {test_r2:.4f}")
    
    # Веса моделей
    weights = meta_model.weights.softmax(0).detach().cpu().numpy()
    print(f"\n  Веса моделей:")
    for i, (name, w) in enumerate(zip(models.keys(), weights)):
        print(f"    {name}: {w:.3f}")
    
    print(f"\n✓ Мета-модель сохранена: meta_model.pth")
    print("Готово!")


if __name__ == "__main__":
    main()
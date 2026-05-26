import numpy as np
import pickle
import os

OUTPUT_DIR = "spectrograms"

specs = np.load(os.path.join(OUTPUT_DIR, "spectrograms.npy"))
labels = np.load(os.path.join(OUTPUT_DIR, "labels.npy"))

with open(os.path.join(OUTPUT_DIR, "classes.pkl"), "rb") as f:
    class_info = pickle.load(f)

old_idx_to_class = class_info['idx_to_class']
print("Старые классы:", old_idx_to_class)

# Старый маппинг (14 -> 11)
# 0=lossless, 1=mp3_32, 2=mp3_64, 3=mp3_128, 4=mp3_192, 5=mp3_320,
# 6=aac_64, 7=aac_128, 8=aac_256,
# 9=opus_32, 10=opus_64, 11=opus_96, 12=opus_128, 13=opus_192

mapping = {
    0: 0,   # lossless -> lossless
    1: 1,   # mp3_32
    2: 2,   # mp3_64
    3: 3,   # mp3_128
    4: 4,   # mp3_192 -> mp3_high
    5: 4,   # mp3_320 -> mp3_high
    6: 5,   # aac_64
    7: 6,   # aac_128 -> aac_high
    8: 6,   # aac_256 -> aac_high
    9: 7,   # opus_32
    10: 8,  # opus_64
    11: 9,  # opus_96
    12: 10, # opus_128 -> opus_high
    13: 10, # opus_192 -> opus_high
}

new_class_names = [
    "lossless",
    "mp3_32", "mp3_64", "mp3_128", "mp3_high",
    "aac_64", "aac_high",
    "opus_32", "opus_64", "opus_96", "opus_high"
]

new_labels = np.array([mapping[l] for l in labels], dtype=np.int64)

# Бэкап старых
for f in ["spectrograms.npy", "labels.npy", "classes.pkl"]:
    src = os.path.join(OUTPUT_DIR, f)
    dst = os.path.join(OUTPUT_DIR, f.replace(".", "_14class."))
    if os.path.exists(src) and not os.path.exists(dst):
        os.rename(src, dst)

# Сохраняем новые
np.save(os.path.join(OUTPUT_DIR, "spectrograms.npy"), specs)
np.save(os.path.join(OUTPUT_DIR, "labels.npy"), new_labels)

new_class_to_idx = {name: i for i, name in enumerate(new_class_names)}
with open(os.path.join(OUTPUT_DIR, "classes.pkl"), "wb") as f:
    pickle.dump({'class_to_idx': new_class_to_idx, 'idx_to_class': new_class_names}, f)

unique, counts = np.unique(new_labels, return_counts=True)
print("\nНовое распределение по классам:")
for u, c in zip(unique, counts):
    print(f"  {new_class_names[u]}: {c:,} сегментов")

print(f"\nГотово! Старые данные сохранены с суффиксом '_14class'")
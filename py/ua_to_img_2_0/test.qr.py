# test_qr_detect.py
import numpy as np
from PIL import Image
import cv2

# Загружаем сохранённую отладку
img = np.array(Image.open("debug_qr_original.png").convert('L'))
print(f"Размер: {img.shape}")

detector = cv2.QRCodeDetector()

# Прямая попытка
data, bbox, rectified = detector.detectAndDecode(img)
print(f"Прямая: {data}")

# Инвертированная
data, bbox, rectified = detector.detectAndDecode(255 - img)
print(f"Инверт: {data}")

# Мульти-детекция (новый API OpenCV)
detector_multi = cv2.QRCodeDetector()
ret, points_list = detector_multi.detectMulti(img)
print(f"detectMulti нашёл: {ret}, точек: {len(points_list) if points_list else 0}")

if ret and points_list:
    for i, points in enumerate(points_list):
        data, straight_qrcode = detector_multi.decode(img, points)
        print(f"  QR {i}: {data}")
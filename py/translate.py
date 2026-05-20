import requests
import json

SERVER = "http://127.0.0.1:5000"

def translate(text, source="ru", target="en"):
    try:
        r = requests.post(
            f"{SERVER}/translate",
            json={"q": text, "source": source, "target": target, "format": "text"},
            timeout=10
        )
        print(f"Status: {r.status_code}")
        data = r.json()
        
        if "error" in data:
            print(f"Error: {data['error']}")
            return None
        
        result = data.get("translatedText", "")
        print(f"'{text}' → '{result}'")
        return result
    except requests.exceptions.ConnectionError:
        print("Ошибка: сервер не запущен")
        return None
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

if __name__ == "__main__":
    print("=== LibreTranslate Test ===\n")
    
    # Проверка, что сервер жив
    try:
        r = requests.get(f"{SERVER}/languages", timeout=5)
        print(f"Сервер доступен, языков: {len(r.json())}")
    except:
        print("Сервер недоступен! Запусти: .\\Scripts\\libretranslate.exe --load-only ru,en --host 127.0.0.1 --port 5000")
        exit()
    
    print()
    
    # Тесты
    tests = [
        ("hello", "en", "ru"),
        ("стрелка", "ru", "en"),
        ("папка", "ru", "en"),
        ("звук", "ru", "en"),
        ("настройки", "ru", "en"),
        ("файл", "ru", "en"),
        ("поиск", "ru", "en"),
        ("стрелка папка звук настройки файл поиск", "ru", "en"),
    ]
    
    for text, src, tgt in tests:
        translate(text, src, tgt)
    
    print("\nГотово!")
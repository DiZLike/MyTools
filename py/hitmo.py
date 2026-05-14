import os
import re
import json
import csv
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup


# Конфигурация
BASE_URL = "https://eu.hitmoz.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
    "Referer": BASE_URL
}


def search_tracks(query: str, check_links: bool = False) -> dict:
    """Поиск треков, возвращает словарь с результатами"""
    result = {"tracks": [], "success": False, "error": "", "query": query}
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        response = session.get(f"{BASE_URL}/search", params={"q": query}, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        track_nodes = soup.select("li.tracks__item") or soup.select("div.track-item")
        
        for node in track_nodes:
            try:
                meta = json.loads(node.get("data-musmeta", "{}"))
                duration = (node.select_one("div.track__fulltime") or 
                          node.select_one(".track-duration"))
                
                download_node = node.select_one("a.track__download-btn") or \
                               node.select_one(".download-link")
                raw_url = download_node.get("href", "") if download_node else meta.get("url", "")
                download_url = urljoin(BASE_URL, raw_url) if raw_url else ""
                
                # Кортеж: (id, artist, title, duration, download_url, cover_url)
                track = (
                    node.get("data-musid", "").replace("track-id-", ""),
                    meta.get("artist", ""),
                    meta.get("title", ""),
                    duration.text.strip() if duration else "Неизвестно",
                    download_url,
                    urljoin(BASE_URL, meta.get("img", ""))
                )
                
                if check_links and download_url:
                    if not is_url_accessible(download_url, session):
                        continue
                        
                result["tracks"].append(track)
                
            except (json.JSONDecodeError, Exception) as e:
                print(f"Ошибка парсинга трека: {e}")
                
        result["success"] = True
        session.close()
        
    except requests.RequestException as e:
        result["error"] = f"Ошибка запроса: {e}"
    except Exception as e:
        result["error"] = f"Неизвестная ошибка: {e}"
        
    return result


def is_url_accessible(url: str, session: requests.Session = None) -> bool:
    try:
        if session:
            response = session.head(url, allow_redirects=True, timeout=10)
        else:
            response = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=10)
        return response.status_code != 404 and response.ok
    except:
        return False


def download_file(url: str, filename: str, download_dir: str = "downloads") -> bool:
    try:
        os.makedirs(download_dir, exist_ok=True)
        filepath = os.path.join(download_dir, sanitize_filename(filename))
        
        if not url.startswith(('http://', 'https://')):
            url = urljoin(BASE_URL, url)
        
        response = requests.get(url, headers=HEADERS, stream=True, timeout=30)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        print(f"\rПрогресс: {(downloaded / total_size) * 100:.1f}%", end='', flush=True)
        
        if total_size > 0:
            print()
        print(f"Скачано: {filepath}")
        return True
        
    except Exception as e:
        print(f"\nОшибка при скачивании: {e}")
        return False


def sanitize_filename(filename: str) -> str:
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename).rstrip('.')
    return filename[:200] if len(filename) > 200 else filename


def save_results(tracks: list, file_path: str, format: str = "txt"):
    """Сохранение результатов в разных форматах"""
    if format == "txt":
        content = '\n\n'.join(f"{t[1]} - {t[2]} ({t[3]})\nСсылка: {t[4]}" for t in tracks)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
    elif format == "links":
        content = '\n'.join(f"{t[1]} - {t[2]}: {t[4]}" for t in tracks)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
    elif format == "csv":
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Исполнитель", "Название", "Длительность", "Ссылка", "Обложка"])
            writer.writerows(tracks)
            
    elif format == "json":
        tracks_data = [{
            "id": t[0], "artist": t[1], "title": t[2],
            "duration": t[3], "download_url": t[4], "cover_url": t[5]
        } for t in tracks]
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(tracks_data, f, ensure_ascii=False, indent=2)


def get_stream_url(download_url: str) -> str:
    try:
        url = urljoin(BASE_URL, download_url)
        headers = {**HEADERS, "Range": "bytes=0-1024"}
        response = requests.get(url, headers=headers, allow_redirects=True, stream=True)
        if response.ok or response.status_code == 206:
            return response.url
    except Exception as e:
        print(f"Ошибка получения прямой ссылки: {e}")
    return ""


def test_connection() -> bool:
    try:
        return requests.get(BASE_URL, timeout=10).ok
    except:
        return False


def main():
    print("=" * 80)
    print("                    ЗАГРУЗЧИК МУЗЫКИ С HITMOZ.COM")
    print("=" * 80)
    
    if not test_connection():
        print("\n❌ Не удалось подключиться к сайту.")
        return
    print("✅ Соединение установлено\n")
    
    query = input("Введите название песни для поиска: ").strip()
    if not query:
        print("Поисковый запрос не может быть пустым!")
        return
    
    print(f"\n🔍 Поиск треков по запросу: '{query}'...")
    result = search_tracks(query)
    
    if not result["success"]:
        print(f"❌ Ошибка: {result['error']}")
        return
    if not result["tracks"]:
        print("❌ Ничего не найдено.")
        return
    
    # Вывод результатов
    print(f"\n✅ Найдено треков: {len(result['tracks'])}\n")
    print("=" * 80)
    
    for i, track in enumerate(result["tracks"], 1):
        print(f"{i}. {track[1]} - {track[2]}")
        print(f"   ⏱️  Длительность: {track[3]}")
        print(f"   🔗 Ссылка: {track[4]}")
        print("-" * 80)
    
    # Выбор и скачивание
    while True:
        try:
            choice = input(f"\nВведите номер трека (1-{len(result['tracks'])}) или 'q' для выхода: ").strip()
            if choice.lower() == 'q':
                print("👋 Выход.")
                return
            
            index = int(choice) - 1
            if 0 <= index < len(result["tracks"]):
                track = result["tracks"][index]
                
                # Определяем расширение
                ext = ".mp3"
                for e in [".m4a", ".ogg", ".mp3"]:
                    if e in track[4].lower():
                        ext = e
                        break
                
                filename = sanitize_filename(f"{track[1]} - {track[2]}{ext}")
                
                print(f"\n📥 Скачивание: {track[1]} - {track[2]}")
                if download_file(track[4], filename):
                    print(f"\n✅ Трек сохранен: downloads/{filename}")
                else:
                    print("\n❌ Не удалось скачать трек.")
                
                if input("\nСкачать еще? (y/n): ").strip().lower() != 'y':
                    print("👋 Выход.")
                    break
                    
                # Показываем список снова
                print("\n" + "=" * 80)
                for i, t in enumerate(result["tracks"], 1):
                    marker = "✅" if i == index + 1 else "  "
                    print(f"{marker} {i}. {t[1]} - {t[2]}")
            else:
                print(f"❌ Введите число от 1 до {len(result['tracks'])}")
                
        except ValueError:
            print("❌ Введите корректное число или 'q'")
        except KeyboardInterrupt:
            print("\n\n👋 Отменено.")
            return


if __name__ == "__main__":
    main()
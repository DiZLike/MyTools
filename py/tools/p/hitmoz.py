import os
import re
import json
import requests
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup

BASE_URL = "https://rus.hitmoz.org"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

def sanitize_filename(filename: str) -> str:
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200] if len(filename) > 200 else filename

def parse_track_items(soup):
    """Общий парсер треков из страницы (поиск или топ)"""
    tracks = []
    items = soup.select("ul.tracks__list li.tracks__item")
    
    for item in items:
        try:
            # Основной источник — JSON
            musmeta = item.get("data-musmeta", "")
            if musmeta:
                meta = json.loads(musmeta)
                title = meta.get("title", "Unknown")
                artist = meta.get("artist", "Unknown")
                download_url = meta.get("url", "")
                cover_url = meta.get("img", "")
                
                # Если JSON-ссылка относительная — дополняем
                if download_url and not download_url.startswith("http"):
                    download_url = urljoin(BASE_URL, download_url)
            else:
                # Запасной — HTML
                title_el = item.select_one(".track__title")
                title = title_el.get_text(strip=True) if title_el else "Unknown"
                
                artist_el = item.select_one(".track__desc")
                artist = artist_el.get_text(strip=True) if artist_el else "Unknown"
                
                download_btn = item.select_one("a.track__download-btn")
                download_url = urljoin(BASE_URL, download_btn.get("href", "")) if download_btn else ""
                
                img_el = item.select_one(".track__img")
                if img_el:
                    style = img_el.get("style", "")
                    cover_url = style.split("url('")[1].split("')")[0] if "url('" in style else ""
                else:
                    cover_url = ""
            
            # Длительность — только из HTML
            duration_el = item.select_one(".track__fulltime")
            duration = duration_el.get_text(strip=True) if duration_el else ""
            
            if title and artist:
                tracks.append({
                    "name": title,
                    "artist": artist,
                    "duration": duration,
                    "url": download_url,
                    "cover": cover_url
                })
                
        except Exception as e:
            print(f"   Ошибка парсинга трека: {e}")
            continue
    
    return tracks


def search_tracks(query: str):
    """Поиск треков"""
    result = {"tracks": [], "success": False, "error": "", "artist": query}
    
    try:
        if len(query.strip()) < 2:
            result["error"] = "Слишком короткий запрос"
            return result
        
        session = requests.Session()
        session.headers.update(HEADERS)
        
        encoded_query = quote(query.strip(), safe='')
        search_url = f"{BASE_URL}/search?q={encoded_query}"
        
        print(f"   Запрос: {search_url}")
        response = session.get(search_url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        result["tracks"] = parse_track_items(soup)
        result["success"] = len(result["tracks"]) > 0
        session.close()
        
    except Exception as e:
        result["error"] = f"Ошибка: {e}"
    
    return result


def get_top_tracks():
    """Топ треков за сегодня"""
    result = {"tracks": [], "success": False, "error": ""}
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        url = f"{BASE_URL}/songs/top-today"
        print(f"   Запрос: {url}")
        response = session.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        result["tracks"] = parse_track_items(soup)
        result["success"] = len(result["tracks"]) > 0
        session.close()
        
    except Exception as e:
        result["error"] = f"Ошибка: {e}"
    
    return result


def download_file(url: str, filepath: str):
    """Скачивает файл"""
    try:
        headers = HEADERS.copy()
        headers["Referer"] = BASE_URL
        
        response = requests.get(url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r   Прогресс: {percent:.1f}%", end='', flush=True)
        
        if total_size > 0:
            print()
        return True
        
    except Exception as e:
        print(f"\n   Ошибка: {e}")
        return False


def main():
    print("=" * 80)
    print("         ЗАГРУЗЧИК МУЗЫКИ С HITMOZ.ORG")
    print("=" * 80)
    
    query = input("\n🔍 Введите название группы или исполнителя (Enter — топ дня): ").strip()
    
    if query:
        print(f"\n🔍 Ищем: '{query}'...")
        search_result = search_tracks(query)
        label = query
    else:
        print("\n🔥 Загружаем топ дня...")
        search_result = get_top_tracks()
        label = "top-today"
    
    if not search_result["success"]:
        print(f"❌ {search_result['error'] if search_result['error'] else 'Ничего не найдено'}")
        return
    
    all_tracks = search_result["tracks"]
    
    print(f"\n✅ Найдено треков: {len(all_tracks)}\n")
    print("=" * 80)
    
    for i, track in enumerate(all_tracks, 1):
        dur = f" ({track['duration']})" if track['duration'] else ""
        url_status = "🔗" if track['url'] else "❌"
        cover_status = "🖼️" if track['cover'] else ""
        print(f"{i:2d}. {track['artist']} - {track['name']}{dur} {url_status} {cover_status}")
        if track['url']:
            print(f"     🎵 {track['url']}")
        if track['cover']:
            print(f"     🖼️  {track['cover']}")
    
    print("=" * 80)
    
    while True:
        print("\n📥 Команды: 'all', 1,3,5-7, 'save', 'q'")
        choice = input("\n👉 Ваш выбор: ").strip().lower()
        
        if choice == 'q':
            print("👋 Выход.")
            break
        
        if choice == 'save':
            filename = f"tracks_{sanitize_filename(label)}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                for i, t in enumerate(all_tracks, 1):
                    f.write(f"{i}. {t['artist']} - {t['name']} ({t['duration']})\n")
                    if t['url']:
                        f.write(f"URL: {t['url']}\n")
                    if t['cover']:
                        f.write(f"Cover: {t['cover']}\n")
                    f.write("\n")
            print(f"✅ Сохранено в {filename}")
            continue
        
        if choice == 'all':
            indices = set(range(1, len(all_tracks) + 1))
        else:
            indices = set()
            for part in choice.replace(' ', '').split(','):
                if '-' in part:
                    try:
                        start, end = map(int, part.split('-'))
                        indices.update(range(start, end + 1))
                    except:
                        pass
                else:
                    try:
                        indices.add(int(part))
                    except:
                        pass
        
        tracks_to_download = [all_tracks[i-1] for i in sorted(indices) if 1 <= i <= len(all_tracks)]
        
        if not tracks_to_download:
            print("❌ Ничего не выбрано")
            continue
        
        tracks_with_url = [t for t in tracks_to_download if t['url']]
        tracks_without_url = [t for t in tracks_to_download if not t['url']]
        
        if tracks_without_url:
            print(f"⚠️  {len(tracks_without_url)} треков без ссылки:")
            for t in tracks_without_url:
                print(f"   - {t['artist']} - {t['name']}")
        
        if not tracks_with_url:
            print("❌ Нет треков с доступными ссылками")
            continue
        
        print(f"\n📥 Скачивание {len(tracks_with_url)} треков...")
        download_dir = f"downloads_{sanitize_filename(label)}"
        os.makedirs(download_dir, exist_ok=True)
        
        downloaded = 0
        for track in tracks_with_url:
            filename = f"{track['artist']} - {track['name']}.mp3"
            filename = sanitize_filename(filename)
            filepath = os.path.join(download_dir, filename)
            
            if os.path.exists(filepath):
                print(f"⏭️  Пропуск: {filename}")
                downloaded += 1
                continue
            
            print(f"\n🎵 {filename}")
            if download_file(track['url'], filepath):
                print(f"   ✅ Сохранён")
                downloaded += 1
            else:
                print(f"   ❌ Ошибка")
        
        print(f"\n✅ Скачано {downloaded} из {len(tracks_with_url)}")
        break


if __name__ == "__main__":
    main()
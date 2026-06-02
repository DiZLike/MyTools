import os
import re
import requests
from urllib.parse import quote
from bs4 import BeautifulSoup

BASE_URL = "https://ru.drivemusic.me"
TOP_URL = "https://ru.drivemusic.me/hits_top40.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

def sanitize_filename(filename: str) -> str:
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200] if len(filename) > 200 else filename

def parse_drivemusic_items(soup, query=None, is_top=False):
    """Общий парсер треков drivemusic (поиск или топ)"""
    tracks = []
    items = soup.select("div.music-popular-wrapper")
    
    # Для поиска — фильтруем по запросу
    if query:
        query_lower = query.lower()
        items = [item for item in items if query_lower in item.get_text(strip=True).lower()]
    
    for item in items:
        try:
            # Название трека
            name_el = item.select_one("a.popular-play-author")
            track_name = name_el.get_text(strip=True) if name_el else "Unknown"
            
            # Исполнитель
            artist_el = item.select_one("div.popular-play-composition a")
            artist = artist_el.get_text(strip=True) if artist_el else "Unknown"
            
            # Длительность
            if is_top:
                # В топе длительности нет, только число скачиваний — не берём
                duration = ""
            else:
                # В поиске длительность есть в span.time-hover
                duration_el = item.select_one("span.time-hover")
                duration = duration_el.get_text(strip=True) if duration_el else ""
                duration = re.sub(r'[^\d:]', '', duration)
            
            # MP3 ссылка из data-url
            mp3_url = ""
            play_btn = item.select_one("button[data-url]")
            if play_btn:
                mp3_url = play_btn.get("data-url", "")
            
            # Запасной — ищем data-url с .mp3 в любом элементе
            if not mp3_url:
                for tag in item.find_all(attrs={"data-url": True}):
                    url = tag.get("data-url", "")
                    if '.mp3' in url:
                        mp3_url = url
                        break
            
            if mp3_url and track_name and artist:
                tracks.append({
                    "name": track_name,
                    "artist": artist,
                    "duration": duration,
                    "url": mp3_url
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
        session.get(BASE_URL + "/", timeout=10)
        
        encoded_query = quote(query.strip(), safe='')
        search_url = f"{BASE_URL}/?do=search&subaction=search&story={encoded_query}"
        
        print(f"   Запрос: {search_url}")
        response = session.get(search_url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        result["tracks"] = parse_drivemusic_items(soup, query=query)
        result["success"] = len(result["tracks"]) > 0
        session.close()
        
    except Exception as e:
        result["error"] = f"Ошибка: {e}"
    
    return result


def get_top_tracks():
    """Топ-40 треков"""
    result = {"tracks": [], "success": False, "error": ""}
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        print(f"   Запрос: {TOP_URL}")
        response = session.get(TOP_URL, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        result["tracks"] = parse_drivemusic_items(soup)
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
    print("         ЗАГРУЗЧИК МУЗЫКИ С DRIVEMUSIC.ME")
    print("=" * 80)
    
    query = input("\n🔍 Введите название группы или исполнителя (Enter — топ-40): ").strip()
    
    if query:
        print(f"\n🔍 Ищем: '{query}'...")
        search_result = search_tracks(query)
        label = query
    else:
        print("\n🔥 Загружаем топ-40...")
        search_result = get_top_tracks()
        label = "top40"
    
    if not search_result["success"]:
        print(f"❌ {search_result['error'] if search_result['error'] else 'Ничего не найдено'}")
        return
    
    all_tracks = search_result["tracks"]
    
    print(f"\n✅ Найдено треков: {len(all_tracks)}\n")
    print("=" * 80)
    
    for i, track in enumerate(all_tracks, 1):
        dur = f" ({track['duration']})" if track['duration'] else ""
        print(f"{i:2d}. {track['artist']} - {track['name']}{dur}")
        print(f"     🎵 {track['url'][:100]}...")
    
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
                    f.write(f"{t['url']}\n\n")
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
        
        print(f"\n📥 Скачивание {len(tracks_to_download)} треков...")
        download_dir = f"downloads_{sanitize_filename(label)}"
        os.makedirs(download_dir, exist_ok=True)
        
        downloaded = 0
        for track in tracks_to_download:
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
        
        print(f"\n✅ Скачано {downloaded} из {len(tracks_to_download)}")
        break


if __name__ == "__main__":
    main()
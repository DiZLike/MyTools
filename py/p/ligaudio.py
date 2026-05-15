import os
import re
import requests
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup

BASE_URL = "https://web.ligaudio.ru"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

def sanitize_filename(filename: str) -> str:
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200] if len(filename) > 200 else filename

def parse_ligaudio_items(soup):
    """Общий парсер треков ligaudio (поиск или главная)"""
    tracks = []
    items = soup.select("div#result div.item")
    
    for item in items:
        try:
            # Название трека
            name_el = item.select_one("span.title[itemprop='name']")
            track_name = name_el.get_text(strip=True) if name_el else "Unknown"
            
            # Исполнитель
            artist_el = item.select_one("span.autor[itemprop='byArtist']")
            artist = artist_el.get_text(strip=True) if artist_el else "Unknown"
            
            # Длительность
            duration_el = item.select_one("span.d")
            duration = duration_el.get_text(strip=True) if duration_el else ""
            
            # MP3 ссылка — напрямую из a.down[href]
            mp3_url = ""
            down_btn = item.select_one("a.down[href]")
            if down_btn:
                href = down_btn.get("href", "")
                if href:
                    mp3_url = urljoin("https:", href)
            
            # Запасной — regex по HTML элемента
            if not mp3_url:
                item_html = str(item)
                mp3_match = re.search(r'//(storage\d+\.lightaudio\.ru/dm/[^\s"\']+\.mp3[^\s"\']*)', item_html)
                if mp3_match:
                    mp3_url = "https:" + mp3_match.group(0)
            
            # Обложка
            cover_url = ""
            img_el = item.select_one("img[src]")
            if img_el:
                src = img_el.get("src", "")
                if src:
                    cover_url = urljoin("https:", src)
            
            if track_name and artist and mp3_url:
                tracks.append({
                    "name": track_name,
                    "artist": artist,
                    "duration": duration,
                    "url": mp3_url,
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
            result["error"] = "Слишком короткий запрос (минимум 2 символа)"
            return result
        
        session = requests.Session()
        session.headers.update(HEADERS)
        session.get(BASE_URL + "/", timeout=10)
        
        encoded_query = quote(query.strip(), safe='')
        url = f"{BASE_URL}/mp3/{encoded_query}"
        
        print(f"   Запрос: {url}")
        response = session.get(url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        h1 = soup.select_one("div#main h1")
        if h1:
            result["artist"] = h1.get_text(strip=True)
        
        result["tracks"] = parse_ligaudio_items(soup)
        result["success"] = len(result["tracks"]) > 0
        session.close()
        
    except Exception as e:
        result["error"] = f"Ошибка: {e}"
    
    return result


def get_popular_tracks():
    """Популярные треки с главной страницы"""
    result = {"tracks": [], "success": False, "error": ""}
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        print(f"   Запрос: {BASE_URL}/")
        response = session.get(BASE_URL + "/", timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        result["tracks"] = parse_ligaudio_items(soup)
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
        print(f"\n   Ошибка при скачивании: {e}")
        return False


def main():
    print("=" * 80)
    print("         ЗАГРУЗЧИК МУЗЫКИ С LIGAUDIO.RU")
    print("=" * 80)
    
    query = input("\n🔍 Введите название группы или исполнителя (Enter — популярное): ").strip()
    
    if query:
        print(f"\n🔍 Ищем: '{query}'...")
        search_result = search_tracks(query)
        label = query
    else:
        print("\n🔥 Загружаем популярное за неделю...")
        search_result = get_popular_tracks()
        label = "popular"
    
    if not search_result["success"]:
        print(f"❌ {search_result['error'] if search_result['error'] else 'Ничего не найдено'}")
        return
    
    all_tracks = search_result["tracks"]
    artist_name = search_result.get("artist", label)
    
    print(f"\n✅ Найдено треков: {len(all_tracks)}")
    if artist_name and artist_name != label:
        print(f"🎤 Исполнитель: {artist_name}")
    print()
    print("=" * 80)
    
    for i, track in enumerate(all_tracks, 1):
        dur = f" ({track['duration']})" if track['duration'] else ""
        cover_status = "🖼️" if track['cover'] else ""
        print(f"{i:2d}. {track['artist']} - {track['name']}{dur} {cover_status}")
        print(f"     🎵 {track['url'][:100]}...")
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
            
            print(f"\n🎵 {filename} ({track['duration']})")
            if download_file(track["url"], filepath):
                print(f"   ✅ Сохранён")
                downloaded += 1
            else:
                print(f"   ❌ Ошибка")
        
        print(f"\n✅ Скачано {downloaded} из {len(tracks_to_download)} в '{download_dir}'")
        break


if __name__ == "__main__":
    main()
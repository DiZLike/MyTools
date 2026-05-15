import os
import re
import requests
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup

BASE_URL = "https://musify.club"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
MAX_TRACKS = 100

def sanitize_filename(filename: str) -> str:
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200] if len(filename) > 200 else filename

def parse_musify_items(soup):
    """Общий парсер треков musify (поиск или топ)"""
    tracks = []
    seen_ids = set()
    
    for row in soup.find_all(attrs={'data-track-id': True}):
        if len(tracks) >= MAX_TRACKS:
            break
        
        track_id = row.get('data-track-id', '')
        if track_id in seen_ids:
            continue
        seen_ids.add(track_id)
        
        # Данные из data-атрибутов
        artist = row.get('data-artist', 'Unknown')
        title = row.get('data-name', 'Unknown')
        
        # Длительность
        time_elem = row.find('span', string=re.compile(r'\d{1,2}:\d{2}'))
        duration = time_elem.get_text(strip=True) if time_elem else ''
        
        # Ссылка на скачивание: /track/dl/ → /track/pl/ (работает без авторизации)
        dl_link = row.find('a', href=re.compile(r'/track/dl/\d+'))
        if not dl_link:
            continue
        
        dl_url = dl_link.get('href', '')
        play_url = dl_url.replace('/track/dl/', '/track/pl/')
        download_url = urljoin(BASE_URL, play_url)
        
        # Обложка из data-art (в дочернем div)
        cover_div = row.select_one('[data-art]')
        cover_url = cover_div.get('data-art', '') if cover_div else ''
        if cover_url and not cover_url.startswith('http'):
            cover_url = urljoin(BASE_URL, cover_url)
        
        tracks.append({
            'artist': artist,
            'title': title,
            'name': f"{artist} - {title}",
            'duration': duration,
            'url': download_url,
            'cover': cover_url
        })
    
    return tracks


def search_tracks(query: str):
    """Поиск треков"""
    result = {"tracks": [], "success": False, "error": ""}
    
    try:
        if len(query.strip()) < 2:
            result["error"] = "Слишком короткий запрос"
            return result
        
        session = requests.Session()
        session.headers.update(HEADERS)
        
        encoded_query = quote(query.strip(), safe='')
        url = f"{BASE_URL}/search?SearchText={encoded_query}"
        
        print(f"   Запрос: {url}")
        response = session.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        result["tracks"] = parse_musify_items(soup)
        result["success"] = len(result["tracks"]) > 0
        session.close()
        
    except Exception as e:
        result["error"] = f"Ошибка: {e}"
    
    return result


def get_top_tracks():
    """Топ треков с /hits"""
    result = {"tracks": [], "success": False, "error": ""}
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        url = f"{BASE_URL}/hits"
        print(f"   Запрос: {url}")
        response = session.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        result["tracks"] = parse_musify_items(soup)
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
    print("         ЗАГРУЗЧИК МУЗЫКИ С MUSIFY.CLUB")
    print("=" * 80)
    
    query = input("\n🔍 Введите название группы или исполнителя (Enter — топ-100): ").strip()
    
    if query:
        print(f"\n🔍 Ищем: '{query}'...")
        search_result = search_tracks(query)
        label = query
    else:
        print("\n🔥 Загружаем топ-100...")
        search_result = get_top_tracks()
        label = "top100"
    
    if not search_result["success"]:
        print(f"❌ {search_result['error'] if search_result['error'] else 'Ничего не найдено'}")
        return
    
    all_tracks = search_result["tracks"]
    
    print(f"\n✅ Найдено треков: {len(all_tracks)}\n")
    print("=" * 80)
    
    for i, track in enumerate(all_tracks, 1):
        dur = f" ({track['duration']})" if track['duration'] else ""
        cover_status = "🖼️" if track['cover'] else ""
        print(f"{i:3d}. {track['name']}{dur} {cover_status}")
        print(f"      🎵 {track['url'][:100]}...")
        if track['cover']:
            print(f"      🖼️  {track['cover']}")
    
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
                    f.write(f"{i}. {t['artist']} - {t['title']} ({t['duration']})\n")
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
            filename = f"{track['artist']} - {track['title']}.mp3"
            filename = sanitize_filename(filename)
            filepath = os.path.join(download_dir, filename)
            
            if os.path.exists(filepath):
                print(f"⏭️  Пропуск: {filename}")
                downloaded += 1
                continue
            
            print(f"\n🎵 {filename} ({track['duration']})")
            if download_file(track['url'], filepath):
                print(f"   ✅ Сохранён")
                downloaded += 1
            else:
                print(f"   ❌ Ошибка")
        
        print(f"\n✅ Скачано {downloaded} из {len(tracks_to_download)} в '{download_dir}'")
        break


if __name__ == "__main__":
    main()
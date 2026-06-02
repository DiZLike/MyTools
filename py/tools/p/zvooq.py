import os
import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup

BASE_URL = "https://i.zvooq.net"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
MAX_TRACKS = 50

def sanitize_filename(filename: str) -> str:
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200]

def format_duration(seconds):
    """Форматирует секунды в MM:SS"""
    if not seconds:
        return ""
    seconds = int(seconds)
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins}:{secs:02d}"

async def search_tracks(session, query):
    """Поиск треков на Zvooq"""
    
    search_url = f"{BASE_URL}/search?q={query}&artist=0"
    
    async with session.get(search_url) as resp:
        if resp.status != 200:
            return []
        html = await resp.text()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    tracks = []
    seen_ids = set()
    
    # Ищем элементы с data-id и data-artist (уровень <li class='idx1c'>)
    for item in soup.find_all(attrs={'data-artist': True, 'data-title': True}):
        if len(tracks) >= MAX_TRACKS:
            break
        
        track_id = item.get('data-id', '')
        if track_id in seen_ids:
            continue
        seen_ids.add(track_id)
        
        artist = item.get('data-artist', '')
        title = item.get('data-title', '')
        duration_sec = item.get('data-duration', '')
        duration = format_duration(duration_sec)
        
        # Ищем ссылку dl внутри этого элемента
        dl_link = item.find('a', href=re.compile(r'dl\d+s?\d*\.zvooq\.net/'))
        if not dl_link:
            continue
        
        download_url = dl_link.get('href', '')
        if download_url.startswith('//'):
            download_url = 'https:' + download_url
        
        tracks.append({
            'artist': artist,
            'title': title,
            'name': f"{artist} - {title}",
            'duration': duration,
            'url': download_url,
        })
    
    return tracks

def download_file(url, filepath):
    """Скачивание файла"""
    try:
        import requests
        dl_headers = {
            **HEADERS,
            "Referer": "https://i.zvooq.net/",
        }
        response = requests.get(url, headers=dl_headers, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        print(f"\r   {downloaded * 100 // total_size}%", end='', flush=True)
        
        if total_size > 0:
            print()
        return True
    except Exception as e:
        print(f"\n   ❌ {e}")
        return False

async def main_async():
    print("=" * 60)
    print("    ZVOOQ MUSIC DOWNLOADER")
    print("=" * 60)
    
    query = input("\n🔍 Поиск: ").strip()
    if not query:
        print("❌ Пустой запрос")
        return
    
    print(f"\n🔍 Ищем: '{query}'...")
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tracks = await search_tracks(session, query)
    
    if not tracks:
        print("❌ Ничего не найдено")
        return
    
    print(f"✅ Найдено: {len(tracks)} треков\n")
    
    for i, track in enumerate(tracks, 1):
        dur = f" [{track['duration']}]" if track['duration'] else ""
        print(f"{i}. {track['name']}{dur}")
    
    while True:
        print("\n📥 Команды: 'all', 1,3,5-7, 'q'")
        choice = input("👉 ").strip().lower()
        
        if choice == 'q':
            print("👋 Выход")
            break
        
        if choice == 'all':
            indices = set(range(1, len(tracks) + 1))
        else:
            indices = set()
            for part in choice.replace(' ', '').split(','):
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    indices.update(range(start, end + 1))
                else:
                    try:
                        indices.add(int(part))
                    except:
                        pass
        
        to_download = [tracks[i-1] for i in sorted(indices) if 1 <= i <= len(tracks)]
        
        if not to_download:
            print("❌ Ничего не выбрано")
            continue
        
        print(f"\n📥 Скачивание {len(to_download)} треков...")
        
        folder = f"downloads_{sanitize_filename(query)}"
        os.makedirs(folder, exist_ok=True)
        
        ok = 0
        for track in to_download:
            filename = f"{track['artist']} - {track['title']}.mp3"
            filename = sanitize_filename(filename)
            filepath = os.path.join(folder, filename)
            
            if os.path.exists(filepath):
                print(f"⏭️  {filename}")
                ok += 1
                continue
            
            print(f"\n🎵 {filename} [{track['duration']}]")
            if download_file(track['url'], filepath):
                ok += 1
        
        print(f"\n✅ Скачано: {ok}/{len(to_download)}")
        break

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
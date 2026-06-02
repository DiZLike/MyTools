import os
import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import unquote

BASE_URL = "https://muzjam.org"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
MAX_TRACKS = 50

def sanitize_filename(filename: str) -> str:
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200]

async def search_tracks(session, query):
    """Поиск треков на Muzjam"""
    
    search_url = f"{BASE_URL}/search/{query}"
    
    async with session.get(search_url) as resp:
        if resp.status != 200:
            return []
        html = await resp.text()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    tracks = []
    seen_urls = set()
    
    # Ищем все ссылки на скачивание
    for a in soup.find_all('a', href=re.compile(r'song\.muzvibe\.org/download/')):
        if len(tracks) >= MAX_TRACKS:
            break
        
        href = a.get('href', '')
        if href in seen_urls:
            continue
        seen_urls.add(href)
        
        # Добавляем https: если ссылка без протокола
        download_url = 'https:' + href if href.startswith('//') else href
        
        # Извлекаем имя файла из URL
        filename = unquote(href.split('/')[-1])
        name = filename.replace('.mp3', '')
        
        # Ищем исполнителя и название
        artist = ""
        title = name
        
        if ' - ' in name:
            parts = name.split(' - ', 1)
            artist = parts[0].strip()
            title = parts[1].strip()
        
        # Ищем время рядом со ссылкой
        parent = a.find_parent(['div', 'li', 'tr'])
        duration = ""
        
        if parent:
            time_elem = parent.find(string=re.compile(r'\d{1,2}:\d{2}'))
            if time_elem:
                duration = time_elem.strip()
        
        tracks.append({
            'artist': artist or 'Unknown',
            'title': title or name,
            'name': f"{artist} - {title}" if artist else title,
            'duration': duration,
            'url': download_url,
        })
    
    return tracks

def download_file(url, filepath):
    """Скачивание файла"""
    try:
        import requests
        response = requests.get(url, headers=HEADERS, stream=True, timeout=60)
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
    print("    MUZJAM MUSIC DOWNLOADER")
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
        print(f"   {track['url'][:100]}...")
    
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
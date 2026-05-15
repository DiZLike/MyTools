import os
import re
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup

BASE_URL = "https://new.zvukofon.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}
MAX_TRACKS = 50

def sanitize_filename(filename: str) -> str:
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200]

async def search_tracks(session, query):
    """Поиск треков с русскими названиями, длительностью и качеством"""
    
    # Получаем куки
    await session.get("https://zvukofon.com")
    await session.get(BASE_URL)
    
    # Поиск
    search_url = f"{BASE_URL}/music/{query}"
    async with session.get(search_url) as resp:
        if resp.status != 200:
            return []
        html = await resp.text()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    tracks = []
    seen_ids = set()
    
    # Ищем элементы с data-musmeta
    for item in soup.find_all(attrs={'data-musmeta': True}):
        if len(tracks) >= MAX_TRACKS:
            break
        
        try:
            # Парсим JSON из data-musmeta
            musmeta = json.loads(item['data-musmeta'])
            track_id = item.get('data-musid', '')
            
            if track_id in seen_ids:
                continue
            seen_ids.add(track_id)
            
            artist = musmeta.get('artist', '')
            title = musmeta.get('title', '')
            
            # Ищем длительность
            time_elem = item.find(class_='topcharts__item-info-time_total')
            duration = time_elem.get_text(strip=True) if time_elem else ''
            
            # Ищем ссылки на скачивание
            download_links = item.find_all('a', href=re.compile(r'/dl/\d+'))
            
            # Собираем все варианты качества
            urls = {}
            for link in download_links:
                href = link.get('href', '')
                # /dl/1100506130/128/...mp3 -> 128
                match = re.search(r'/dl/\d+/(\d+)/', href)
                if match:
                    quality = match.group(1)
                    urls[quality] = BASE_URL + href
                else:
                    # /dl/1100506130/...mp3 -> качество по умолчанию
                    urls['default'] = BASE_URL + href
            
            if not urls:
                continue
            
            # Выбираем лучший URL: max quality > default
            if urls:
                qualities = [q for q in urls.keys() if q.isdigit()]
                if qualities:
                    best_quality = max(qualities, key=int)
                    best_url = urls[best_quality]
                else:
                    best_url = urls['default']
                    best_quality = 'default'
            else:
                continue
            
            tracks.append({
                'artist': artist,
                'title': title,
                'name': f"{artist} - {title}",
                'duration': duration,
                'url': best_url,
                'quality': best_quality,
            })
            
        except (json.JSONDecodeError, KeyError) as e:
            continue
    
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
    print("    ZVUKOFON MUSIC DOWNLOADER")
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
    
    # Выводим список
    for i, track in enumerate(tracks, 1):
        dur = f" [{track['duration']}]" if track['duration'] else ""
        qual = f" ({track['quality']}kbps)" if track['quality'].isdigit() else ""
        print(f"{i}. {track['name']}{dur}{qual}")
        print(f"   {track['url']}")
    
    # Скачивание
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
            
            print(f"\n🎵 {filename} {track['duration']} ({track['quality']}kbps)")
            if download_file(track['url'], filepath):
                ok += 1
        
        print(f"\n✅ Скачано: {ok}/{len(to_download)}")
        
        another = input("\n📥 Ещё? (y/n): ").strip().lower()
        if another != 'y':
            break

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
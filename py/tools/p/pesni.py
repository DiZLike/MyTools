# ССЫЛКИ НЕ СООТВЕТСТВУЮТ ТРЕКАМ

import os
import re
import json
import asyncio
import aiohttp
from urllib.parse import quote
from bs4 import BeautifulSoup

BASE_URL = "https://music.pesni.me"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
MAX_TRACKS = 100
MAX_CONCURRENT = 10  # Количество одновременных запросов

def sanitize_filename(filename: str) -> str:
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200] if len(filename) > 200 else filename

async def fetch(session, url, timeout=30):
    """Асинхронный GET запрос"""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            return await response.text()
    except:
        return None

async def parse_track_page(session, track_info, semaphore):
    """Асинхронно парсит страницу одного трека"""
    async with semaphore:
        try:
            html = await fetch(session, track_info['page_url'], timeout=15)
            if not html:
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Ищем JSON-LD
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string)
                    if data.get('@type') == 'MusicRecording':
                        if 'name' in data and data['name']:
                            track_info['name'] = data['name']
                        if 'byArtist' in data:
                            artists = data['byArtist']
                            if isinstance(artists, list) and artists:
                                track_info['artist'] = artists[0].get('name', track_info['artist'])
                            elif isinstance(artists, dict):
                                track_info['artist'] = artists.get('name', track_info['artist'])
                        
                        duration = data.get('duration', '')
                        if duration.startswith('PT'):
                            duration = duration[2:]
                            minutes = re.search(r'(\d+)M', duration)
                            seconds = re.search(r'(\d+)S', duration)
                            if minutes and seconds:
                                track_info['duration'] = f"{minutes.group(1)}:{seconds.group(1)}"
                        
                        # Ищем MP3 в JSON-LD
                        mp3_url = data.get('contentUrl') or data.get('url')
                        
                        if not mp3_url and 'associatedMedia' in data:
                            media = data['associatedMedia']
                            if isinstance(media, list) and media:
                                mp3_url = media[0].get('contentUrl', '')
                            elif isinstance(media, dict):
                                mp3_url = media.get('contentUrl', '')
                        
                        # Если нашли в JSON - отлично
                        if mp3_url and track_info.get('name'):
                            # Очищаем URL от экранирования
                            mp3_url = mp3_url.replace('\\/', '/').rstrip('\\')
                            return {
                                'name': track_info['name'],
                                'artist': track_info['artist'],
                                'duration': track_info.get('duration', ''),
                                'url': mp3_url,
                                'page_url': track_info['page_url']
                            }
                except:
                    pass
            
            # Если JSON не дал результат, ищем по всему HTML
            # Но теперь с приоритетами:
            
            # 1. Ищем audio/source теги
            audio_tags = soup.find_all(['audio', 'source'])
            for tag in audio_tags:
                src = tag.get('src', '')
                if '.mp3' in src:
                    return {
                        'name': track_info['name'],
                        'artist': track_info['artist'],
                        'duration': track_info.get('duration', ''),
                        'url': src,
                        'page_url': track_info['page_url']
                    }
            
            # 2. Ищем data-url атрибуты
            elements_with_url = soup.find_all(attrs={'data-url': re.compile(r'\.mp3')})
            for elem in elements_with_url:
                url = elem.get('data-url', '')
                if url:
                    return {
                        'name': track_info['name'],
                        'artist': track_info['artist'],
                        'duration': track_info.get('duration', ''),
                        'url': url,
                        'page_url': track_info['page_url']
                    }
            
            # 3. Ищем ВСЕ MP3 ссылки в HTML, но выбираем ПЕРВУЮ
            # (обычно первая ссылка на странице - это текущий трек)
            all_mp3 = re.findall(r'https?://[^"\'\s]+\.mp3[^"\'\s]*', html)
            if all_mp3:
                # Очищаем и берём первую ссылку
                mp3_url = all_mp3[0].replace('\\/', '/').rstrip('\\')
                if track_info.get('name'):
                    return {
                        'name': track_info['name'],
                        'artist': track_info['artist'],
                        'duration': track_info.get('duration', ''),
                        'url': mp3_url,
                        'page_url': track_info['page_url']
                    }
            
            return None
            
        except Exception as e:
            print(f"      ❌ Ошибка: {track_info['name'][:30]} - {e}")
            return None

async def get_tracks_from_search(query: str):
    """Асинхронный сбор треков"""
    result = {"tracks": [], "success": False, "error": ""}
    
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # Загружаем главную страницу
            await fetch(session, BASE_URL + "/", timeout=10)
            
            # Загружаем страницу поиска
            encoded_query = quote(query.strip(), safe='')
            search_url = f"{BASE_URL}/search/{encoded_query}?type=tracks"
            html = await fetch(session, search_url, timeout=30)
            
            if not html:
                result["error"] = "Не удалось загрузить страницу поиска"
                return result
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Собираем ссылки на треки
            track_links = []
            seen_urls = set()
            
            for a in soup.find_all('a', href=re.compile(r'/track/\d+')):
                if len(track_links) >= MAX_TRACKS:
                    break
                
                href = a.get('href', '')
                full_url = BASE_URL + href
                
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)
                
                track_name = a.get_text(strip=True)
                artist = query
                
                parent = a.find_parent(['div', 'li', 'tr'])
                if parent:
                    full_text = parent.get_text(separator='|', strip=True)
                    parts = full_text.split('|')
                    for part in parts:
                        if ' - ' in part:
                            potential_artist, potential_track = part.split(' - ', 1)
                            if query.lower() in potential_artist.lower():
                                artist = potential_artist.strip()
                                track_name = potential_track.strip()
                                break
                
                track_links.append({
                    'name': track_name,
                    'artist': artist,
                    'page_url': full_url
                })
            
            if not track_links:
                result["error"] = "Треки не найдены"
                return result
            
            print(f"   Найдено треков: {len(track_links)} (ограничение: {MAX_TRACKS})")
            print(f"   Параллельная обработка (макс. {MAX_CONCURRENT} одновременных запросов)...")
            
            # Создаем семафор для ограничения конкурентности
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            
            # Запускаем параллельную обработку всех треков
            tasks = [parse_track_page(session, track, semaphore) for track in track_links]
            
            # Отслеживаем прогресс
            completed = 0
            total = len(tasks)
            
            for coro in asyncio.as_completed(tasks):
                track_data = await coro
                completed += 1
                if track_data:
                    result["tracks"].append(track_data)
                    print(f"\r   Прогресс: {completed}/{total} ({len(result['tracks'])} с MP3)", end='', flush=True)
                else:
                    print(f"\r   Прогресс: {completed}/{total} ({len(result['tracks'])} с MP3)", end='', flush=True)
            
            print()  # Новая строка после прогресс-бара
        
        result["success"] = len(result["tracks"]) > 0
        
    except Exception as e:
        result["error"] = f"Ошибка: {e}"
    
    return result

def download_file(url: str, filepath: str):
    """Скачивает файл (синхронно, так как обычно качаем по одному)"""
    try:
        import requests
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
    print("         ЗАГРУЗЧИК МУЗЫКИ С PESNI.ME (АСИНХРОННЫЙ)")
    print("=" * 80)
    
    query = input("\n🔍 Введите название группы или исполнителя: ").strip()
    if not query:
        print("❌ Пустой запрос!")
        return
    
    print(f"\n🔍 Ищем: '{query}'...")
    
    # Запускаем асинхронный поиск
    search_result = asyncio.run(get_tracks_from_search(query))
    
    if not search_result["success"]:
        print(f"❌ Ошибка: {search_result['error']}")
        return
    
    all_tracks = search_result["tracks"]
    
    print(f"\n✅ Найдено треков с MP3: {len(all_tracks)}\n")
    print("=" * 80)
    
    for i, track in enumerate(all_tracks, 1):
        dur = f" ({track['duration']})" if track.get('duration') else ""
        print(f"{i}. {track['artist']} - {track['name']}{dur}")
        print(f"   🔗 {track['url'][:100]}")
    
    print("=" * 80)
    
    while True:
        print("\n📥 Команды: 'all', 1,3,5-7, 'save', 'q'")
        choice = input("\n👉 Ваш выбор: ").strip().lower()
        
        if choice == 'q':
            print("👋 Выход.")
            break
        
        if choice == 'save':
            filename = f"tracks_{sanitize_filename(query)}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                for i, t in enumerate(all_tracks, 1):
                    f.write(f"{i}. {t['artist']} - {t['name']} ({t.get('duration', '')})\n")
                    f.write(f"{t['url']}\n\n")
            print(f"✅ Сохранено в {filename}")
            continue
        
        if choice == 'all':
            indices = set(range(1, len(all_tracks) + 1))
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
        
        tracks_to_download = [all_tracks[i-1] for i in sorted(indices) if 1 <= i <= len(all_tracks)]
        
        if not tracks_to_download:
            print("❌ Ничего не выбрано")
            continue
        
        print(f"\n📥 Скачивание {len(tracks_to_download)} треков...")
        download_dir = f"downloads_{sanitize_filename(query)}"
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
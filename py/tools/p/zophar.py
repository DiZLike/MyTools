import os
import re
import asyncio
import aiohttp
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Конфигурация
BASE_URL = "https://www.zophar.net"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
MAX_GAMES = 50  # Максимум игр для обработки
MAX_CONCURRENT = 10  # Количество одновременных запросов

def sanitize_filename(filename: str) -> str:
    """Очистка имени файла от недопустимых символов"""
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200] if len(filename) > 200 else filename

async def fetch(session, url, timeout=30):
    """Асинхронный GET запрос"""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            response.raise_for_status()
            return await response.text()
    except Exception as e:
        print(f"      Ошибка запроса: {url[:80]} - {e}")
        return None

async def search_games(session, query):
    """Поиск игр на Zophar's Domain"""
    result = {"games": [], "success": False, "error": ""}
    
    if len(query.strip()) < 3:
        result["error"] = "Слишком короткий поисковый запрос (минимум 3 символа)"
        return result
    
    try:
        html = await fetch(session, f"{BASE_URL}/music/search?search={query}")
        if not html:
            result["error"] = "Не удалось загрузить результаты поиска"
            return result
        
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.select_one("table#gamelist")
        
        if not table:
            result["error"] = "Таблица с результатами не найдена"
            return result
        
        rows = table.select("tr:not(.headerrow)")[:MAX_GAMES]
        
        for row in rows:
            try:
                name_cell = row.select_one("td.name")
                if not name_cell:
                    continue
                
                link = name_cell.find("a")
                if not link:
                    continue
                
                game_url = urljoin(BASE_URL, link.get("href", ""))
                game_name = link.get_text(strip=True)
                
                console_cell = row.select_one("td.console")
                console = console_cell.get_text(strip=True) if console_cell else "Unknown"
                
                result["games"].append({
                    "name": game_name,
                    "url": game_url,
                    "console": console
                })
                
            except Exception as e:
                print(f"      Ошибка при парсинге строки: {e}")
                continue
        
        result["success"] = True
        
    except Exception as e:
        result["error"] = f"Ошибка: {e}"
    
    return result

async def get_tracks_from_game(session, game, semaphore):
    """Асинхронно получает MP3 треки со страницы игры"""
    async with semaphore:
        game_name = game['name']
        console = game['console']
        tracks = []
        
        try:
            html = await fetch(session, game['url'], timeout=15)
            if not html:
                return game_name, console, []
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Ищем таблицу с треками
            track_table = soup.select_one("table#tracklist")
            if not track_table:
                return game_name, console, []
            
            rows = track_table.select("tr.trackrow")
            
            for row in rows:
                try:
                    # Номер трека
                    number_cell = row.select_one("td.number")
                    track_number = number_cell.get_text(strip=True).replace(".", "") if number_cell else ""
                    
                    # Название трека
                    name_cell = row.select_one("td.name")
                    track_name = name_cell.get_text(strip=True) if name_cell else f"Track {track_number}"
                    
                    # Длительность
                    length_cell = row.select_one("td.length")
                    duration = length_cell.get_text(strip=True) if length_cell else ""
                    
                    # Ссылка на скачивание MP3
                    download_cell = row.select_one("td.download")
                    if download_cell:
                        download_link = download_cell.find("a")
                        if download_link and download_link.get("href"):
                            mp3_url = urljoin(BASE_URL, download_link.get("href"))
                            
                            if mp3_url.lower().endswith('.mp3'):
                                tracks.append({
                                    "number": track_number,
                                    "name": track_name,
                                    "duration": duration,
                                    "url": mp3_url,
                                    "game": game_name,
                                    "platform": console
                                })
                    
                except Exception as e:
                    print(f"      Ошибка при парсинге трека: {e}")
                    continue
            
        except Exception as e:
            print(f"      Ошибка обработки игры {game_name}: {e}")
        
        return game_name, console, tracks

async def get_all_tracks(query):
    """Асинхронный сбор всех треков"""
    result = {"tracks": [], "success": False, "error": ""}
    
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # Поиск игр
            print(f"\n🔍 Ищем игры: '{query}'...")
            search_result = await search_games(session, query)
            
            if not search_result["success"]:
                result["error"] = search_result["error"]
                return result
            
            games = search_result["games"]
            
            if not games:
                result["error"] = "Игры не найдены"
                return result
            
            print(f"✅ Найдено игр: {len(games)}")
            print(f"📡 Параллельный сбор треков (макс. {MAX_CONCURRENT} одновременных запросов)...")
            
            # Создаем семафор для ограничения конкурентности
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            
            # Запускаем параллельную обработку всех игр
            tasks = [get_tracks_from_game(session, game, semaphore) for game in games]
            
            # Отслеживаем прогресс
            completed = 0
            total = len(tasks)
            
            for coro in asyncio.as_completed(tasks):
                game_name, console, tracks = await coro
                completed += 1
                
                if tracks:
                    result["tracks"].extend(tracks)
                    print(f"\r   Прогресс: {completed}/{total} - {game_name[:30]} ({console}) ✅ {len(tracks)} треков", end='', flush=True)
                else:
                    print(f"\r   Прогресс: {completed}/{total} - {game_name[:30]} ({console}) ⚠️ нет MP3", end='', flush=True)
            
            print()  # Новая строка после прогресс-бара
        
        result["success"] = len(result["tracks"]) > 0
        
    except Exception as e:
        result["error"] = f"Ошибка: {e}"
    
    return result

def download_file(url: str, filepath: str):
    """Скачивает файл (синхронно)"""
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
    print("         ЗАГРУЗЧИК МУЗЫКИ С ZOPHAR (АСИНХРОННЫЙ)")
    print("=" * 80)
    
    query = input("\n🔍 Введите название игры: ").strip()
    if not query:
        print("❌ Пустой запрос!")
        return
    
    # Запускаем асинхронный сбор треков
    search_result = asyncio.run(get_all_tracks(query))
    
    if not search_result["success"]:
        print(f"❌ Ошибка: {search_result['error']}")
        return
    
    all_tracks = search_result["tracks"]
    
    print(f"\n✅ Всего собрано треков: {len(all_tracks)}\n")
    print("=" * 80)
    
    for i, track in enumerate(all_tracks, 1):
        if track["number"]:
            display_name = f"{track['number']}. {track['name']}"
        else:
            display_name = track['name']
        
        print(f"{i}. {display_name} ({track['duration']}) [{track['game']} | {track['platform']}]")
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
                for track in all_tracks:
                    if track["number"]:
                        f.write(f"{track['number']}. {track['name']} ({track['duration']}) [{track['game']} | {track['platform']}]\n")
                    else:
                        f.write(f"{track['name']} ({track['duration']}) [{track['game']} | {track['platform']}]\n")
                    f.write(f"{track['url']}\n\n")
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
            # Формируем имя файла
            filename = f"{track['game']} - {track['platform']}"
            if track["number"]:
                filename += f" - {track['number']}. {track['name']}"
            else:
                filename += f" - {track['name']}"
            filename = sanitize_filename(filename) + ".mp3"
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
        
        print(f"\n✅ Скачано {downloaded} из {len(tracks_to_download)}")
        
        another = input("\n📥 Скачать ещё треки из этого списка? (y/n): ").strip().lower()
        if another != 'y':
            print("👋 Выход.")
            break

if __name__ == "__main__":
    main()
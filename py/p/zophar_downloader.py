import os
import re
import json
import asyncio
import aiohttp
import aiofiles
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup

BASE_URL = "https://www.zophar.net"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
MAX_CONCURRENT_GAMES = 5
MAX_CONCURRENT_DOWNLOADS = 10
DOWNLOAD_DIR = "downloads"
PROGRESS_UPDATE_INTERVAL = 5  # секунд между обновлением сводки

def sanitize_filename(filename: str) -> str:
    """Очистка имени файла"""
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200] if len(filename) > 200 else filename

def format_size(size_bytes):
    """Форматирование размера в читаемый вид"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def format_time(seconds):
    """Форматирование времени"""
    if seconds < 60:
        return f"{seconds:.0f}с"
    elif seconds < 3600:
        return f"{seconds/60:.0f}м"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}ч {minutes}м"

def is_game_downloaded(platform_slug, game_slug):
    """Проверяет, скачана ли игра полностью"""
    game_dir = os.path.join(DOWNLOAD_DIR, platform_slug, game_slug)
    info_path = os.path.join(game_dir, "info.json")
    
    if not os.path.exists(info_path):
        return False
    
    try:
        with open(info_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        for track in metadata.get("tracks", []):
            num = track.get('number', '')
            prefix = f"{num:02d} - " if num else ""
            filename = sanitize_filename(f"{prefix}{track['name']}.mp3")
            if not os.path.exists(os.path.join(game_dir, filename)):
                return False
        
        for sfx in metadata.get("sfx", []):
            filename = sanitize_filename(f"{sfx['name']}.mp3")
            if not os.path.exists(os.path.join(game_dir, "sfx", filename)):
                return False
        
        if metadata.get("archives", {}).get("emu_zip"):
            archive_path = os.path.join(game_dir, f"{game_slug}_original.zip")
            if not os.path.exists(archive_path):
                return False
        
        if metadata.get("cover_url"):
            for ext in ['.jpg', '.png', '.gif']:
                if os.path.exists(os.path.join(game_dir, f"cover{ext}")):
                    break
            else:
                return False
        
        return True
    except:
        return False

async def fetch(session, url, timeout=30):
    """GET запрос"""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            response.raise_for_status()
            return await response.text()
    except:
        return None

async def download_file(session, url, filepath):
    """Простое скачивание файла без прогресса"""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as response:
            response.raise_for_status()
            async with aiofiles.open(filepath, 'wb') as f:
                async for chunk in response.content.iter_chunked(8192):
                    await f.write(chunk)
        return True
    except:
        if os.path.exists(filepath):
            os.remove(filepath)
        return False

class ProgressTracker:
    """Отслеживание общего прогресса"""
    def __init__(self, total_games):
        self.total_games = total_games
        self.completed = 0
        self.success = 0
        self.skipped = 0
        self.errors = 0
        self.total_tracks = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.lock = asyncio.Lock()
    
    async def add_result(self, status, tracks_count=0):
        async with self.lock:
            self.completed += 1
            if status == 'success':
                self.success += 1
                self.total_tracks += tracks_count
            elif status == 'skipped':
                self.skipped += 1
            elif status == 'error':
                self.errors += 1
            
            # Выводим сводку каждые N секунд или каждые 10 игр
            current_time = time.time()
            if (current_time - self.last_update_time > PROGRESS_UPDATE_INTERVAL or 
                self.completed % 10 == 0 or 
                self.completed == self.total_games):
                
                await self.print_progress()
                self.last_update_time = current_time
    
    async def print_progress(self):
        elapsed = time.time() - self.start_time
        percent = (self.completed / self.total_games * 100) if self.total_games > 0 else 0
        
        # Скорость обработки
        speed = self.completed / (elapsed / 60) if elapsed > 0 else 0
        
        # Оставшееся время
        if speed > 0:
            remaining_games = self.total_games - self.completed
            remaining_time = (remaining_games / speed) * 60
            eta = format_time(remaining_time)
        else:
            eta = "..."
        
        # Прогресс-бар
        bar_length = 30
        filled = int(bar_length * self.completed / self.total_games) if self.total_games > 0 else 0
        bar = '█' * filled + '░' * (bar_length - filled)
        
        status_line = (
            f"\r📊 [{bar}] {percent:.1f}% | "
            f"Игр: {self.completed}/{self.total_games} | "
            f"Треков: {self.total_tracks} | "
            f"⏭️ {self.skipped} | ❌ {self.errors} | "
            f"⚡ {speed:.1f} игр/мин | "
            f"Осталось: {eta} | "
            f"Прошло: {format_time(elapsed)}"
        )
        
        # Очищаем строку и выводим
        print(f"\r{' ' * 120}", end='', flush=True)
        print(status_line, end='', flush=True)
        
        if self.completed == self.total_games:
            print()  # Финальный перевод строки

async def parse_game_page(session, game_url, platform_slug, download_semaphore, game_num, progress):
    """Парсинг страницы игры и скачивание всего"""
    
    game_slug_from_url = game_url.rstrip('/').split('/')[-1]
    
    # Проверяем, скачана ли уже игра
    if is_game_downloaded(platform_slug, game_slug_from_url):
        print(f"  ⏭️ [{game_num}/{progress.total_games}] {game_slug_from_url} — уже скачана")
        await progress.add_result('skipped')
        return
    
    html = await fetch(session, game_url)
    if not html:
        print(f"  ❌ [{game_num}/{progress.total_games}] {game_slug_from_url} — ошибка загрузки страницы")
        await progress.add_result('error')
        return
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # --- Название игры ---
    title_tag = soup.select_one("#music_info h2")
    game_title = title_tag.get_text(strip=True) if title_tag else game_slug_from_url
    game_slug = sanitize_filename(game_title)
    
    # --- Метаданные ---
    metadata = {"title": game_title, "url": game_url}
    for p in soup.select("#music_info p"):
        name_span = p.select_one(".infoname")
        data_span = p.select_one(".infodata")
        if name_span and data_span:
            key = name_span.get_text(strip=True).rstrip(':').lower().replace(' ', '_')
            value = data_span.get_text(strip=True)
            links = [urljoin(BASE_URL, a.get('href')) for a in data_span.find_all('a', href=True)]
            metadata[key] = {"text": value, "links": links}
    
    # --- Обложка ---
    cover_img = soup.select_one("#music_cover img")
    cover_url = urljoin(BASE_URL, cover_img.get('src')) if cover_img else None
    metadata["cover_url"] = cover_url
    
    # --- Архивы ---
    mass_download = soup.select_one("#mass_download")
    archives = {}
    if mass_download:
        for a in mass_download.find_all('a', href=True):
            text = a.get_text(strip=True)
            url = urljoin(BASE_URL, a.get('href'))
            if 'original' in text.lower() or 'emu' in text.lower():
                archives['emu_zip'] = url
    metadata["archives"] = archives
    
    # --- Треки ---
    tracks = []
    sfx = []
    
    for row in soup.select("#tracklist tr"):
        if not row.select_one("td.download"):
            continue
        
        number_cell = row.select_one("td.number")
        name_cell = row.select_one("td.name")
        length_cell = row.select_one("td.length")
        download_cell = row.select_one("td.download a")
        
        track_number = number_cell.get_text(strip=True).rstrip('.') if number_cell else ""
        track_name = name_cell.get_text(strip=True) if name_cell else "Unknown"
        duration = length_cell.get_text(strip=True) if length_cell else ""
        track_url = urljoin(BASE_URL, download_cell.get('href')) if download_cell else None
        
        track_data = {
            "name": track_name,
            "duration": duration,
            "url": track_url
        }
        
        if track_number:
            track_data["number"] = int(track_number)
            tracks.append(track_data)
        else:
            sfx.append(track_data)
    
    metadata["tracks"] = tracks
    metadata["sfx"] = sfx
    
    total_tracks = len(tracks) + len(sfx)
    
    # --- Создание папок ---
    game_dir = os.path.join(DOWNLOAD_DIR, platform_slug, game_slug)
    os.makedirs(game_dir, exist_ok=True)
    
    # --- Подготовка списка файлов для скачивания ---
    files_to_download = []
    
    # Обложка
    if cover_url:
        ext = os.path.splitext(cover_url)[1] or '.jpg'
        cover_path = os.path.join(game_dir, f"cover{ext}")
        if not os.path.exists(cover_path):
            files_to_download.append(('cover', cover_url, cover_path))
    
    # Архив
    for archive_type, archive_url in archives.items():
        if archive_url:
            archive_path = os.path.join(game_dir, f"{game_slug}_original.zip")
            if not os.path.exists(archive_path):
                files_to_download.append(('archive', archive_url, archive_path))
    
    # Треки
    for track in tracks:
        num = track.get('number', '')
        prefix = f"{num:02d} - " if num else ""
        filename = sanitize_filename(f"{prefix}{track['name']}.mp3")
        filepath = os.path.join(game_dir, filename)
        if not os.path.exists(filepath):
            files_to_download.append(('track', track["url"], filepath))
    
    # SFX
    if sfx:
        sfx_dir = os.path.join(game_dir, "sfx")
        os.makedirs(sfx_dir, exist_ok=True)
        for track in sfx:
            filename = sanitize_filename(f"{track['name']}.mp3")
            filepath = os.path.join(sfx_dir, filename)
            if not os.path.exists(filepath):
                files_to_download.append(('sfx', track["url"], filepath))
    
    total_files = len(files_to_download)
    
    # --- Скачивание ---
    if total_files > 0:
        async def download_with_semaphore(file_type, url, path):
            async with download_semaphore:
                return await download_file(session, url, path)
        
        tasks = [download_with_semaphore(ft, url, path) for ft, url, path in files_to_download]
        results = await asyncio.gather(*tasks)
        success_count = sum(1 for r in results if r)
    else:
        success_count = 0
    
    # --- Сохранение info.json ---
    if total_files == 0 or success_count == total_files:
        info_path = os.path.join(game_dir, "info.json")
        async with aiofiles.open(info_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(metadata, indent=2, ensure_ascii=False))
        
        details = f"{len(tracks)} треков"
        if sfx:
            details += f", {len(sfx)} SFX"
        if archives:
            details += ", архив"
        if cover_url:
            details += ", обложка"
        
        print(f"  ✅ [{game_num}/{progress.total_games}] {game_title} — {details}")
        await progress.add_result('success', total_tracks)
    else:
        print(f"  ⚠️ [{game_num}/{progress.total_games}] {game_title} — скачано {success_count}/{total_files}")
        await progress.add_result('error')

async def get_total_pages(session, platform_url):
    """Определяет количество страниц для платформы"""
    html = await fetch(session, platform_url)
    if not html:
        return 1
    
    soup = BeautifulSoup(html, 'html.parser')
    
    max_page = 1
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if 'page=' in href:
            try:
                page_num = int(href.split('page=')[-1])
                max_page = max(max_page, page_num)
            except:
                pass
    
    return max_page

async def get_game_links_from_page(session, platform_url, page_num):
    """Собирает ссылки на игры с конкретной страницы"""
    url = f"{platform_url}?page={page_num}" if page_num > 1 else platform_url
    
    html = await fetch(session, url)
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.select_one("table#gamelist")
    
    if not table:
        return []
    
    game_links = []
    for row in table.select("tr:not(.headerrow)"):
        name_cell = row.select_one("td.name")
        if name_cell:
            link = name_cell.find("a")
            if link:
                game_url = urljoin(BASE_URL, link.get("href"))
                game_links.append(game_url)
    
    return game_links

async def download_platform(platform_url, platform_name=None):
    """Скачивание всех игр платформы"""
    
    platform_slug = platform_url.rstrip('/').split('/')[-1]
    
    print("=" * 80)
    print(f"🎮 ПЛАТФОРМА: {platform_name or platform_slug}")
    print(f"   URL: {platform_url}")
    print("=" * 80)
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Определяем количество страниц
        print("\n📊 Определение количества страниц...")
        total_pages = await get_total_pages(session, platform_url)
        print(f"   Найдено страниц: {total_pages}")
        
        # Собираем ссылки на все игры
        print("\n📋 Сбор списка игр...")
        all_game_links = []
        
        for page_num in range(1, total_pages + 1):
            page_links = await get_game_links_from_page(session, platform_url, page_num)
            all_game_links.extend(page_links)
            print(f"   Стр. {page_num}/{total_pages}: найдено {len(page_links)} игр (всего: {len(all_game_links)})")
        
        total_games = len(all_game_links)
        print(f"\n   Всего игр: {total_games}")
        
        # Проверяем уже скачанные
        downloaded_count = 0
        for game_url in all_game_links:
            game_slug = game_url.rstrip('/').split('/')[-1]
            if is_game_downloaded(platform_slug, game_slug):
                downloaded_count += 1
        
        print(f"   Уже скачано: {downloaded_count}")
        print(f"   Осталось скачать: {total_games - downloaded_count}")
        
        if downloaded_count == total_games:
            print("\n✅ Все игры уже скачаны!")
            return
        
        # Инициализируем трекер прогресса
        progress = ProgressTracker(total_games)
        
        print(f"\n🚀 Начинаем скачивание...")
        print(f"   Одновременно игр: {MAX_CONCURRENT_GAMES}")
        print(f"   Одновременно загрузок: {MAX_CONCURRENT_DOWNLOADS}")
        print("=" * 80)
        
        download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        
        # Запускаем параллельную обработку игр
        tasks = []
        for i, game_url in enumerate(all_game_links, 1):
            task = parse_game_page(
                session, game_url, platform_slug,
                download_semaphore, i, progress
            )
            tasks.append(task)
        
        # Ограничиваем количество одновременных игр через gather с чанками
        for i in range(0, len(tasks), MAX_CONCURRENT_GAMES):
            chunk = tasks[i:i + MAX_CONCURRENT_GAMES]
            await asyncio.gather(*chunk, return_exceptions=True)
        
        # Финальный прогресс
        await progress.print_progress()
        print("\n\n" + "=" * 80)
        print("✅ Скачивание платформы завершено!")
        print("=" * 80)

async def main():
    """Главная функция"""
    
    platforms = {
        "1": {"name": "Nintendo NES (NSF)", "url": "https://www.zophar.net/music/nintendo-nes-nsf"},
        "2": {"name": "Nintendo SNES (SPC)", "url": "https://www.zophar.net/music/nintendo-snes-spc"},
        "3": {"name": "Gameboy (GBS)", "url": "https://www.zophar.net/music/gameboy-gbs"},
        "4": {"name": "Gameboy Advance (GSF)", "url": "https://www.zophar.net/music/gameboy-advance-gsf"},
        "5": {"name": "Nintendo DS (2SF)", "url": "https://www.zophar.net/music/nintendo-ds-2sf"},
        "6": {"name": "Nintendo 3DS (3SF)", "url": "https://www.zophar.net/music/nintendo-3ds-3sf"},
        "7": {"name": "Nintendo 64 (USF)", "url": "https://www.zophar.net/music/nintendo-64-usf"},
        "8": {"name": "Nintendo Gamecube (GCN)", "url": "https://www.zophar.net/music/nintendo-gamecube-gcn"},
        "9": {"name": "Nintendo Wii", "url": "https://www.zophar.net/music/nintendo-wii"},
        "10": {"name": "Playstation (PSF)", "url": "https://www.zophar.net/music/playstation-psf"},
        "11": {"name": "PSP", "url": "https://www.zophar.net/music/playstation-portable-psp"},
        "12": {"name": "Sega Game Gear (SGC)", "url": "https://www.zophar.net/music/sega-game-gear-sgc"},
        "13": {"name": "Sega Master System (VGM)", "url": "https://www.zophar.net/music/sega-master-system-vgm"},
        "14": {"name": "Sega Genesis / Mega Drive", "url": "https://www.zophar.net/music/sega-mega-drive-genesis"},
        "15": {"name": "Sega Saturn (SSF)", "url": "https://www.zophar.net/music/sega-saturn-ssf"},
        "16": {"name": "TurboGrafx-16 (HES)", "url": "https://www.zophar.net/music/turbografx-16-hes"},
        "17": {"name": "Amiga", "url": "https://www.zophar.net/music/amiga"},
        "18": {"name": "Arcade", "url": "https://www.zophar.net/music/arcade"},
        "19": {"name": "Atari ST", "url": "https://www.zophar.net/music/atari-st"},
        "20": {"name": "Atari 8-Bit", "url": "https://www.zophar.net/music/atari-8bit"},
        "21": {"name": "Commodore 64", "url": "https://www.zophar.net/music/commodore-64"},
        "22": {"name": "FM Towns", "url": "https://www.zophar.net/music/fm-towns"},
        "23": {"name": "MS-DOS", "url": "https://www.zophar.net/music/ms-dos"},
        "24": {"name": "MSX2", "url": "https://www.zophar.net/music/msx2"},
        "25": {"name": "PC-88", "url": "https://www.zophar.net/music/pc-8801"},
        "26": {"name": "PC-98", "url": "https://www.zophar.net/music/pc-9801"},
        "27": {"name": "Philips CD-i", "url": "https://www.zophar.net/music/cd-i"},
        "28": {"name": "Sharp X1", "url": "https://www.zophar.net/music/sharp-x1"},
        "29": {"name": "Windows", "url": "https://www.zophar.net/music/windows"},
        "30": {"name": "X68000", "url": "https://www.zophar.net/music/x68000"},
        "31": {"name": "ZX Spectrum", "url": "https://www.zophar.net/music/spectrum"},
    }
    
    print("=" * 80)
    print("         ЗАГРУЗЧИК МУЗЫКИ С ZOPHAR (ПО ПЛАТФОРМАМ)")
    print("=" * 80)
    
    print("\n📋 Доступные платформы:")
    for key, platform in platforms.items():
        print(f"  {key:2s}. {platform['name']}")
    
    print("\n" + "-" * 80)
    choice = input("\n👉 Выберите платформу (номер или 'all' для всех): ").strip()
    
    if choice.lower() == 'all':
        for key, platform in platforms.items():
            await download_platform(platform["url"], platform["name"])
            print("\n⏸️ Пауза 5 секунд перед следующей платформой...")
            await asyncio.sleep(5)
    elif choice in platforms:
        platform = platforms[choice]
        await download_platform(platform["url"], platform["name"])
    else:
        print("❌ Неверный выбор!")

if __name__ == "__main__":
    asyncio.run(main())
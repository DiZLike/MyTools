import os
import re
import json
import asyncio
import aiohttp
import aiofiles
import time
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from aiohttp_socks import ProxyConnector

BASE_URL = "https://www.zophar.net"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
MAX_CONCURRENT_GAMES = 5
MAX_CONCURRENT_DOWNLOADS = 10
DOWNLOAD_DIR = "downloads"
PROGRESS_UPDATE_INTERVAL = 2
PROXY_URL = "socks5://evgeny:9c7V12n9886020@n.dlike.ru:1080"
ERROR_LOG_FILE = "errors.log"

def log_error(message):
    """Запись ошибки в лог-файл"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ERROR_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")

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
        
        tracks = metadata.get("tracks", [])
        sfx = metadata.get("sfx", [])
        
        if not tracks and not sfx:
            return False
        
        for track in tracks:
            num = track.get('number', '')
            prefix = f"{num:02d} - " if num else ""
            filename = sanitize_filename(f"{prefix}{track['name']}.mp3")
            if not os.path.exists(os.path.join(game_dir, filename)):
                return False
        
        for track in sfx:
            filename = sanitize_filename(f"{track['name']}.mp3")
            if not os.path.exists(os.path.join(game_dir, "sfx", filename)):
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

async def download_file(session, url, filepath, max_retries=3):
    """Скачивание файла с повторными попытками"""
    for attempt in range(max_retries):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as response:
                response.raise_for_status()
                async with aiofiles.open(filepath, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
            return True, None
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
            else:
                error_msg = f"Файл: {os.path.basename(filepath)} | URL: {url} | Ошибка: {str(e)}"
                return False, error_msg
    
    return False, f"Не удалось скачать {url} после {max_retries} попыток"

class ProgressTracker:
    """Отслеживание общего прогресса"""
    def __init__(self, total_games):
        self.total_games = total_games
        self.completed = 0
        self.success = 0
        self.skipped = 0
        self.errors = 0
        self.total_tracks = 0
        self.total_bytes = 0
        self.start_time = time.time()
        self.lock = asyncio.Lock()
    
    async def add_bytes(self, bytes_count):
        """Добавляет байты во время скачивания"""
        async with self.lock:
            self.total_bytes += bytes_count
    
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
    
    async def print_progress(self):
        async with self.lock:
            completed = self.completed
            total_games = self.total_games
            total_tracks = self.total_tracks
            total_bytes = self.total_bytes
            skipped = self.skipped
            errors = self.errors
        
        elapsed = time.time() - self.start_time
        percent = (completed / total_games * 100) if total_games > 0 else 0
        
        games_per_min = completed / (elapsed / 60) if elapsed > 0 else 0
        mb_per_sec = (total_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0
        
        if games_per_min > 0:
            remaining_games = total_games - completed
            remaining_time = (remaining_games / games_per_min) * 60
            eta = format_time(remaining_time)
        else:
            eta = "..."
        
        bar_length = 30
        filled = int(bar_length * completed / total_games) if total_games > 0 else 0
        bar = '█' * filled + '░' * (bar_length - filled)
        
        line1 = (
            f"📊 [{bar}] {percent:.1f}% | "
            f"Игр: {completed}/{total_games} | "
            f"Треков: {total_tracks} | "
            f"⏭️ {skipped} | ❌ {errors}"
        )
        
        line2 = (
            f"💾 Скачано: {format_size(total_bytes)} | "
            f"⚡ {games_per_min:.1f} игр/мин | "
            f"📀 {mb_per_sec:.1f} MB/s | "
            f"⏱️ Прошло: {format_time(elapsed)} | "
            f"🕐 Осталось: {eta}"
        )
        
        print(f"\r\033[K{line1}\n\033[K{line2}", end='', flush=True)
        print(f"\r\033[1A", end='', flush=True)
        
        if completed == total_games:
            print("\n")

async def progress_updater(progress, stop_event):
    """Фоновое обновление прогресса"""
    while not stop_event.is_set():
        await asyncio.sleep(PROGRESS_UPDATE_INTERVAL)
        if not stop_event.is_set():
            await progress.print_progress()

async def parse_game_page(session, game_url, platform_slug, download_semaphore, game_num, progress):
    """Парсинг страницы игры и скачивание всего"""
    
    game_slug = game_url.rstrip('/').split('/')[-1]
    
    # Проверяем, скачана ли уже игра (по slug из URL)
    if is_game_downloaded(platform_slug, game_slug):
        await progress.add_result('skipped')
        return
    
    html = await fetch(session, game_url)
    if not html:
        log_error(f"Не удалось загрузить страницу: {game_url}")
        await progress.add_result('error')
        return
    
    soup = BeautifulSoup(html, 'html.parser')
    
    title_tag = soup.select_one("#music_info h2")
    game_title = title_tag.get_text(strip=True) if title_tag else game_slug
    
    metadata = {"title": game_title, "url": game_url}
    for p in soup.select("#music_info p"):
        name_span = p.select_one(".infoname")
        data_span = p.select_one(".infodata")
        if name_span and data_span:
            key = name_span.get_text(strip=True).rstrip(':').lower().replace(' ', '_')
            value = data_span.get_text(strip=True)
            links = [urljoin(BASE_URL, a.get('href')) for a in data_span.find_all('a', href=True)]
            metadata[key] = {"text": value, "links": links}
    
    cover_img = soup.select_one("#music_cover img")
    cover_url = urljoin(BASE_URL, cover_img.get('src')) if cover_img else None
    metadata["cover_url"] = cover_url
    
    mass_download = soup.select_one("#mass_download")
    archives = {}
    if mass_download:
        for a in mass_download.find_all('a', href=True):
            text = a.get_text(strip=True)
            url = urljoin(BASE_URL, a.get('href'))
            if 'original' in text.lower() or 'emu' in text.lower():
                archives['emu_zip'] = url
    metadata["archives"] = archives
    
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
    
    game_dir = os.path.join(DOWNLOAD_DIR, platform_slug, game_slug)
    os.makedirs(game_dir, exist_ok=True)
    
    # Собираем список файлов для скачивания с информацией о типе
    files_to_download = []
    
    if cover_url:
        ext = os.path.splitext(cover_url.split('?')[0])[1] or '.jpg'
        cover_path = os.path.join(game_dir, f"cover{ext}")
        if not os.path.exists(cover_path):
            files_to_download.append({
                "url": cover_url,
                "path": cover_path,
                "display_name": f"Обложка (cover{ext})"
            })
    
    for archive_key, archive_url in archives.items():
        archive_path = os.path.join(game_dir, f"{game_slug}_original.zip")
        if not os.path.exists(archive_path):
            files_to_download.append({
                "url": archive_url,
                "path": archive_path,
                "display_name": "Архив (original.zip)"
            })
    
    for track in tracks:
        num = track.get('number', '')
        prefix = f"{num:02d} - " if num else ""
        filename = sanitize_filename(f"{prefix}{track['name']}.mp3")
        filepath = os.path.join(game_dir, filename)
        if not os.path.exists(filepath):
            files_to_download.append({
                "url": track["url"],
                "path": filepath,
                "display_name": f"Трек {num}: {track['name']}" if num else f"Трек: {track['name']}"
            })
    
    if sfx:
        sfx_dir = os.path.join(game_dir, "sfx")
        os.makedirs(sfx_dir, exist_ok=True)
        for i, track in enumerate(sfx):
            filename = sanitize_filename(f"{track['name']}.mp3")
            filepath = os.path.join(sfx_dir, filename)
            if not os.path.exists(filepath):
                files_to_download.append({
                    "url": track["url"],
                    "path": filepath,
                    "display_name": f"SFX {i+1}: {track['name']}"
                })
    
    total_files = len(files_to_download)
    failed_downloads = []
    
    if total_files > 0:
        async def download_with_semaphore(file_info):
            async with download_semaphore:
                success, error_msg = await download_file(session, file_info["url"], file_info["path"])
                
                if success and os.path.exists(file_info["path"]):
                    file_size = os.path.getsize(file_info["path"])
                    await progress.add_bytes(file_size)
                    return True, None
                else:
                    return False, error_msg or f"Не удалось скачать: {file_info['display_name']}"
        
        tasks = [download_with_semaphore(file_info) for file_info in files_to_download]
        results = await asyncio.gather(*tasks)
        
        for file_info, (success, error_msg) in zip(files_to_download, results):
            if not success:
                failed_downloads.append({
                    "display_name": file_info["display_name"],
                    "url": file_info["url"],
                    "path": file_info["path"],
                    "error": error_msg
                })
        
        success_count = sum(1 for success, _ in results if success)
    else:
        success_count = 0
    
    # Сохраняем metadata независимо от результата (чтобы знать, что скачивали)
    info_path = os.path.join(game_dir, "info.json")
    async with aiofiles.open(info_path, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(metadata, indent=2, ensure_ascii=False))
    
    if total_files == 0 or len(failed_downloads) == 0:
        await progress.add_result('success', total_tracks)
    else:
        # Детальное логирование ошибок
        error_details = "\n".join([
            f"   • {fd['display_name']}\n     URL: {fd['url']}\n     Причина: {fd['error']}"
            for fd in failed_downloads
        ])
        
        log_error(
            f"Скачано частично: {game_title} ({success_count}/{total_files} файлов)\n"
            f"Не скачаны:\n{error_details}"
        )
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
    print(f"   Прокси: {PROXY_URL}")
    print("=" * 80)
    
    connector = ProxyConnector.from_url(PROXY_URL)
    
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        print("\n📊 Определение количества страниц...")
        total_pages = await get_total_pages(session, platform_url)
        print(f"   Найдено страниц: {total_pages}")
        
        print("\n📋 Сбор списка игр...")
        all_game_links = []
        
        for page_num in range(1, total_pages + 1):
            page_links = await get_game_links_from_page(session, platform_url, page_num)
            all_game_links.extend(page_links)
            print(f"\r   Стр. {page_num}/{total_pages}: найдено {len(page_links)} игр (всего: {len(all_game_links)})", end='', flush=True)
        
        print()
        
        total_games = len(all_game_links)
        print(f"\n   Всего игр: {total_games}")
        
        progress = ProgressTracker(total_games)
        
        print(f"\n🚀 Начинаем скачивание...")
        print(f"   Одновременно игр: {MAX_CONCURRENT_GAMES}")
        print(f"   Одновременно загрузок: {MAX_CONCURRENT_DOWNLOADS}")
        print()
        
        download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        
        stop_event = asyncio.Event()
        updater_task = asyncio.create_task(progress_updater(progress, stop_event))
        
        try:
            tasks = []
            for i, game_url in enumerate(all_game_links, 1):
                task = parse_game_page(
                    session, game_url, platform_slug,
                    download_semaphore, i, progress
                )
                tasks.append(task)
            
            for i in range(0, len(tasks), MAX_CONCURRENT_GAMES):
                chunk = tasks[i:i + MAX_CONCURRENT_GAMES]
                await asyncio.gather(*chunk, return_exceptions=True)
        finally:
            stop_event.set()
            await updater_task
        
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
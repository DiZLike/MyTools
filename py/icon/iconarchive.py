from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import os
import sys
import time
import random
import re
import shutil
import signal
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Event

# === НАСТРОЙКИ ===
BASE_URL = "https://www.iconarchive.com"
DOWNLOAD_DIR = "downloads"
PROGRESS_FILE = "progress.json"
PACKS_INDEX_FILE = "packs_index.json"
FAILED_FILE = "failed_icons.log"
DELAY_MIN = 0.1
DELAY_MAX = 0.3
MAX_WORKERS = 70
FORCE_RECHECK_ERRORS = True
MAX_RETRY_ATTEMPTS = 3

BROWSER = "chrome120"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Referer": "https://www.iconarchive.com/",
}

# Глобальные переменные
print_lock = Lock()
shutdown_event = Event()
save_lock = Lock()
log_lock = Lock()

# Для компактного вывода
console_lock = Lock()
last_error_msg = ""
current_icon_msg = ""
pack_progress_msg = ""
global_progress_msg = ""
speed_msg = ""
download_start_time = time.time()
downloaded_count = 0
downloaded_lock = Lock()

# === УТИЛИТЫ ===

def log(msg):
    """Обычный лог (для важных сообщений)"""
    if shutdown_event.is_set():
        return
    with print_lock:
        sys.stdout.write("\033[K")
        print(f"\n{msg}", flush=True)
        draw_status()

def draw_status():
    """Рисует компактный статус в 5 строк"""
    with console_lock:
        lines = [
            f"┌─ Файл: {current_icon_msg}",
            f"├─ Пак:  {pack_progress_msg}",
            f"├─ Всего: {global_progress_msg}",
            f"├─ Скорость: {speed_msg}",
            f"└─ Ошибка: {last_error_msg}"
        ]
        
        for line in lines:
            sys.stdout.write("\033[K")
            print(line, flush=True)
        
        sys.stdout.write(f"\033[5A")

def update_current_icon(icon_name, status="⏳"):
    global current_icon_msg
    current_icon_msg = f"{status} {icon_name[:80]}"
    draw_status()

def update_pack_progress(current, total, pack_name):
    global pack_progress_msg
    pct = (current / total * 100) if total > 0 else 0
    bar = progress_bar_compact(current, total, 20)
    pack_progress_msg = f"{bar} {pct:.1f}% | {current}/{total} | {pack_name[:40]}"
    draw_status()

def update_global_progress(done_packs, total_packs, current_page, total_pages):
    global global_progress_msg
    global_progress_msg = f"Паков: {done_packs}/{total_packs} | Страница: {current_page}/{total_pages}"
    draw_status()

def update_speed():
    global speed_msg, download_start_time, downloaded_count
    elapsed = time.time() - download_start_time
    if elapsed > 0:
        speed = downloaded_count / (elapsed / 60)
        speed_msg = f"{speed:.1f} файлов/мин | Всего скачано: {downloaded_count}"
    draw_status()

def update_last_error(error_msg):
    global last_error_msg
    last_error_msg = error_msg[:80] if error_msg else ""
    draw_status()

def log_error(error_type, url, details=""):
    """Логирует реальные ошибки в файл"""
    with log_lock:
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(FAILED_FILE, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} | {error_type} | {url} | {details}\n")
        except:
            pass

def progress_bar_compact(current, total, width=20):
    if total == 0:
        return "[" + "░" * width + "]"
    filled = int(width * current / total)
    return "[" + "█" * filled + "░" * (width - filled) + "]"

def safe_save_json(data, filepath):
    with save_lock:
        try:
            os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
            temp_path = filepath + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if os.path.exists(filepath):
                os.replace(temp_path, filepath)
            else:
                os.rename(temp_path, filepath)
        except Exception as e:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except:
                pass

def load_json(filepath):
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            if not content.strip():
                return {}
            return json.loads(content)
    except json.JSONDecodeError as e:
        log(f"⚠️ JSON поврежден: {filepath}")
        backup_path = filepath + f".backup_{int(time.time())}"
        try:
            shutil.copy2(filepath, backup_path)
            log(f"   Бэкап: {backup_path}")
        except:
            pass
        repaired = try_repair_json(filepath)
        if repaired is not None:
            return repaired
        log(f"   Использую пустую структуру")
        return {}
    except Exception as e:
        log(f"❌ Ошибка чтения {filepath}: {e}")
        return {}

def try_repair_json(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        repaired = re.sub(r',\s*}', '}', content)
        repaired = re.sub(r',\s*]', ']', repaired)
        try:
            data = json.loads(repaired)
            log(f"✓ Восстановлен (trailing commas)")
            safe_save_json(data, filepath)
            return data
        except:
            pass
        lines = content.split('\n')
        for i in range(len(lines) - 1, 0, -1):
            partial = '\n'.join(lines[:i]) + '\n}'
            try:
                data = json.loads(partial)
                log(f"✓ Восстановлен частично (до строки {i})")
                safe_save_json(data, filepath)
                return data
            except:
                continue
    except Exception as e:
        log(f"   Ошибка восстановления: {e}")
    return None

def rebuild_progress_from_disk():
    log("🔄 Восстановление прогресса из папки downloads...")
    if not os.path.exists(DOWNLOAD_DIR):
        log("   Папка downloads не найдена")
        return {}
    
    progress = {}
    try:
        for pack_dir in os.listdir(DOWNLOAD_DIR):
            pack_path = os.path.join(DOWNLOAD_DIR, pack_dir)
            if not os.path.isdir(pack_path):
                continue
            
            meta_file = os.path.join(pack_path, "meta.json")
            pack_url = None
            
            if os.path.exists(meta_file):
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        pack_url = meta.get("url")
                except:
                    pass
            
            if not pack_url:
                continue
            
            icons_dir = os.path.join(pack_path, "icons")
            total_icons = 0
            downloaded_icons = 0
            
            if os.path.exists(meta_file):
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        total_icons = meta.get("icons_count", 0)
                        if isinstance(total_icons, str):
                            match = re.search(r'(\d+)', total_icons)
                            total_icons = int(match.group(1)) if match else 0
                except:
                    pass
            
            if os.path.exists(icons_dir):
                icon_files = [f for f in os.listdir(icons_dir) 
                             if f.endswith(('.png', '.svg', '.ico', '.icns'))]
                downloaded_icons = len(icon_files)
                if total_icons == 0:
                    total_icons = downloaded_icons
            
            errors = total_icons - downloaded_icons if total_icons > 0 else 0
            status = "done" if errors == 0 else "done_with_errors"
            
            progress[pack_url] = {
                "status": status,
                "icons_total": total_icons,
                "icons_downloaded": downloaded_icons,
                "errors_count": errors,
                "rebuilt_from_disk": True,
                "rebuilt_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        
        log(f"✓ Восстановлено {len(progress)} паков")
        if progress:
            safe_save_json(progress, PROGRESS_FILE)
            log(f"✓ progress.json пересоздан")
        
        return progress
    except Exception as e:
        log(f"❌ Ошибка при восстановлении: {e}")
        return {}

def is_downloaded(filepath):
    return os.path.exists(filepath) and os.path.getsize(filepath) > 100

def safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()

def sleep():
    if shutdown_event.is_set():
        return
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

# === ОБРАБОТЧИКИ СИГНАЛОВ ===

def signal_handler(signum, frame):
    with print_lock:
        sys.stdout.write("\033[K\n")
    log("⚠️ Получен сигнал остановки (Ctrl+C)")
    log("⏳ Завершаю текущие задачи...")
    shutdown_event.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# === HTTP ===

def create_session():
    if shutdown_event.is_set():
        return None
    s = curl_requests.Session()
    s.headers.update(HEADERS)
    return s

def safe_get(url, retries=3):
    if shutdown_event.is_set():
        return None
    
    session = create_session()
    if not session:
        return None
    
    for attempt in range(retries):
        if shutdown_event.is_set():
            return None
        try:
            sleep()
            resp = session.get(url, impersonate=BROWSER, timeout=30)
            
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                wait = 10 * (attempt + 1)
                update_last_error(f"Rate limit, ждём {wait}с...")
                for _ in range(wait):
                    if shutdown_event.is_set():
                        return None
                    time.sleep(1)
            elif resp.status_code == 404:
                return None
            else:
                time.sleep(random.uniform(1, 2))
        except Exception as e:
            if shutdown_event.is_set():
                return None
            time.sleep(2 * (attempt + 1))
    return None

def download_file(url, filepath, referer):
    """Скачивает файл иконки"""
    if shutdown_event.is_set():
        return False
    
    session = create_session()
    if not session:
        return False
    
    for attempt in range(3):
        if shutdown_event.is_set():
            return False
        try:
            sleep()
            resp = session.get(url, impersonate=BROWSER, timeout=30,
                             headers={"Referer": referer})
            
            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type:
                    return False
                
                if len(resp.content) < 100:
                    return False
                
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                
                global downloaded_count
                with downloaded_lock:
                    downloaded_count += 1
                
                return True
            elif resp.status_code == 429:
                for _ in range(10 * (attempt + 1)):
                    if shutdown_event.is_set():
                        return False
                    time.sleep(1)
            else:
                time.sleep(random.uniform(1, 2))
        except Exception as e:
            if shutdown_event.is_set():
                return False
            time.sleep(2 * (attempt + 1))
    return False

# === ПАРСИНГ ===

def parse_packs_from_page(html):
    soup = BeautifulSoup(html, "html.parser")
    packs = []
    
    for iconset in soup.find_all("div", class_="iconset"):
        a_tag = iconset.find("a", href=True)
        h2 = iconset.find("h2")
        
        if a_tag and h2:
            count_text = iconset.text
            match = re.search(r'(\d+)\s*ICONS', count_text, re.IGNORECASE)
            icons_count = int(match.group(1)) if match else 0
            
            packs.append({
                "title": h2.text.strip(),
                "url": urljoin(BASE_URL, a_tag["href"]),
                "icons_count": icons_count
            })
    
    return packs

def get_total_pages(html):
    soup = BeautifulSoup(html, "html.parser")
    pagination = soup.find("div", class_="paginationnumbers")
    if pagination:
        pages = pagination.find_all("a")
        if pages:
            for page in reversed(pages):
                try:
                    return int(page.text.strip())
                except:
                    continue
    return 1

def parse_pack_meta(html, pack_url):
    soup = BeautifulSoup(html, "html.parser")
    meta = {
        "url": pack_url,
        "author": "",
        "author_url": "",
        "categories": "",
        "style": "",
        "icons_count": 0,
        "license": "",
        "tags": [],
        "icons": []
    }
    
    for td in soup.find_all("td"):
        text = td.text.strip()
        if "Designer:" in text:
            a = td.find("a")
            if a:
                meta["author"] = a.text.strip()
                meta["author_url"] = urljoin(BASE_URL, a.get("href", ""))
            else:
                meta["author"] = text.replace("Designer:", "").strip()
        elif "Categories:" in text:
            meta["categories"] = text.replace("Categories:", "").strip()
        elif "License:" in text:
            meta["license"] = text.replace("License:", "").strip()
    
    intro = soup.find("div", class_="intro")
    if intro:
        match = re.search(r'of\s+(\d+)\s+icons', intro.text)
        if match:
            meta["icons_count"] = int(match.group(1))
    
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.text.strip()
        match = re.match(r'^(.+?)\s+Iconpack', title_text)
        if match:
            meta["title"] = match.group(1)
    
    return meta

def parse_icon_ids_from_pack_page(html):
    soup = BeautifulSoup(html, "html.parser")
    icons = []
    
    for icon_div in soup.find_all("div", class_="icondetail"):
        a_tag = icon_div.find("a", href=True)
        if a_tag:
            icon_url = urljoin(BASE_URL, a_tag["href"])
            if icon_url not in icons:
                icons.append(icon_url)
    
    return icons

def parse_icon_page(html):
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "title": "",
        "tags": [],
        "downloads": []
    }
    
    h1 = soup.find("h1")
    if h1:
        result["title"] = h1.text.strip()
    
    for a in soup.find_all("a", class_="tagbutton"):
        tag = a.text.strip()
        if tag:
            result["tags"].append(tag)
    
    for a in soup.find_all("a", class_="downbutton"):
        href = a.get("href", "")
        text = a.text.strip()
        if href:
            result["downloads"].append({
                "text": text,
                "url": href
            })
    
    return result

# === ЗАГРУЗКА ИКОНКИ ===

def download_icon(icon_data):
    if shutdown_event.is_set():
        return None
    
    icon_url = icon_data['icon_url']
    icon_name = icon_data['icon_name']
    icons_dir = icon_data['icons_dir']
    pack_url = icon_data['pack_url']
    icon_idx = icon_data['icon_idx']
    total_icons = icon_data['total_icons']
    pack_name = icon_data['pack_name']
    
    # Проверяем, не скачана ли уже
    for ext in [".svg", ".png", ".ico", ".icns"]:
        filepath = os.path.join(icons_dir, safe_filename(icon_name) + ext)
        if is_downloaded(filepath):
            update_current_icon(f"{icon_name}{ext}", "✓")
            update_pack_progress(icon_idx, total_icons, pack_name)
            return {
                "name": icon_name,
                "file": safe_filename(icon_name) + ext,
                "tags": []
            }
    
    # Получаем страницу иконки
    update_current_icon(f"{icon_name} (страница)", "⏳")
    icon_html = safe_get(icon_url)
    if not icon_html:
        update_current_icon(icon_name, "✗")
        update_last_error(f"Страница не загрузилась: {icon_name[:40]}")
        log_error("ICON_PAGE_ERROR", icon_url, f"Иконка: {icon_name}")
        return None
    
    if shutdown_event.is_set():
        return None
    
    # Парсим страницу
    icon_info = parse_icon_page(icon_html)
    
    if not icon_info["downloads"]:
        update_current_icon(icon_name, "✗")
        update_last_error(f"Нет ссылок: {icon_name[:40]}")
        log_error("NO_DOWNLOAD_LINKS", icon_url, f"Иконка: {icon_name}")
        return None
    
    # Приоритет: SVG -> PNG 512px -> любой PNG
    download_attempts = []
    
    svg_url = next((d["url"] for d in icon_info["downloads"] if ".svg" in d["url"].lower()), None)
    if svg_url:
        download_attempts.append((svg_url, ".svg"))
    
    png512_url = next((d["url"] for d in icon_info["downloads"] if ".512.png" in d["url"].lower()), None)
    if png512_url:
        download_attempts.append((png512_url, ".png"))
    
    for d in icon_info["downloads"]:
        if ".png" in d["url"].lower() and ".512.png" not in d["url"].lower():
            download_attempts.append((d["url"], ".png"))
    
    if not download_attempts:
        update_current_icon(icon_name, "✗")
        update_last_error(f"Нет форматов: {icon_name[:40]}")
        log_error("NO_SUITABLE_FORMAT", icon_url, f"Иконка: {icon_name}")
        return None
    
    # Пробуем скачать по очереди
    for download_url, ext in download_attempts:
        if shutdown_event.is_set():
            return None
        
        update_current_icon(f"{icon_name}{ext}", "↓")
        
        filename = safe_filename(icon_name) + ext
        filepath = os.path.join(icons_dir, filename)
        
        if download_file(download_url, filepath, icon_url):
            update_current_icon(f"{icon_name}{ext}", "✓")
            return {
                "name": icon_name,
                "file": filename,
                "tags": icon_info["tags"]
            }
        # Не получилось - пробуем следующий формат (SVG->PNG это нормально)
    
    # Все форматы не удались
    update_current_icon(icon_name, "✗")
    update_last_error(f"Не скачалась: {icon_name[:40]}")
    log_error("ALL_DOWNLOADS_FAILED", icon_url, 
             f"Иконка: {icon_name}, попыток: {len(download_attempts)}")
    return None

# === ОБРАБОТКА ПАКА ===

def process_pack(pack, pack_num, total_processed, packs_index, total_packs, current_page, total_pages):
    if shutdown_event.is_set():
        return
    
    pack_url = pack["url"]
    pack_title = pack["title"]
    
    log(f"ПАК [{pack_num}] {pack_title}")
    
    progress = load_json(PROGRESS_FILE)
    
    if pack_url in progress:
        pack_progress = progress[pack_url]
        status = pack_progress.get("status", "")
        
        if status == "done" and pack_progress.get("errors_count", 0) == 0:
            icons_total = pack_progress.get("icons_total", 0)
            log(f"  ✅ Уже готов ({icons_total} иконок)")
            return
        
        attempts = pack_progress.get("attempts", 0)
        if attempts >= MAX_RETRY_ATTEMPTS:
            log(f"  ⚠️ Превышено попыток ({MAX_RETRY_ATTEMPTS})")
            return
        
        if FORCE_RECHECK_ERRORS and status in ["done_with_errors", "error", "in_progress"]:
            errors_count = pack_progress.get("errors_count", 0)
            log(f"  🔄 Повтор (ошибок: {errors_count})")
            progress[pack_url]["status"] = "retry"
            progress[pack_url]["attempts"] = attempts + 1
            safe_save_json(progress, PROGRESS_FILE)
    
    if pack_url not in progress or progress[pack_url].get("status") == "retry":
        if pack_url not in progress:
            progress[pack_url] = {
                "status": "in_progress",
                "icons_downloaded": 0,
                "errors_count": 0,
                "attempts": 1,
                "first_attempt": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            progress[pack_url]["status"] = "in_progress"
        safe_save_json(progress, PROGRESS_FILE)
    
    if shutdown_event.is_set():
        return
    
    html = safe_get(pack_url)
    if not html:
        progress[pack_url]["status"] = "error"
        safe_save_json(progress, PROGRESS_FILE)
        log_error("PACK_PAGE_ERROR", pack_url, f"Пак: {pack_title}")
        return
    
    pack_dirname = safe_filename(pack_title)
    pack_dir = os.path.join(DOWNLOAD_DIR, pack_dirname)
    pack_rel_path = f"{DOWNLOAD_DIR}/{pack_dirname}"
    
    meta_file = os.path.join(pack_dir, "meta.json")
    if not os.path.exists(meta_file):
        meta = parse_pack_meta(html, pack_url)
        meta["title"] = pack_title
        safe_save_json(meta, meta_file)
        
        if not any(p["path"] == pack_rel_path for p in packs_index):
            packs_index.append({
                "title": pack_title,
                "path": pack_rel_path
            })
            safe_save_json(packs_index, PACKS_INDEX_FILE)
    
    # Собираем все иконки пака
    all_icons = []
    page_num = 1
    
    while True:
        if shutdown_event.is_set():
            return
        
        if page_num == 1:
            page_html = html
        else:
            base_pack_url = pack_url.replace(".html", "")
            page_url = f"{base_pack_url}.{page_num}.html"
            page_html = safe_get(page_url)
        
        if not page_html:
            break
        
        icons_on_page = parse_icon_ids_from_pack_page(page_html)
        if not icons_on_page:
            break
        
        all_icons.extend(icons_on_page)
        
        soup = BeautifulSoup(page_html, "html.parser")
        next_link = soup.find("a", string=re.compile(r"Next page"))
        if not next_link:
            break
        
        page_num += 1
    
    if not all_icons:
        progress[pack_url]["status"] = "empty"
        safe_save_json(progress, PROGRESS_FILE)
        log(f"  ⚠️ Иконки не найдены")
        return
    
    icons_dir = os.path.join(pack_dir, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    
    # Подготавливаем задачи
    icon_tasks = []
    skipped = 0
    
    for icon_idx, icon_url in enumerate(all_icons, 1):
        icon_name = icon_url.rstrip("/").split("/")[-1].replace("-icon.html", "")
        
        already_exists = False
        for ext in [".svg", ".png", ".ico", ".icns"]:
            filepath = os.path.join(icons_dir, safe_filename(icon_name) + ext)
            if is_downloaded(filepath):
                already_exists = True
                break
        
        if already_exists:
            skipped += 1
            continue
        
        icon_tasks.append({
            'icon_url': icon_url,
            'icon_name': icon_name,
            'icons_dir': icons_dir,
            'pack_url': pack_url,
            'icon_idx': icon_idx,
            'total_icons': len(all_icons),
            'pack_name': pack_title
        })
    
    if skipped > 0:
        log(f"  Уже скачано: {skipped}, осталось: {len(icon_tasks)}")
    
    if not icon_tasks:
        progress[pack_url]["status"] = "done"
        progress[pack_url]["icons_total"] = len(all_icons)
        progress[pack_url]["icons_downloaded"] = len(all_icons)
        progress[pack_url]["errors_count"] = 0
        safe_save_json(progress, PROGRESS_FILE)
        update_meta_with_icons(meta_file, pack_url)
        return
    
    # Параллельная загрузка
    downloaded = skipped
    failed = 0
    icons_info = []
    
    update_pack_progress(downloaded, len(all_icons), pack_title)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for task in icon_tasks:
            if shutdown_event.is_set():
                break
            future = executor.submit(download_icon, task)
            futures.append(future)
        
        for future in as_completed(futures):
            if shutdown_event.is_set():
                log("⏹️ Загрузка прервана")
                break
            
            try:
                result = future.result()
                if result:
                    downloaded += 1
                    icons_info.append(result)
                else:
                    failed += 1
            except Exception as e:
                log_error("THREAD_ERROR", pack_url, str(e)[:100])
                failed += 1
            
            progress[pack_url]["icons_downloaded"] = downloaded
            progress[pack_url]["errors_count"] = failed + (len(all_icons) - downloaded - failed)
            safe_save_json(progress, PROGRESS_FILE)
            
            update_pack_progress(downloaded + failed, len(all_icons), pack_title)
            update_speed()
    
    update_meta_with_icons(meta_file, pack_url, icons_info)
    
    total_errors = len(all_icons) - downloaded
    progress[pack_url]["status"] = "done" if total_errors == 0 else "done_with_errors"
    progress[pack_url]["icons_total"] = len(all_icons)
    progress[pack_url]["icons_downloaded"] = downloaded
    progress[pack_url]["errors_count"] = total_errors
    progress[pack_url]["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    safe_save_json(progress, PROGRESS_FILE)
    
    if total_errors == 0:
        log(f"  ✅ {downloaded}/{len(all_icons)}")
    else:
        log(f"  ⚠️ {downloaded}/{len(all_icons)} (ошибок: {total_errors})")

def update_meta_with_icons(meta_file, pack_url, new_icons_info=None):
    if not os.path.exists(meta_file):
        return
    
    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except:
        return
    
    existing_icons = meta.get("icons", [])
    existing_names = {icon["name"] for icon in existing_icons}
    
    if new_icons_info:
        for icon_info in new_icons_info:
            if icon_info["name"] not in existing_names:
                existing_icons.append(icon_info)
                existing_names.add(icon_info["name"])
    
    if not new_icons_info:
        icons_dir = os.path.join(os.path.dirname(meta_file), "icons")
        if os.path.exists(icons_dir):
            for filename in os.listdir(icons_dir):
                if filename.endswith(('.svg', '.png', '.ico', '.icns')):
                    name = os.path.splitext(filename)[0]
                    if name not in existing_names:
                        existing_icons.append({
                            "name": name,
                            "file": filename,
                            "tags": []
                        })
                        existing_names.add(name)
    
    all_tags = set()
    for icon in existing_icons:
        for tag in icon.get("tags", []):
            all_tags.add(tag)
    meta["tags"] = sorted(list(all_tags))
    meta["icons"] = existing_icons
    
    safe_save_json(meta, meta_file)

# === ГЛАВНАЯ ===

def main():
    print("\n" * 5)
    
    log("=" * 60)
    log("🚀 ПАРСЕР ИКОНОК С ICONARCHIVE.COM")
    log(f"📋 Приоритет: SVG -> PNG 512px -> PNG")
    log(f"🔧 Потоков: {MAX_WORKERS} | Лог ошибок: {FAILED_FILE}")
    log("=" * 60)
    
    progress = load_json(PROGRESS_FILE)
    if not progress:
        progress = rebuild_progress_from_disk()
    
    done_packs = sum(1 for p in progress.values()
                    if p.get("status") == "done" and p.get("errors_count", 0) == 0)
    
    packs_index = load_json(PACKS_INDEX_FILE)
    if not isinstance(packs_index, list):
        packs_index = []
    
    start_page = progress.get("__current_page__", 1) if isinstance(progress, dict) else 1
    
    first_page_html = safe_get("https://www.iconarchive.com/news.html")
    if not first_page_html:
        log("❌ Не удалось загрузить первую страницу")
        return
    
    total_pages = get_total_pages(first_page_html)
    log(f"📄 Страниц: {total_pages}")
    
    pack_num = 0
    total_processed = done_packs
    
    try:
        for page in range(start_page, total_pages + 1):
            if shutdown_event.is_set():
                break
            
            log(f"📑 СТРАНИЦА {page}/{total_pages}")
            
            if page == 1:
                url = "https://www.iconarchive.com/news.html"
            else:
                url = f"https://www.iconarchive.com/news.{page}.html"
            
            html = safe_get(url)
            if not html:
                log_error("PAGE_ERROR", url, f"Страница {page}/{total_pages}")
                continue
            
            packs = parse_packs_from_page(html)
            log(f"📦 Паков: {len(packs)}")
            
            update_global_progress(total_processed, 2517, page, total_pages)
            
            for pack in packs:
                if shutdown_event.is_set():
                    break
                
                pack_num += 1
                process_pack(pack, pack_num, total_processed, packs_index, 2517, page, total_pages)
                
                if pack["url"] in progress and progress[pack["url"]].get("status") == "done":
                    total_processed += 1
                    update_global_progress(total_processed, 2517, page, total_pages)
            
            progress["__current_page__"] = page
            safe_save_json(progress, PROGRESS_FILE)
    
    except KeyboardInterrupt:
        log("\n⚠️ Прервано пользователем")
    except Exception as e:
        log(f"\n❌ Критическая ошибка: {e}")
        log_error("CRITICAL_ERROR", "main()", str(e))
    finally:
        safe_save_json(progress, PROGRESS_FILE)
        safe_save_json(packs_index, PACKS_INDEX_FILE)
    
    final_progress = load_json(PROGRESS_FILE)
    final_progress.pop("__current_page__", None)
    
    final_done = sum(1 for p in final_progress.values()
                    if p.get("status") == "done" and p.get("errors_count", 0) == 0)
    final_errors = sum(1 for p in final_progress.values()
                      if p.get("status") == "done_with_errors")
    total_icons = sum(p.get("icons_total", 0) for p in final_progress.values())
    total_downloaded = sum(p.get("icons_downloaded", 0) for p in final_progress.values())
    
    log(f"\n{'='*60}")
    log(f"🏁 ГОТОВО")
    log(f"✅ Паков: {final_done} | ⚠️ С ошибками: {final_errors}")
    if total_icons > 0:
        log(f"🎨 Иконок: {total_downloaded}/{total_icons} ({total_downloaded/total_icons*100:.1f}%)")
    log(f"📝 Ошибки в: {FAILED_FILE}")

if __name__ == "__main__":
    main()
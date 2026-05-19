from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urljoin, unquote
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
BASE_URL = "https://icon-icons.com"
DOWNLOAD_DIR = "downloads"
PROGRESS_FILE = "progress.json"
PACKS_INDEX_FILE = "packs_index.json"
FAILED_FILE = "failed.txt"
DELAY_MIN = 0.1
DELAY_MAX = 0.3
MAX_WORKERS = 70
FORCE_RECHECK_ERRORS = True
MAX_RETRY_ATTEMPTS = 3

SIZE_ORDER = ["512", "256", "128", "96", "64", "48", "32"]
BROWSER = "chrome120"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Referer": "https://icon-icons.com/",
}

# Глобальные переменные для управления
print_lock = Lock()
shutdown_event = Event()  # Для безопасной остановки
save_lock = Lock()  # Для потокобезопасного сохранения JSON

# === УТИЛИТЫ ===

def log(msg):
    if shutdown_event.is_set():
        return
    timestamp = time.strftime("%H:%M:%S")
    with print_lock:
        print(f"[{timestamp}] {msg}", flush=True)

def safe_save_json(data, filepath):
    """Потокобезопасное сохранение JSON с атомарной записью"""
    with save_lock:
        try:
            os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
            temp_path = filepath + ".tmp"
            
            # Пишем во временный файл
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Атомарно заменяем
            if os.path.exists(filepath):
                os.replace(temp_path, filepath)
            else:
                os.rename(temp_path, filepath)
                
        except Exception as e:
            log(f"❌ Ошибка сохранения {filepath}: {e}")
            # Запасной вариант - прямая запись
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e2:
                log(f"❌ Критическая ошибка: {e2}")

def load_json(filepath):
    """Загружает JSON с обработкой ошибок"""
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
        log(f"   Ошибка: {e}")
        
        # Создаем бэкап
        backup_path = filepath + f".backup_{int(time.time())}"
        try:
            shutil.copy2(filepath, backup_path)
            log(f"   Бэкап: {backup_path}")
        except:
            pass
        
        # Пробуем восстановить
        repaired = try_repair_json(filepath)
        if repaired is not None:
            return repaired
        
        # Если не вышло - возвращаем пустой словарь
        log(f"   Использую пустую структуру")
        return {}
    except Exception as e:
        log(f"❌ Ошибка чтения {filepath}: {e}")
        return {}

def try_repair_json(filepath):
    """Пытается восстановить поврежденный JSON"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Метод 1: Удаляем trailing commas
        repaired = re.sub(r',\s*}', '}', content)
        repaired = re.sub(r',\s*]', ']', repaired)
        
        try:
            data = json.loads(repaired)
            log(f"✓ Восстановлен методом 1 (trailing commas)")
            safe_save_json(data, filepath)
            return data
        except:
            pass
        
        # Метод 2: Пробуем найти последнюю валидную строку
        lines = content.split('\n')
        for i in range(len(lines) - 1, 0, -1):
            partial = '\n'.join(lines[:i]) + '\n}'
            try:
                data = json.loads(partial)
                log(f"✓ Восстановлен методом 2 (частично, до строки {i})")
                safe_save_json(data, filepath)
                return data
            except:
                continue
        
        # Метод 3: Пробуем загрузить как JSON lines (построчно)
        json_objects = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('//'):
                try:
                    obj = json.loads(line)
                    json_objects.append(obj)
                except:
                    pass
        
        if json_objects:
            log(f"✓ Восстановлен методом 3 (JSON lines, найдено {len(json_objects)} объектов)")
            return json_objects if isinstance(json_objects[0], dict) else json_objects
        
    except Exception as e:
        log(f"   Ошибка восстановления: {e}")
    
    return None

def rebuild_progress_from_disk():
    """Восстанавливает progress.json из существующих файлов в папке downloads"""
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
            
            # Ищем meta.json для получения URL пака
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
                # Если нет meta.json - пропускаем
                continue
            
            # Считаем иконки
            icons_dir = os.path.join(pack_path, "icons")
            total_icons = 0
            downloaded_icons = 0
            
            if os.path.exists(icons_dir):
                # Считаем все файлы иконок
                icon_files = [f for f in os.listdir(icons_dir) 
                             if f.endswith(('.png', '.webp'))]
                downloaded_icons = len(icon_files)
                
                # Если есть meta.json с информацией о количестве
                if os.path.exists(meta_file):
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            total_icons = meta.get("icons_count", downloaded_icons)
                            if isinstance(total_icons, str):
                                # Пробуем извлечь число из строки
                                match = re.search(r'(\d+)', total_icons)
                                total_icons = int(match.group(1)) if match else downloaded_icons
                    except:
                        total_icons = downloaded_icons
                else:
                    total_icons = downloaded_icons
            
            # Определяем статус
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
        
        log(f"✓ Восстановлено {len(progress)} паков из папки downloads")
        
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

def progress_bar(current, total, width=30):
    if total == 0:
        return "[░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]   0.0% | 0/0"
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = (current / total) * 100
    return f"[{bar}] {pct:5.1f}% | {current}/{total}"

def sleep():
    if shutdown_event.is_set():
        return
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


# === ОБРАБОТЧИКИ СИГНАЛОВ ===

def signal_handler(signum, frame):
    """Обработчик Ctrl+C для безопасного завершения"""
    log("\n⚠️ Получен сигнал остановки (Ctrl+C)")
    log("⏳ Завершаю текущие задачи...")
    shutdown_event.set()

# Регистрируем обработчики
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
                log(f"  429, ждём {wait} сек...")
                for _ in range(wait):
                    if shutdown_event.is_set():
                        return None
                    time.sleep(1)
            else:
                log(f"  Статус {resp.status_code}, попытка {attempt+1}")
                time.sleep(random.uniform(1, 2))
        except Exception as e:
            if shutdown_event.is_set():
                return None
            log(f"  Ошибка: {e}, попытка {attempt+1}")
            time.sleep(2 * (attempt + 1))
    return None

def download_file(url, filepath, referer):
    """Скачивает прямую ссылку на файл"""
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
            
            if resp.status_code == 200 and len(resp.content) > 200:
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type:
                    return False
                
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "wb") as f:
                    f.write(resp.content)
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

def parse_packs_list(html):
    soup = BeautifulSoup(html, "html.parser")
    packs = []
    for card in soup.find_all("div", attrs={"x-ref": "card"}):
        a_tag = card.find("a", href=True)
        title_tag = card.find("h4")
        icons_span = card.find("span", string=lambda t: t and "иконки" in t if t else False)
        
        if a_tag and title_tag:
            count = 0
            if icons_span:
                match = re.search(r'(\d+)', icons_span.text)
                if match:
                    count = int(match.group(1))
            packs.append({
                "title": title_tag.text.strip(),
                "url": urljoin(BASE_URL, a_tag["href"]),
                "icons_count": count
            })
    return packs

def get_total_pages():
    url = "https://icon-icons.com/ru/packs-of-icons?search_in_packs=1&sort=popular&page=1"
    html = safe_get(url)
    if not html:
        return 1
    soup = BeautifulSoup(html, "html.parser")
    page_input = soup.find("input", class_="js-toPage")
    return int(page_input["data-max-page"]) if page_input else 1

def parse_pack_meta(html, pack_url):
    soup = BeautifulSoup(html, "html.parser")
    meta = {
        "url": pack_url,
        "author": "",
        "author_url": "",
        "categories": "",
        "style": "",
        "icons_count": "",
        "license": "",
        "tags": []
    }
    
    ul = soup.find("ul", class_="space-y-2")
    if ul:
        for li in ul.find_all("li", class_="flex"):
            spans = li.find_all("span")
            if len(spans) >= 2:
                key = spans[0].text.strip().rstrip(":")
                value = spans[1].text.strip()
                
                if key == "Автор":
                    a = spans[1].find("a")
                    meta["author"] = a.text.strip() if a else value
                    meta["author_url"] = urljoin(BASE_URL, a["href"]) if a else ""
                elif key == "Категории":
                    meta["categories"] = value
                elif key == "Стиль":
                    meta["style"] = value
                elif key == "Иконки":
                    meta["icons_count"] = value
                elif key == "Лицензия":
                    meta["license"] = value
    
    tags_div = soup.find("div", class_="mx-2 my-5")
    if tags_div:
        for a in tags_div.find_all("a", href=True):
            i_tag = a.find("i")
            if i_tag:
                i_tag.decompose()
            tag_text = a.text.strip()
            if tag_text:
                meta["tags"].append(tag_text)
    
    return meta

def parse_icons_from_pack(html):
    soup = BeautifulSoup(html, "html.parser")
    icons = []
    for div in soup.find_all("div", class_=["border", "rounded-lg", "bg-white"]):
        style = div.get("style", "")
        if "--w:" not in style or "--h:" not in style:
            continue
        a_tag = div.find("a", href=True)
        if a_tag and "/icon/" in a_tag["href"]:
            icon_url = urljoin(BASE_URL, a_tag["href"])
            if icon_url not in icons:
                icons.append(icon_url)
    return icons

def parse_download_links(html):
    """Извлекает прямые ссылки на файлы. Приоритет: PNG -> WebP"""
    soup = BeautifulSoup(html, "html.parser")
    found = {"PNG": {}, "WEBP": {}}
    
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/download-file?file=" not in href:
            continue
        parsed = parse_qs(urlparse(href).query)
        file_url = parsed.get("file", [""])[0]
        
        if not file_url:
            continue
        
        decoded = unquote(file_url)
        url_lower = decoded.lower()
        
        # Извлекаем размер из URL
        parts = decoded.split("/")
        if len(parts) >= 2:
            size = parts[-2]
            if "/png/" in url_lower:
                found["PNG"][size] = decoded
            elif "/webp/" in url_lower:
                found["WEBP"][size] = decoded
    
    # Ищем лучший PNG
    best_png = None
    for size in SIZE_ORDER:
        if size in found["PNG"]:
            best_png = found["PNG"][size]
            break
    
    # Если нет PNG - ищем WebP
    best_webp = None
    if not best_png:
        for size in SIZE_ORDER:
            if size in found["WEBP"]:
                best_webp = found["WEBP"][size]
                break
    
    return best_png, best_webp


# === ЗАГРУЗКА ИКОНКИ ===

def download_icon(icon_data):
    """Скачивает одну иконку в отдельном потоке"""
    if shutdown_event.is_set():
        return False
        
    icon_url = icon_data['icon_url']
    icon_name = icon_data['icon_name']
    png_file = icon_data['png_file']
    webp_file = icon_data['webp_file']
    icon_idx = icon_data['icon_idx']
    total_icons = icon_data['total_icons']
    
    # Проверяем, не скачана ли уже иконка
    if is_downloaded(png_file) or is_downloaded(webp_file):
        log(f"  ✓ [{icon_idx}/{total_icons}] {icon_name} (уже есть)")
        return True
    
    if shutdown_event.is_set():
        return False
    
    # Получаем страницу иконки
    icon_html = safe_get(icon_url)
    if not icon_html:
        log(f"  ✗ [{icon_idx}/{total_icons}] {icon_name} - страница не загрузилась")
        return False
    
    if shutdown_event.is_set():
        return False
    
    # Парсим ссылки
    png_url, webp_url = parse_download_links(icon_html)
    
    success = False
    
    # Пробуем PNG
    if png_url and not shutdown_event.is_set():
        if download_file(png_url, png_file, icon_url):
            log(f"  ✓ [{icon_idx}/{total_icons}] {icon_name}.png")
            success = True
    
    # Если PNG не скачался - пробуем WebP
    if not success and webp_url and not shutdown_event.is_set():
        if download_file(webp_url, webp_file, icon_url):
            log(f"  ✓ [{icon_idx}/{total_icons}] {icon_name}.webp (fallback)")
            success = True
    
    if not success and not shutdown_event.is_set():
        if not png_url and not webp_url:
            log(f"  ⚠ [{icon_idx}/{total_icons}] {icon_name} - нет PNG/WebP")
        else:
            log(f"  ✗ [{icon_idx}/{total_icons}] {icon_name} - ошибка скачивания")
    
    return success


# === ОБРАБОТКА ПАКА ===

def process_pack(pack, pack_num, total_processed, packs_index):
    if shutdown_event.is_set():
        return
        
    pack_url = pack["url"]
    pack_title = pack["title"]
    
    log(f"\n{'='*60}")
    log(f"ПАК [{pack_num}] {pack_title}")
    log(f"  Всего обработано: {total_processed}")
    log(f"{'='*60}")
    
    progress = load_json(PROGRESS_FILE)
    
    # Проверяем статус пака
    if pack_url in progress:
        pack_progress = progress[pack_url]
        status = pack_progress.get("status", "")
        
        # Пропускаем только полностью успешные паки
        if status == "done" and pack_progress.get("errors_count", 0) == 0:
            icons_total = pack_progress.get("icons_total", 0)
            log(f"  ✅ Уже готов ({icons_total} иконок)")
            return
        
        # Проверяем количество попыток
        attempts = pack_progress.get("attempts", 0)
        if attempts >= MAX_RETRY_ATTEMPTS:
            log(f"  ⚠️ Превышено макс. количество попыток ({MAX_RETRY_ATTEMPTS})")
            return
        
        # Если есть ошибки - повторяем
        if FORCE_RECHECK_ERRORS and status in ["done_with_errors", "error", "in_progress"]:
            errors_count = pack_progress.get("errors_count", 0)
            log(f"  🔄 Повторная попытка (скачано: {pack_progress.get('icons_downloaded', 0)}, ошибок: {errors_count})")
            progress[pack_url]["status"] = "retry"
            progress[pack_url]["attempts"] = attempts + 1
            safe_save_json(progress, PROGRESS_FILE)
    
    # Инициализируем запись
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
        return
    
    # Создаем папку пака
    pack_dirname = safe_filename(pack_title)
    pack_dir = os.path.join(DOWNLOAD_DIR, pack_dirname)
    pack_rel_path = f"{DOWNLOAD_DIR}/{pack_dirname}"
    
    # Сохраняем метаданные
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
        
        log(f"  📋 Автор: {meta.get('author','?')}, иконок: {meta.get('icons_count','?')}")
    
    # Получаем список иконок
    icons = parse_icons_from_pack(html)
    if not icons:
        progress[pack_url]["status"] = "empty"
        safe_save_json(progress, PROGRESS_FILE)
        log(f"  ⚠️ Иконки не найдены")
        return
    
    # Папка для иконок
    icons_dir = os.path.join(pack_dir, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    
    log(f"  🎨 Иконок: {len(icons)} (потоков: {MAX_WORKERS})")
    
    # Подготавливаем задачи
    icon_tasks = []
    skipped = 0
    
    for icon_idx, icon_url in enumerate(icons, 1):
        icon_name = icon_url.rstrip("/").split("/")[-2]
        png_file = os.path.join(icons_dir, f"{safe_filename(icon_name)}.png")
        webp_file = os.path.join(icons_dir, f"{safe_filename(icon_name)}.webp")
        
        if is_downloaded(png_file) or is_downloaded(webp_file):
            skipped += 1
            continue
        
        icon_tasks.append({
            'icon_url': icon_url,
            'icon_name': icon_name,
            'png_file': png_file,
            'webp_file': webp_file,
            'icon_idx': icon_idx,
            'total_icons': len(icons)
        })
    
    if skipped > 0:
        log(f"  ✓ Уже скачано: {skipped}, осталось: {len(icon_tasks)}")
    
    if not icon_tasks:
        log(f"  ✅ Все иконки уже скачаны!")
        progress[pack_url]["status"] = "done"
        progress[pack_url]["icons_total"] = len(icons)
        progress[pack_url]["icons_downloaded"] = len(icons)
        progress[pack_url]["errors_count"] = 0
        safe_save_json(progress, PROGRESS_FILE)
        return
    
    # Параллельная загрузка
    downloaded = skipped
    failed = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for task in icon_tasks:
            if shutdown_event.is_set():
                break
            future = executor.submit(download_icon, task)
            futures.append(future)
        
        for future in as_completed(futures):
            if shutdown_event.is_set():
                log("  ⏹️ Загрузка прервана пользователем")
                break
                
            try:
                if future.result():
                    downloaded += 1
                else:
                    failed += 1
            except Exception as e:
                log(f"  ❌ Ошибка потока: {e}")
                failed += 1
            
            # Обновляем прогресс
            progress[pack_url]["icons_downloaded"] = downloaded
            progress[pack_url]["errors_count"] = failed + (len(icons) - downloaded - failed)
            safe_save_json(progress, PROGRESS_FILE)
            
            if (downloaded + failed) % 10 == 0:
                bar = progress_bar(downloaded + failed, len(icons))
                log(f"  📊 {bar}")
    
    # Финальное обновление
    total_errors = len(icons) - downloaded
    progress[pack_url]["status"] = "done" if total_errors == 0 else "done_with_errors"
    progress[pack_url]["icons_total"] = len(icons)
    progress[pack_url]["icons_downloaded"] = downloaded
    progress[pack_url]["errors_count"] = total_errors
    progress[pack_url]["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    safe_save_json(progress, PROGRESS_FILE)
    
    if total_errors == 0:
        log(f"  ✅ ГОТОВО: {downloaded}/{len(icons)} (100%)")
    else:
        log(f"  ⚠️ С ошибками: {downloaded}/{len(icons)} ({downloaded/len(icons)*100:.1f}%)")


# === ГЛАВНАЯ ===

def main():
    log("=" * 60)
    log("🚀 ПАРСЕР ИКОНОК С ICON-ICONS.COM")
    log("=" * 60)
    log(f"📂 Папка: {DOWNLOAD_DIR}")
    log(f"🔧 Потоков: {MAX_WORKERS}")
    log(f"🔄 Проверка ошибок: {'Да' if FORCE_RECHECK_ERRORS else 'Нет'}")
    log(f"🛑 Ctrl+C для безопасной остановки")
    
    # Проверяем progress.json
    progress = load_json(PROGRESS_FILE)
    
    if not progress:
        log("⚠️ progress.json пуст или поврежден")
        log("🔄 Пробую восстановить из папки downloads...")
        progress = rebuild_progress_from_disk()
    
    # Статистика
    done_packs = sum(1 for p in progress.values() 
                    if p.get("status") == "done" and p.get("errors_count", 0) == 0)
    error_packs = sum(1 for p in progress.values() 
                     if p.get("status") in ["done_with_errors", "error", "in_progress", "retry"])
    
    log(f"\n📊 Статистика:")
    log(f"   Всего паков: {len(progress)}")
    log(f"   Готово: {done_packs}")
    log(f"   С ошибками: {error_packs}")
    
    # Загружаем индекс
    packs_index = load_json(PACKS_INDEX_FILE)
    if not isinstance(packs_index, list):
        packs_index = []
    
    # Получаем страницы
    total_pages = get_total_pages()
    log(f"\n📄 Страниц с паками: {total_pages}")
    
    pack_num = 0
    total_processed = done_packs
    
    try:
        for page in range(1, total_pages + 1):
            if shutdown_event.is_set():
                log("\n⏹️ Работа остановлена")
                break
                
            log(f"\n{'~'*60}")
            log(f"📑 СТРАНИЦА {page}/{total_pages}")
            log(f"{'~'*60}")
            
            url = f"https://icon-icons.com/ru/packs-of-icons?search_in_packs=1&sort=popular&page={page}"
            html = safe_get(url)
            
            if not html:
                log(f"  ❌ Страница {page} не загружена")
                continue
            
            packs = parse_packs_list(html)
            log(f"  📦 Паков: {len(packs)}")
            
            for pack in packs:
                if shutdown_event.is_set():
                    break
                    
                pack_num += 1
                process_pack(pack, pack_num, total_processed, packs_index)
                
                pack_url = pack["url"]
                if pack_url in progress and progress[pack_url].get("status") == "done":
                    total_processed += 1
    
    except KeyboardInterrupt:
        log("\n⚠️ Прервано пользователем")
    except Exception as e:
        log(f"\n❌ Критическая ошибка: {e}")
    finally:
        # Финальное сохранение
        log("\n💾 Сохраняю прогресс...")
        safe_save_json(progress, PROGRESS_FILE)
        safe_save_json(packs_index, PACKS_INDEX_FILE)
    
    # Итоговая статистика
    final_progress = load_json(PROGRESS_FILE)
    final_done = sum(1 for p in final_progress.values() 
                    if p.get("status") == "done" and p.get("errors_count", 0) == 0)
    final_errors = sum(1 for p in final_progress.values() 
                      if p.get("status") == "done_with_errors")
    total_icons = sum(p.get("icons_total", 0) for p in final_progress.values())
    total_downloaded = sum(p.get("icons_downloaded", 0) for p in final_progress.values())
    
    log(f"\n{'='*60}")
    log(f"🏁 РАБОТА ЗАВЕРШЕНА")
    log(f"{'='*60}")
    log(f"📦 Паков обработано: {pack_num}")
    log(f"✅ Полностью готово: {final_done}")
    log(f"⚠️ С ошибками: {final_errors}")
    log(f"🎨 Всего иконок: {total_icons}")
    log(f"💾 Скачано: {total_downloaded}")
    if total_icons > 0:
        log(f"📊 Процент: {total_downloaded/total_icons*100:.1f}%")
    
    if final_errors > 0:
        log(f"\n💡 Запустите скрипт снова для докачки недостающих иконок")


if __name__ == "__main__":
    main()
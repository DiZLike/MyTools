from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urljoin, unquote
import json
import os
import sys
import time
import random
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# === НАСТРОЙКИ ===
BASE_URL = "https://icon-icons.com"
DOWNLOAD_DIR = "downloads"
PROGRESS_FILE = "progress.json"
PACKS_INDEX_FILE = "packs_index.json"
FAILED_FILE = "failed.txt"
DELAY_MIN = 0.1
DELAY_MAX = 0.3
MAX_WORKERS = 8  # Количество параллельных потоков

SIZE_ORDER = ["64", "48", "72", "96", "128", "256", "512", "32"]
BROWSER = "chrome120"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Referer": "https://icon-icons.com/",
}

# Глобальная блокировка для потокобезопасных операций
print_lock = Lock()

# === УТИЛИТЫ ===

def log(msg):
    timestamp = time.strftime("%H:%M:%S")
    with print_lock:
        print(f"[{timestamp}] {msg}", flush=True)

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(data, filepath):
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def log_failed(msg):
    with open(FAILED_FILE, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n")

def is_downloaded(filepath):
    return os.path.exists(filepath) and os.path.getsize(filepath) > 100

def safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()

def progress_bar(current, total, width=30):
    filled = int(width * current / total) if total > 0 else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = (current / total) * 100 if total > 0 else 0
    return f"[{bar}] {pct:5.1f}% | {current}/{total}"

def sleep():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


# === HTTP ===

def create_session():
    s = curl_requests.Session()
    s.headers.update(HEADERS)
    return s

def safe_get(url, retries=3):
    session = create_session()
    for attempt in range(retries):
        try:
            sleep()
            resp = session.get(url, impersonate=BROWSER, timeout=30)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                wait = 10 * (attempt + 1)
                log(f"  429, ждём {wait} сек...")
                time.sleep(wait)
            else:
                log(f"  Статус {resp.status_code}, попытка {attempt+1}")
                time.sleep(random.uniform(1, 2))
        except Exception as e:
            log(f"  Ошибка: {e}, попытка {attempt+1}")
            time.sleep(2 * (attempt + 1))
    return None

def download_file(url, filepath, referer):
    """Скачивает прямую ссылку на файл (images.icon-icons.com)"""
    session = create_session()
    for attempt in range(3):
        try:
            sleep()
            resp = session.get(url, impersonate=BROWSER, timeout=30, headers={"Referer": referer})
            
            if resp.status_code == 200 and len(resp.content) > 200:
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type:
                    return False
                
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                return True
                
            elif resp.status_code == 429:
                time.sleep(10 * (attempt + 1))
            else:
                time.sleep(random.uniform(1, 2))
                
        except Exception as e:
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
    """Извлекает ПРЯМЫЕ ссылки на файлы (images.icon-icons.com)"""
    soup = BeautifulSoup(html, "html.parser")
    found = {"PNG": {}, "ICO": {}}
    
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/download-file?file=" not in href:
            continue
        parsed = parse_qs(urlparse(href).query)
        file_url = parsed.get("file", [""])[0]
        
        if not file_url:
            continue
        
        decoded = unquote(file_url)
        parts = decoded.split("/")
        
        if len(parts) >= 2:
            size = parts[-2]
            fmt = parts[-3]
            if fmt in found:
                found[fmt][size] = decoded
    
    best_png = None
    for size in SIZE_ORDER:
        if size in found["PNG"]:
            best_png = found["PNG"][size]
            break
    
    best_ico = None
    for size in SIZE_ORDER:
        if size in found["ICO"]:
            best_ico = found["ICO"][size]
            break
    
    return best_png, best_ico


# === ПАРАЛЛЕЛЬНАЯ ОБРАБОТКА ИКОНОК ===

def download_icon(icon_data):
    """Скачивает одну иконку (PNG + ICO) в отдельном потоке"""
    icon_url = icon_data['icon_url']
    icon_name = icon_data['icon_name']
    png_file = icon_data['png_file']
    ico_file = icon_data['ico_file']
    icon_idx = icon_data['icon_idx']
    total_icons = icon_data['total_icons']
    
    # Проверяем, не скачана ли уже иконка
    if is_downloaded(png_file) and is_downloaded(ico_file):
        log(f"  ✓ [{icon_idx}/{total_icons}] {icon_name} (уже есть)")
        return True
    
    # Получаем страницу иконки
    icon_html = safe_get(icon_url)
    if not icon_html:
        log(f"  ✗ [{icon_idx}/{total_icons}] {icon_name} - страница не загрузилась")
        log_failed(f"Страница: {icon_url}")
        return False
    
    # Парсим ссылки на скачивание
    png_url, ico_url = parse_download_links(icon_html)
    
    success = True
    
    # Скачиваем PNG
    if png_url and not is_downloaded(png_file):
        if download_file(png_url, png_file, icon_url):
            log(f"  ✓ [{icon_idx}/{total_icons}] {icon_name}.png")
        else:
            log(f"  ✗ [{icon_idx}/{total_icons}] {icon_name}.png - ошибка скачивания")
            log_failed(f"PNG: {icon_url}")
            success = False
    elif not png_url:
        log(f"  ⚠ [{icon_idx}/{total_icons}] {icon_name} - нет PNG")
    
    # Скачиваем ICO
    if ico_url and not is_downloaded(ico_file):
        if download_file(ico_url, ico_file, icon_url):
            log(f"  ✓ [{icon_idx}/{total_icons}] {icon_name}.ico")
        else:
            log(f"  ✗ [{icon_idx}/{total_icons}] {icon_name}.ico - ошибка скачивания")
            log_failed(f"ICO: {icon_url}")
            success = False
    elif not ico_url:
        log(f"  ⚠ [{icon_idx}/{total_icons}] {icon_name} - нет ICO")
    
    return success


# === ОБРАБОТКА ПАКА ===

def process_pack(pack, pack_num, total_processed, packs_index):
    pack_url = pack["url"]
    pack_title = pack["title"]
    
    log(f"\n{'='*60}")
    log(f"ПАК [{pack_num}] {pack_title}")
    log(f"  Всего обработано: {total_processed}")
    log(f"{'='*60}")
    
    progress = load_json(PROGRESS_FILE)
    
    if pack_url in progress and progress[pack_url].get("status") == "done":
        log(f"  Уже готов, пропускаю")
        return
    
    if pack_url not in progress:
        progress[pack_url] = {"status": "in_progress", "icons_downloaded": 0}
        save_json(progress, PROGRESS_FILE)
    
    html = safe_get(pack_url)
    if not html:
        progress[pack_url]["status"] = "error"
        save_json(progress, PROGRESS_FILE)
        return
    
    # Папка пака
    pack_dirname = safe_filename(pack_title)
    pack_dir = os.path.join(DOWNLOAD_DIR, pack_dirname)
    pack_rel_path = f"{DOWNLOAD_DIR}/{pack_dirname}"
    
    # Метаданные
    meta_file = os.path.join(pack_dir, "meta.json")
    if not os.path.exists(meta_file):
        meta = parse_pack_meta(html, pack_url)
        meta["title"] = pack_title
        save_json(meta, meta_file)
        
        packs_index.append({
            "title": pack_title,
            "path": pack_rel_path
        })
        save_json(packs_index, PACKS_INDEX_FILE)
        
        log(f"  Автор: {meta.get('author','?')}, тегов: {len(meta.get('tags',[]))}")
    else:
        log(f"  Мета уже есть")
    
    # Получаем список иконок
    icons = parse_icons_from_pack(html)
    if not icons:
        progress[pack_url]["status"] = "empty"
        save_json(progress, PROGRESS_FILE)
        log(f"  Иконки не найдены")
        return
    
    png_dir = os.path.join(pack_dir, "png")
    ico_dir = os.path.join(pack_dir, "ico")
    os.makedirs(png_dir, exist_ok=True)
    os.makedirs(ico_dir, exist_ok=True)
    
    log(f"  Иконок: {len(icons)} (загрузка в {MAX_WORKERS} потоков)")
    
    # Подготавливаем данные для параллельной загрузки
    icon_tasks = []
    for icon_idx, icon_url in enumerate(icons, 1):
        icon_name = icon_url.rstrip("/").split("/")[-2]
        png_file = os.path.join(png_dir, f"{safe_filename(icon_name)}.png")
        ico_file = os.path.join(ico_dir, f"{safe_filename(icon_name)}.ico")
        
        icon_tasks.append({
            'icon_url': icon_url,
            'icon_name': icon_name,
            'png_file': png_file,
            'ico_file': ico_file,
            'icon_idx': icon_idx,
            'total_icons': len(icons)
        })
    
    # Параллельная загрузка иконок
    downloaded = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Запускаем задачи пачками для контроля прогресса
        futures = []
        for task in icon_tasks:
            future = executor.submit(download_icon, task)
            futures.append(future)
        
        # Отслеживаем выполнение
        for future in as_completed(futures):
            try:
                if future.result():
                    downloaded += 1
            except Exception as e:
                log(f"  Ошибка в потоке: {e}")
                log_failed(f"Thread error: {e}")
            
            # Обновляем прогресс
            progress[pack_url]["icons_downloaded"] = downloaded
            save_json(progress, PROGRESS_FILE)
            
            # Показываем общий прогресс
            if downloaded % 5 == 0 or downloaded == len(icons):
                bar = progress_bar(downloaded, len(icons))
                log(f"  ПРОГРЕСС ПАКА: {bar}")
    
    # Финальное обновление
    progress[pack_url]["status"] = "done"
    progress[pack_url]["icons_total"] = len(icons)
    progress[pack_url]["icons_downloaded"] = downloaded
    save_json(progress, PROGRESS_FILE)
    
    log(f"  ГОТОВО: {downloaded}/{len(icons)} иконок")


# === ГЛАВНАЯ ===

def main():
    log("=== ЗАПУСК ПАРСЕРА (МНОГОПОТОЧНЫЙ РЕЖИМ) ===")
    log(f"Количество потоков: {MAX_WORKERS}")
    
    total_pages = get_total_pages()
    log(f"Всего страниц паков: {total_pages}")
    
    progress = load_json(PROGRESS_FILE)
    total_processed = sum(1 for p in progress.values() if p.get("status") == "done")
    
    # Загружаем индекс
    packs_index = load_json(PACKS_INDEX_FILE)
    if not isinstance(packs_index, list):
        packs_index = []
    
    pack_num = 0
    
    for page in range(1, total_pages + 1):
        log(f"\n{'~'*60}")
        log(f"СТРАНИЦА {page}/{total_pages}")
        log(f"{'~'*60}")
        
        url = f"https://icon-icons.com/ru/packs-of-icons?search_in_packs=1&sort=popular&page={page}"
        html = safe_get(url)
        
        if not html:
            log(f"  Не удалось загрузить страницу {page}")
            continue
        
        packs = parse_packs_list(html)
        log(f"  Паков на странице: {len(packs)}")
        
        for pack in packs:
            pack_num += 1
            process_pack(pack, pack_num, total_processed, packs_index)
            total_processed += 1
    
    log(f"\n{'='*60}")
    log(f"ВСЁ ГОТОВО!")
    log(f"Всего паков: {pack_num}")
    log(f"Иконки: {DOWNLOAD_DIR}/")
    log(f"Индекс: {PACKS_INDEX_FILE}")


if __name__ == "__main__":
    main()
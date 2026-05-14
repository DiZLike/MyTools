import os
import re
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Конфигурация
BASE_URL = "https://www.zophar.net"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
}

def sanitize_filename(filename: str) -> str:
    """Очистка имени файла от недопустимых символов"""
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip().rstrip('.')
    return filename[:200] if len(filename) > 200 else filename

def search_games(query: str):
    """Поиск игр на Zophar's Domain"""
    result = {"games": [], "success": False, "error": ""}
    
    try:
        if len(query.strip()) < 3:
            result["error"] = "Слишком короткий поисковый запрос (минимум 3 символа)"
            return result
        
        session = requests.Session()
        session.headers.update(HEADERS)
        
        response = session.get(f"{BASE_URL}/music/search", params={"search": query}, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.select_one("table#gamelist")
        
        if not table:
            result["error"] = "Таблица с результатами не найдена"
            return result
        
        rows = table.select("tr:not(.headerrow)")
        
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
                print(f"Ошибка при парсинге строки: {e}")
                continue
        
        result["success"] = True
        session.close()
        
    except requests.RequestException as e:
        result["error"] = f"Ошибка запроса: {e}"
    except Exception as e:
        result["error"] = f"Неизвестная ошибка: {e}"
    
    return result

def get_tracks_from_game(game_url: str, game_name: str, console_name: str):
    """Получает список MP3 треков со страницы игры"""
    result = {"tracks": [], "success": False, "error": ""}
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        response = session.get(game_url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем таблицу с треками
        track_table = soup.select_one("table#tracklist")
        if not track_table:
            return result
        
        # Парсим строки с треками
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
                            result["tracks"].append({
                                "number": track_number,
                                "name": track_name,
                                "duration": duration,
                                "url": mp3_url,
                                "game": game_name,
                                "platform": console_name
                            })
                
            except Exception as e:
                print(f"Ошибка при парсинге трека: {e}")
                continue
        
        result["success"] = True
        session.close()
        
    except requests.RequestException as e:
        result["error"] = f"Ошибка запроса: {e}"
    except Exception as e:
        result["error"] = f"Неизвестная ошибка: {e}"
    
    return result

def download_file(url: str, filepath: str):
    """Скачивает файл по ссылке"""
    try:
        response = requests.get(url, headers=HEADERS, stream=True, timeout=30)
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
        print(f"\n   Ошибка при скачивании: {e}")
        return False

def main():
    print("=" * 80)
    print("         ЗАГРУЗЧИК МУЗЫКИ C ZOPHAR")
    print("=" * 80)
    
    # Поиск игр
    query = input("\n🔍 Введите название игры: ").strip()
    if not query:
        print("❌ Поисковый запрос не может быть пустым!")
        return
    
    print(f"\n🔍 Ищем: '{query}'...")
    search_result = search_games(query)
    
    if not search_result["success"]:
        print(f"❌ Ошибка: {search_result['error']}")
        return
    
    if not search_result["games"]:
        print("❌ Ничего не найдено.")
        return
    
    print(f"\n✅ Найдено игр: {len(search_result['games'])}")
    print(f"📡 Собираю треки со всех страниц...\n")
    
    # Собираем треки со всех игр
    all_tracks = []
    
    for i, game in enumerate(search_result["games"], 1):
        print(f"   Обработка {i}/{len(search_result['games'])}: {game['name']} ({game['console']})...")
        tracks_result = get_tracks_from_game(game["url"], game["name"], game["console"])
        
        if tracks_result["success"] and tracks_result["tracks"]:
            all_tracks.extend(tracks_result["tracks"])
            print(f"      ✅ Найдено треков: {len(tracks_result['tracks'])}")
        elif tracks_result["error"]:
            print(f"      ⚠️ {tracks_result['error']}")
        else:
            print(f"      ⚠️ MP3 треки не найдены")
    
    if not all_tracks:
        print("\n❌ MP3 треки не найдены ни на одной странице.")
        return
    
    # Выводим список всех треков
    print(f"\n✅ Всего собрано треков: {len(all_tracks)}\n")
    print("=" * 80)
    
    for i, track in enumerate(all_tracks, 1):
        # Формат: Номер. Название трека (длительность) [Игра | Платформа]
        if track["number"]:
            display_name = f"{track['number']}. {track['name']}"
        else:
            display_name = track['name']
        
        print(f"{i}. {display_name} ({track['duration']}) [{track['game']} | {track['platform']}]")
        print(f"   🔗 {track['url']}")
    
    print("=" * 80)
    
    # Скачивание треков
    while True:
        print("\n📥 Команды:")
        print("   • Введите номер трека (например: 5)")
        print("   • Введите диапазон (например: 3-7)")
        print("   • Введите несколько номеров через запятую (например: 1,3,5,7)")
        print("   • 'all' - скачать все треки")
        print("   • 'save' - сохранить список в файл")
        print("   • 'q' - выход")
        
        choice = input("\n👉 Ваш выбор: ").strip().lower()
        
        if choice == 'q':
            print("👋 Выход.")
            break
        
        elif choice == 'save':
            filename = f"tracks_{sanitize_filename(query)}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                for track in all_tracks:
                    if track["number"]:
                        f.write(f"{track['number']}. {track['name']} ({track['duration']}) [{track['game']} | {track['platform']}]\n")
                    else:
                        f.write(f"{track['name']} ({track['duration']}) [{track['game']} | {track['platform']}]\n")
                    f.write(f"{track['url']}\n\n")
            print(f"✅ Список сохранён в {filename}")
            continue
        
        elif choice == 'all':
            tracks_to_download = all_tracks
            print(f"\n📥 Скачивание всех {len(tracks_to_download)} треков...")
            
            # Создаём папку для скачивания
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
                    print(f"⏭️  Пропуск (уже есть): {filename}")
                    downloaded += 1
                    continue
                
                print(f"\n🎵 {filename} ({track['duration']})")
                if download_file(track["url"], filepath):
                    print(f"   ✅ Сохранён: {filepath}")
                    downloaded += 1
                else:
                    print(f"   ❌ Ошибка при скачивании")
            
            print(f"\n✅ Скачано {downloaded} из {len(tracks_to_download)} треков в папку '{download_dir}'")
            break
        
        else:
            # Парсим ввод пользователя (диапазоны, списки)
            indices_to_download = set()
            
            # Разбиваем по запятым
            parts = choice.replace(' ', '').split(',')
            
            for part in parts:
                if '-' in part:
                    # Диапазон: 3-7
                    start, end = map(int, part.split('-'))
                    for idx in range(start, end + 1):
                        if 1 <= idx <= len(all_tracks):
                            indices_to_download.add(idx)
                else:
                    # Одиночный номер
                    try:
                        idx = int(part)
                        if 1 <= idx <= len(all_tracks):
                            indices_to_download.add(idx)
                        else:
                            print(f"❌ Номер {idx} вне диапазона (1-{len(all_tracks)})")
                    except ValueError:
                        print(f"❌ Неверный формат: {part}")
            
            if not indices_to_download:
                print("❌ Не выбрано ни одного трека для скачивания")
                continue
            
            tracks_to_download = [all_tracks[idx-1] for idx in sorted(indices_to_download)]
            
            print(f"\n📥 Будет скачано {len(tracks_to_download)} треков:")
            for track in tracks_to_download:
                if track["number"]:
                    print(f"   - {track['number']}. {track['name']} ({track['duration']}) [{track['game']} | {track['platform']}]")
                else:
                    print(f"   - {track['name']} ({track['duration']}) [{track['game']} | {track['platform']}]")
            
            confirm = input("\n✅ Продолжить скачивание? (y/n): ").strip().lower()
            if confirm != 'y':
                print("❌ Скачивание отменено")
                continue
            
            # Создаём папку для скачивания
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
                    print(f"⏭️  Пропуск (уже есть): {filename}")
                    downloaded += 1
                    continue
                
                print(f"\n🎵 {filename} ({track['duration']})")
                if download_file(track["url"], filepath):
                    print(f"   ✅ Сохранён: {filepath}")
                    downloaded += 1
                else:
                    print(f"   ❌ Ошибка при скачивании")
            
            print(f"\n✅ Скачано {downloaded} из {len(tracks_to_download)} треков в папку '{download_dir}'")
            
            another = input("\n📥 Скачать ещё треки из этого списка? (y/n): ").strip().lower()
            if another != 'y':
                print("👋 Выход.")
                break

if __name__ == "__main__":
    main()
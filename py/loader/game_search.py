import os
import json
import logging
import urllib.parse
from datetime import datetime
from pathlib import Path

# ==================== КОНСТАНТЫ ====================
BASE_PATH = "F:\!Evgeny\git\MyTools\py\loader\downloads"
BASE_URL = "https://dlike.ru/media/gm"
COMMON_JSON = "games_index.json"
LOG_FILE = "scan_errors.log"
FORCE_REWRITE = True

# ==================== НАСТРОЙКА ЛОГГЕРА ====================
# Логгер в файл
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.WARNING)
file_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))

# Логгер в консоль (только ошибки)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))

logging.basicConfig(
    level=logging.WARNING,
    handlers=[file_handler, console_handler],
)

# ==================== ФУНКЦИИ ====================

def url_encode_path(path: str) -> str:
    """Кодирует относительный путь для URL."""
    parts = path.replace("\\", "/").split("/")
    encoded_parts = [urllib.parse.quote(part) for part in parts]
    return "/".join(encoded_parts)


def find_cover(game_dir: Path) -> Path | None:
    """Ищет файл cover с любым расширением."""
    for f in game_dir.iterdir():
        if f.is_file() and f.stem.lower() == "cover":
            return f
    return None


def find_7z(game_dir: Path) -> Path | None:
    """Ищет единственный .7z архив."""
    archives = list(game_dir.glob("*.7z"))
    if not archives:
        return None
    return archives[0]


def build_url(relative_path: str) -> str:
    """Формирует полный URL."""
    return f"{BASE_URL}/{url_encode_path(relative_path)}"


def process_game(game_dir: Path, base_path: Path, platform_from_path: str) -> dict | None:
    """
    Обрабатывает одну игру.
    Возвращает словарь для game.json и записи в индекс, либо None при ошибке.
    """
    info_path = game_dir / "info.json"
    relative_dir = game_dir.relative_to(base_path)

    # Читаем info.json
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            info = json.load(f)
    except FileNotFoundError:
        logging.warning("%s: info.json not found", relative_dir)
        return None
    except json.JSONDecodeError as e:
        logging.warning("%s: failed to parse info.json — %s", relative_dir, e)
        return None

    # Извлекаем поля
    title = info.get("title", None)

    alternative_name = info.get("alternative_name", {})
    if isinstance(alternative_name, dict):
        alternative_name = alternative_name.get("text", None)
    else:
        alternative_name = None

    release_date = info.get("release_date", {})
    if isinstance(release_date, dict):
        release_date = release_date.get("text", None)
    else:
        release_date = None

    console = info.get("console", {})
    if isinstance(console, dict):
        console_text = console.get("text", None)
    else:
        console_text = None

    developer = info.get("developer", None)
    if isinstance(developer, dict):
        developer = developer.get("text", None)

    publisher = info.get("publisher", None)
    if isinstance(publisher, dict):
        publisher = publisher.get("text", None)
        
    download_date = info.get("download_date", None)

    # Определяем платформу
    platform = console_text if console_text else platform_from_path

    # Ищем cover
    cover_file = find_cover(game_dir)
    if cover_file:
        relative_cover = cover_file.relative_to(base_path)
        cover_url = build_url(str(relative_cover))
    else:
        cover_url = None

    # Ищем 7z
    archive_file = find_7z(game_dir)
    if not archive_file:
        logging.warning("%s: 7z archive not found", relative_dir)
        return None

    relative_7z = archive_file.relative_to(base_path)
    archive_url = build_url(str(relative_7z))

    # Собираем game_data
    game_data = {
        "title": title,
        "alternative_name": alternative_name,
        "release_date": release_date,
        "console": console_text,
        "developer": developer,
        "publisher": publisher,
        "download_date": download_date,
        "platform": platform,
        "cover_url": cover_url,
        "7z_url": archive_url,
    }

    return game_data


def save_game_json(game_dir: Path, game_data: dict) -> Path:
    """Сохраняет game.json в папку игры, возвращает путь к файлу."""
    game_json_path = game_dir / "game.json"
    with open(game_json_path, "w", encoding="utf-8") as f:
        json.dump(game_data, f, ensure_ascii=False, indent=2)
    return game_json_path


def main():
    base_path = Path(BASE_PATH).resolve()

    # Загружаем существующий индекс, если есть
    index_path = Path(COMMON_JSON)
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        print(f"Loaded existing index: {len(index)} entries")
    else:
        index = {}

    # Статистика
    processed = 0
    rewritten = 0
    skipped_json = 0
    skipped_7z = 0
    skipped_existing = 0

    print(f"Force rewrite: {FORCE_REWRITE}")
    print("Scanning...\n")

    # Обходим все папки
    for root, dirs, files in os.walk(base_path):
        game_dir = Path(root)

        # Проверяем, что это папка игры (есть info.json)
        if "info.json" not in files:
            continue

        # Пропускаем или перезаписываем существующие
        game_json_exists = (game_dir / "game.json").exists()
        if game_json_exists and not FORCE_REWRITE:
            skipped_existing += 1
            continue

        # Определяем платформу из пути
        try:
            platform_from_path = game_dir.relative_to(base_path).parts[0]
        except (ValueError, IndexError):
            platform_from_path = "Unknown"

        # Обрабатываем игру
        game_data = process_game(game_dir, base_path, platform_from_path)

        if game_data is None:
            if (game_dir / "info.json").exists() and not list(game_dir.glob("*.7z")):
                skipped_7z += 1
            else:
                skipped_json += 1
            continue

        # Сохраняем game.json
        game_json_path = save_game_json(game_dir, game_data)
        relative_game_json = str(game_json_path.relative_to(base_path))

        # Добавляем в индекс
        index[relative_game_json] = {
            "title": game_data["title"],
            "platform": game_data["platform"],
        }

        if game_json_exists:
            rewritten += 1
        else:
            processed += 1

        total_done = processed + rewritten

        # Лог каждые 10 игр
        if total_done % 10 == 0:
            print(
                f"[{total_done:5d}] new: {processed:5d} | rewritten: {rewritten:5d} | "
                f"index: {len(index):5d} | "
                f"last: {game_data['title'] or '?'}"
            )

    # Сохраняем общий индекс
    with open(COMMON_JSON, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    # Итоговая статистика
    print("\n==================== DONE ====================")
    print(f"Processed (new):      {processed}")
    print(f"Rewritten:            {rewritten}")
    print(f"Skipped (existing):   {skipped_existing}")
    print(f"Skipped (no 7z):      {skipped_7z}")
    print(f"Skipped (bad json):   {skipped_json}")
    print(f"Total in index:       {len(index)}")
    print(f"Log file:             {LOG_FILE}")


if __name__ == "__main__":
    main()
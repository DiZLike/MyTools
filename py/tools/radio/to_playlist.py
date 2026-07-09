"""Скрипт проверяет дубликаты только в плейлисте! Дубликаты на сервере проверяет другой скрипт"""

import os
import sys
import re
from pathlib import Path
from datetime import datetime

def normalize_track_name(track_name):
    """Удаляет дату в формате 2025-12-24 из названия трека"""
    pattern = r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}[_\-]?'
    normalized = re.sub(pattern, '', track_name)
    return ' '.join(normalized.split()).lower()

def get_existing_tracks(playlist_file):
    """Получает список уже добавленных треков из M3U плейлиста"""
    existing_tracks = set()
    
    if not os.path.exists(playlist_file):
        return existing_tracks
    
    try:
        with open(playlist_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Пропускаем заголовок #EXTM3U и другие комментарии
                if not line or line.startswith('#'):
                    continue
                normalized = normalize_track_name(Path(line).stem)
                existing_tracks.add(normalized)
                print(f"Найден существующий трек: {line} (нормализовано: {normalized})")
    except Exception as e:
        print(f"Ошибка при чтении плейлиста: {e}")
    
    print(f"Всего найдено уникальных треков в плейлисте: {len(existing_tracks)}")
    return existing_tracks

def create_playlist(server_folder, local_folder, playlist_file):
    """Создает или обновляет M3U плейлист"""
    server_path = Path(server_folder)
    local_path = Path(local_folder)
    
    if not local_path.exists():
        print(f"Ошибка: Локальная папка '{local_folder}' не существует")
        return False
    
    existing_tracks = get_existing_tracks(playlist_file)
    
    audio_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma', '.opus'}
    new_tracks = []
    
    for file_path in local_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
            relative_path = server_path / file_path.relative_to(local_path)
            track_name = file_path.stem
            normalized_name = normalize_track_name(track_name)
            
            if normalized_name in existing_tracks:
                print(f"Пропуск: Трек '{track_name}' уже существует в плейлисте")
                continue
            
            new_tracks.append(relative_path)
            existing_tracks.add(normalized_name)
            print(f"Найден новый трек: {track_name} -> {relative_path}")
    
    if not new_tracks:
        print("Новых треков для добавления не найдено")
        return True
    
    try:
        # Проверяем, существует ли файл и есть ли в нём заголовок
        add_header = not os.path.exists(playlist_file) or os.path.getsize(playlist_file) == 0
        
        with open(playlist_file, 'a', encoding='utf-8') as f:
            if add_header:
                f.write('#EXTM3U\n')
            
            for track_path in new_tracks:
                f.write(f"{track_path}\n")
                print(f"Добавлен: {track_path}")
        
        print(f"\nДобавлено {len(new_tracks)} новых треков в плейлист '{playlist_file}'")
        return True
        
    except Exception as e:
        print(f"Ошибка при записи в плейлист: {e}")
        return False

def main():
    if len(sys.argv) != 4:
        print("Использование: python playlist_creator.py <серверная_папка> <локальная_папка> <файл_плейлиста>")
        print("Пример: python playlist_creator.py /music/server/path /home/user/music playlist.m3u")
        return
    
    server_folder = sys.argv[1]
    local_folder = sys.argv[2]
    playlist_file = sys.argv[3]
    
    success = create_playlist(server_folder, local_folder, playlist_file)
    
    if success:
        print("Операция завершена успешно")
        sys.exit(0)
    else:
        print("Операция завершилась с ошибками")
        sys.exit(1)

if __name__ == "__main__":
    main()
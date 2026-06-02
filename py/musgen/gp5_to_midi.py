from pathlib import Path
import sys
import guitarpro
from mido import MidiFile, MidiTrack, Message, MetaMessage

def gp_to_midi(input_file, output_file):
    """Конвертирует Guitar Pro файл в MIDI"""
    song = guitarpro.parse(str(input_file))
    
    mid = MidiFile(ticks_per_beat=960)
    
    # Темп
    tempo = song.tempo if hasattr(song, 'tempo') and song.tempo > 0 else 120
    tempo_microseconds = int(60_000_000 / tempo)
    
    for track_idx, gp_track in enumerate(song.tracks):
        track = MidiTrack()
        mid.tracks.append(track)
        
        # Название трека
        track_name = gp_track.name if hasattr(gp_track, 'name') and gp_track.name else f"Track {track_idx + 1}"
        track.append(MetaMessage('track_name', name=track_name, time=0))
        
        # Темп только в первом треке
        if track_idx == 0:
            track.append(MetaMessage('set_tempo', tempo=tempo_microseconds, time=0))
        
        # Инструмент
        channel = 0
        instrument = 0
        volume = 100
        
        if hasattr(gp_track, 'channel'):
            ch = gp_track.channel
            if hasattr(ch, 'channel'):
                channel = int(ch.channel) % 16
            if hasattr(ch, 'instrument'):
                instrument = int(ch.instrument) % 128
            if hasattr(ch, 'volume'):
                volume = min(int(ch.volume * 127 / 100), 127)
        
        track.append(Message('program_change', channel=channel, program=instrument, time=0))
        if volume > 0:
            track.append(Message('control_change', channel=channel, control=7, value=volume, time=0))
        
        # Собираем все события с абсолютным временем
        events = []
        current_ticks = 0
        
        for measure in gp_track.measures:
            for voice in measure.voices:
                for beat in voice.beats:
                    # Длительность бита в тиках
                    duration = int(beat.duration.time * 960)
                    
                    # Собираем ноты
                    notes_to_play = []
                    for note in beat.notes:
                        if hasattr(note, 'value') and note.value > 0 and note.value < 128:
                            velocity = int(note.velocity) if hasattr(note, 'velocity') and note.velocity > 0 else 100
                            velocity = min(velocity, 127)
                            notes_to_play.append((int(note.value), velocity))
                    
                    if notes_to_play:
                        # Добавляем Note On события
                        for note_value, velocity in notes_to_play:
                            events.append({
                                'type': 'note_on',
                                'time': current_ticks,
                                'note': note_value,
                                'velocity': velocity
                            })
                        
                        # Добавляем Note Off события
                        for note_value, _ in notes_to_play:
                            events.append({
                                'type': 'note_off',
                                'time': current_ticks + duration,
                                'note': note_value,
                                'velocity': 0
                            })
                    
                    current_ticks += duration
        
        # Сортируем события по времени
        events.sort(key=lambda x: x['time'])
        
        # Конвертируем абсолютное время в delta и добавляем в трек
        last_time = 0
        for event in events:
            delta = event['time'] - last_time
            last_time = event['time']
            
            if event['type'] == 'note_on':
                track.append(Message('note_on',
                                   channel=channel,
                                   note=event['note'],
                                   velocity=event['velocity'],
                                   time=delta))
            else:
                track.append(Message('note_off',
                                   channel=channel,
                                   note=event['note'],
                                   velocity=0,
                                   time=delta))
    
    # Сохраняем
    mid.save(str(output_file))

def recursive_convert(input_dir="gp5_files", output_dir="midi_dataset", flat=False):
    """Рекурсивно сканирует папку и конвертирует все Guitar Pro файлы в MIDI"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    output_path.mkdir(parents=True, exist_ok=True)
    
    gp_files = []
    for ext in ['*.gp5', '*.gp4', '*.gp3']:
        gp_files.extend(list(input_path.rglob(ext)))
    
    if not gp_files:
        print(f"Guitar Pro файлы не найдены в {input_dir}")
        return
    
    gp_files = sorted(set(gp_files))
    
    print(f"Найдено файлов: {len(gp_files)}")
    print("-" * 50)
    
    successful = 0
    failed = 0
    
    for i, gp_file in enumerate(gp_files, 1):
        if flat:
            output_file = output_path / (gp_file.stem + '.mid')
        else:
            relative_path = gp_file.relative_to(input_path)
            output_file = output_path / relative_path.with_suffix('.mid')
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            gp_to_midi(str(gp_file), str(output_file))
            successful += 1
            print(f"[{i}/{len(gp_files)}] ✓ {gp_file.relative_to(input_path)}")
        except Exception as e:
            failed += 1
            print(f"[{i}/{len(gp_files)}] ✗ {gp_file.relative_to(input_path)} - {str(e)[:80]}")
    
    print("-" * 50)
    print(f"Готово! Успешно: {successful}, Ошибок: {failed}")
    
    if successful > 0:
        midi_files = list(output_path.rglob('*.mid'))
        total_size = sum(f.stat().st_size for f in midi_files)
        print(f"Создано файлов: {len(midi_files)}, Общий размер: {total_size / 1024:.1f} KB")

if __name__ == "__main__":
    import subprocess
    try:
        import mido
    except ImportError:
        print("Устанавливаю mido...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "mido"])
        import mido
    
    input_dir = sys.argv[1] if len(sys.argv) > 1 else "gp5_files"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "midi_dataset"
    flat = "--flat" in sys.argv
    
    recursive_convert(input_dir, output_dir, flat)
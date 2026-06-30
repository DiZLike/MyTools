namespace FuzzCast.Source;

public class PlaylistManager : IDisposable
{
    private readonly string _playlistPath;
    private readonly string _statePath;
    private readonly bool _shuffle;
    private List<string> _tracks = new();
    private List<string> _remainingTracks = new();
    private readonly Random _rng = new();
    private FileSystemWatcher? _watcher;
    private DateTime _lastRead = DateTime.MinValue;
    private readonly TimeSpan _debounceInterval = TimeSpan.FromMilliseconds(500);

    public PlaylistManager(string playlistPath, bool shuffle)
    {
        _playlistPath = playlistPath;
        _statePath = Path.ChangeExtension(playlistPath, ".state");
        _shuffle = shuffle;
        Load();
        StartWatching();
    }

    private void Load()
    {
        if (!File.Exists(_playlistPath))
        {
            Console.WriteLine($"[WARN] Playlist not found: {_playlistPath}");
            File.WriteAllText(_playlistPath, "# Add file paths here, one per line\n");
            return;
        }

        var previousTracks = new HashSet<string>(_tracks);

        _tracks = File.ReadAllLines(_playlistPath)
            .Select(line => line.Trim())
            .Where(line => !string.IsNullOrEmpty(line) && !line.StartsWith("#"))
            .ToList();

        if (_tracks.Count == 0)
        {
            Console.WriteLine("[WARN] Playlist is empty");
            ClearState();
            return;
        }

        // Проверяем существование файлов
        var missing = _tracks.Where(t => !File.Exists(t)).ToList();
        foreach (var m in missing)
            Console.WriteLine($"[WARN] File not found: {m}");

        _tracks = _tracks.Where(File.Exists).ToList();

        if (_tracks.Count == 0)
        {
            Console.WriteLine("[WARN] No valid tracks found");
            ClearState();
            return;
        }

        if (_shuffle)
        {
            if (_remainingTracks.Count == 0)
            {
                // Первая загрузка
                LoadState();
            }
            else
            {
                // Динамическое обновление: ищем новые и удалённые треки
                var newTracks = _tracks.Where(t => !previousTracks.Contains(t)).ToList();
                if (newTracks.Count > 0)
                {
                    Console.WriteLine($"[INFO] Found {newTracks.Count} new track(s)");
                    MergeNewTracks(newTracks);
                    SaveState();
                }

                var removedTracks = _remainingTracks.Where(t => !_tracks.Contains(t)).ToList();
                if (removedTracks.Count > 0)
                {
                    Console.WriteLine($"[INFO] {removedTracks.Count} track(s) no longer in playlist");
                    foreach (var track in removedTracks)
                        _remainingTracks.Remove(track);
                    SaveState();
                }
            }
        }
        else
        {
            _remainingTracks = new List<string>(_tracks);
        }

        Console.WriteLine($"Playlist loaded: {_tracks.Count} tracks, {_remainingTracks.Count} remaining");
    }

    private void LoadState()
    {
        if (File.Exists(_statePath))
        {
            var stateTracks = File.ReadAllLines(_statePath)
                .Select(line => line.Trim())
                .Where(line => !string.IsNullOrEmpty(line))
                .ToList();

            _remainingTracks = stateTracks.Where(t => _tracks.Contains(t)).ToList();

            if (_remainingTracks.Count == 0)
            {
                Console.WriteLine("[INFO] All tracks played, reshuffling...");
                _remainingTracks = new List<string>(_tracks);
                ShuffleList(_remainingTracks);
                SaveState();
            }
            else
            {
                var newTracks = _tracks.Where(t => !stateTracks.Contains(t)).ToList();
                if (newTracks.Count > 0)
                {
                    MergeNewTracks(newTracks);
                    SaveState();
                }
            }
        }
        else
        {
            _remainingTracks = new List<string>(_tracks);
            ShuffleList(_remainingTracks);
            SaveState();
        }
    }

    private void MergeNewTracks(List<string> newTracks)
    {
        if (newTracks.Count == 0)
            return;

        // Перемешиваем, чтобы треки одного альбома/артиста не шли группой
        ShuffleList(newTracks);

        // Равномерный шаг: распределяем N новых треков по M существующим слотам
        double step = (double)_remainingTracks.Count / newTracks.Count;

        for (int i = 0; i < newTracks.Count; i++)
        {
            int insertIndex = (int)Math.Round(i * step);
            insertIndex = Math.Clamp(insertIndex, 0, _remainingTracks.Count);
            _remainingTracks.Insert(insertIndex, newTracks[i]);
        }
    }

    public string? GetNext()
    {
        if (_remainingTracks.Count == 0)
            return null;

        var track = _remainingTracks[0];
        _remainingTracks.RemoveAt(0);

        if (_shuffle)
        {
            if (_remainingTracks.Count == 0)
            {
                Console.WriteLine("[INFO] All tracks played, reshuffling...");
                _remainingTracks = new List<string>(_tracks);
                ShuffleList(_remainingTracks);
            }

            SaveState();
        }

        return track;
    }

    public void Reset()
    {
        if (_shuffle)
        {
            _remainingTracks = new List<string>(_tracks);
            ShuffleList(_remainingTracks);
            SaveState();
        }
        else
        {
            _remainingTracks = new List<string>(_tracks);
            ClearState();
        }
    }

    private void SaveState()
    {
        File.WriteAllLines(_statePath, _remainingTracks);
    }

    private void ClearState()
    {
        if (File.Exists(_statePath))
            File.Delete(_statePath);
    }

    private void ShuffleList(List<string> list)
    {
        for (int i = list.Count - 1; i > 0; i--)
        {
            int j = _rng.Next(i + 1);
            (list[i], list[j]) = (list[j], list[i]);
        }
    }

    private void StartWatching()
    {
        var directory = Path.GetDirectoryName(_playlistPath);
        var filename = Path.GetFileName(_playlistPath);

        if (directory == null || filename == null)
            return;

        _watcher = new FileSystemWatcher(directory, filename)
        {
            NotifyFilter = NotifyFilters.LastWrite | NotifyFilters.Size,
            EnableRaisingEvents = true
        };

        _watcher.Changed += OnPlaylistChanged;
    }

    private void OnPlaylistChanged(object sender, FileSystemEventArgs e)
    {
        var now = DateTime.Now;
        if (now - _lastRead < _debounceInterval)
            return;
        _lastRead = now;

        Console.WriteLine("[INFO] Playlist changed, reloading...");
        Thread.Sleep(100);
        Load();
    }

    public void Dispose()
    {
        _watcher?.Dispose();
    }
}
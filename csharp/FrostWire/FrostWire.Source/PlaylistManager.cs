namespace FrostWire.Source;

public class PlaylistManager
{
    private readonly string _playlistPath;
    private readonly bool _shuffle;
    private List<string> _tracks = new();
    private int _currentIndex;
    private readonly Random _rng = new();

    public PlaylistManager(string playlistPath, bool shuffle)
    {
        _playlistPath = playlistPath;
        _shuffle = shuffle;
        Load();
    }

    private void Load()
    {
        if (!File.Exists(_playlistPath))
        {
            Console.WriteLine($"[WARN] Playlist not found: {_playlistPath}");
            File.WriteAllText(_playlistPath, "# Add file paths here, one per line\n");
            return;
        }

        _tracks = File.ReadAllLines(_playlistPath)
            .Select(line => line.Trim())
            .Where(line => !string.IsNullOrEmpty(line) && !line.StartsWith("#"))
            .ToList();

        if (_tracks.Count == 0)
        {
            Console.WriteLine("[WARN] Playlist is empty");
            return;
        }

        // Проверяем существование файлов
        var missing = _tracks.Where(t => !File.Exists(t)).ToList();
        foreach (var m in missing)
            Console.WriteLine($"[WARN] File not found: {m}");

        _tracks = _tracks.Where(File.Exists).ToList();

        if (_shuffle)
            Shuffle();

        Console.WriteLine($"Playlist loaded: {_tracks.Count} tracks");
    }

    public string? GetNext()
    {
        if (_tracks.Count == 0)
            return null;

        if (_currentIndex >= _tracks.Count)
        {
            _currentIndex = 0;
            if (_shuffle)
                Shuffle();
        }

        return _tracks[_currentIndex++];
    }

    public void Reset()
    {
        _currentIndex = 0;
        if (_shuffle)
            Shuffle();
    }

    private void Shuffle()
    {
        for (int i = _tracks.Count - 1; i > 0; i--)
        {
            int j = _rng.Next(i + 1);
            (_tracks[i], _tracks[j]) = (_tracks[j], _tracks[i]);
        }
    }
}
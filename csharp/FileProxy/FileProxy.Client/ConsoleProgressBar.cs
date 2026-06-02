namespace FileProxy.Client;

public class ConsoleProgressBar : IDisposable
{
    private readonly string _label;
    private readonly long _totalBytes;
    private long _currentBytes;
    private readonly int _barWidth;
    private readonly Timer _renderTimer;
    private readonly DateTime _startTime;
    private bool _completed;

    public ConsoleProgressBar(string label, long totalBytes)
    {
        _label = label;
        _totalBytes = totalBytes;
        _startTime = DateTime.UtcNow;
        _barWidth = Math.Min(50, Console.WindowWidth - 30);
        _renderTimer = new Timer(_ => Render(), null, 0, 250);
    }

    public void Update(long bytes) => Interlocked.Add(ref _currentBytes, bytes);

    private void Render()
    {
        if (_completed) return;
        var current = Interlocked.Read(ref _currentBytes);
        var percent = _totalBytes > 0 ? Math.Clamp((double)current / _totalBytes, 0, 1) : 0;
        var filled = (int)(_barWidth * percent);
        var bar = new string('█', filled) + new string('░', _barWidth - filled);
        var elapsed = DateTime.UtcNow - _startTime;
        var speed = elapsed.TotalSeconds > 0 ? current / elapsed.TotalSeconds : 0;
        Console.Write($"\r{_label}: [{bar}] {percent:P0}  {FormatSize(current)} / {FormatSize(_totalBytes)}  {FormatSize((long)speed)}/с  ");
    }

    public void Complete()
    {
        _completed = true;
        _renderTimer.Dispose();
        Interlocked.Exchange(ref _currentBytes, _totalBytes);
        var bar = new string('█', _barWidth);
        var elapsed = DateTime.UtcNow - _startTime;
        var speed = elapsed.TotalSeconds > 0 ? _totalBytes / elapsed.TotalSeconds : 0;
        Console.WriteLine($"\r{_label}: [{bar}] 100%  {FormatSize(_totalBytes)} / {FormatSize(_totalBytes)}  {FormatSize((long)speed)}/с  ");
    }

    public void Dispose() => _renderTimer.Dispose();

    private static string FormatSize(long bytes)
    {
        return bytes switch
        {
            >= 1_073_741_824 => $"{bytes / 1_073_741_824.0:F1} ГБ",
            >= 1_048_576 => $"{bytes / 1_048_576.0:F1} МБ",
            >= 1024 => $"{bytes / 1024.0:F1} КБ",
            _ => $"{bytes} Б"
        };
    }
}
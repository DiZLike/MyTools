using System;
using System.Collections.Generic;

namespace Mp3ToOpus
{
    public class ProgressBar : IDisposable
    {
        private readonly int _total;
        private int _current;
        private readonly int _barLength;
        private readonly object _lock = new();
        private readonly List<string> _extraLines = new();
        private bool _disposed;
        private readonly DateTime _startTime;

        public int Total => _total;
        public DateTime StartTime => _startTime;

        public ProgressBar(int total, int barLength = 30)
        {
            _total = total > 0 ? total : 1;
            _barLength = barLength;
            _startTime = DateTime.Now;
            Console.CursorVisible = false;
        }

        public void Update(int? current = null)
        {
            lock (_lock)
            {
                if (current.HasValue)
                    _current = current.Value;
                else
                    _current++;

                if (_current > _total)
                    _current = _total;

                Render();
            }
        }

        public void SetExtraLines(params string[] lines)
        {
            lock (_lock)
            {
                _extraLines.Clear();
                _extraLines.AddRange(lines);
                Render();
            }
        }

        private void Render()
        {
            var percent = (double)_current / _total * 100;
            var filled = (int)(_barLength * _current / _total);
            var bar = new string('█', filled) + new string('░', _barLength - filled);

            Console.Write($"\r\e[K📊 [{bar}] {percent:F1}% | {_current}/{_total}");

            if (_extraLines.Count > 0)
            {
                foreach (var line in _extraLines)
                    Console.Write($"\n\e[K{line}");
                Console.Write($"\r\e[{_extraLines.Count}A");
            }
        }

        public void Finish(string message = null)
        {
            lock (_lock)
            {
                _current = _total;
                var bar = new string('█', _barLength);
                Console.Write($"\r\e[K📊 [{bar}] 100% | {_total}/{_total}");

                for (int i = 0; i < _extraLines.Count; i++)
                    Console.Write($"\n\e[K");

                if (message != null)
                    Console.Write($"\n{message}");

                Console.WriteLine();
            }
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                Console.CursorVisible = true;
                _disposed = true;
            }
        }
    }

    public class FileSearchProgress : IDisposable
    {
        private readonly object _lock = new();
        private bool _disposed;

        public FileSearchProgress()
        {
            Console.CursorVisible = false;
        }

        public void Update(string currentFile, int found)
        {
            lock (_lock)
            {
                Console.Write($"\r\e[K🔍 Поиск: {found} файлов... {TruncatePath(currentFile, 60)}");
            }
        }

        public void Finish(int total, TimeSpan elapsed)
        {
            lock (_lock)
            {
                Console.Write($"\r\e[K✅ Найдено: {total} файлов за {FormatTime(elapsed)}");
                Console.WriteLine();
                Console.CursorVisible = true;
            }
        }

        private static string TruncatePath(string path, int maxLength)
        {
            if (path.Length <= maxLength) return path;
            return "..." + path[^(maxLength - 3)..];
        }

        private static string FormatTime(TimeSpan ts)
        {
            if (ts.TotalSeconds < 1) return $"{ts.TotalMilliseconds:F0}ms";
            if (ts.TotalSeconds < 60) return $"{ts.TotalSeconds:F1}s";
            return $"{ts.Minutes}m {ts.Seconds}s";
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                Console.CursorVisible = true;
                _disposed = true;
            }
        }
    }
}
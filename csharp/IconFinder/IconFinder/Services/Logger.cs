using System;
using System.IO;

namespace IconFinder.Services
{
    public static class Logger
    {
        private static readonly string LogPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "iconfinder.log");
        private static readonly object _lock = new();

        static Logger()
        {
            File.WriteAllText(LogPath, $"=== IconFinder Log Started: {DateTime.Now} ==={Environment.NewLine}");
        }

        public static void Log(string message)
        {
            lock (_lock)
            {
                var line = $"[{DateTime.Now:HH:mm:ss.fff}] {message}{Environment.NewLine}";
                File.AppendAllText(LogPath, line);
                System.Diagnostics.Debug.Write(line);
            }
        }
    }
}
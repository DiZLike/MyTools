using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Mp3ToOpus
{
    public class AudioConverter
    {
        private readonly Config _config;
        private readonly ProgressBar _progressBar;
        private readonly string _tempDir;
        private readonly string _toolsDir;

        private long _totalBytesOrig;
        private long _totalBytesOpus;
        private int _success;
        private int _skipped;
        private int _failed;
        private int _completed;
        private readonly DateTime _startTime;
        private readonly object _lock = new();
        private readonly object _errorLogLock = new();
        private readonly ConcurrentBag<(string mp3, string opus)> _convertedPairs = new();
        private readonly ConcurrentBag<(string mp3, string opus)> _skippedPairs = new();

        private string OpusEnc => Path.Combine(_toolsDir, "opusenc.exe");
        private string Ffmpeg => Path.Combine(_toolsDir, "ffmpeg.exe");
        private string Ffprobe => Path.Combine(_toolsDir, "ffprobe.exe");
        private string ErrorLogFile => Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "errors.log");

        public int Success => _success;
        public int Skipped => _skipped;
        public int Failed => _failed;
        public long TotalBytesOrig => _totalBytesOrig;
        public long TotalBytesOpus => _totalBytesOpus;
        public IReadOnlyCollection<(string mp3, string opus)> ConvertedPairs => _convertedPairs;
        public IReadOnlyCollection<(string mp3, string opus)> SkippedPairs => _skippedPairs;

        public AudioConverter(Config config, ProgressBar progressBar, string tempDir, string toolsDir)
        {
            _config = config;
            _progressBar = progressBar;
            _tempDir = tempDir;
            _toolsDir = toolsDir;
            _startTime = DateTime.Now;
        }

        public void ConvertAll(List<string> mp3Files)
        {
            var parallelOptions = new ParallelOptions
            {
                MaxDegreeOfParallelism = _config.MaxWorkers
            };

            Parallel.ForEach(mp3Files, parallelOptions, mp3Path =>
            {
                ProcessFile(mp3Path);
            });
        }

        private void ProcessFile(string mp3Path)
        {
            var opusPath = Path.ChangeExtension(mp3Path, ".opus");
            var opusTemp = Path.Combine(_tempDir, $"{Path.GetFileNameWithoutExtension(mp3Path)}_{Thread.CurrentThread.ManagedThreadId}_{Guid.NewGuid():N}.opus.temp");

            // Проверка существующего Opus
            if (File.Exists(opusPath) && new FileInfo(opusPath).Length > 0)
            {
                if (!_config.DeleteExistingOpus)
                {
                    HandleSkip(mp3Path, opusPath);
                    return;
                }
                else
                {
                    try { File.Delete(opusPath); } catch { }
                }
            }

            if (File.Exists(opusPath) && new FileInfo(opusPath).Length == 0)
            {
                try { File.Delete(opusPath); } catch { }
            }

            if (!File.Exists(mp3Path))
            {
                HandleError(mp3Path, "MP3 not found");
                return;
            }

            // Конвертация MP3 -> WAV -> Opus
            var wavTemp = Path.Combine(_tempDir, $"{Path.GetFileNameWithoutExtension(mp3Path)}_{Thread.CurrentThread.ManagedThreadId}_{Guid.NewGuid():N}.wav");
            try
            {
                if (!RunCmd(Ffmpeg, $"-i \"{mp3Path}\" -acodec pcm_s16le -ar 48000 -ac 2 -y \"{wavTemp}\""))
                {
                    HandleError(mp3Path, "MP3->WAV failed");
                    return;
                }

                if (!File.Exists(wavTemp) || new FileInfo(wavTemp).Length == 0)
                {
                    HandleError(mp3Path, "WAV empty");
                    return;
                }

                if (!RunCmd(OpusEnc, $"--bitrate {_config.Bitrate} --framesize {_config.FrameSize} --comp {_config.Complexity} --music \"{wavTemp}\" \"{opusTemp}\""))
                {
                    HandleError(mp3Path, "WAV->Opus failed");
                    CleanupFile(opusTemp);
                    return;
                }

                if (!File.Exists(opusTemp) || new FileInfo(opusTemp).Length == 0)
                {
                    HandleError(mp3Path, "Opus temp empty");
                    CleanupFile(opusTemp);
                    return;
                }
            }
            finally
            {
                CleanupFile(wavTemp);
            }

            // Валидация Opus
            if (!ValidateOpus(opusTemp))
            {
                HandleError(mp3Path, "Opus validation failed");
                CleanupFile(opusTemp);
                return;
            }

            // Метаданные
            var metadata = ExtractMetadata(mp3Path);
            if (metadata.Count > 0)
            {
                ApplyMetadata(opusTemp, metadata);
            }

            // Перемещение результата
            try
            {
                if (File.Exists(opusPath))
                    File.Delete(opusPath);
                File.Move(opusTemp, opusPath);
            }
            catch (Exception ex)
            {
                HandleError(mp3Path, $"Failed to move opus: {ex.Message}");
                CleanupFile(opusTemp);
                return;
            }

            HandleSuccess(mp3Path, opusPath);
        }

        private void HandleSkip(string mp3Path, string opusPath)
        {
            if (!File.Exists(mp3Path))
            {
                HandleError(mp3Path, "MP3 not found (opus exists)");
                return;
            }

            var mp3Size = new FileInfo(mp3Path).Length;
            var opusSize = new FileInfo(opusPath).Length;

            lock (_lock)
            {
                _completed++;
                _skipped++;
                _totalBytesOrig += mp3Size;
                _totalBytesOpus += opusSize;
            }
            _skippedPairs.Add((mp3Path, opusPath));
            UpdateProgress();
        }

        private void HandleSuccess(string mp3Path, string opusPath)
        {
            var mp3Size = new FileInfo(mp3Path).Length;
            var opusSize = new FileInfo(opusPath).Length;

            lock (_lock)
            {
                _completed++;
                _success++;
                _totalBytesOrig += mp3Size;
                _totalBytesOpus += opusSize;
            }
            _convertedPairs.Add((mp3Path, opusPath));
            UpdateProgress();
        }

        private void HandleError(string mp3Path, string message)
        {
            lock (_lock)
            {
                _completed++;
                _failed++;
            }
            LogError($"{message}: {mp3Path}");
            UpdateProgress();
        }

        private void UpdateProgress()
        {
            var elapsed = DateTime.Now - _startTime;
            var filesPerMin = elapsed.TotalMinutes > 0 ? _completed / elapsed.TotalMinutes : 0;
            var saved = _totalBytesOrig - _totalBytesOpus;
            var savedPct = _totalBytesOrig > 0 ? (double)saved / _totalBytesOrig * 100 : 0;

            var eta = filesPerMin > 0
                ? FormatTime(TimeSpan.FromMinutes((_progressBar.Total - _completed) / filesPerMin))
                : "...";

            _progressBar.Update(_completed);
            _progressBar.SetExtraLines(
                $"💾 Было: {FormatSize(_totalBytesOrig)} | Стало: {FormatSize(_totalBytesOpus)} | Экономия: {savedPct:F1}% ({FormatSize(saved)}) | ⚡ {filesPerMin:F1} файл/мин | ⏱️ {FormatTime(elapsed)} | 🕐 {eta}",
                $"✅ {_success} | ⏭️ {_skipped} | ❌ {_failed}"
            );
        }

        private bool ValidateOpus(string opusPath)
        {
            var codecCheck = RunCmdOutput(Ffprobe, $"-v error -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 \"{opusPath}\"");
            return !string.IsNullOrEmpty(codecCheck) && codecCheck.Contains("opus", StringComparison.OrdinalIgnoreCase);
        }

        private Dictionary<string, string> ExtractMetadata(string mp3Path)
        {
            var output = RunCmdOutput(Ffprobe, $"-v quiet -print_format json -show_entries format_tags \"{mp3Path}\"");
            if (string.IsNullOrEmpty(output)) return new();

            try
            {
                using var doc = JsonDocument.Parse(output);
                var tags = doc.RootElement.GetProperty("format").GetProperty("tags");
                var result = new Dictionary<string, string>();
                var keys = new[] { "title", "artist", "album", "date", "track", "genre", "comment" };
                foreach (var key in keys)
                {
                    if (tags.TryGetProperty(key, out var val))
                        result[key] = val.GetString() ?? "";
                }
                return result;
            }
            catch { return new(); }
        }

        private void ApplyMetadata(string opusPath, Dictionary<string, string> metadata)
        {
            if (metadata.Count == 0) return;

            var tempPath = opusPath + ".meta.temp";
            var args = $"-i \"{opusPath}\"";
            foreach (var kv in metadata)
                args += $" -metadata {kv.Key}=\"{kv.Value.Replace("\"", "\\\"")}\"";
            args += $" -c copy -y \"{tempPath}\"";

            if (RunCmd(Ffmpeg, args) && File.Exists(tempPath) && new FileInfo(tempPath).Length > 0)
            {
                File.Delete(opusPath);
                File.Move(tempPath, opusPath);
            }
            else
            {
                CleanupFile(tempPath);
            }
        }

        private bool RunCmd(string exe, string args, int timeoutMs = 300000)
        {
            try
            {
                using var process = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = exe,
                        Arguments = args,
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true
                    }
                };
                process.Start();
                process.WaitForExit(timeoutMs);
                return process.ExitCode == 0;
            }
            catch { return false; }
        }

        private string RunCmdOutput(string exe, string args, int timeoutMs = 30000)
        {
            try
            {
                using var process = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = exe,
                        Arguments = args,
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true
                    }
                };
                process.Start();
                process.WaitForExit(timeoutMs);
                return process.StandardOutput.ReadToEnd();
            }
            catch { return ""; }
        }

        private void LogError(string message)
        {
            lock (_errorLogLock)
            {
                File.AppendAllText(ErrorLogFile, $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}\n");
            }
        }

        public void CleanupTempFiles()
        {
            try
            {
                if (Directory.Exists(_tempDir))
                    Directory.Delete(_tempDir, true);
            }
            catch { }
        }

        private static void CleanupFile(string path)
        {
            try { if (File.Exists(path)) File.Delete(path); } catch { }
        }

        public static string FormatSize(long bytes)
        {
            string[] units = { "B", "KB", "MB", "GB", "TB" };
            var size = (double)bytes;
            var unitIndex = 0;
            while (size >= 1024 && unitIndex < units.Length - 1)
            {
                size /= 1024;
                unitIndex++;
            }
            return $"{size:F1} {units[unitIndex]}";
        }

        public static string FormatTime(TimeSpan ts)
        {
            if (ts.TotalHours >= 1)
                return $"{(int)ts.TotalHours}:{ts.Minutes:D2}:{ts.Seconds:D2}";
            return $"{ts.Minutes}:{ts.Seconds:D2}";
        }
    }
}
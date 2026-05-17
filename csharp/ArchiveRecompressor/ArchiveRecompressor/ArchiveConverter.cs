using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;

namespace ArchiveRecompressor
{
    public class ArchiveConverter
    {
        private readonly Config _config;
        private readonly ProgressBar _progressBar;
        private readonly string _tempDir;
        private readonly string _sevenZipPath;

        private long _totalBytesOrig;
        private long _totalBytes7z;
        private int _success;
        private int _skipped;
        private int _failed;
        private int _completed;
        private readonly DateTime _startTime;
        private readonly object _lock = new();
        private readonly object _errorLogLock = new();
        private readonly List<(string orig, string sevenZ)> _convertedPairs = new();
        private readonly List<(string orig, string sevenZ)> _skippedPairs = new();

        private string ErrorLogFile => Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "errors.log");

        public int Success => _success;
        public int Skipped => _skipped;
        public int Failed => _failed;
        public long TotalBytesOrig => _totalBytesOrig;
        public long TotalBytes7z => _totalBytes7z;
        public IReadOnlyList<(string orig, string sevenZ)> ConvertedPairs => _convertedPairs;
        public IReadOnlyList<(string orig, string sevenZ)> SkippedPairs => _skippedPairs;

        public ArchiveConverter(Config config, ProgressBar progressBar, string tempDir, string sevenZipPath)
        {
            _config = config;
            _progressBar = progressBar;
            _tempDir = tempDir;
            _sevenZipPath = sevenZipPath;
            _startTime = DateTime.Now;
        }

        public void ConvertAll(List<string> archiveFiles)
        {
            foreach (var archivePath in archiveFiles)
            {
                ProcessFile(archivePath);
            }
        }

        private void ProcessFile(string archivePath)
        {
            var archiveName = Path.GetFileNameWithoutExtension(archivePath);
            var archiveDir = Path.GetDirectoryName(archivePath);
            var outputPath = Path.Combine(archiveDir, archiveName + ".7z");

            // Проверяем существующий 7z
            if (File.Exists(outputPath) && new FileInfo(outputPath).Length > 0)
            {
                if (_config.OverwriteExisting7z)
                {
                    // Удаляем существующий 7z — будем перепаковывать
                    try { File.Delete(outputPath); } catch { }
                }
                else
                {
                    // Пропускаем, не перезаписываем
                    HandleSkip(archivePath, outputPath);
                    return;
                }
            }

            if (!File.Exists(archivePath))
            {
                HandleError(archivePath, "Archive not found");
                return;
            }

            // Создаём уникальную временную папку для извлечения
            var extractDir = Path.Combine(_tempDir, $"{archiveName}_{Guid.NewGuid():N}");
            Directory.CreateDirectory(extractDir);

            try
            {
                // Шаг 1: Извлечение
                var extractArgs = $"x \"{archivePath}\" -o\"{extractDir}\" -y";
                if (!RunCmd(_sevenZipPath, extractArgs))
                {
                    HandleError(archivePath, "Extraction failed");
                    return;
                }

                // Проверяем, что что-то извлеклось
                if (!Directory.EnumerateFileSystemEntries(extractDir).Any())
                {
                    HandleError(archivePath, "Extraction produced no files");
                    return;
                }

                // Шаг 2: Сжатие в 7z
                var sevenZipTemp = Path.Combine(_tempDir, $"{archiveName}_{Guid.NewGuid():N}.7z.temp");
                var compressArgs = BuildCompressArgs(sevenZipTemp, extractDir);
                if (!RunCmd(_sevenZipPath, compressArgs))
                {
                    HandleError(archivePath, "Compression failed");
                    CleanupFile(sevenZipTemp);
                    return;
                }

                if (!File.Exists(sevenZipTemp) || new FileInfo(sevenZipTemp).Length == 0)
                {
                    HandleError(archivePath, "7z temp empty");
                    CleanupFile(sevenZipTemp);
                    return;
                }

                // Шаг 3: Валидация
                var testArgs = $"t \"{sevenZipTemp}\"";
                if (!RunCmd(_sevenZipPath, testArgs))
                {
                    HandleError(archivePath, "7z validation failed");
                    CleanupFile(sevenZipTemp);
                    return;
                }

                // Шаг 4: Перемещение результата
                try
                {
                    if (File.Exists(outputPath))
                        File.Delete(outputPath);
                    File.Move(sevenZipTemp, outputPath);
                }
                catch (Exception ex)
                {
                    HandleError(archivePath, $"Failed to move 7z: {ex.Message}");
                    CleanupFile(sevenZipTemp);
                    return;
                }

                HandleSuccess(archivePath, outputPath);
            }
            finally
            {
                // Очистка временной папки извлечения
                try { if (Directory.Exists(extractDir)) Directory.Delete(extractDir, true); } catch { }
            }
        }

        private string BuildCompressArgs(string outputPath, string inputDir)
        {
            var memoryMB = _config.MemoryLimitMB;
            // Для словаря используем 50% от лимита памяти, но не более 1536 МБ
            var dictSize = (int)(memoryMB * 0.9);

            // -t7z: формат
            // -mx=N: уровень сжатия
            // -ms=on/off: solid архив
            // -mmt=1: однопоточный режим
            // -m0=LZMA: метод сжатия (не LZMA2)
            // -md=Nm: размер словаря
            // -mfb=273: максимальный fast bytes
            var solid = _config.SolidArchive ? "on" : "off";

            return $"a -t7z -mx={_config.CompressionLevel} -ms={solid} -mmt=1 " +
                   $"-m0=LZMA:d{dictSize}m -md={dictSize}m -mfb=273 " +
                   $"-y \"{outputPath}\" \"{inputDir}{Path.DirectorySeparatorChar}*\"";
        }

        private void HandleSkip(string origPath, string sevenZPath)
        {
            if (!File.Exists(origPath))
            {
                HandleError(origPath, "Original archive not found (7z exists)");
                return;
            }

            var origSize = new FileInfo(origPath).Length;
            var sevenZSize = new FileInfo(sevenZPath).Length;

            lock (_lock)
            {
                _completed++;
                _skipped++;
                _totalBytesOrig += origSize;
                _totalBytes7z += sevenZSize;
            }
            _skippedPairs.Add((origPath, sevenZPath));
            UpdateProgress();
        }

        private void HandleSuccess(string origPath, string sevenZPath)
        {
            var origSize = new FileInfo(origPath).Length;
            var sevenZSize = new FileInfo(sevenZPath).Length;

            lock (_lock)
            {
                _completed++;
                _success++;
                _totalBytesOrig += origSize;
                _totalBytes7z += sevenZSize;
            }
            _convertedPairs.Add((origPath, sevenZPath));
            UpdateProgress();
        }

        private void HandleError(string archivePath, string message)
        {
            lock (_lock)
            {
                _completed++;
                _failed++;
            }
            LogError($"{message}: {archivePath}");
            UpdateProgress();
        }

        private void UpdateProgress()
        {
            var elapsed = DateTime.Now - _startTime;
            var filesPerMin = elapsed.TotalMinutes > 0 ? _completed / elapsed.TotalMinutes : 0;
            var saved = _totalBytesOrig - _totalBytes7z;
            var savedPct = _totalBytesOrig > 0 ? (double)saved / _totalBytesOrig * 100 : 0;

            var eta = filesPerMin > 0
                ? FormatTime(TimeSpan.FromMinutes((_progressBar.Total - _completed) / filesPerMin))
                : "...";

            _progressBar.Update(_completed);
            _progressBar.SetExtraLines(
                $"💾 Было: {FormatSize(_totalBytesOrig)} | Стало: {FormatSize(_totalBytes7z)} | Экономия: {savedPct:F1}% ({FormatSize(saved)}) | ⚡ {filesPerMin:F1} файл/мин | ⏱️ {FormatTime(elapsed)} | 🕐 {eta}",
                $"✅ {_success} | ⏭️ {_skipped} | ❌ {_failed}"
            );
        }

        private bool RunCmd(string exe, string args, int timeoutMs = 3600000)
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

                if (process.ExitCode != 0)
                {
                    var error = process.StandardError.ReadToEnd();
                    if (!string.IsNullOrEmpty(error))
                    {
                        LogError($"7z exit code {process.ExitCode}: {error.Trim()}");
                    }
                }

                return process.ExitCode == 0;
            }
            catch (Exception ex)
            {
                LogError($"Process error: {ex.Message}");
                return false;
            }
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
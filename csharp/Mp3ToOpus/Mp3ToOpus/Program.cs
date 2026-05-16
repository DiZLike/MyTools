using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Mp3ToOpus
{
    class Program
    {
        static readonly string ToolsDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "tools");
        static string TempDir => Path.Combine(@"D:\temp", "mp3_to_opus_temp");
        static string ErrorLogFile => Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "errors.log");

        static void Main(string[] args)
        {
            Console.OutputEncoding = System.Text.Encoding.UTF8;

            var config = Config.Load();

            if (!CheckTools())
            {
                Console.WriteLine("Нажмите Enter для выхода...");
                Console.ReadLine();
                return;
            }

            Directory.CreateDirectory(TempDir);

            if (!Directory.Exists(config.AudioFolder))
            {
                Console.WriteLine($"Ошибка: Папка {config.AudioFolder} не существует!");
                Console.ReadLine();
                return;
            }

            // Очистка временных файлов
            CleanupOrphanTempFiles(config.AudioFolder);

            // Поиск аудиофайлов с прогрессом
            var audioFiles = FileScanner.FindAudioFiles(config.AudioFolder, new[] { ".mp3", ".wav" });

            if (audioFiles.Count == 0)
            {
                Console.WriteLine($"Аудио файлы не найдены в {config.AudioFolder}");
                Console.ReadLine();
                return;
            }

            // Статистика существующих Opus
            var existingOpus = audioFiles.Count(f => File.Exists(Path.ChangeExtension(f, ".opus")));

            Console.WriteLine("=".PadRight(60, '='));
            Console.WriteLine("КОНВЕРТЕР АУДИО -> OPUS");
            Console.WriteLine("=".PadRight(60, '='));
            Console.WriteLine($"Папка: {config.AudioFolder}");
            Console.WriteLine($"Найдено файлов: {audioFiles.Count}");
            Console.WriteLine($"Битрейт: {config.Bitrate} kbps");
            Console.WriteLine($"Размер кадра: {config.FrameSize} ms");
            Console.WriteLine($"Сложность: {config.Complexity}");
            Console.WriteLine($"Потоков: {config.MaxWorkers} (CPU: {Environment.ProcessorCount})");
            Console.WriteLine($"Переконвертировать Opus: {(config.DeleteExistingOpus ? "Да" : "Нет")}");
            Console.WriteLine($"Временная папка: {TempDir}");
            Console.WriteLine("=".PadRight(60, '='));

            if (existingOpus > 0 && !config.DeleteExistingOpus)
                Console.WriteLine($"\nНайдено {existingOpus} существующих Opus файлов (будут пропущены)");

            Console.WriteLine();

            // Конвертация с прогресс-баром
            using var progressBar = new ProgressBar(audioFiles.Count);
            var converter = new AudioConverter(config, progressBar, TempDir, ToolsDir);
            converter.ConvertAll(audioFiles);

            progressBar.Finish();
            Console.WriteLine();

            // Результаты
            var elapsed = DateTime.Now - progressBar.StartTime;
            PrintResults(converter, elapsed);

            // Ошибки
            if (File.Exists(ErrorLogFile))
            {
                var errorLines = File.ReadAllLines(ErrorLogFile);
                if (errorLines.Length > 0)
                    Console.WriteLine($"\n⚠ Ошибки записаны в: {ErrorLogFile} ({errorLines.Length} шт.)");
            }

            // Удаление оригиналов
            AskForDeletion(converter);

            // Очистка
            converter.CleanupTempFiles();

            Console.WriteLine("\nНажмите Enter для выхода...");
            Console.ReadLine();
        }

        static void PrintResults(AudioConverter converter, TimeSpan elapsed)
        {
            Console.WriteLine("=".PadRight(60, '='));
            Console.WriteLine("РЕЗУЛЬТАТЫ:");
            Console.WriteLine($"  ✅ Успешно: {converter.Success}");
            Console.WriteLine($"  ⏭️ Пропущено: {converter.Skipped}");
            Console.WriteLine($"  ❌ Ошибок: {converter.Failed}");

            if (converter.TotalBytesOrig > 0)
            {
                var saved = converter.TotalBytesOrig - converter.TotalBytesOpus;
                var pct = (1.0 - (double)converter.TotalBytesOpus / converter.TotalBytesOrig) * 100;
                Console.WriteLine($"  💾 Было: {AudioConverter.FormatSize(converter.TotalBytesOrig)}");
                Console.WriteLine($"  📦 Стало: {AudioConverter.FormatSize(converter.TotalBytesOpus)}");
                Console.WriteLine($"  🗜️ Экономия: {AudioConverter.FormatSize(saved)} ({pct:F1}%)");
            }

            Console.WriteLine($"  ⏱️ Время: {AudioConverter.FormatTime(elapsed)}");
            Console.WriteLine("=".PadRight(60, '='));
        }

        static void AskForDeletion(AudioConverter converter)
        {
            var allPairs = converter.ConvertedPairs.Concat(converter.SkippedPairs).ToList();
            if (allPairs.Count == 0) return;

            Console.WriteLine("\n" + "=".PadRight(60, '='));
            Console.WriteLine("УДАЛЕНИЕ ОРИГИНАЛЬНЫХ MP3");
            Console.WriteLine("=".PadRight(60, '='));

            var convList = converter.ConvertedPairs.ToList();
            var skipList = converter.SkippedPairs.ToList();

            if (convList.Count > 0)
            {
                var size = convList.Sum(p => File.Exists(p.mp3) ? new FileInfo(p.mp3).Length : 0);
                Console.WriteLine($"\n1. Конвертированные: {convList.Count} файлов ({AudioConverter.FormatSize(size)})");
            }

            if (skipList.Count > 0)
            {
                var size = skipList.Sum(p => File.Exists(p.mp3) ? new FileInfo(p.mp3).Length : 0);
                Console.WriteLine($"2. Пропущенные: {skipList.Count} файлов ({AudioConverter.FormatSize(size)})");
            }

            var totalSize = allPairs.Sum(p => File.Exists(p.mp3) ? new FileInfo(p.mp3).Length : 0);
            Console.WriteLine($"\nВсего можно удалить: {allPairs.Count} MP3 файлов");
            Console.WriteLine($"Освободится: {AudioConverter.FormatSize(totalSize)}");
            Console.WriteLine("\n⚠ ВНИМАНИЕ: Удаление необратимо!");

            Console.Write("\nУдалить ВСЕ оригинальные MP3? (y/n): ");
            var choice = Console.ReadLine()?.ToLower().Trim();

            if (choice == "y" || choice == "yes")
            {
                FileDeleter.DeleteMp3Files(convList, "Конвертированные");
                FileDeleter.DeleteMp3Files(skipList, "Пропущенные");
                Console.WriteLine("\n✅ Готово!");
            }
            else
            {
                Console.WriteLine("\nОригиналы сохранены.");
            }
        }

        static bool CheckTools()
        {
            var required = new Dictionary<string, string>
            {
                {"opusenc", Path.Combine(ToolsDir, "opusenc.exe")},
                {"ffmpeg", Path.Combine(ToolsDir, "ffmpeg.exe")},
                {"ffprobe", Path.Combine(ToolsDir, "ffprobe.exe")}
            };

            foreach (var (name, path) in required)
            {
                if (!File.Exists(path))
                {
                    Console.WriteLine($"Ошибка: {name} не найден по пути {path}");
                    return false;
                }
            }
            return true;
        }

        static void CleanupOrphanTempFiles(string audioFolder)
        {
            try
            {
                foreach (var tempFile in Directory.GetFiles(audioFolder, "*.opus.temp", SearchOption.AllDirectories))
                {
                    try { File.Delete(tempFile); } catch { }
                }
            }
            catch { }

            try
            {
                if (Directory.Exists(TempDir))
                {
                    foreach (var file in Directory.GetFiles(TempDir))
                    {
                        try { File.Delete(file); } catch { }
                    }
                }
            }
            catch { }
        }
    }
}
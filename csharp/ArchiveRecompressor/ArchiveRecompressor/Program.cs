using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace ArchiveRecompressor
{
    class Program
    {
        static string TempDir => Path.Combine(@"d:\temp", "archive_recompressor_temp");
        static string ErrorLogFile => Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "errors.log");

        static void Main(string[] args)
        {
            Console.OutputEncoding = System.Text.Encoding.UTF8;

            var config = Config.Load();

            var sevenZipPath = Find7Zip();
            if (string.IsNullOrEmpty(sevenZipPath))
            {
                Console.WriteLine("Ошибка: 7-Zip не найден!");
                Console.WriteLine("Установите 7-Zip или укажите путь к 7z.exe в переменной PATH.");
                Console.WriteLine("Скачать: https://www.7-zip.org/");
                Console.WriteLine("\nНажмите Enter для выхода...");
                Console.ReadLine();
                return;
            }

            Console.WriteLine($"Найден 7-Zip: {sevenZipPath}");

            Directory.CreateDirectory(TempDir);

            if (!Directory.Exists(config.ScanFolder))
            {
                Console.WriteLine($"Ошибка: Папка {config.ScanFolder} не существует!");
                Console.ReadLine();
                return;
            }

            // Очистка временных файлов
            CleanupOrphanTempFiles(config.ScanFolder);

            // Поиск архивов с прогрессом
            var archiveFiles = FileScanner.FindArchiveFiles(config.ScanFolder);

            if (archiveFiles.Count == 0)
            {
                Console.WriteLine($"Архивы не найдены в {config.ScanFolder}");
                Console.ReadLine();
                return;
            }

            // Статистика существующих 7z
            var existing7z = archiveFiles.Count(f =>
            {
                var sevenZPath = Path.Combine(Path.GetDirectoryName(f),
                    Path.GetFileNameWithoutExtension(f) + ".7z");
                return File.Exists(sevenZPath);
            });

            Console.WriteLine("=".PadRight(60, '='));
            Console.WriteLine("ПЕРЕПАКОВЩИК АРХИВОВ -> 7Z");
            Console.WriteLine("=".PadRight(60, '='));
            Console.WriteLine($"Папка: {config.ScanFolder}");
            Console.WriteLine($"Найдено архивов: {archiveFiles.Count}");
            Console.WriteLine($"Уровень сжатия: {config.CompressionLevel}");
            Console.WriteLine($"Solid архив: {(config.SolidArchive ? "Да" : "Нет")}");
            Console.WriteLine($"Лимит памяти: {config.MemoryLimitMB} МБ");
            Console.WriteLine($"Перезаписывать существующие 7z: {(config.OverwriteExisting7z ? "Да" : "Нет")}");
            Console.WriteLine($"Удалять оригиналы после: {(config.DeleteOriginalArchive ? "Да" : "Нет")}");
            Console.WriteLine($"Временная папка: {TempDir}");
            Console.WriteLine("=".PadRight(60, '='));

            if (existing7z > 0 && !config.OverwriteExisting7z)
                Console.WriteLine($"\nНайдено {existing7z} существующих 7z файлов (будут пропущены)");

            Console.WriteLine();

            // Конвертация с прогресс-баром
            using var progressBar = new ProgressBar(archiveFiles.Count);
            var converter = new ArchiveConverter(config, progressBar, TempDir, sevenZipPath);
            converter.ConvertAll(archiveFiles);

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

        static string Find7Zip()
        {
            // Стандартные пути установки
            var standardPaths = new[]
            {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "7-Zip", "7z.exe"),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "7-Zip", "7z.exe"),
            };

            foreach (var path in standardPaths)
            {
                if (File.Exists(path))
                    return path;
            }

            // Поиск в PATH
            var pathEnv = Environment.GetEnvironmentVariable("PATH");
            if (!string.IsNullOrEmpty(pathEnv))
            {
                foreach (var dir in pathEnv.Split(';'))
                {
                    var fullPath = Path.Combine(dir.Trim(), "7z.exe");
                    if (File.Exists(fullPath))
                        return fullPath;
                }
            }

            return null;
        }

        static void PrintResults(ArchiveConverter converter, TimeSpan elapsed)
        {
            Console.WriteLine("=".PadRight(60, '='));
            Console.WriteLine("РЕЗУЛЬТАТЫ:");
            Console.WriteLine($"  ✅ Успешно: {converter.Success}");
            Console.WriteLine($"  ⏭️ Пропущено: {converter.Skipped}");
            Console.WriteLine($"  ❌ Ошибок: {converter.Failed}");

            if (converter.TotalBytesOrig > 0)
            {
                var saved = converter.TotalBytesOrig - converter.TotalBytes7z;
                var pct = (double)saved / converter.TotalBytesOrig * 100;
                Console.WriteLine($"  💾 Было: {ArchiveConverter.FormatSize(converter.TotalBytesOrig)}");
                Console.WriteLine($"  📦 Стало: {ArchiveConverter.FormatSize(converter.TotalBytes7z)}");
                Console.WriteLine($"  🗜️ Экономия: {ArchiveConverter.FormatSize(saved)} ({pct:F1}%)");
            }

            Console.WriteLine($"  ⏱️ Время: {ArchiveConverter.FormatTime(elapsed)}");
            Console.WriteLine("=".PadRight(60, '='));
        }

        static void AskForDeletion(ArchiveConverter converter)
        {
            var allPairs = converter.ConvertedPairs.Concat(converter.SkippedPairs).ToList();
            if (allPairs.Count == 0) return;

            Console.WriteLine("\n" + "=".PadRight(60, '='));
            Console.WriteLine("УДАЛЕНИЕ ОРИГИНАЛЬНЫХ АРХИВОВ");
            Console.WriteLine("=".PadRight(60, '='));

            var convList = converter.ConvertedPairs.ToList();
            var skipList = converter.SkippedPairs.ToList();

            if (convList.Count > 0)
            {
                var size = convList.Sum(p => File.Exists(p.orig) ? new FileInfo(p.orig).Length : 0);
                Console.WriteLine($"\n1. Перепакованные: {convList.Count} архивов ({ArchiveConverter.FormatSize(size)})");
            }

            if (skipList.Count > 0)
            {
                var size = skipList.Sum(p => File.Exists(p.orig) ? new FileInfo(p.orig).Length : 0);
                Console.WriteLine($"2. Пропущенные: {skipList.Count} архивов ({ArchiveConverter.FormatSize(size)})");
            }

            var totalSize = allPairs.Sum(p => File.Exists(p.orig) ? new FileInfo(p.orig).Length : 0);
            Console.WriteLine($"\nВсего можно удалить: {allPairs.Count} архивов");
            Console.WriteLine($"Освободится: {ArchiveConverter.FormatSize(totalSize)}");
            Console.WriteLine("\n⚠ ВНИМАНИЕ: Удаление необратимо!");

            Console.Write("\nУдалить ВСЕ оригинальные архивы? (y/n): ");
            var choice = Console.ReadLine()?.ToLower().Trim();

            if (choice == "y" || choice == "yes")
            {
                FileDeleter.DeleteOriginalArchives(convList, "Перепакованные");
                FileDeleter.DeleteOriginalArchives(skipList, "Пропущенные");
                Console.WriteLine("\n✅ Готово!");
            }
            else
            {
                Console.WriteLine("\nОригиналы сохранены.");
            }
        }

        static void CleanupOrphanTempFiles(string scanFolder)
        {
            try
            {
                foreach (var tempFile in Directory.GetFiles(scanFolder, "*.7z.temp", SearchOption.AllDirectories))
                {
                    try { File.Delete(tempFile); } catch { }
                }
            }
            catch { }

            try
            {
                if (Directory.Exists(TempDir))
                {
                    Directory.Delete(TempDir, true);
                }
            }
            catch { }
        }
    }
}
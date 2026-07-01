using System.Text.Json;
using FuzzCast.ReplayGain.Helpers;
using FuzzCast.ReplayGain.Models;
using FuzzCast.ReplayGain.Services;

namespace FuzzCast.ReplayGain;

class Program
{
    static int Main(string[] args)
    {
        args = new string[] { "C:\\Users\\Evgeny\\Music\\GlitchVania" };
        if (args.Length == 0)
        {
            Console.WriteLine("Использование: FuzzCast.ReplayGain <путь к файлу или папке>");
            return 1;
        }

        string inputPath = args[0];

        // Загружаем конфиг
        var config = LoadConfiguration();
        if (config == null) return 1;

        // Инициализируем Bass
        var bassInit = new BassInitializer();
        if (!bassInit.Initialize(config.DecodersPath)) return 1;

        try
        {
            var analyzer = new ReplayGainAnalyzer(config.ReferenceLevel, config.PreAmp);
            var tagWriter = new TagWriter(config.TagCommentFormat);

            // Собираем файлы
            var files = GetFiles(inputPath, config.SupportedExtensions);

            if (files.Count == 0)
            {
                Logger.Warn("Не найдено поддерживаемых аудиофайлов");
                return 0;
            }

            Logger.Info($"Найдено файлов: {files.Count}");

            int processed = 0;
            int errors = 0;
            int skipped = 0;

            foreach (var file in files)
            {
                var result = analyzer.Analyze(file);

                if (!result.Success)
                {
                    Logger.Error($"{Path.GetFileName(file)} -> {result.ErrorMessage}");
                    errors++;
                    continue;
                }

                bool written = tagWriter.Write(file, result);

                if (written)
                {
                    Logger.Ok($"{Path.GetFileName(file)} -> Gain: {result.TrackGain:0.00} dB, RMS: {result.RmsMaxDb:0.00} dB, Peak: {result.TrackPeak:0.000000}");
                    processed++;
                }
                else
                {
                    skipped++;
                }
            }

            Logger.Info($"Обработано: {processed}, ошибок: {errors}, пропущено: {skipped}");
            return errors > 0 ? 1 : 0;
        }
        finally
        {
            bassInit.Free();
        }
    }

    static ReplayGainConfig? LoadConfiguration()
    {
        try
        {
            string configPath = Path.Combine(AppContext.BaseDirectory, "appsettings.json");

            if (!File.Exists(configPath))
            {
                Logger.Error($"Файл конфигурации не найден: {configPath}");
                return new ReplayGainConfig();
            }

            string json = File.ReadAllText(configPath);

            var options = new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true  // Разрешаем разный регистр
            };

            var config = JsonSerializer.Deserialize<ReplayGainConfig>(json, options);

            return config ?? new ReplayGainConfig();
        }
        catch (Exception ex)
        {
            Logger.Error($"Ошибка загрузки конфигурации: {ex.Message}");
            return null;
        }
    }

    static List<string> GetFiles(string path, List<string> extensions)
    {
        var files = new List<string>();

        var normalizedExtensions = extensions
            .Select(e => e.StartsWith('.') ? e.ToLowerInvariant() : $".{e.ToLowerInvariant()}")
            .ToHashSet();

        if (File.Exists(path))
        {
            string ext = Path.GetExtension(path).ToLowerInvariant();
            if (normalizedExtensions.Contains(ext))
                files.Add(path);
        }
        else if (Directory.Exists(path))
        {
            foreach (var file in Directory.EnumerateFiles(path, "*.*", SearchOption.AllDirectories))
            {
                string ext = Path.GetExtension(file).ToLowerInvariant();
                if (normalizedExtensions.Contains(ext))
                    files.Add(file);
            }
        }
        else
        {
            Logger.Error($"Путь не существует: {path}");
        }

        return files;
    }
}
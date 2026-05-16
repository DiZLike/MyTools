using System;
using System.IO;
using System.Text.Json;

namespace Mp3ToOpus
{
    public class Config
    {
        public string AudioFolder { get; set; } = @"Z:\!Evgeny\src\py\downloads";
        public int Bitrate { get; set; } = 40;
        public int FrameSize { get; set; } = 60;
        public int Complexity { get; set; } = 10;
        public bool DeleteExistingOpus { get; set; } = false;
        public int MaxWorkers { get; set; } = Environment.ProcessorCount;

        private static readonly string ConfigFile = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "config.json");

        public static Config Load()
        {
            if (File.Exists(ConfigFile))
            {
                try
                {
                    var json = File.ReadAllText(ConfigFile);
                    var loaded = JsonSerializer.Deserialize<Config>(json);
                    if (loaded != null)
                    {
                        Console.WriteLine($"Загружен конфиг: {ConfigFile}");
                        return loaded;
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Ошибка загрузки конфига: {ex.Message}. Использую значения по умолчанию.");
                }
            }

            var config = new Config();
            config.Save();
            Console.WriteLine($"Создан конфиг по умолчанию: {ConfigFile}");
            return config;
        }

        public void Save()
        {
            var json = JsonSerializer.Serialize(this, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(ConfigFile, json);
        }
    }
}
using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ArchiveRecompressor
{
    public enum MemoryLimit
    {
        MB256 = 256,
        MB512 = 512,
        MB1024 = 1024,
        MB2048 = 2048,
        MB4096 = 4096,
        MB8192 = 8192,
        MB16384 = 16384,
        MB32768 = 32768
    }

    public class Config
    {
        public string ScanFolder { get; set; } = @"F:\!Evgeny\git\MyTools\py\p\downloads";
        public bool DeleteOriginalArchive { get; set; } = true;
        public bool OverwriteExisting7z { get; set; } = true;

        public int CompressionLevel { get; set; } = 9;
        public bool SolidArchive { get; set; } = true;
        public MemoryLimit MemoryLimit { get; set; } = MemoryLimit.MB4096;

        [JsonIgnore]
        public int MemoryLimitMB => (int)MemoryLimit;

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
using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;

namespace IconFinder.Services
{
    public static class JsonService
    {
        public static void SaveToJson<T>(T obj, string path)
        {
            var options = new JsonSerializerOptions
            {
                WriteIndented = true,
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            };
            var json = JsonSerializer.Serialize(obj, options);
            File.WriteAllText(path, json);
        }
        public static T LoadFromJson<T>(string path) where T : new()
        {
            if (!File.Exists(path))
                return new T();

            var json = File.ReadAllText(path);
            return JsonSerializer.Deserialize<T>(json) ?? new T();
        }
    }
}

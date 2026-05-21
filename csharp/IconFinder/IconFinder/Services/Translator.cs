// Файл: Translator.cs - Оптимизированная версия

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

namespace IconFinder.Services
{
    public static class Translator
    {
        private static readonly ConcurrentDictionary<string, string> _dict = new ConcurrentDictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static readonly ConcurrentDictionary<string, byte> _newWords = new ConcurrentDictionary<string, byte>(); // потокобезопасный HashSet
        private static LibreTranslateService _ltService;
        private static string _dictPath;
        private static volatile bool _loaded = false;
        private static readonly object _loadLock = new object();

        public static void LoadDictionary(string dictPath)
        {
            if (_loaded) return;

            lock (_loadLock)
            {
                if (_loaded) return;

                _loaded = true;
                _dictPath = dictPath;

                if (!File.Exists(dictPath))
                {
                    Logger.Log($"Dictionary not found: {dictPath}");
                    return;
                }

                foreach (var line in File.ReadAllLines(dictPath))
                {
                    var parts = line.Split(new[] { " → ", "\t", "=" }, StringSplitOptions.RemoveEmptyEntries);
                    if (parts.Length == 2)
                        _dict.TryAdd(parts[0].Trim().ToLower(), parts[1].Trim().ToLower());
                }

                Logger.Log($"Dictionary: {_dict.Count} words");
            }
        }

        public static void SetTranslateService(LibreTranslateService service)
        {
            _ltService = service;
        }

        public static bool ContainsRussian(string text)
        {
            return text.Any(c => c >= 'а' && c <= 'я' || c >= 'А' && c <= 'Я' || c == 'ё' || c == 'Ё');
        }

        public static async Task<string> TranslateAsync(string query)
        {
            if (string.IsNullOrWhiteSpace(query)) return query;
            if (!ContainsRussian(query)) return query;
            if (query.Length <= 2) return query;

            var words = query.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            var result = new List<string>();
            var unknownIndices = new List<int>();

            // 1. Локальный словарь (точное + частичное совпадение)
            for (int i = 0; i < words.Length; i++)
            {
                var word = words[i].ToLower();

                // Точное совпадение
                if (_dict.TryGetValue(word, out var exactMatch))
                {
                    result.Add(exactMatch);
                    continue;
                }

                // Частичное совпадение
                var partialMatch = _dict
                    .Where(kv => kv.Key.StartsWith(word))
                    .Select(kv => kv.Value)
                    .FirstOrDefault();

                if (partialMatch != null)
                {
                    result.Add(partialMatch);
                    continue;
                }

                // Слово не найдено
                result.Add(word);
                unknownIndices.Add(i);
            }

            // 2. LibreTranslate для неизвестных
            if (unknownIndices.Count > 0 && _ltService?.IsReady == true)
            {
                var toTranslate = string.Join(" ", unknownIndices.Select(i => words[i]));
                Logger.Log($"Translating via server: '{toTranslate}'");

                var translated = await _ltService.TranslateAsync(toTranslate);

                if (!string.IsNullOrEmpty(translated) && translated != toTranslate)
                {
                    Logger.Log($"Server translated: '{toTranslate}' → '{translated}'");

                    var translatedWords = translated.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                    for (int j = 0; j < translatedWords.Length && j < unknownIndices.Count; j++)
                    {
                        var ruWord = words[unknownIndices[j]].ToLower();
                        var enWord = translatedWords[j].ToLower();

                        result[unknownIndices[j]] = enWord;

                        // Добавляем в словарь и в список новых слов
                        if (_dict.TryAdd(ruWord, enWord))
                        {
                            _newWords.TryAdd($"{ruWord} → {enWord}", 0);
                        }
                    }
                }
            }

            var finalResult = string.Join(" ", result);
            return finalResult;
        }

        /// <summary>
        /// Сохраняет новые слова в конец файла словаря. Вызывать при закрытии программы.
        /// </summary>
        public static void SaveNewWords()
        {
            if (_newWords.Count == 0) return;
            if (string.IsNullOrEmpty(_dictPath)) return;

            try
            {
                var linesToAdd = _newWords.Keys
                    .Where(w => !DictContainsLine(w))
                    .ToList();

                if (linesToAdd.Count == 0) return;

                // Добавляем пустую строку перед новыми словами (если файл не пустой)
                var content = File.ReadAllText(_dictPath);
                if (!content.EndsWith("\n") && content.Length > 0)
                    File.AppendAllText(_dictPath, "\n");

                File.AppendAllLines(_dictPath, linesToAdd);
                Logger.Log($"Saved {linesToAdd.Count} new words to dictionary");
                _newWords.Clear();
            }
            catch (Exception ex)
            {
                Logger.Log($"Failed to save dictionary: {ex.Message}");
            }
        }

        private static bool DictContainsLine(string line)
        {
            if (!File.Exists(_dictPath)) return false;
            return File.ReadAllLines(_dictPath).Any(l => l.Trim() == line.Trim());
        }
    }
}
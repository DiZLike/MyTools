using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace IconFinder.Services
{
    public class LibreTranslateService : IDisposable
    {
        private Process _process;
        private HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(5) };
        private string _pythonPath;
        private string _serverUrl = "http://127.0.0.1:5500";
        private bool _started = false;

        public bool IsReady => _started;

        public LibreTranslateService(string basePath)
        {
            _pythonPath = Path.Combine(basePath, "Data", "Python", "python.exe");
        }

        public async Task<bool> StartAsync()
        {
            if (_started) return true;
            if (!File.Exists(_pythonPath))
            {
                Logger.Log("LibreTranslate: executable not found");
                return false;
            }

            // Уже запущен?
            if (await PingAsync())
            {
                _started = true;
                Logger.Log("LibreTranslate: already running");
                return true;
            }

            // Запускаем
            var workingDir = Path.GetDirectoryName(_pythonPath);
            Logger.Log($"LibreTranslate: starting from {_pythonPath}");

            _process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = _pythonPath,
                    Arguments = "-m libretranslate.main --load-only ru,en --host 127.0.0.1 --port 5500",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    WorkingDirectory = workingDir
                }
            };

            _process.OutputDataReceived += (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    Logger.Log($"LT: {e.Data}");
            };
            _process.ErrorDataReceived += (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    Logger.Log($"LT-ERR: {e.Data}");
            };

            _process.Start();
            _process.BeginOutputReadLine();
            _process.BeginErrorReadLine();

            // Ждём до 30 секунд
            for (int i = 0; i < 60; i++)
            {
                await Task.Delay(500);
                if (await PingAsync())
                {
                    _started = true;
                    Logger.Log("LibreTranslate: ready");
                    return true;
                }

                if (_process.HasExited)
                {
                    Logger.Log($"LibreTranslate: process exited with code {_process.ExitCode}");
                    return false;
                }
            }

            Logger.Log("LibreTranslate: timeout");
            return false;
        }

        private async Task<bool> PingAsync()
        {
            try
            {
                var response = await _http.GetAsync($"{_serverUrl}/languages");
                return response.IsSuccessStatusCode;
            }
            catch
            {
                return false;
            }
        }

        public async Task<string> TranslateAsync(string text, string source = "ru", string target = "en")
        {
            if (!_started || string.IsNullOrWhiteSpace(text))
                return text;

            try
            {
                var content = JsonContent.Create(new
                {
                    q = text,
                    source,
                    target,
                    format = "text"
                });

                var response = await _http.PostAsync($"{_serverUrl}/translate", content);
                var json = await response.Content.ReadAsStringAsync();
                var doc = JsonDocument.Parse(json);

                if (doc.RootElement.TryGetProperty("error", out var error))
                {
                    Logger.Log($"LibreTranslate error: {error}");
                    return text;
                }

                return doc.RootElement.GetProperty("translatedText").GetString() ?? text;
            }
            catch (Exception ex)
            {
                Logger.Log($"LibreTranslate translate error: {ex.Message}");
                return text;
            }
        }

        public void Dispose()
        {
            if (_process != null && !_process.HasExited)
            {
                _process.Kill();
                _process.Dispose();
                Logger.Log("LibreTranslate: stopped");
            }
        }
    }

    public static class JsonContent
    {
        public static StringContent Create(object obj)
        {
            var json = JsonSerializer.Serialize(obj);
            return new StringContent(json, System.Text.Encoding.UTF8, "application/json");
        }
    }
}
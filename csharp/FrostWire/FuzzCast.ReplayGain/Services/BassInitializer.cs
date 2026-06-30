using System.Reflection;
using FuzzCast.ReplayGain.Helpers;
using Un4seen.Bass;

namespace FuzzCast.ReplayGain.Services;

public class BassInitializer
{
    private bool _initialized;

    public bool Initialize(string decodersPath)
    {
        if (_initialized) return true;

        // Регистрируем Bass.Net на Windows
        string? currentDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        if (!string.IsNullOrEmpty(currentDir))
        {
            string bassDll = Path.Combine(currentDir, "bass.dll");
            if (File.Exists(bassDll))
                BassNet.Registration("", ""); // можно email и ключ если нужно
        }

        if (!Bass.BASS_Init(0, 44100, BASSInit.BASS_DEVICE_DEFAULT, IntPtr.Zero))
        {
            Logger.Error($"Ошибка инициализации Bass: {Bass.BASS_ErrorGetCode()}");
            return false;
        }

        LoadDecoders(decodersPath);
        _initialized = true;
        return true;
    }

    private void LoadDecoders(string decodersPath)
    {
        if (!Directory.Exists(decodersPath))
        {
            Logger.Warn($"Папка декодеров не найдена: {decodersPath}");
            return;
        }

        var dlls = Directory.GetFiles(decodersPath, "*.dll");
        int loaded = 0;

        foreach (var dll in dlls)
        {
            try
            {
                int pluginHandle = Bass.BASS_PluginLoad(dll);
                if (pluginHandle != 0)
                {
                    loaded++;
                }
            }
            catch
            {
                Logger.Warn($"Не удалось загрузить декодер: {Path.GetFileName(dll)}");
            }
        }

        Logger.Info($"Загружено декодеров: {loaded}");
    }

    public void Free()
    {
        if (_initialized)
        {
            Bass.BASS_PluginFree(0);
            Bass.BASS_Free();
            _initialized = false;
        }
    }
}
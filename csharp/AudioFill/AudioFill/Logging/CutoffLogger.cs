using AudioFill.Audio;
using System;
using System.IO;
using System.Text;

namespace AudioFill.Logging
{
    public static class CutoffLogger
    {
        public static string FormatLog(AnalysisResult result, int fftSize, string windowName, double overlap, bool logScale, double thresholdDb)
        {
            var sb = new StringBuilder();
            sb.AppendLine("======== AudioFill Analysis Log ========");
            sb.AppendLine($"Файл: {result.FilePath}");
            sb.AppendLine($"Формат: {result.SampleRate} Гц, {result.BitsPerSample} бит, каналов: {result.Channels} → моно");
            sb.AppendLine($"Длительность: {TimeSpan.FromSeconds(result.DurationSec):m\\:ss\\.fff}");
            sb.AppendLine($"Размер БПФ: {fftSize}, Окно: {windowName}, Перекрытие: {overlap * 100:0}%");
            sb.AppendLine($"Шкала частот: {(logScale ? "Логарифмическая" : "Линейная")}");
            sb.AppendLine($"Порог среза ВЧ: {thresholdDb} дБ");
            sb.AppendLine("------------------------------------------");
            sb.AppendLine($"Опорный уровень: {result.ReferenceLevelDb} дБ на {result.ReferenceFrequencyHz} Гц");

            if (result.CutoffDetected)
            {
                sb.AppendLine($"Частота среза ВЧ: {result.CutoffFrequencyHz} Гц");
                sb.AppendLine($"Уровень в точке среза: {result.CutoffLevelDb} дБ");
                sb.AppendLine($"Наклон спектра перед срезом: {result.SpectralSlopeDbPerOctave:F1} дБ/октава");
                sb.AppendLine("------------------------------------------");
                sb.AppendLine("Статус: ОБНАРУЖЕН СРЕЗ ВЫСОКИХ ЧАСТОТ");
            }
            else
            {
                sb.AppendLine("Срез ВЧ не обнаружен");
                sb.AppendLine("------------------------------------------");
                sb.AppendLine("Статус: ОК (полный спектр)");
            }

            sb.AppendLine("==========================================");
            return sb.ToString();
        }

        public static void SaveLog(string content, string audioFilePath)
        {
            string dir = Path.GetDirectoryName(audioFilePath) ?? ".";
            string name = Path.GetFileNameWithoutExtension(audioFilePath);
            string logPath = Path.Combine(dir, $"{name}_analysis.txt");
            File.WriteAllText(logPath, content);
        }

        public static void SaveCsv(AnalysisResult result, string audioFilePath)
        {
            string dir = Path.GetDirectoryName(audioFilePath) ?? ".";
            string name = Path.GetFileNameWithoutExtension(audioFilePath);
            string csvPath = Path.Combine(dir, $"{name}_spectrum.csv");

            using var writer = new StreamWriter(csvPath, false, Encoding.UTF8);
            writer.WriteLine("Frequency (Hz),Level (dB)");
            double[] spectrum = result.AvgSpectrumDb;
            int bins = spectrum.Length;
            for (int i = 0; i < bins; i++)
            {
                double freq = i * result.SampleRate / (double)(bins * 2);
                writer.WriteLine($"{freq:F2},{spectrum[i]:F2}");
            }
        }
    }
}
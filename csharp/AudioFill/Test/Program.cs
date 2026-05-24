using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using NAudio.Dsp;
using NAudio.Wave;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;

class Program
{
    static readonly object _consoleLock = new();

    // ================== КОНФИГУРАЦИЯ ==================
    const string ModelPath = "model.onnx";
    const int TargetSampleRate = 48000;
    const int LowSampleRate = 16000;
    const string OriginalFile = "original.wav";
    const string DegradedFile = "degraded.wav";
    const string RestoredFile = "restored.wav";
    const string ChartFile = "frequency_chart.png";
    // =================================================

    static void Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        Console.WriteLine("🎵 Test — FlashSR Audio Restoration");
        Console.WriteLine("===================================\n");

        string? inputFile;
        if (args.Length > 0)
        {
            inputFile = args[0];
            Console.WriteLine($"📂 Файл: {Path.GetFileName(inputFile)}");
        }
        else
        {
            Console.Write("📂 Перетащите аудиофайл и нажмите Enter:\n   ");
            inputFile = Console.ReadLine()?.Trim().Trim('"');
        }

        if (string.IsNullOrEmpty(inputFile) || !File.Exists(inputFile))
        {
            Console.WriteLine("❌ Файл не найден!");
            Console.ReadLine();
            return;
        }

        if (!File.Exists(ModelPath))
        {
            Console.WriteLine($"❌ Модель не найдена: {ModelPath}");
            Console.WriteLine("   Скачайте: https://huggingface.co/YatharthS/FlashSR/resolve/main/onnx/model.onnx");
            Console.ReadLine();
            return;
        }

        try
        {
            // ===== Шаг 1 и 2: Загружаем эталон и готовим испорченный трек =====
            Console.WriteLine("\n⚙️  Загрузка и подготовка аудио...");

            float[] originalLeft, originalRight, degradedLeft, degradedRight;
            using (var reader = new MediaFoundationReader(inputFile))
            {
                int channels = reader.WaveFormat.Channels;
                Console.WriteLine($"   Источник: {reader.WaveFormat.SampleRate} Гц, {channels} кан.");

                using var resampler = new MediaFoundationResampler(reader, new WaveFormat(TargetSampleRate, channels));
                var allSamples = ReadAllSamples(resampler.ToSampleProvider());

                int totalFrames = allSamples.Length / channels;
                originalLeft = new float[totalFrames];
                originalRight = new float[totalFrames];
                for (int i = 0; i < totalFrames; i++)
                {
                    originalLeft[i] = allSamples[i * channels];
                    originalRight[i] = channels > 1 ? allSamples[i * channels + 1] : allSamples[i * channels];
                }

                degradedLeft = DegradeAudio(originalLeft, TargetSampleRate);
                degradedRight = DegradeAudio(originalRight, TargetSampleRate);
            }

            // ===== Шаг 3: Восстановление через FlashSR (параллельно) =====
            Console.WriteLine("\n🧠 Восстановление высоких частот через FlashSR...");

            float[] left16k = To16k(degradedLeft, TargetSampleRate);
            float[] right16k = To16k(degradedRight, TargetSampleRate);

            float[]? restoredLeft = null;
            float[]? restoredRight = null;

            Parallel.Invoke(
                () => restoredLeft = FlashSRRestore(left16k, ModelPath, "Левый"),
                () => restoredRight = FlashSRRestore(right16k, ModelPath, "Правый")
            );

            // ===== Шаг 4: Сохраняем WAV-файлы =====
            Console.WriteLine("\n💾 Сохранение WAV-файлов...");
            SaveStereoWav(OriginalFile, originalLeft, originalRight, TargetSampleRate);
            SaveStereoWav(DegradedFile, degradedLeft, degradedRight, TargetSampleRate);
            SaveStereoWav(RestoredFile, restoredLeft!, restoredRight!, TargetSampleRate);

            // ===== Шаг 5: Рисуем АЧХ =====
            Console.WriteLine("📊 Построение графика АЧХ...");
            DrawFrequencyChart(originalLeft, degradedLeft, restoredLeft!, TargetSampleRate, ChartFile);

            Console.WriteLine("\n✅ Готово!");
            Console.WriteLine($"   {OriginalFile} — оригинал");
            Console.WriteLine($"   {DegradedFile} — с обрезанными ВЧ");
            Console.WriteLine($"   {RestoredFile} — восстановленный FlashSR");
            Console.WriteLine($"   {ChartFile} — сравнение АЧХ");
            Console.ReadLine();
        }
        catch (Exception ex)
        {
            Console.WriteLine($"\n❌ Ошибка: {ex.Message}");
            Console.WriteLine(ex.StackTrace);
            Console.ReadLine();
        }
    }

    // ================== МЕТОДЫ ==================

    static float[] ReadAllSamples(ISampleProvider provider)
    {
        var samples = new List<float>();
        var buffer = new float[4096];
        int read;
        while ((read = provider.Read(buffer, 0, buffer.Length)) > 0)
            samples.AddRange(buffer.Take(read));
        return samples.ToArray();
    }

    static float[] DegradeAudio(float[] samples, int sourceRate)
    {
        var low = Resample(samples, sourceRate, LowSampleRate);
        return Resample(low, LowSampleRate, sourceRate);
    }

    static float[] To16k(float[] samples, int sourceRate)
    {
        return Resample(samples, sourceRate, LowSampleRate);
    }

    static float[] Resample(float[] samples, int fromRate, int toRate)
    {
        var format = new WaveFormat(fromRate, 16, 1);
        var bytes = new byte[samples.Length * 2];
        for (int i = 0; i < samples.Length; i++)
        {
            short s = (short)Math.Clamp(samples[i] * 32767f, -32768, 32767);
            BitConverter.GetBytes(s).CopyTo(bytes, i * 2);
        }

        using var rawStream = new RawSourceWaveStream(new MemoryStream(bytes), format);
        using var resampler = new MediaFoundationResampler(rawStream, new WaveFormat(toRate, 1));
        return ReadAllSamples(resampler.ToSampleProvider());
    }

    static float[] FlashSRRestore(float[] samples16k, string modelPath, string channelName)
    {
        using var session = new InferenceSession(modelPath);

        const int inputChunkSize = 16000;

        var restoredChunks = new List<float[]>();
        int totalChunks = (int)Math.Ceiling((double)samples16k.Length / inputChunkSize);

        for (int i = 0; i < samples16k.Length; i += inputChunkSize)
        {
            int chunkSize = Math.Min(inputChunkSize, samples16k.Length - i);
            var chunk = new float[inputChunkSize];

            Array.Copy(samples16k, i, chunk, 0, chunkSize);

            var inputTensor = new DenseTensor<float>(chunk, new[] { 1, inputChunkSize });
            var inputs = new List<NamedOnnxValue>
            {
                NamedOnnxValue.CreateFromTensor("audio_values", inputTensor)
            };

            using var results = session.Run(inputs);
            var outputTensor = results.First().AsTensor<float>();
            var restored = outputTensor.ToArray();

            if (i + chunkSize >= samples16k.Length)
            {
                int validOutputSamples = chunkSize * 3;
                var trimmed = new float[validOutputSamples];
                Array.Copy(restored, trimmed, validOutputSamples);
                restoredChunks.Add(trimmed);
            }
            else
            {
                restoredChunks.Add(restored);
            }

            int current = i / inputChunkSize + 1;
            lock (_consoleLock)
            {
                DrawProgressBar(channelName, current, totalChunks);
            }
        }

        lock (_consoleLock)
        {
            Console.WriteLine();
        }

        return restoredChunks.SelectMany(c => c).ToArray();
    }

    static void DrawProgressBar(string label, int current, int total)
    {
        const int barWidth = 30;
        float percent = (float)current / total;
        int filled = (int)(barWidth * percent);

        Console.Write($"\r   {label}: [");
        Console.Write(new string('█', filled));
        Console.Write(new string('░', barWidth - filled));
        Console.Write($"] {current}/{total}");
    }

    static void SaveStereoWav(string path, float[] left, float[] right, int sampleRate)
    {
        int length = Math.Max(left.Length, right.Length);
        using var writer = new WaveFileWriter(path, new WaveFormat(sampleRate, 2));
        var buffer = new float[2];
        for (int i = 0; i < length; i++)
        {
            buffer[0] = i < left.Length ? left[i] : 0f;
            buffer[1] = i < right.Length ? right[i] : 0f;
            writer.WriteSamples(buffer, 0, 2);
        }
    }

    static void DrawFrequencyChart(float[] original, float[] degraded, float[] restored, int sampleRate, string outputPath)
    {
        int fftSize = 8192;
        var origSpec = ComputeAvgSpectrum(original, fftSize);
        var degrSpec = ComputeAvgSpectrum(degraded, fftSize);
        var restSpec = ComputeAvgSpectrum(restored, fftSize);

        int w = 1200, h = 600;
        int ml = 70, mr = 30, mt = 30, mb = 50;
        int pw = w - ml - mr, ph = h - mt - mb;

        using var bmp = new Bitmap(w, h);
        using var g = Graphics.FromImage(bmp);
        g.Clear(Color.FromArgb(24, 24, 27));
        g.SmoothingMode = SmoothingMode.AntiAlias;

        var plotRect = new Rectangle(ml, mt, pw, ph);

        using (var gridPen = new Pen(Color.FromArgb(50, 50, 60), 0.5f))
        using (var axisPen = new Pen(Color.FromArgb(120, 120, 130), 1.5f))
        using (var font = new Font("Segoe UI", 9))
        using (var brush = new SolidBrush(Color.FromArgb(200, 200, 200)))
        {
            for (int db = 0; db >= -100; db -= 10)
            {
                float y = plotRect.Top + (float)(-db / 100.0 * ph);
                g.DrawLine(gridPen, plotRect.Left, y, plotRect.Right, y);
                g.DrawString($"{db} дБ", font, brush, 5, y - 8);
            }
            int[] freqs = { 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000 };
            double logMin = Math.Log10(20);
            double logMax = Math.Log10(sampleRate / 2.0);
            foreach (int f in freqs)
            {
                if (f > sampleRate / 2) continue;
                float x = plotRect.Left + (float)((Math.Log10(f) - logMin) / (logMax - logMin) * pw);
                g.DrawLine(gridPen, x, plotRect.Top, x, plotRect.Bottom);
                string label = f >= 1000 ? $"{f / 1000} кГц" : $"{f} Гц";
                g.DrawString(label, font, brush, x - 20, plotRect.Bottom + 5);
            }
            g.DrawRectangle(axisPen, plotRect);
        }

        DrawCurve(g, origSpec, sampleRate, plotRect, Color.FromArgb(0, 150, 255), 2f);
        DrawCurve(g, degrSpec, sampleRate, plotRect, Color.FromArgb(255, 80, 80), 1.5f);
        DrawCurve(g, restSpec, sampleRate, plotRect, Color.FromArgb(0, 230, 100), 1.5f);

        using (var font = new Font("Segoe UI", 10))
        {
            g.DrawString("─ Оригинал", font, new SolidBrush(Color.FromArgb(0, 150, 255)), plotRect.Right - 200, plotRect.Top + 10);
            g.DrawString("─ Испорченный", font, new SolidBrush(Color.FromArgb(255, 80, 80)), plotRect.Right - 200, plotRect.Top + 30);
            g.DrawString("─ FlashSR", font, new SolidBrush(Color.FromArgb(0, 230, 100)), plotRect.Right - 200, plotRect.Top + 50);
        }

        bmp.Save(outputPath, ImageFormat.Png);
    }

    static double[] ComputeAvgSpectrum(float[] samples, int fftSize)
    {
        int bins = fftSize / 2;
        double[] sum = new double[bins];
        int chunks = 0;

        for (int off = 0; off + fftSize <= samples.Length; off += fftSize / 2)
        {
            var data = new Complex[fftSize];
            for (int i = 0; i < fftSize; i++)
            {
                double w = 0.5 * (1 - Math.Cos(2 * Math.PI * i / (fftSize - 1)));
                data[i] = new Complex { X = (float)(samples[off + i] * w), Y = 0 };
            }
            FastFourierTransform.FFT(true, (int)Math.Log2(fftSize), data);
            for (int i = 0; i < bins; i++)
            {
                double mag = Math.Sqrt(data[i].X * data[i].X + data[i].Y * data[i].Y);
                sum[i] += 20 * Math.Log10(Math.Max(mag, 1e-10));
            }
            chunks++;
        }

        for (int i = 0; i < bins; i++)
            sum[i] /= Math.Max(1, chunks);
        return sum;
    }

    static void DrawCurve(Graphics g, double[] spectrum, int sampleRate, Rectangle rect, Color color, float width)
    {
        using var pen = new Pen(color, width);
        var pts = new List<PointF>();
        double logMin = Math.Log10(20);
        double logMax = Math.Log10(sampleRate / 2.0);

        for (int i = 0; i < spectrum.Length; i++)
        {
            double freq = i * sampleRate / (double)(spectrum.Length * 2);
            if (freq < 20) continue;
            float x = rect.Left + (float)((Math.Log10(freq) - logMin) / (logMax - logMin) * rect.Width);
            float y = rect.Bottom - (float)((Math.Max(spectrum[i], -100) + 100) / 100.0 * rect.Height);
            pts.Add(new PointF(x, Math.Clamp(y, rect.Top, rect.Bottom)));
        }

        if (pts.Count > 1)
            g.DrawLines(pen, pts.ToArray());
    }
}
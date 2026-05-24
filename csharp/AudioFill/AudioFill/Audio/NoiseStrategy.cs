using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using NAudio.Dsp;
using Complex = NAudio.Dsp.Complex;

namespace AudioFill.Audio.Restore
{
    public class NoiseStrategy : IRestoreStrategy
    {
        public string Name => "Musical Noise Synthesis";
        public int FftSize { get; set; } = 2048;
        public int OverlapFactor { get; set; } = 4;
        public int Iterations { get; set; } = 5;

        private List<string> _log = null!;

        public float[] GenerateFill(float[] signal, int sampleRate, double cutoffFrequency, double cutoffLevelDb,
                                    AnalysisResult analysisResult,
                                    IProgress<RestoreProgress>? progress, List<string> debugLog)
        {
            _log = debugLog;
            var startTime = DateTime.Now;

            void Report(int percent, string step, string? details = null)
            {
                if (progress == null) return;
                var elapsed = DateTime.Now - startTime;
                var remaining = percent > 0 ? elapsed * (100 - percent) / percent : TimeSpan.Zero;
                progress.Report(new RestoreProgress
                {
                    Percent = percent,
                    Step = details != null ? $"{step} ({details})" : step,
                    Elapsed = elapsed,
                    Remaining = remaining
                });
            }

            int length = signal.Length;
            double fCut = cutoffFrequency;
            double spectralSlope = analysisResult.SpectralSlopeDbPerOctave;
            Log($"Spectral slope: {spectralSlope:F1} dB/oct");

            Report(0, "Анализ уровней и динамики");

            // Измеряем уровень в полосах перед срезом
            double band1Low = fCut * 0.70;
            double band1High = fCut * 0.85;
            var band1 = BandpassSimple(signal, band1Low, band1High, sampleRate);
            float rms1 = Rms(band1);

            double band2Low = fCut * 0.85;
            double band2High = fCut * 0.95;
            var band2 = BandpassSimple(signal, band2Low, band2High, sampleRate);
            float rms2 = Rms(band2);

            double band3Low = fCut * 0.95;
            double band3High = fCut * 1.00;
            var band3 = BandpassSimple(signal, band3Low, band3High, sampleRate);
            float rms3 = Rms(band3);

            float targetRms = Math.Max(Math.Max(rms1, rms2), rms3);
            Log($"Target RMS: {targetRms:F6}");

            if (targetRms < 0.00001f)
            {
                var wideBand = BandpassSimple(signal, fCut * 0.3, fCut * 0.9, sampleRate);
                targetRms = Rms(wideBand);
                if (targetRms < 0.00001f)
                {
                    Report(100, "Сигнал слишком тихий");
                    return new float[length];
                }
            }

            // Выбираем полосу для огибающей
            float bestRms = rms1;
            double envLow = band1Low;
            double envHigh = band1High;
            if (rms2 > bestRms) { bestRms = rms2; envLow = band2Low; envHigh = band2High; }
            if (rms3 > bestRms) { bestRms = rms3; envLow = band3Low; envHigh = band3High; }

            var envelopeSource = BandpassSimple(signal, envLow, envHigh, sampleRate);

            // Извлекаем основную огибающую
            var mainEnvelope = ExtractEnvelope(envelopeSource, sampleRate);

            // Извлекаем микро-динамику
            var microDynamics = ExtractMicroDynamics(envelopeSource, sampleRate);

            Report(20, "Генерация розового шума");

            // Генерируем розовый шум
            var noise = GeneratePinkNoise(length);

            Report(40, "Фильтрация шума");

            // Highpass
            var highpassNoise = HighpassSimple(noise, fCut, sampleRate);

            Report(50, "Применение спектрального спада");

            // Применяем спектральный спад к шуму
            if (Math.Abs(spectralSlope) > 0.5)
            {
                highpassNoise = ApplySpectralTilt(highpassNoise, sampleRate, fCut, spectralSlope);
            }

            Report(60, "Применение огибающих");

            // Применяем основную огибающую
            var envelopedNoise = new float[length];
            for (int i = 0; i < length; i++)
                envelopedNoise[i] = highpassNoise[i] * mainEnvelope[i];

            // Применяем микро-динамику
            for (int i = 0; i < length; i++)
                envelopedNoise[i] *= (0.7f + 0.3f * microDynamics[i]);

            // Амплитудная модуляция
            float modFreq1 = 4.5f;
            float modFreq2 = 7.3f;
            for (int i = 0; i < length; i++)
            {
                double mod1 = Math.Sin(2 * Math.PI * modFreq1 * i / sampleRate);
                double mod2 = Math.Cos(2 * Math.PI * modFreq2 * i / sampleRate);
                float modulation = 1.0f + 0.15f * (float)(mod1 + mod2) * 0.5f;
                envelopedNoise[i] *= modulation;
            }

            Report(80, "Масштабирование");

            // Масштабируем до целевого уровня
            float envelopedRms = Rms(envelopedNoise);
            float scale = targetRms / Math.Max(envelopedRms, 0.0000001f);
            Log($"Scale factor: {scale:F3}");

            for (int i = 0; i < length; i++)
                envelopedNoise[i] *= scale;

            // Мягкий saturation
            for (int i = 0; i < length; i++)
            {
                float x = envelopedNoise[i];
                float saturated = (float)Math.Tanh(x * 2.0f) * 0.7f + x * 0.3f;
                envelopedNoise[i] = saturated;
            }

            float finalRms = Rms(envelopedNoise);
            Log($"Final noise RMS: {finalRms:F6}");

            Report(100, "Готово");
            return envelopedNoise;
        }

        // ==================== СПЕКТРАЛЬНЫЙ СПАД ====================

        private float[] ApplySpectralTilt(float[] signal, int sampleRate,
                                           double cutoffFreq, double slopeDbPerOctave)
        {
            int length = signal.Length;
            int fftSize = 4096;
            int hopSize = fftSize / 4;
            int bins = fftSize / 2;

            var window = new float[fftSize];
            for (int i = 0; i < fftSize; i++)
                window[i] = (float)(0.5 - 0.5 * Math.Cos(2 * Math.PI * i / (fftSize - 1)));

            var outputAccum = new double[length];
            var windowAccum = new double[length];

            int numFrames = Math.Max(1, (length - fftSize) / hopSize + 1);

            for (int frame = 0; frame < numFrames; frame++)
            {
                int offset = frame * hopSize;
                var fft = new Complex[fftSize];

                for (int i = 0; i < fftSize && offset + i < length; i++)
                {
                    fft[i].X = signal[offset + i] * window[i];
                    fft[i].Y = 0;
                }

                FastFourierTransform.FFT(true, (int)Math.Log2(fftSize), fft);

                // Применяем наклон к магнитудам после cutoff
                for (int i = 0; i < bins; i++)
                {
                    double freq = i * sampleRate / (double)fftSize;
                    if (freq > cutoffFreq && freq > 0)
                    {
                        double octavesAbove = Math.Log2(freq / cutoffFreq);
                        double attenuationDb = slopeDbPerOctave * octavesAbove;
                        double gain = Math.Pow(10, attenuationDb / 20.0);
                        gain = Math.Clamp(gain, 0.001, 1.0);

                        fft[i].X *= (float)gain;
                        fft[i].Y *= (float)gain;
                    }
                }

                FastFourierTransform.FFT(false, (int)Math.Log2(fftSize), fft);

                for (int i = 0; i < fftSize && offset + i < length; i++)
                {
                    outputAccum[offset + i] += fft[i].X * window[i];
                    windowAccum[offset + i] += window[i] * window[i];
                }
            }

            var result = new float[length];
            for (int i = 0; i < length; i++)
            {
                if (windowAccum[i] > 0.001)
                    result[i] = (float)(outputAccum[i] / windowAccum[i]);
            }

            return result;
        }

        // ==================== РОЗОВЫЙ ШУМ ====================

        private float[] GeneratePinkNoise(int length)
        {
            var noise = new float[length];
            var rng = new Random(42);

            float b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;

            for (int i = 0; i < length; i++)
            {
                float white = (float)(rng.NextDouble() * 2 - 1);

                b0 = 0.99886f * b0 + white * 0.0555179f;
                b1 = 0.99332f * b1 + white * 0.0750759f;
                b2 = 0.96900f * b2 + white * 0.1538520f;
                b3 = 0.86650f * b3 + white * 0.3104856f;
                b4 = 0.55000f * b4 + white * 0.5329522f;
                b5 = -0.7616f * b5 - white * 0.0168980f;

                noise[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362f) * 0.11f;
                b6 = white * 0.115926f;
            }

            return noise;
        }

        // ==================== МИКРО-ДИНАМИКА ====================

        private float[] ExtractMicroDynamics(float[] signal, int sampleRate)
        {
            int length = signal.Length;

            var fastEnvelope = new float[length];
            var rectified = new float[length];

            for (int i = 0; i < length; i++)
                rectified[i] = Math.Abs(signal[i]);

            double cutoffFreq = 200.0;
            double rc = 1.0 / (2 * Math.PI * cutoffFreq);
            double dt = 1.0 / sampleRate;
            double alpha = dt / (rc + dt);

            fastEnvelope[0] = rectified[0];
            for (int i = 1; i < length; i++)
                fastEnvelope[i] = (float)(fastEnvelope[i - 1] + alpha * (rectified[i] - fastEnvelope[i - 1]));

            float maxVal = 0;
            for (int i = 0; i < length; i++)
                maxVal = Math.Max(maxVal, fastEnvelope[i]);

            if (maxVal > 0.0001f)
            {
                float normFactor = 1.0f / maxVal;
                for (int i = 0; i < length; i++)
                    fastEnvelope[i] *= normFactor;
            }

            return fastEnvelope;
        }

        // ==================== ОГИБАЮЩАЯ ====================

        private float[] ExtractEnvelope(float[] signal, int sampleRate)
        {
            int length = signal.Length;
            var envelope = new float[length];

            var rectified = new float[length];
            for (int i = 0; i < length; i++)
                rectified[i] = Math.Abs(signal[i]);

            double cutoffFreq = 50.0;
            double rc = 1.0 / (2 * Math.PI * cutoffFreq);
            double dt = 1.0 / sampleRate;
            double alpha = dt / (rc + dt);

            envelope[0] = rectified[0];
            for (int i = 1; i < length; i++)
                envelope[i] = (float)(envelope[i - 1] + alpha * (rectified[i] - envelope[i - 1]));

            float maxVal = 0;
            for (int i = 0; i < length; i++)
                maxVal = Math.Max(maxVal, envelope[i]);

            if (maxVal > 0.0001f)
            {
                float normFactor = 1.0f / maxVal;
                for (int i = 0; i < length; i++)
                    envelope[i] *= normFactor;
            }

            var smoothed = new float[length];
            smoothed[0] = envelope[0];

            float attackTime = 0.005f;
            float releaseTime = 0.05f;
            float attackCoeff = (float)Math.Exp(-1.0 / (sampleRate * attackTime));
            float releaseCoeff = (float)Math.Exp(-1.0 / (sampleRate * releaseTime));

            for (int i = 1; i < length; i++)
            {
                float coeff = envelope[i] > smoothed[i - 1] ? attackCoeff : releaseCoeff;
                smoothed[i] = envelope[i] + coeff * (smoothed[i - 1] - envelope[i]);
            }

            float envelopeRms = Rms(smoothed);
            if (envelopeRms > 0.0001f)
            {
                float envelopeGain = 1.0f / envelopeRms;
                for (int i = 0; i < length; i++)
                    smoothed[i] *= envelopeGain;
            }

            return smoothed;
        }

        // ==================== ФИЛЬТРЫ ====================

        private static float[] HighpassSimple(float[] s, double cutoff, int sampleRate)
        {
            var r = new float[s.Length];
            if (s.Length < 2) return r;
            double rc = 1.0 / (2 * Math.PI * cutoff);
            double dt = 1.0 / sampleRate;
            double alpha = dt / (rc + dt);

            var lp = new float[s.Length];
            lp[0] = (float)(alpha * s[0]);
            for (int i = 1; i < s.Length; i++)
                lp[i] = (float)(lp[i - 1] + alpha * (s[i] - lp[i - 1]));

            for (int i = 0; i < s.Length; i++)
                r[i] = s[i] - lp[i];

            return r;
        }

        private static float[] BandpassSimple(float[] s, double lowCut, double highCut, int sampleRate)
        {
            var lp = LowpassSimple(s, highCut, sampleRate);
            return HighpassSimple(lp, lowCut, sampleRate);
        }

        private static float[] LowpassSimple(float[] s, double cutoff, int sampleRate)
        {
            var r = new float[s.Length];
            if (s.Length < 2) return r;
            double rc = 1.0 / (2 * Math.PI * cutoff);
            double dt = 1.0 / sampleRate;
            double alpha = dt / (rc + dt);
            r[0] = (float)(alpha * s[0]);
            for (int i = 1; i < s.Length; i++)
                r[i] = (float)(r[i - 1] + alpha * (s[i] - r[i - 1]));
            return r;
        }

        private static float Rms(float[] s)
        {
            if (s == null || s.Length == 0) return 0;
            double sum = 0;
            for (int i = 0; i < s.Length; i++) sum += (double)s[i] * s[i];
            return (float)Math.Sqrt(sum / s.Length);
        }

        private void Log(string msg) => _log.Add($"[{DateTime.Now:HH:mm:ss.fff}] {msg}");
    }
}
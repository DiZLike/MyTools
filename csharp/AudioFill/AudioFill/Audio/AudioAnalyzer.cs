using NAudio.Wave;
using NAudio.Dsp;
using Complex = NAudio.Dsp.Complex;

namespace AudioFill.Audio
{
    public class AudioAnalyzer
    {
        private readonly int _fftSize;
        private readonly double _overlap;
        private readonly int _windowType;
        private readonly double _cutoffThresholdDb;
        private readonly int _cutoffPersistence;

        public AudioAnalyzer(int fftSize = 4096, double overlap = 0.5, int windowType = 0,
                             double cutoffThresholdDb = -40, int cutoffPersistence = 5)
        {
            _fftSize = fftSize;
            _overlap = Math.Clamp(overlap, 0, 0.75);
            _windowType = windowType;
            _cutoffThresholdDb = cutoffThresholdDb;
            _cutoffPersistence = cutoffPersistence;
        }

        public AnalysisResult Analyze(string filePath, Action<int>? progressCallback = null)
        {
            using var reader = new MediaFoundationReader(filePath);
            var result = new AnalysisResult
            {
                FilePath = filePath,
                SampleRate = reader.WaveFormat.SampleRate,
                BitsPerSample = reader.WaveFormat.BitsPerSample,
                Channels = reader.WaveFormat.Channels,
                DurationSec = reader.TotalTime.TotalSeconds
            };

            int channels = reader.WaveFormat.Channels;
            var provider = reader.ToSampleProvider();

            int fftBins = _fftSize / 2;
            double[] sumSpectrum = new double[fftBins];
            var spectrogram = new List<double[]>();
            int totalSamples = (int)(result.DurationSec * result.SampleRate);
            int hopSize = (int)(_fftSize * (1 - _overlap));
            if (hopSize <= 0) hopSize = _fftSize;
            int totalSteps = totalSamples / hopSize;
            int processedSteps = 0;

            var interleavedBuffer = new float[_fftSize * channels];
            var monoBuffer = new float[_fftSize];
            var fftBuffer = new Complex[_fftSize];
            var window = CreateWindow();

            while (true)
            {
                int read = provider.Read(interleavedBuffer, 0, _fftSize * channels);
                int framesRead = read / channels;

                if (framesRead == 0 && processedSteps > 0) break;

                Array.Clear(monoBuffer, 0, _fftSize);
                for (int i = 0; i < framesRead; i++)
                {
                    double sum = 0;
                    for (int ch = 0; ch < channels; ch++)
                        sum += interleavedBuffer[i * channels + ch];
                    monoBuffer[i] = (float)(sum / channels);
                }

                if (framesRead < _fftSize)
                    Array.Clear(monoBuffer, framesRead, _fftSize - framesRead);

                for (int i = 0; i < _fftSize; i++)
                {
                    fftBuffer[i].X = monoBuffer[i] * window[i];
                    fftBuffer[i].Y = 0;
                }

                FastFourierTransform.FFT(true, (int)Math.Log2(_fftSize), fftBuffer);

                var lineSpectrum = new double[fftBins];
                for (int i = 0; i < fftBins; i++)
                {
                    double magnitude = Math.Sqrt(fftBuffer[i].X * fftBuffer[i].X + fftBuffer[i].Y * fftBuffer[i].Y);
                    double db = 20 * Math.Log10(Math.Max(magnitude, 1e-10));
                    lineSpectrum[i] = db;
                    sumSpectrum[i] += db;
                }

                spectrogram.Add(lineSpectrum);
                processedSteps++;

                if (framesRead < _fftSize) break;

                progressCallback?.Invoke((int)(processedSteps * 100.0 / totalSteps));
            }

            int lineCount = spectrogram.Count;
            for (int i = 0; i < fftBins; i++)
                sumSpectrum[i] /= lineCount;
            result.AvgSpectrumDb = sumSpectrum;
            result.SpectrogramLines = spectrogram;

            FindHighFrequencyCutoff(result);

            return result;
        }

        private float[] CreateWindow()
        {
            var w = new float[_fftSize];
            for (int i = 0; i < _fftSize; i++)
            {
                double ratio = i / (double)(_fftSize - 1);
                w[i] = _windowType switch
                {
                    1 => (float)(0.54 - 0.46 * Math.Cos(2 * Math.PI * ratio)),
                    2 => (float)(0.42 - 0.5 * Math.Cos(2 * Math.PI * ratio) + 0.08 * Math.Cos(4 * Math.PI * ratio)),
                    3 => 1f,
                    _ => (float)(0.5 - 0.5 * Math.Cos(2 * Math.PI * ratio))
                };
            }
            return w;
        }

        private void FindHighFrequencyCutoff(AnalysisResult result)
        {
            RecalculateCutoff(result, _cutoffThresholdDb, _cutoffPersistence);

            if (result.CutoffDetected)
                EstimateSpectralSlope(result);
        }

        public static void RecalculateCutoff(AnalysisResult result, double cutoffThresholdDb, int cutoffPersistence = 5)
        {
            int fftBins = result.AvgSpectrumDb.Length;
            double[] spectrum = result.AvgSpectrumDb;
            int sampleRate = result.SampleRate;
            int fftSize = fftBins * 2;

            int refLimitBin = (int)(2000.0 * fftSize / sampleRate);
            refLimitBin = Math.Min(refLimitBin, fftBins - 1);
            double refLevel = double.MinValue;
            int refBin = 0;

            for (int i = 0; i <= refLimitBin; i++)
            {
                if (spectrum[i] > refLevel)
                {
                    refLevel = spectrum[i];
                    refBin = i;
                }
            }

            result.ReferenceLevelDb = Math.Round(refLevel, 2);
            result.ReferenceFrequencyHz = Math.Round(refBin * sampleRate / (double)fftSize, 1);

            double threshold = refLevel + cutoffThresholdDb;
            int belowCount = 0;
            int cutoffBin = -1;

            for (int i = refBin + 1; i < fftBins; i++)
            {
                if (spectrum[i] < threshold)
                {
                    belowCount++;
                    if (belowCount >= cutoffPersistence && cutoffBin < 0)
                        cutoffBin = i - belowCount + 1;
                }
                else
                {
                    belowCount = 0;
                    cutoffBin = -1;
                }
            }

            if (cutoffBin > 0)
            {
                result.CutoffFrequencyHz = Math.Round(cutoffBin * sampleRate / (double)fftSize, 1);
                result.CutoffLevelDb = Math.Round(spectrum[cutoffBin], 2);
            }
            else
            {
                result.CutoffFrequencyHz = -1;
                result.CutoffLevelDb = 0;
            }
        }

        private static void EstimateSpectralSlope(AnalysisResult result)
        {
            int fftBins = result.AvgSpectrumDb.Length;
            int fftSize = fftBins * 2;
            double fCut = result.CutoffFrequencyHz;

            // Берём диапазон 50-95% от частоты среза
            double analysisLow = fCut * 0.5;
            double analysisHigh = fCut * 0.95;

            int binLow = (int)(analysisLow * fftSize / result.SampleRate);
            int binHigh = (int)(analysisHigh * fftSize / result.SampleRate);

            binLow = Math.Max(1, binLow);
            binHigh = Math.Min(fftBins - 1, binHigh);

            if (binHigh - binLow < 4)
            {
                result.SpectralSlopeDbPerOctave = -6.0; // дефолтный спад
                return;
            }

            // Линейная регрессия dB vs log2(freq)
            double sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
            int n = 0;

            for (int i = binLow; i <= binHigh; i++)
            {
                double freq = i * result.SampleRate / (double)fftSize;
                double logFreq = Math.Log2(freq / 1000.0); // относительно 1 кГц
                double db = result.AvgSpectrumDb[i];

                sumX += logFreq;
                sumY += db;
                sumXY += logFreq * db;
                sumX2 += logFreq * logFreq;
                n++;
            }

            if (n < 4)
            {
                result.SpectralSlopeDbPerOctave = -6.0;
                return;
            }

            double slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
            result.SpectralSlopeDbPerOctave = Math.Round(slope, 2);
        }
    }
}
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using AudioFill.Audio.Restore;

namespace AudioFill.Audio
{
    public class AudioRestorer
    {
        private readonly int _sampleRate;
        private readonly double _cutoffFrequency;
        private readonly AnalysisResult _analysisResult;

        public double EnvelopeLevel { get; set; } = 1.0;
        public double NoiseAmount { get; set; } = 0.15;
        public double CutoffLevelDb { get; set; } = -60;
        public IRestoreStrategy Strategy { get; set; } = new NoiseStrategy();

        public List<string> DebugLog { get; } = new List<string>();

        public AudioRestorer(int sampleRate, double cutoffFrequency, AnalysisResult analysisResult)
        {
            _sampleRate = sampleRate;
            _cutoffFrequency = cutoffFrequency;
            _analysisResult = analysisResult;
        }

        private void Log(string msg) => DebugLog.Add($"[{DateTime.Now:HH:mm:ss.fff}] {msg}");

        public float[] Restore(float[] samples, IProgress<RestoreProgress>? progress = null)
        {
            var (left, _) = RestoreStereo(samples, null, progress);
            return left;
        }

        public (float[] left, float[] right) RestoreStereo(
            float[] leftChannel,
            float[]? rightChannel,
            IProgress<RestoreProgress>? progress = null)
        {
            DebugLog.Clear();

            bool isStereo = rightChannel != null && rightChannel.Length == leftChannel.Length;
            Log($"=== {(isStereo ? "Stereo" : "Mono")} Restore Start ===");
            Log($"SampleRate: {_sampleRate}, Cutoff: {_cutoffFrequency:F1} Hz");
            Log($"Spectral slope: {_analysisResult.SpectralSlopeDbPerOctave:F1} dB/oct");
            Log($"Input L RMS: {Rms(leftChannel):F4}" + (isStereo ? $", R: {Rms(rightChannel!):F4}" : ""));

            if (_cutoffFrequency <= 0 || _cutoffFrequency >= _sampleRate / 2.0)
            {
                Log("No cutoff detected, returning original");
                progress?.Report(new RestoreProgress { Percent = 100, Step = "Срез не обнаружен" });
                return (leftChannel, rightChannel ?? leftChannel);
            }

            Log("--- Generating Fill ---");
            float[] leftFill, rightFill;

            if (isStereo)
            {
                var rightLog = new List<string>();
                float[]? leftResult = null, rightResult = null;

                Parallel.Invoke(
                    () => leftResult = Strategy.GenerateFill(leftChannel, _sampleRate, _cutoffFrequency, CutoffLevelDb, _analysisResult, progress, DebugLog),
                    () => rightResult = Strategy.GenerateFill(rightChannel!, _sampleRate, _cutoffFrequency, CutoffLevelDb, _analysisResult, null, rightLog)
                );

                leftFill = leftResult!;
                rightFill = rightResult!;

                lock (DebugLog)
                {
                    foreach (var line in rightLog)
                        DebugLog.Add(line.Replace("[", "[R]["));
                }
            }
            else
            {
                leftFill = Strategy.GenerateFill(leftChannel, _sampleRate, _cutoffFrequency, CutoffLevelDb, _analysisResult, progress, DebugLog);
                rightFill = leftFill;
            }

            Log($"Fill L RMS: {Rms(leftFill):F6}");

            var resultLeft = new float[leftChannel.Length];
            var resultRight = new float[leftChannel.Length];

            for (int i = 0; i < leftChannel.Length; i++)
            {
                resultLeft[i] = leftChannel[i] + leftFill[i] * (float)EnvelopeLevel;
                resultRight[i] = (isStereo ? rightChannel![i] : leftChannel[i]) + rightFill[i] * (float)EnvelopeLevel;
            }

            Log($"Result L RMS: {Rms(resultLeft):F4}");

            SoftLimit(resultLeft, resultRight);

            Log($"=== Final L RMS: {Rms(resultLeft):F4} ===");

            progress?.Report(new RestoreProgress { Percent = 100, Step = "Готово" });
            return (resultLeft, resultRight);
        }

        private void SoftLimit(float[] left, float[] right)
        {
            float maxVal = 0;
            for (int i = 0; i < left.Length; i++)
            {
                float absL = Math.Abs(left[i]);
                float absR = Math.Abs(right[i]);
                if (absL > maxVal) maxVal = absL;
                if (absR > maxVal) maxVal = absR;
            }
            if (maxVal <= 0.95f) return;

            float scale = 0.95f / maxVal;
            for (int i = 0; i < left.Length; i++)
            {
                left[i] *= scale;
                right[i] *= scale;
            }
        }

        private static float Rms(float[] s)
        {
            if (s == null || s.Length == 0) return 0;
            double sum = 0;
            for (int i = 0; i < s.Length; i++) sum += (double)s[i] * s[i];
            return (float)Math.Sqrt(sum / s.Length);
        }
    }
}
using System;
using System.Collections.Generic;

namespace AudioFill.Audio.Restore
{
    public interface IRestoreStrategy
    {
        string Name { get; }
        float[] GenerateFill(float[] signal, int sampleRate, double cutoffFrequency, double cutoffLevelDb,
                             AnalysisResult analysisResult,
                             IProgress<RestoreProgress>? progress, List<string> debugLog);
    }
}
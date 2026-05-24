namespace AudioFill.Audio
{
    public class AnalysisResult
    {
        public string FilePath { get; set; }
        public int SampleRate { get; set; }
        public int BitsPerSample { get; set; }
        public int Channels { get; set; }
        public double DurationSec { get; set; }

        public double[] AvgSpectrumDb { get; set; }
        public List<double[]> SpectrogramLines { get; set; }

        public double CutoffFrequencyHz { get; set; } = -1;
        public double CutoffLevelDb { get; set; }
        public double ReferenceLevelDb { get; set; }
        public double ReferenceFrequencyHz { get; set; }

        public bool CutoffDetected => CutoffFrequencyHz > 0;

        // Наклон спектра перед срезом (дБ/октава)
        public double SpectralSlopeDbPerOctave { get; set; }

        // Сырые сэмплы для реставрации
        public float[]? OriginalLeft { get; set; }
        public float[]? OriginalRight { get; set; }
    }
}
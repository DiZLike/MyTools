using System;
using FuzzCast.Fx.Trinity.Filters;
using FuzzCast.Fx.Trinity.Meters;

namespace FuzzCast.Fx.Trinity.Compressors
{
    public class ThreeBandCompressor
    {
        private LinkwitzRileyFilter _lowpassFilter;
        private LinkwitzRileyFilter _bandpassLowFilter;
        private LinkwitzRileyFilter _bandpassHighFilter;
        private LinkwitzRileyFilter _highpassFilter;

        public PeakCompressor LowCompressor { get; }
        public PeakCompressor MidCompressor { get; }
        public PeakCompressor HighCompressor { get; }
        public LookaheadLimiter Limiter { get; }

        public MeterProcessor LowInputMeter { get; }
        public MeterProcessor LowOutputMeter { get; }
        public MeterProcessor MidInputMeter { get; }
        public MeterProcessor MidOutputMeter { get; }
        public MeterProcessor HighInputMeter { get; }
        public MeterProcessor HighOutputMeter { get; }
        public MeterProcessor MasterOutputMeter { get; }

        private float _crossoverLowFreq = 300f;
        private float _crossoverHighFreq = 3000f;
        private int _sampleRate;

        public float CrossoverLowFreq
        {
            get => _crossoverLowFreq;
            set { _crossoverLowFreq = Math.Clamp(value, 20f, _crossoverHighFreq - 100f); InitializeFilters(); }
        }

        public float CrossoverHighFreq
        {
            get => _crossoverHighFreq;
            set { _crossoverHighFreq = Math.Clamp(value, _crossoverLowFreq + 100f, 20000f); InitializeFilters(); }
        }

        public int SampleRate
        {
            get => _sampleRate;
            set
            {
                _sampleRate = value;
                InitializeFilters();
                LowCompressor.SampleRate = value;
                MidCompressor.SampleRate = value;
                HighCompressor.SampleRate = value;
                Limiter.SampleRate = value;
            }
        }

        public ThreeBandCompressor(int sampleRate = 44100)
        {
            _sampleRate = sampleRate;
            LowCompressor = new PeakCompressor(sampleRate);
            MidCompressor = new PeakCompressor(sampleRate);
            HighCompressor = new PeakCompressor(sampleRate);
            Limiter = new LookaheadLimiter(sampleRate);

            LowInputMeter = new MeterProcessor();
            LowOutputMeter = new MeterProcessor();
            MidInputMeter = new MeterProcessor();
            MidOutputMeter = new MeterProcessor();
            HighInputMeter = new MeterProcessor();
            HighOutputMeter = new MeterProcessor();
            MasterOutputMeter = new MeterProcessor();

            InitializeFilters();
            SetDefaults();
        }

        private void InitializeFilters()
        {
            _lowpassFilter = new LinkwitzRileyFilter(_sampleRate, _crossoverLowFreq, FilterType.LowPass);
            _bandpassLowFilter = new LinkwitzRileyFilter(_sampleRate, _crossoverLowFreq, FilterType.HighPass);
            _bandpassHighFilter = new LinkwitzRileyFilter(_sampleRate, _crossoverHighFreq, FilterType.LowPass);
            _highpassFilter = new LinkwitzRileyFilter(_sampleRate, _crossoverHighFreq, FilterType.HighPass);
        }

        private void SetDefaults()
        {
            LowCompressor.Threshold = -18f;
            LowCompressor.Ratio = 3f;
            LowCompressor.AttackMs = 15f;
            LowCompressor.ReleaseMs = 100f;
            LowCompressor.KneeWidth = 6f;

            MidCompressor.Threshold = -20f;
            MidCompressor.Ratio = 4f;
            MidCompressor.AttackMs = 8f;
            MidCompressor.ReleaseMs = 60f;
            MidCompressor.KneeWidth = 3f;

            HighCompressor.Threshold = -22f;
            HighCompressor.Ratio = 5f;
            HighCompressor.AttackMs = 2f;
            HighCompressor.ReleaseMs = 40f;
            HighCompressor.KneeWidth = 0f;
        }

        public float Process(float input)
        {
            float lowSignal = _lowpassFilter.Process(input);
            float highPassForBand = _bandpassLowFilter.Process(input);
            float midSignal = _bandpassHighFilter.Process(highPassForBand);
            float highSignal = _highpassFilter.Process(input);

            LowInputMeter.Process(lowSignal);
            MidInputMeter.Process(midSignal);
            HighInputMeter.Process(highSignal);

            float lowCompressed = LowCompressor.Process(lowSignal);
            float midCompressed = MidCompressor.Process(midSignal);
            float highCompressed = HighCompressor.Process(highSignal);

            LowOutputMeter.Process(lowCompressed);
            MidOutputMeter.Process(midCompressed);
            HighOutputMeter.Process(highCompressed);

            float mixed = lowCompressed + midCompressed + highCompressed;
            float output = Limiter.Process(mixed);
            MasterOutputMeter.Process(output);

            return output;
        }

        public void UpdateMeters()
        {
            LowInputMeter.UpdateWindow();
            LowOutputMeter.UpdateWindow();
            MidInputMeter.UpdateWindow();
            MidOutputMeter.UpdateWindow();
            HighInputMeter.UpdateWindow();
            HighOutputMeter.UpdateWindow();
            MasterOutputMeter.UpdateWindow();
        }

        public void Reset()
        {
            _lowpassFilter.Reset();
            _bandpassLowFilter.Reset();
            _bandpassHighFilter.Reset();
            _highpassFilter.Reset();
            LowCompressor.Reset();
            MidCompressor.Reset();
            HighCompressor.Reset();
            Limiter.Reset();
        }
    }
}
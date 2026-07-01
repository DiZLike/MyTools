using System;

namespace BrickwallCompressor.Core
{
    public class ThreeBandCompressor
    {
        // Кроссоверы
        private LinkwitzRileyFilter _lowpassFilter;
        private LinkwitzRileyFilter _bandpassLowFilter;
        private LinkwitzRileyFilter _bandpassHighFilter;
        private LinkwitzRileyFilter _highpassFilter;

        // Компрессоры для каждой полосы
        public PeakCompressor LowCompressor { get; }
        public PeakCompressor MidCompressor { get; }
        public PeakCompressor HighCompressor { get; }
        public LookaheadLimiter Limiter { get; }

        // Частоты раздела
        private float _crossoverLowFreq = 300f;
        private float _crossoverHighFreq = 3000f;
        private int _sampleRate;

        // Метры для каждой полосы
        public MeterProcessor LowInputMeter { get; }
        public MeterProcessor LowOutputMeter { get; }
        public MeterProcessor MidInputMeter { get; }
        public MeterProcessor MidOutputMeter { get; }
        public MeterProcessor HighInputMeter { get; }
        public MeterProcessor HighOutputMeter { get; }
        public MeterProcessor MasterOutputMeter { get; }

        public ThreeBandCompressor(int sampleRate = 44100)
        {
            _sampleRate = sampleRate;
            InitializeFilters();

            LowCompressor = new PeakCompressor(sampleRate);
            MidCompressor = new PeakCompressor(sampleRate);
            HighCompressor = new PeakCompressor(sampleRate);
            Limiter = new LookaheadLimiter(sampleRate);

            LowInputMeter = new MeterProcessor(sampleRate);
            LowOutputMeter = new MeterProcessor(sampleRate);
            MidInputMeter = new MeterProcessor(sampleRate);
            MidOutputMeter = new MeterProcessor(sampleRate);
            HighInputMeter = new MeterProcessor(sampleRate);
            HighOutputMeter = new MeterProcessor(sampleRate);
            MasterOutputMeter = new MeterProcessor(sampleRate);

            SetDefaultSettings();
        }

        private void InitializeFilters()
        {
            _lowpassFilter = new LinkwitzRileyFilter(_sampleRate, _crossoverLowFreq, FilterType.LowPass);
            _bandpassLowFilter = new LinkwitzRileyFilter(_sampleRate, _crossoverLowFreq, FilterType.HighPass);
            _bandpassHighFilter = new LinkwitzRileyFilter(_sampleRate, _crossoverHighFreq, FilterType.LowPass);
            _highpassFilter = new LinkwitzRileyFilter(_sampleRate, _crossoverHighFreq, FilterType.HighPass);
        }

        private void SetDefaultSettings()
        {
            // Низкие частоты — мягкая компрессия
            LowCompressor.SetThreshold(-18f);
            LowCompressor.SetRatio(3f);
            LowCompressor.SetAttack(15f);
            LowCompressor.SetRelease(100f);
            LowCompressor.SetKneeWidth(6f);
            LowCompressor.SetMakeupGain(0f);

            // Средние частоты — умеренная компрессия
            MidCompressor.SetThreshold(-20f);
            MidCompressor.SetRatio(4f);
            MidCompressor.SetAttack(8f);
            MidCompressor.SetRelease(60f);
            MidCompressor.SetKneeWidth(3f);
            MidCompressor.SetMakeupGain(0f);

            // Высокие частоты — быстрая компрессия
            HighCompressor.SetThreshold(-22f);
            HighCompressor.SetRatio(5f);
            HighCompressor.SetAttack(2f);
            HighCompressor.SetRelease(40f);
            HighCompressor.SetKneeWidth(0f);
            HighCompressor.SetMakeupGain(0f);
        }

        public void SetCrossoverFrequencies(float lowFreq, float highFreq)
        {
            _crossoverLowFreq = Math.Max(20f, Math.Min(lowFreq, highFreq - 100f));
            _crossoverHighFreq = Math.Max(_crossoverLowFreq + 100f, Math.Min(highFreq, 20000f));
            InitializeFilters();
        }

        public void SetSampleRate(int sampleRate)
        {
            _sampleRate = sampleRate;
            InitializeFilters();
            LowCompressor.SetSampleRate(sampleRate);
            MidCompressor.SetSampleRate(sampleRate);
            HighCompressor.SetSampleRate(sampleRate);
            Limiter.SetSampleRate(sampleRate);
        }

        public float Process(float input)
        {
            // Шаг 1: Расщепление на полосы
            float lowSignal = _lowpassFilter.Process(input);
            float highPassForBand = _bandpassLowFilter.Process(input);
            float midSignal = _bandpassHighFilter.Process(highPassForBand);
            float highSignal = _highpassFilter.Process(input);

            // Измеряем входные уровни по полосам
            LowInputMeter.Process(lowSignal);
            MidInputMeter.Process(midSignal);
            HighInputMeter.Process(highSignal);

            // Шаг 2: Компрессия каждой полосы
            float lowCompressed = LowCompressor.Process(lowSignal);
            float midCompressed = MidCompressor.Process(midSignal);
            float highCompressed = HighCompressor.Process(highSignal);

            // Измеряем выходные уровни полос
            LowOutputMeter.Process(lowCompressed);
            MidOutputMeter.Process(midCompressed);
            HighOutputMeter.Process(highCompressed);

            // Шаг 3: Смешивание
            float mixed = lowCompressed + midCompressed + highCompressed;

            // Шаг 4: Мастер-лимитер
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
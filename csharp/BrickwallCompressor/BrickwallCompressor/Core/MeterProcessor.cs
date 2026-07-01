using System;

namespace BrickwallCompressor.Core
{
    public class MeterProcessor
    {
        private float _rmsAccumulator;
        private int _rmsSampleCount;
        private float _peakLevel;
        private int _sampleRate;
        private float _rmsWindowMs;

        public float PeakLevel { get; private set; }
        public float RmsLevel { get; private set; }

        public MeterProcessor(int sampleRate = 44100, float rmsWindowMs = 50f)
        {
            _sampleRate = sampleRate;
            _rmsWindowMs = rmsWindowMs;
            Reset();
        }

        public void Process(float input)
        {
            float abs = MathF.Abs(input);

            // Пиковый детектор
            if (abs > _peakLevel)
                _peakLevel = abs;

            // RMS — накапливаем квадраты
            _rmsAccumulator += input * input;
            _rmsSampleCount++;
        }

        public void UpdateWindow()
        {
            // Пиковое значение
            PeakLevel = _peakLevel;
            _peakLevel *= 0.9f; // Медленное затухание
            if (_peakLevel < 0.0001f) _peakLevel = 0f;

            // RMS за окно
            if (_rmsSampleCount > 0)
            {
                RmsLevel = MathF.Sqrt(_rmsAccumulator / _rmsSampleCount);
                _rmsAccumulator = 0f;
                _rmsSampleCount = 0;
            }
            else
            {
                RmsLevel *= 0.9f;
                if (RmsLevel < 0.0001f) RmsLevel = 0f;
            }
        }

        public void Reset()
        {
            _rmsAccumulator = 0f;
            _rmsSampleCount = 0;
            _peakLevel = 0f;
            PeakLevel = 0f;
            RmsLevel = 0f;
        }
    }
}
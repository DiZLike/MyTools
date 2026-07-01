using System;

namespace FuzzCast.Fx.Trinity.Meters
{
    public class MeterProcessor
    {
        private float _rmsAccumulator;
        private int _rmsSampleCount;
        private float _peakLevel;

        public float PeakLevel { get; private set; }
        public float RmsLevel { get; private set; }

        public void Process(float input)
        {
            float abs = MathF.Abs(input);
            if (abs > _peakLevel) _peakLevel = abs;
            _rmsAccumulator += input * input;
            _rmsSampleCount++;
        }

        public void UpdateWindow()
        {
            PeakLevel = _peakLevel;
            _peakLevel *= 0.9f;
            if (_peakLevel < 0.0001f) _peakLevel = 0f;

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
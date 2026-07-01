using System;

namespace BrickwallCompressor.Core
{
    public enum FilterType
    {
        LowPass,
        HighPass
    }

    /// <summary>
    /// Фильтр Линквица-Райли 4-го порядка (24 дБ/октава)
    /// Состоит из двух биквадратных фильтров Баттерворта 2-го порядка
    /// </summary>
    public class LinkwitzRileyFilter
    {
        private BiquadFilter _stage1;
        private BiquadFilter _stage2;

        public LinkwitzRileyFilter(int sampleRate, float frequency, FilterType type)
        {
            _stage1 = new BiquadFilter(sampleRate, frequency, type);
            _stage2 = new BiquadFilter(sampleRate, frequency, type);
        }

        public float Process(float input)
        {
            return _stage2.Process(_stage1.Process(input));
        }

        public void Reset()
        {
            _stage1.Reset();
            _stage2.Reset();
        }
    }

    /// <summary>
    /// Биквадратный фильтр (2-й порядок)
    /// </summary>
    internal class BiquadFilter
    {
        private float _a0, _a1, _a2, _b1, _b2;
        private float _x1, _x2, _y1, _y2;

        public BiquadFilter(int sampleRate, float freq, FilterType type)
        {
            float omega = 2f * MathF.PI * freq / sampleRate;
            float cos = MathF.Cos(omega);
            float sin = MathF.Sin(omega);
            float alpha = sin / (2f * 0.7071f); // Q = 0.7071 (Баттерворт)

            if (type == FilterType.LowPass)
            {
                _a0 = (1f - cos) / 2f;
                _a1 = 1f - cos;
                _a2 = (1f - cos) / 2f;
                float norm = 1f + alpha;
                _a0 /= norm;
                _a1 /= norm;
                _a2 /= norm;
                _b1 = (-2f * cos) / norm;
                _b2 = (1f - alpha) / norm;
            }
            else // HighPass
            {
                _a0 = (1f + cos) / 2f;
                _a1 = -(1f + cos);
                _a2 = (1f + cos) / 2f;
                float norm = 1f + alpha;
                _a0 /= norm;
                _a1 /= norm;
                _a2 /= norm;
                _b1 = (-2f * cos) / norm;
                _b2 = (1f - alpha) / norm;
            }
        }

        public float Process(float input)
        {
            float output = _a0 * input + _a1 * _x1 + _a2 * _x2 - _b1 * _y1 - _b2 * _y2;
            _x2 = _x1;
            _x1 = input;
            _y2 = _y1;
            _y1 = output;
            return output;
        }

        public void Reset()
        {
            _x1 = _x2 = _y1 = _y2 = 0f;
        }
    }
}
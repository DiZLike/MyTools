using System;

namespace FuzzCast.Fx.Trinity.Filters
{
    internal class BiquadFilter
    {
        private float _a0, _a1, _a2, _b1, _b2;
        private float _x1, _x2, _y1, _y2;

        public BiquadFilter(int sampleRate, float freq, FilterType type)
        {
            float omega = 2f * MathF.PI * freq / sampleRate;
            float cos = MathF.Cos(omega);
            float sin = MathF.Sin(omega);
            float alpha = sin / (2f * 0.7071f);

            if (type == FilterType.LowPass)
            {
                _a0 = (1f - cos) / 2f;
                _a1 = 1f - cos;
                _a2 = (1f - cos) / 2f;
                float norm = 1f + alpha;
                _a0 /= norm; _a1 /= norm; _a2 /= norm;
                _b1 = (-2f * cos) / norm;
                _b2 = (1f - alpha) / norm;
            }
            else
            {
                _a0 = (1f + cos) / 2f;
                _a1 = -(1f + cos);
                _a2 = (1f + cos) / 2f;
                float norm = 1f + alpha;
                _a0 /= norm; _a1 /= norm; _a2 /= norm;
                _b1 = (-2f * cos) / norm;
                _b2 = (1f - alpha) / norm;
            }
        }

        public float Process(float input)
        {
            float output = _a0 * input + _a1 * _x1 + _a2 * _x2 - _b1 * _y1 - _b2 * _y2;
            _x2 = _x1; _x1 = input;
            _y2 = _y1; _y1 = output;
            return output;
        }

        public void Reset()
        {
            _x1 = _x2 = _y1 = _y2 = 0f;
        }
    }
}
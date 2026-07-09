using System;

namespace FuzzCast.Fx.Trinity.Compressors
{
    public class LookaheadLimiter
    {
        private float _ceiling;
        private float _ceilingLinear;
        private float _lookaheadMs;
        private float _attackMs;
        private float _releaseMs;
        private float[] _lookaheadBufferL;
        private float[] _lookaheadBufferR;
        private int _lookaheadSamples;
        private int _lookaheadIndex;
        private bool _bufferFilled;
        private float _envelope;
        private float _attackCoeff;
        private float _releaseCoeff;
        private int _sampleRate;

        public float CurrentGainReduction { get; private set; }
        public int ClipCount { get; private set; }

        public float Ceiling
        {
            get => _ceiling;
            set { _ceiling = Math.Min(value, 0f); _ceilingLinear = AudioMath.DbToLinear(_ceiling); }
        }

        public float LookaheadMs
        {
            get => _lookaheadMs;
            set { _lookaheadMs = Math.Max(0.1f, value); ReallocateBuffer(); }
        }

        public float AttackMs
        {
            get => _attackMs;
            set { _attackMs = Math.Max(0.01f, value); RecalculateCoefficients(); }
        }

        public float ReleaseMs
        {
            get => _releaseMs;
            set { _releaseMs = Math.Max(0.01f, value); RecalculateCoefficients(); }
        }

        public int SampleRate
        {
            get => _sampleRate;
            set { _sampleRate = value; ReallocateBuffer(); RecalculateCoefficients(); }
        }

        public LookaheadLimiter(int sampleRate = 44100)
        {
            _sampleRate = sampleRate;
            Ceiling = -0.3f;
            LookaheadMs = 1f;
            AttackMs = 0.5f;
            ReleaseMs = 30f;
            _envelope = 0f;
        }

        /// <summary>Моно-обработка (оставлена для обратной совместимости)</summary>
        public float Process(float input)
        {
            float delayed = _lookaheadBufferL[_lookaheadIndex];
            _lookaheadBufferL[_lookaheadIndex] = input;
            _lookaheadIndex = (_lookaheadIndex + 1) % _lookaheadSamples;

            if (_lookaheadIndex == 0) _bufferFilled = true;
            if (!_bufferFilled) delayed = input;

            float inputLevel = MathF.Abs(input);
            bool isAttack = inputLevel > _envelope;
            float coeff = isAttack ? _attackCoeff : _releaseCoeff;
            _envelope = coeff * _envelope + (1f - coeff) * inputLevel;

            float gainReductionDb = 0f;
            if (_envelope > _ceilingLinear)
            {
                gainReductionDb = AudioMath.LinearToDb(_envelope) - _ceiling;
                CurrentGainReduction = gainReductionDb;
            }
            else
            {
                CurrentGainReduction = 0f;
            }

            float gain = AudioMath.DbToLinear(-gainReductionDb);
            float output = delayed * gain;

            if (output > _ceilingLinear) { output = _ceilingLinear; ClipCount++; }
            else if (output < -_ceilingLinear) { output = -_ceilingLinear; ClipCount++; }

            return output;
        }

        /// <summary>
        /// Стерео-обработка с linked-детектором.
        /// Envelope по max(|L|,|R|), gain применяется одинаковый, буферы раздельные для каждого канала.
        /// </summary>
        public void ProcessStereo(float left, float right, out float outLeft, out float outRight)
        {
            float delayedL = _lookaheadBufferL[_lookaheadIndex];
            float delayedR = _lookaheadBufferR[_lookaheadIndex];

            _lookaheadBufferL[_lookaheadIndex] = left;
            _lookaheadBufferR[_lookaheadIndex] = right;
            _lookaheadIndex = (_lookaheadIndex + 1) % _lookaheadSamples;

            if (_lookaheadIndex == 0) _bufferFilled = true;
            if (!_bufferFilled)
            {
                delayedL = left;
                delayedR = right;
            }

            float inputLevel = MathF.Max(MathF.Abs(left), MathF.Abs(right));
            bool isAttack = inputLevel > _envelope;
            float coeff = isAttack ? _attackCoeff : _releaseCoeff;
            _envelope = coeff * _envelope + (1f - coeff) * inputLevel;

            float gainReductionDb = 0f;
            if (_envelope > _ceilingLinear)
            {
                gainReductionDb = AudioMath.LinearToDb(_envelope) - _ceiling;
                CurrentGainReduction = gainReductionDb;
            }
            else
            {
                CurrentGainReduction = 0f;
            }

            float gain = AudioMath.DbToLinear(-gainReductionDb);
            outLeft = delayedL * gain;
            outRight = delayedR * gain;

            if (outLeft > _ceilingLinear) { outLeft = _ceilingLinear; ClipCount++; }
            else if (outLeft < -_ceilingLinear) { outLeft = -_ceilingLinear; ClipCount++; }
            if (outRight > _ceilingLinear) { outRight = _ceilingLinear; ClipCount++; }
            else if (outRight < -_ceilingLinear) { outRight = -_ceilingLinear; ClipCount++; }
        }

        private void ReallocateBuffer()
        {
            _lookaheadSamples = Math.Max(1, (int)(_lookaheadMs * 0.001f * _sampleRate));
            _lookaheadBufferL = new float[_lookaheadSamples];
            _lookaheadBufferR = new float[_lookaheadSamples];
            _lookaheadIndex = 0;
            _bufferFilled = false;
        }

        private void RecalculateCoefficients()
        {
            _attackCoeff = MathF.Exp(-1f / (_attackMs * 0.001f * _sampleRate));
            _releaseCoeff = MathF.Exp(-1f / (_releaseMs * 0.001f * _sampleRate));
        }

        public void Reset()
        {
            _envelope = 0f;
            CurrentGainReduction = 0f;
            ClipCount = 0;
            if (_lookaheadBufferL != null)
                Array.Clear(_lookaheadBufferL, 0, _lookaheadBufferL.Length);
            if (_lookaheadBufferR != null)
                Array.Clear(_lookaheadBufferR, 0, _lookaheadBufferR.Length);
            _lookaheadIndex = 0;
            _bufferFilled = false;
        }
    }
}
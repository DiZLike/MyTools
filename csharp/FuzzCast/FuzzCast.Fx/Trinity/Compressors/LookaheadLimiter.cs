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
        private float[] _lookaheadBuffer;
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

        public float Process(float input)
        {
            float delayed = _lookaheadBuffer[_lookaheadIndex];
            _lookaheadBuffer[_lookaheadIndex] = input;
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

        private void ReallocateBuffer()
        {
            _lookaheadSamples = Math.Max(1, (int)(_lookaheadMs * 0.001f * _sampleRate));
            _lookaheadBuffer = new float[_lookaheadSamples];
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
            if (_lookaheadBuffer != null)
                Array.Clear(_lookaheadBuffer, 0, _lookaheadBuffer.Length);
            _lookaheadIndex = 0;
            _bufferFilled = false;
        }
    }
}
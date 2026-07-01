using System;

namespace BrickwallCompressor.Core
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

        public LookaheadLimiter(int sampleRate = 44100)
        {
            _sampleRate = sampleRate;
            _envelope = 0f;
            ClipCount = 0;

            SetCeiling(-0.3f);
            SetLookahead(1f);
            SetAttack(0.5f);
            SetRelease(30f);
        }

        public void SetCeiling(float db)
        {
            _ceiling = Math.Min(db, 0f);
            _ceilingLinear = DbToLinear(_ceiling);
        }

        public void SetLookahead(float ms)
        {
            _lookaheadMs = Math.Max(0.1f, ms);
            ReallocateBuffer();
        }

        public void SetAttack(float ms)
        {
            _attackMs = Math.Max(0.01f, ms);
            RecalculateCoefficients();
        }

        public void SetRelease(float ms)
        {
            _releaseMs = Math.Max(0.01f, ms);
            RecalculateCoefficients();
        }

        public void SetSampleRate(int sampleRate)
        {
            _sampleRate = sampleRate;
            ReallocateBuffer();
            RecalculateCoefficients();
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

        public float Process(float input)
        {
            // Lookahead: пишем вход, читаем задержанный
            float delayed = _lookaheadBuffer[_lookaheadIndex];
            _lookaheadBuffer[_lookaheadIndex] = input;
            _lookaheadIndex = (_lookaheadIndex + 1) % _lookaheadSamples;

            // Отслеживаем заполнение буфера
            if (_lookaheadIndex == 0)
                _bufferFilled = true;
            if (!_bufferFilled)
                delayed = input; // Первый проход без задержки

            // Огибающая по ОРИГИНАЛЬНОМУ сигналу (смотрим вперёд!)
            float inputLevel = MathF.Abs(input);
            bool isAttack = inputLevel > _envelope;
            float coeff = isAttack ? _attackCoeff : _releaseCoeff;
            _envelope = coeff * _envelope + (1f - coeff) * inputLevel;

            // Вычисляем ослабление
            float gainReductionDb = 0f;
            if (_envelope > _ceilingLinear)
            {
                gainReductionDb = LinearToDb(_envelope) - _ceiling;
                CurrentGainReduction = gainReductionDb;
            }
            else
            {
                CurrentGainReduction = 0f;
            }

            // Применяем к задержанному сигналу
            float gain = DbToLinear(-gainReductionDb);
            float output = delayed * gain;

            // Hard clip как последний рубеж
            if (output > _ceilingLinear)
            {
                output = _ceilingLinear;
                ClipCount++;
            }
            else if (output < -_ceilingLinear)
            {
                output = -_ceilingLinear;
                ClipCount++;
            }

            return output;
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

        private static float DbToLinear(float db)
        {
            if (db <= -150f) return 0f;
            return MathF.Pow(10f, db / 20f);
        }

        private static float LinearToDb(float linear)
        {
            if (linear < 1e-10f) return -150f;
            return 20f * MathF.Log10(linear);
        }
    }
}
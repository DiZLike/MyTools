using System;

namespace BrickwallCompressor.Core
{
    public class PeakCompressor
    {
        private float _threshold;
        private float _ratio;
        private float _attackMs;
        private float _releaseMs;
        private float _kneeWidth;
        private float _makeupGain;

        private float _envelope;
        private float _attackCoeff;
        private float _releaseCoeff;
        private int _sampleRate;

        private float _thresholdLinear;
        private float _makeupGainLinear;
        private float _ratioInverse;
        private float _kneeHalf;

        public float CurrentGainReduction { get; private set; }

        public PeakCompressor(int sampleRate = 44100)
        {
            _sampleRate = sampleRate;
            _envelope = 0f;
            CurrentGainReduction = 0f;

            SetThreshold(-18f);
            SetRatio(4f);
            SetAttack(10f);
            SetRelease(80f);
            SetKneeWidth(3f);
            SetMakeupGain(0f);
        }

        public void SetThreshold(float db)
        {
            _threshold = db;
            _thresholdLinear = DbToLinear(db);
        }

        public void SetRatio(float ratio)
        {
            _ratio = Math.Max(1f, ratio);
            _ratioInverse = 1f / _ratio;
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

        public void SetKneeWidth(float db)
        {
            _kneeWidth = Math.Max(0f, db);
            _kneeHalf = _kneeWidth * 0.5f;
        }

        public void SetMakeupGain(float db)
        {
            _makeupGain = db;
            _makeupGainLinear = DbToLinear(db);
        }

        public void SetSampleRate(int sampleRate)
        {
            _sampleRate = sampleRate;
            RecalculateCoefficients();
        }

        private void RecalculateCoefficients()
        {
            _attackCoeff = MathF.Exp(-1f / (_attackMs * 0.001f * _sampleRate));
            _releaseCoeff = MathF.Exp(-1f / (_releaseMs * 0.001f * _sampleRate));
        }

        public float Process(float input)
        {
            float inputLevel = MathF.Abs(input);

            // Огибающая
            bool isAttack = inputLevel > _envelope;
            float coeff = isAttack ? _attackCoeff : _releaseCoeff;
            _envelope = coeff * _envelope + (1f - coeff) * inputLevel;

            // Gain reduction
            float gainReductionDb = ComputeGainReduction(_envelope);
            CurrentGainReduction = gainReductionDb;

            // Применяем
            float totalGain = DbToLinear(-gainReductionDb + _makeupGain);
            return input * totalGain;
        }

        private float ComputeGainReduction(float envelopeLinear)
        {
            float envelopeDb = LinearToDb(envelopeLinear);
            float kneeLowerBound = _threshold - _kneeHalf;

            if (envelopeDb <= kneeLowerBound)
                return 0f;

            if (_kneeWidth <= 0f)
            {
                if (envelopeDb <= _threshold)
                    return 0f;
                return (envelopeDb - _threshold) * (1f - _ratioInverse);
            }

            float kneeUpperBound = _threshold + _kneeHalf;
            if (envelopeDb >= kneeUpperBound)
            {
                return (envelopeDb - _threshold) * (1f - _ratioInverse);
            }
            else
            {
                float delta = envelopeDb - kneeLowerBound;
                float deltaNorm = delta / _kneeWidth;
                float maxReduction = (kneeUpperBound - _threshold) * (1f - _ratioInverse);
                return maxReduction * deltaNorm * deltaNorm;
            }
        }

        public void Reset()
        {
            _envelope = 0f;
            CurrentGainReduction = 0f;
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
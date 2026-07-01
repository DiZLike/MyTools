using System;

namespace FuzzCast.Fx.Trinity.Compressors
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

        public float Threshold
        {
            get => _threshold;
            set { _threshold = value; _thresholdLinear = AudioMath.DbToLinear(value); }
        }

        public float Ratio
        {
            get => _ratio;
            set { _ratio = Math.Max(1f, value); _ratioInverse = 1f / _ratio; }
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

        public float KneeWidth
        {
            get => _kneeWidth;
            set { _kneeWidth = Math.Max(0f, value); _kneeHalf = _kneeWidth * 0.5f; }
        }

        public float MakeupGain
        {
            get => _makeupGain;
            set { _makeupGain = value; _makeupGainLinear = AudioMath.DbToLinear(value); }
        }

        public int SampleRate
        {
            get => _sampleRate;
            set { _sampleRate = value; RecalculateCoefficients(); }
        }

        public PeakCompressor(int sampleRate = 44100)
        {
            _sampleRate = sampleRate;
            Threshold = -18f;
            Ratio = 4f;
            AttackMs = 10f;
            ReleaseMs = 80f;
            KneeWidth = 3f;
            MakeupGain = 0f;
            _envelope = 0f;
        }

        public float Process(float input)
        {
            float inputLevel = MathF.Abs(input);
            bool isAttack = inputLevel > _envelope;
            float coeff = isAttack ? _attackCoeff : _releaseCoeff;
            _envelope = coeff * _envelope + (1f - coeff) * inputLevel;

            float gainReductionDb = ComputeGainReduction(_envelope);
            CurrentGainReduction = gainReductionDb;

            float totalGain = AudioMath.DbToLinear(-gainReductionDb + _makeupGain);
            return input * totalGain;
        }

        private float ComputeGainReduction(float envelopeLinear)
        {
            float envelopeDb = AudioMath.LinearToDb(envelopeLinear);
            float kneeLowerBound = _threshold - _kneeHalf;

            if (envelopeDb <= kneeLowerBound)
                return 0f;

            if (_kneeWidth <= 0f)
            {
                if (envelopeDb <= _threshold) return 0f;
                return (envelopeDb - _threshold) * (1f - _ratioInverse);
            }

            float kneeUpperBound = _threshold + _kneeHalf;
            if (envelopeDb >= kneeUpperBound)
                return (envelopeDb - _threshold) * (1f - _ratioInverse);

            float delta = envelopeDb - kneeLowerBound;
            float deltaNorm = delta / _kneeWidth;
            float maxReduction = (kneeUpperBound - _threshold) * (1f - _ratioInverse);
            return maxReduction * deltaNorm * deltaNorm;
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
        }
    }
}
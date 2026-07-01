namespace FuzzCast.Fx.Trinity.Filters
{
    public enum FilterType
    {
        LowPass,
        HighPass
    }

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
}
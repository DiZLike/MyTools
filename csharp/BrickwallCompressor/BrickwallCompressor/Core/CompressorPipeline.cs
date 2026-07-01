namespace BrickwallCompressor.Core
{
    public class CompressorPipeline
    {
        public ThreeBandCompressor ThreeBand { get; }

        // Для совместимости с старым кодом
        public MeterProcessor InputMeter => ThreeBand.MasterOutputMeter;
        public MeterProcessor OutputMeter => ThreeBand.MasterOutputMeter;

        public CompressorPipeline(int sampleRate = 44100)
        {
            ThreeBand = new ThreeBandCompressor(sampleRate);
        }

        public float Process(float input)
        {
            return ThreeBand.Process(input);
        }

        public void SetSampleRate(int sampleRate)
        {
            ThreeBand.SetSampleRate(sampleRate);
        }

        public void UpdateMeters()
        {
            ThreeBand.UpdateMeters();
        }

        public void Reset()
        {
            ThreeBand.Reset();
        }
    }
}
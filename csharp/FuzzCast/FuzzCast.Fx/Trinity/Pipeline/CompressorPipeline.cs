using FuzzCast.Fx.Trinity.Compressors;
using FuzzCast.Fx.Trinity.Meters;

namespace FuzzCast.Fx.Trinity.Pipeline
{
    public class CompressorPipeline
    {
        public ThreeBandCompressor ThreeBand { get; }

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
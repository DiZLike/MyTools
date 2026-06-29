namespace FuzzCast.Core.Native;

public class OpusDecoder : IDisposable
{
    private readonly IntPtr _handle;
    private readonly int _sampleRate;

    public OpusDecoder(int sampleRate, int channels)
    {
        _sampleRate = sampleRate;
        _handle = OpusNative.opus_decoder_create(sampleRate, channels, out int error);

        if (error != 0)
        {
            string[] errorNames = { "OK", "BadArg", "BufferTooSmall", "InternalError", "InvalidPacket", "Unimplemented", "InvalidState", "AllocFail" };
            string errorName = error < errorNames.Length ? errorNames[error] : $"Unknown({error})";
            throw new InvalidOperationException($"Opus decoder error: {errorName}");
        }
    }

    public (int frameMs, int packetBytes, string bandwidth, int decodedSamples)? Decode(byte[]? opusData, short[] pcm, bool fec = false)
    {
        if (opusData == null || opusData.Length == 0)
        {
            int plcSamples = OpusNative.opus_decode(_handle, null, 0, pcm, _sampleRate * 60 / 1000, 1);
            if (plcSamples <= 0)
                return null;
            int frameMs = plcSamples * 1000 / _sampleRate;
            return (frameMs, 0, "PLC", plcSamples);
        }

        int frameSize = OpusNative.opus_packet_get_nb_samples(opusData, opusData.Length, _sampleRate);
        if (frameSize <= 0)
            return null;

        int bandwidthCode = OpusNative.opus_packet_get_bandwidth(opusData, opusData.Length);
        string bandwidth = bandwidthCode switch
        {
            1101 => "NB",
            1102 => "MB",
            1103 => "WB",
            1104 => "SWB",
            1105 => "FB",
            _ => "??"
        };

        int decodedSamples = OpusNative.opus_decode(_handle, opusData, opusData.Length, pcm, frameSize, fec ? 1 : 0);
        if (decodedSamples <= 0)
            return null;

        int decodedFrameMs = decodedSamples * 1000 / _sampleRate;
        return (decodedFrameMs, opusData.Length, bandwidth, decodedSamples);
    }

    public void Dispose()
    {
        if (_handle != IntPtr.Zero)
        {
            OpusNative.opus_decoder_destroy(_handle);
        }
    }
}
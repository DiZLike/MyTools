namespace FuzzCast.Core.Native;

/// <summary>
/// Managed обёртка для Opus энкодера.
/// Замена Concentus OpusCodecFactory.CreateEncoder().
/// </summary>
public class OpusEncoder : IDisposable
{
    private readonly IntPtr _handle;
    private readonly int _sampleRate;
    private readonly int _channels;
    private readonly int _frameSize; // samples per channel

    public OpusEncoder(int sampleRate, int channels, OpusApplication application, int frameSizeMs = 20)
    {
        _sampleRate = sampleRate;
        _channels = channels;
        _frameSize = sampleRate * frameSizeMs / 1000;

        _handle = OpusNative.opus_encoder_create(sampleRate, channels, (int)application, out int error);

        if (error != 0)
        {
            string[] errorNames = { "OK", "BadArg", "BufferTooSmall", "InternalError", "InvalidPacket", "Unimplemented", "InvalidState", "AllocFail" };
            string errorName = error < errorNames.Length ? errorNames[error] : $"Unknown({error})";
            throw new InvalidOperationException($"Opus encoder error: {errorName}");
        }
    }

    public int FrameSize => _frameSize;

    public int Bitrate
    {
        set => OpusNative.opus_encoder_ctl(_handle, 4002, value); // OPUS_SET_BITRATE
    }

    public int Complexity
    {
        set => OpusNative.opus_encoder_ctl(_handle, 4010, value); // OPUS_SET_COMPLEXITY
    }

    public bool Vbr
    {
        set => OpusNative.opus_encoder_ctl(_handle, 4006, value ? 1 : 0); // OPUS_SET_VBR
    }

    public bool InbandFec
    {
        set => OpusNative.opus_encoder_ctl(_handle, 4012, value ? 1 : 0); // OPUS_SET_INBAND_FEC
    }

    public int PacketLossPercent
    {
        set => OpusNative.opus_encoder_ctl(_handle, 4014, value); // OPUS_SET_PACKET_LOSS_PERC
    }

    public bool Dtx
    {
        set => OpusNative.opus_encoder_ctl(_handle, 4016, value ? 1 : 0); // OPUS_SET_DTX
    }

    public OpusSignal SignalType
    {
        set => OpusNative.opus_encoder_ctl(_handle, 4024, (int)value); // OPUS_SET_SIGNAL
    }

    public OpusBandwidth MaxBandwidth
    {
        set => OpusNative.opus_encoder_ctl(_handle, 4008, (int)value); // OPUS_SET_MAX_BANDWIDTH
    }

    /// <summary>
    /// Кодирует PCM-данные в Opus-пакет.
    /// При использовании FEC: сначала вызовите этот метод с ПРЕДЫДУЩИМ кадром,
    /// затем с ТЕКУЩИМ кадром — тогда текущий пакет будет содержать FEC-информацию.
    /// </summary>
    public int Encode(short[] pcm, byte[] output)
    {
        return OpusNative.opus_encode(_handle, pcm, _frameSize, output, output.Length);
    }

    public int Encode(ReadOnlySpan<short> pcm, Span<byte> output)
    {
        short[] pcmArray = pcm.ToArray();
        byte[] outArray = new byte[output.Length];
        int result = OpusNative.opus_encode(_handle, pcmArray, _frameSize, outArray, outArray.Length);
        outArray.AsSpan(0, result).CopyTo(output);
        return result;
    }

    public void Dispose()
    {
        if (_handle != IntPtr.Zero)
        {
            OpusNative.opus_encoder_destroy(_handle);
        }
    }
}

public enum OpusApplication
{
    Voip = 2048,
    Audio = 2049,
    RestrictedLowDelay = 2051
}

public enum OpusSignal
{
    Auto = -1000,
    Voice = 3001,
    Music = 3002
}

public enum OpusBandwidth
{
    Auto = -1000,
    Narrowband = 1101,
    Mediumband = 1102,
    Wideband = 1103,
    SuperWideband = 1104,
    Fullband = 1105
}
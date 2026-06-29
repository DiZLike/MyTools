namespace FuzzCast.Core.Protocol.Models;

public class AudioPacket
{
    public byte[]? PasswordMD5 { get; set; }
    public uint Sequence { get; set; }
    public long Timestamp { get; set; }
    public TrackMetadata? Metadata { get; set; }
    public byte[] OpusFrame { get; set; } = Array.Empty<byte>();

    public bool HasPassword => PasswordMD5 is { Length: 16 };
    public bool HasMetadata => Metadata != null && !Metadata.IsEmpty;
}
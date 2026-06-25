namespace FrostWire.Core.Protocol.Models;

public class ServerInfoPacket
{
    public const byte StatusLive = 0x01;
    public const byte StatusNoSource = 0x02;
    public const byte StatusShuttingDown = 0x03;

    public long Timestamp { get; set; }
    public uint Uptime { get; set; }
    public byte Status { get; set; }
    public int ClientsCount { get; set; }
    public uint TrackPosition { get; set; }
}
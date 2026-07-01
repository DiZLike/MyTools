namespace FuzzCast.Core.Protocol;

public static class PacketTypes
{
    public const byte Subscribe = 0x10;
    public const byte KeepAlive = 0x12;
    public const byte Audio = 0x20;
    public const byte SourceStatus = 0x21;
    public const byte ServerInfo = 0x30;
}
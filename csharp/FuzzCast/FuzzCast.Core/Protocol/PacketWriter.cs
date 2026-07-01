using System.Text;
using FuzzCast.Core.Protocol.Models;

namespace FuzzCast.Core.Protocol;

public static class PacketWriter
{
    // ─── Общие методы для записи в буфер ─────────────────────

    /// <summary>
    /// Записывает базовую структуру Audio пакета (без MD5)
    /// </summary>
    private static byte[] WriteAudioPacketBase(AudioPacket packet, bool includePassword)
    {
        if (includePassword)
        {
            if (packet.PasswordMD5 == null || packet.PasswordMD5.Length != 16)
                throw new ArgumentException("PasswordMD5 must be 16 bytes");
        }

        byte[] metaBytes = packet.Metadata?.Serialize() ?? Array.Empty<byte>();
        if (metaBytes.Length > ushort.MaxValue)
            throw new ArgumentException("Metadata too large");

        int headerSize = 1 + 4 + 8 + 2; // Type + Seq + Timestamp + MetaLen
        if (includePassword)
            headerSize += 16; // + MD5

        int totalLen = headerSize + metaBytes.Length + packet.OpusFrame.Length;
        byte[] buffer = new byte[totalLen];
        int offset = 0;

        // Type
        buffer[offset++] = PacketTypes.Audio;

        // Password MD5 (если нужно)
        if (includePassword)
        {
            Buffer.BlockCopy(packet.PasswordMD5!, 0, buffer, offset, 16);
            offset += 16;
        }

        // Sequence
        BitConverter.TryWriteBytes(buffer.AsSpan(offset, 4), packet.Sequence);
        offset += 4;

        // Timestamp
        BitConverter.TryWriteBytes(buffer.AsSpan(offset, 8), packet.Timestamp);
        offset += 8;

        // Metadata length + data
        BitConverter.TryWriteBytes(buffer.AsSpan(offset, 2), (ushort)metaBytes.Length);
        offset += 2;

        if (metaBytes.Length > 0)
        {
            Buffer.BlockCopy(metaBytes, 0, buffer, offset, metaBytes.Length);
            offset += metaBytes.Length;
        }

        // Opus frame
        Buffer.BlockCopy(packet.OpusFrame, 0, buffer, offset, packet.OpusFrame.Length);

        return buffer;
    }

    // ─── AUDIO (Source → Server) ───────────────────────────────
    // [0x20] [MD5:16] [Seq:4] [Timestamp:8] [MetaLen:2] [MetaJSON:N] [OpusFrame:M]

    public static byte[] WriteAudioFromSource(AudioPacket packet)
    {
        return WriteAudioPacketBase(packet, includePassword: true);
    }

    // ─── AUDIO (Server → Player) ──────────────────────────────
    // [0x20] [Seq:4] [Timestamp:8] [MetaLen:2] [MetaJSON:N] [OpusFrame:M]

    public static byte[] WriteAudioToPlayer(AudioPacket packet)
    {
        return WriteAudioPacketBase(packet, includePassword: false);
    }

    // ─── SOURCE_STATUS ─────────────────────────────────────────
    // [0x21] [Timestamp:8] [ClientsCount:4]

    public static byte[] WriteSourceStatus(SourceStatusPacket packet)
    {
        byte[] buffer = new byte[1 + 8 + 4];
        int offset = 0;

        buffer[offset++] = PacketTypes.SourceStatus;
        BitConverter.TryWriteBytes(buffer.AsSpan(offset, 8), packet.Timestamp);
        offset += 8;
        BitConverter.TryWriteBytes(buffer.AsSpan(offset, 4), packet.ClientsCount);

        return buffer;
    }

    // ─── SUBSCRIBE ─────────────────────────────────────────────
    // [0x10] [ClientId:16]

    public static byte[] WriteSubscribe(SubscribePacket packet)
    {
        if (packet.ClientId.Length != 16)
            throw new ArgumentException("ClientId must be 16 bytes");

        byte[] buffer = new byte[1 + 16];
        buffer[0] = PacketTypes.Subscribe;
        Buffer.BlockCopy(packet.ClientId, 0, buffer, 1, 16);

        return buffer;
    }

    // ─── KEEPALIVE ─────────────────────────────────────────────
    // [0x12] [ClientId:16]

    public static byte[] WriteKeepAlive(KeepAlivePacket packet)
    {
        if (packet.ClientId.Length != 16)
            throw new ArgumentException("ClientId must be 16 bytes");

        byte[] buffer = new byte[1 + 16];
        buffer[0] = PacketTypes.KeepAlive;
        Buffer.BlockCopy(packet.ClientId, 0, buffer, 1, 16);

        return buffer;
    }

    // ─── SERVER_INFO ───────────────────────────────────────────
    // [0x30] [Timestamp:8] [Uptime:4] [Status:1] [ClientsCount:4] [TrackPosition:4]

    public static byte[] WriteServerInfo(ServerInfoPacket packet)
    {
        byte[] buffer = new byte[1 + 8 + 4 + 1 + 4 + 4];
        int offset = 0;

        buffer[offset++] = PacketTypes.ServerInfo;
        BitConverter.TryWriteBytes(buffer.AsSpan(offset, 8), packet.Timestamp);
        offset += 8;
        BitConverter.TryWriteBytes(buffer.AsSpan(offset, 4), packet.Uptime);
        offset += 4;
        buffer[offset++] = packet.Status;
        BitConverter.TryWriteBytes(buffer.AsSpan(offset, 4), packet.ClientsCount);
        offset += 4;
        BitConverter.TryWriteBytes(buffer.AsSpan(offset, 4), packet.TrackPosition);

        return buffer;
    }
}
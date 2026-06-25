using System.Text;
using FrostWire.Core.Protocol.Models;

namespace FrostWire.Core.Protocol;

public static class PacketReader
{
    public static byte GetPacketType(byte[] data)
    {
        if (data.Length < 1)
            throw new ArgumentException("Packet too short");
        return data[0];
    }

    // ─── AUDIO (от Source, с паролем) ─────────────────────────

    public static AudioPacket ReadAudioFromSource(byte[] data)
    {
        // Минимум: Type(1) + MD5(16) + Seq(4) + Timestamp(8) + MetaLen(2) = 31
        if (data.Length < 31)
            throw new ArgumentException($"Audio packet too short: {data.Length}");

        int offset = 1;

        byte[] passwordMD5 = new byte[16];
        Buffer.BlockCopy(data, offset, passwordMD5, 0, 16);
        offset += 16;

        uint sequence = BitConverter.ToUInt32(data, offset);
        offset += 4;

        long timestamp = BitConverter.ToInt64(data, offset);
        offset += 8;

        ushort metaLen = BitConverter.ToUInt16(data, offset);
        offset += 2;

        TrackMetadata? metadata = null;
        if (metaLen > 0)
        {
            if (offset + metaLen > data.Length)
                throw new ArgumentException("Metadata length exceeds packet size");

            byte[] metaBytes = new byte[metaLen];
            Buffer.BlockCopy(data, offset, metaBytes, 0, metaLen);
            metadata = TrackMetadata.Deserialize(metaBytes);
            offset += metaLen;
        }

        int opusLen = data.Length - offset;
        byte[] opusFrame = new byte[opusLen];
        Buffer.BlockCopy(data, offset, opusFrame, 0, opusLen);

        return new AudioPacket
        {
            PasswordMD5 = passwordMD5,
            Sequence = sequence,
            Timestamp = timestamp,
            Metadata = metadata,
            OpusFrame = opusFrame
        };
    }

    // ─── AUDIO (от Сервера, без пароля) ───────────────────────

    public static AudioPacket ReadAudioFromServer(byte[] data)
    {
        // Минимум: Type(1) + Seq(4) + Timestamp(8) + MetaLen(2) = 15
        if (data.Length < 15)
            throw new ArgumentException($"Audio packet too short: {data.Length}");

        int offset = 1;

        uint sequence = BitConverter.ToUInt32(data, offset);
        offset += 4;

        long timestamp = BitConverter.ToInt64(data, offset);
        offset += 8;

        ushort metaLen = BitConverter.ToUInt16(data, offset);
        offset += 2;

        TrackMetadata? metadata = null;
        if (metaLen > 0)
        {
            if (offset + metaLen > data.Length)
                throw new ArgumentException("Metadata length exceeds packet size");

            byte[] metaBytes = new byte[metaLen];
            Buffer.BlockCopy(data, offset, metaBytes, 0, metaLen);
            metadata = TrackMetadata.Deserialize(metaBytes);
            offset += metaLen;
        }

        int opusLen = data.Length - offset;
        byte[] opusFrame = new byte[opusLen];
        Buffer.BlockCopy(data, offset, opusFrame, 0, opusLen);

        return new AudioPacket
        {
            Sequence = sequence,
            Timestamp = timestamp,
            Metadata = metadata,
            OpusFrame = opusFrame
        };
    }

    // ─── SOURCE_STATUS ─────────────────────────────────────────

    public static SourceStatusPacket ReadSourceStatus(byte[] data)
    {
        if (data.Length < 13)
            throw new ArgumentException($"SourceStatus packet too short: {data.Length}");

        return new SourceStatusPacket
        {
            Timestamp = BitConverter.ToInt64(data, 1),
            ClientsCount = BitConverter.ToInt32(data, 9)
        };
    }

    // ─── SUBSCRIBE ─────────────────────────────────────────────

    public static SubscribePacket ReadSubscribe(byte[] data)
    {
        if (data.Length < 17)
            throw new ArgumentException($"Subscribe packet too short: {data.Length}");

        byte[] clientId = new byte[16];
        Buffer.BlockCopy(data, 1, clientId, 0, 16);

        return new SubscribePacket { ClientId = clientId };
    }

    // ─── KEEPALIVE ─────────────────────────────────────────────

    public static KeepAlivePacket ReadKeepAlive(byte[] data)
    {
        if (data.Length < 17)
            throw new ArgumentException($"KeepAlive packet too short: {data.Length}");

        byte[] clientId = new byte[16];
        Buffer.BlockCopy(data, 1, clientId, 0, 16);

        return new KeepAlivePacket { ClientId = clientId };
    }

    // ─── SERVER_INFO ───────────────────────────────────────────

    public static ServerInfoPacket ReadServerInfo(byte[] data)
    {
        if (data.Length < 22)
            throw new ArgumentException($"ServerInfo packet too short: {data.Length}");

        return new ServerInfoPacket
        {
            Timestamp = BitConverter.ToInt64(data, 1),
            Uptime = BitConverter.ToUInt32(data, 9),
            Status = data[13],
            ClientsCount = BitConverter.ToInt32(data, 14),
            TrackPosition = BitConverter.ToUInt32(data, 18)
        };
    }
}
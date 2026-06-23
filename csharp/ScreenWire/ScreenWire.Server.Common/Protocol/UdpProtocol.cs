using System;

namespace ScreenWire.Server.Protocol
{
    public static class UdpProtocol
    {
        public static readonly byte[] Magic = { (byte)'S', (byte)'C', (byte)'W', (byte)'I' };

        public const byte MsgAuthRequest = 0x01;
        public const byte MsgAuthResponse = 0x02;
        public const byte MsgAuthResult = 0x03;
        public const byte MsgScreenInfo = 0x04;
        public const byte MsgFrameRequest = 0x05;
        public const byte MsgMouseEvent = 0x06;
        public const byte MsgKeyboardEvent = 0x07;
        public const byte MsgQualityRequest = 0x08;
        public const byte MsgClipboardText = 0x09;
        public const byte MsgPing = 0x0A;
        public const byte MsgUpdateRequest = 0x0B;
        public const byte MsgUpdatePort = 0x0C;
        public const byte MsgUpdateStatus = 0x0D;
        public const byte MsgDisconnect = 0x0E;
        public const byte MsgFpsRequest = 0x0F;
        public const byte MsgDisplaySelect = 0x10;
        public const byte MsgDisplayInfo = 0x11;
        public const byte MsgAck = 0xFF;

        public const byte AuthOk = 0x00;
        public const byte AuthBadPassword = 0x01;

        public const byte MouseLeftDown = 1 << 0;
        public const byte MouseRightDown = 1 << 1;
        public const byte MouseMiddleDown = 1 << 2;
        public const byte MouseX1Down = 1 << 3;
        public const byte MouseX2Down = 1 << 4;
        public const byte MouseMove = 1 << 5;
        public const byte MouseWheel = 1 << 6;
        public const byte KeyDown = 1 << 0;

        public const int CmdHeaderSize = 9;
        public const int VideoHeaderSize = 10;
        public const int BlockHeaderSize = 12;
        public const int TcpLengthPrefixSize = 4;

        public const int AckTimeout = 3000;
        public const int MaxRetries = 5;

        public const byte VideoFlagKeyFrame = 0x01;
        public const byte VideoFlagDelta = 0x00;

        public const byte UpdateStatusReady = 0x00;
        public const byte UpdateStatusReceiving = 0x01;
        public const byte UpdateStatusVerifying = 0x02;
        public const byte UpdateStatusInstalling = 0x03;
        public const byte UpdateStatusSuccess = 0x04;
        public const byte UpdateStatusError = 0xFF;

        public const byte UpdateErrorNone = 0x00;
        public const byte UpdateErrorInvalidZip = 0x01;
        public const byte UpdateErrorNoExe = 0x02;
        public const byte UpdateErrorExtract = 0x03;
        public const byte UpdateErrorInstall = 0x04;
        public const byte UpdateErrorTimeout = 0x05;

        public static byte[] CreateCommandPacket(ushort msgId, byte type, byte[] payload)
        {
            int plen = payload?.Length ?? 0;
            byte[] p = new byte[CmdHeaderSize + plen];
            Buffer.BlockCopy(Magic, 0, p, 0, 4);
            p[4] = (byte)(msgId >> 8);
            p[5] = (byte)(msgId & 0xFF);
            p[6] = type;
            p[7] = (byte)(plen >> 8);
            p[8] = (byte)(plen & 0xFF);
            if (plen > 0) Buffer.BlockCopy(payload, 0, p, CmdHeaderSize, plen);
            return p;
        }

        public static byte[] CreateAckPacket(ushort msgId)
        {
            return CreateCommandPacket(msgId, MsgAck, null);
        }

        public static bool ParseCommandHeader(byte[] p, out ushort msgId, out byte type, out ushort plen)
        {
            msgId = 0; type = 0; plen = 0;
            if (p.Length < CmdHeaderSize) return false;
            if (p[0] != Magic[0] || p[1] != Magic[1] || p[2] != Magic[2] || p[3] != Magic[3])
                return false;

            msgId = (ushort)((p[4] << 8) | p[5]);
            type = p[6];
            plen = (ushort)((p[7] << 8) | p[8]);
            return true;
        }

        public static byte[] CreateVideoBlockPacket(uint frameId, byte flags, ushort blockIndex, ushort totalBlocks,
            ushort blockX, ushort blockY, ushort blockW, ushort blockH, byte[] jpegData)
        {
            int header = VideoHeaderSize + BlockHeaderSize;
            byte[] p = new byte[header + jpegData.Length];

            p[0] = (byte)(frameId >> 24);
            p[1] = (byte)(frameId >> 16);
            p[2] = (byte)(frameId >> 8);
            p[3] = (byte)frameId;
            p[4] = flags;
            p[5] = (byte)(blockIndex >> 8);
            p[6] = (byte)(blockIndex & 0xFF);
            p[7] = (byte)(totalBlocks >> 8);
            p[8] = (byte)(totalBlocks & 0xFF);
            p[9] = 0;

            p[10] = (byte)(blockX >> 8);
            p[11] = (byte)(blockX & 0xFF);
            p[12] = (byte)(blockY >> 8);
            p[13] = (byte)(blockY & 0xFF);
            p[14] = (byte)(blockW >> 8);
            p[15] = (byte)(blockW & 0xFF);
            p[16] = (byte)(blockH >> 8);
            p[17] = (byte)(blockH & 0xFF);
            p[18] = (byte)(jpegData.Length >> 24);
            p[19] = (byte)(jpegData.Length >> 16);
            p[20] = (byte)(jpegData.Length >> 8);
            p[21] = (byte)(jpegData.Length & 0xFF);

            Buffer.BlockCopy(jpegData, 0, p, header, jpegData.Length);
            return p;
        }

        public static byte[] WrapTcpFrame(byte[] data)
        {
            byte[] frame = new byte[TcpLengthPrefixSize + data.Length];
            frame[0] = (byte)(data.Length >> 24);
            frame[1] = (byte)(data.Length >> 16);
            frame[2] = (byte)(data.Length >> 8);
            frame[3] = (byte)(data.Length & 0xFF);
            Buffer.BlockCopy(data, 0, frame, TcpLengthPrefixSize, data.Length);
            return frame;
        }

        public static bool ParseVideoBlockHeader(byte[] p, out uint frameId, out byte flags,
            out ushort blockIndex, out ushort totalBlocks,
            out ushort blockX, out ushort blockY,
            out ushort blockW, out ushort blockH,
            out int jpegSize)
        {
            frameId = 0; flags = 0; blockIndex = 0; totalBlocks = 0;
            blockX = 0; blockY = 0; blockW = 0; blockH = 0; jpegSize = 0;

            int minLen = VideoHeaderSize + BlockHeaderSize;
            if (p.Length < minLen) return false;

            frameId = (uint)((p[0] << 24) | (p[1] << 16) | (p[2] << 8) | p[3]);
            flags = p[4];
            blockIndex = (ushort)((p[5] << 8) | p[6]);
            totalBlocks = (ushort)((p[7] << 8) | p[8]);

            blockX = (ushort)((p[10] << 8) | p[11]);
            blockY = (ushort)((p[12] << 8) | p[13]);
            blockW = (ushort)((p[14] << 8) | p[15]);
            blockH = (ushort)((p[16] << 8) | p[17]);
            jpegSize = (p[18] << 24) | (p[19] << 16) | (p[20] << 8) | p[21];

            return p.Length >= minLen + jpegSize;
        }
    }
}
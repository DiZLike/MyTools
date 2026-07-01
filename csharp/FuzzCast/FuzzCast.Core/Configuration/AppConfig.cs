namespace FuzzCast.Core.Configuration;

public class AppConfig
{
    public ServerConfig Server { get; set; } = new();
    public SourceConfig Source { get; set; } = new();
    public PlayerConfig Player { get; set; } = new();
    public OpusConfig Opus { get; set; } = new();
    public CompressorConfig Compressor { get; set; } = new();
}

public class ServerConfig
{
    public int ListenPort { get; set; } = 5000;
    public int ListenPortFallback { get; set; } = 5001;
    public string Password { get; set; } = string.Empty;
    public int SourceStatusIntervalMs { get; set; } = 3000;
    public int SourceTimeoutMs { get; set; } = 5000;
    public int PlayerTimeoutMs { get; set; } = 10000;
    public int ServerInfoIntervalMs { get; set; } = 5000;
}

public class SourceConfig
{
    public string ServerAddress { get; set; } = "127.0.0.1";
    public int ServerPort { get; set; } = 5000;
    public string Password { get; set; } = string.Empty;
    public string PlaylistPath { get; set; } = "playlist.m3u";
    public bool Shuffle { get; set; } = true;
}

public class PlayerConfig
{
    public string ServerAddress { get; set; } = "127.0.0.1";
    public int ServerPort { get; set; } = 5000;
    public int ServerPortFallback { get; set; } = 5001;
    public int KeepAliveIntervalMs { get; set; } = 3000;
    public int ToleranceSwitchToFallback { get; set; } = 10;
    public int ToleranceSwitchToPrimary { get; set; } = 3;
    public int QualityCheckIntervalMs { get; set; } = 2000;
}

public class OpusConfig
{
    public int SampleRate { get; set; } = 48000;
    public int Channels { get; set; } = 2;
    public int Bitrate { get; set; } = 128000;
    public int FrameSize { get; set; } = 20;
    public int Complexity { get; set; } = 10;
    public int PacketLossPercent { get; set; } = 15;
    public int FallbackBitrate { get; set; } = 64000;
    public int FallbackChannels { get; set; } = 1;
    public int FallbackPacketLossPercent { get; set; } = 15;
}
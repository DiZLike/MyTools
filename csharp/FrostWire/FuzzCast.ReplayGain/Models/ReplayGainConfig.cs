namespace FuzzCast.ReplayGain.Models;

public class ReplayGainConfig
{
    public double ReferenceLevel { get; set; } = -14.0;
    public double PreAmp { get; set; } = 0.0;
    public string DecodersPath { get; set; } = "decoders";
    public List<string> SupportedExtensions { get; set; } = new();
    public string TagCommentFormat { get; set; } = "REPLAYGAIN_TRACK_GAIN={gain:0.00} dB\nREPLAYGAIN_TRACK_PEAK={peak:0.000000}";
}
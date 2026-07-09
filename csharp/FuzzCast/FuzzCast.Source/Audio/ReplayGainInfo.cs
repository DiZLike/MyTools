namespace FuzzCast.Source.Audio;

public class ReplayGainInfo
{
    public float TrackGainDb { get; set; }
    public float TrackPeak { get; set; } = 1.0f;
    public float? RmsDb { get; set; }
    public float? RmsLowDb { get; set; }
    public float? RmsMidDb { get; set; }
    public float? RmsHighDb { get; set; }
}
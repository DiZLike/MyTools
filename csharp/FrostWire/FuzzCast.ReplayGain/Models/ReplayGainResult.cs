namespace FuzzCast.ReplayGain.Models;

public class ReplayGainResult
{
    public double RmsLeft { get; set; }
    public double RmsRight { get; set; }
    public double PeakLeft { get; set; }
    public double PeakRight { get; set; }
    public double TrackGain { get; set; }
    public double TrackPeak { get; set; }
    public bool Success { get; set; }
    public string? ErrorMessage { get; set; }

    public static ReplayGainResult Fail(string message) => new() { Success = false, ErrorMessage = message };
}
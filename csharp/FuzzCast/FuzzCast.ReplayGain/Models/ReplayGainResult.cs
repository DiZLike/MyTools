namespace FuzzCast.ReplayGain.Models;

public class ReplayGainResult
{
    public bool Success { get; set; }
    public string? ErrorMessage { get; set; }

    public double RmsLeft { get; set; }
    public double RmsRight { get; set; }
    public double PeakLeft { get; set; }
    public double PeakRight { get; set; }
    public double TrackGain { get; set; }
    public double TrackPeak { get; set; }

    public double RmsMax => Math.Max(RmsLeft, RmsRight);

    /// <summary>
    /// Максимальный RMS в децибелах (20 * log10)
    /// </summary>
    public double RmsMaxDb => RmsMax > 1e-10 ? 20.0 * Math.Log10(RmsMax) : double.NegativeInfinity;

    public static ReplayGainResult Fail(string message)
    {
        return new ReplayGainResult
        {
            Success = false,
            ErrorMessage = message
        };
    }
}
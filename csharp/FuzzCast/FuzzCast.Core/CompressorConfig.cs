namespace FuzzCast.Core.Configuration;

public class CompressorConfig
{
    public bool ReplayGainEnabled { get; set; } = true;
    public bool CompressorEnabled { get; set; } = true;
    public double HeadroomDb { get; set; } = 6.0;
    public double Ratio { get; set; } = 4.0;
    public double AttackMs { get; set; } = 5.0;
    public double ReleaseMs { get; set; } = 100.0;
}
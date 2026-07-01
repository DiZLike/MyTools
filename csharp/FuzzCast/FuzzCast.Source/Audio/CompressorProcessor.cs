using FuzzCast.Core.Configuration;
using Un4seen.Bass;
using Un4seen.Bass.AddOn.Fx;

namespace FuzzCast.Source.Audio;

public class CompressorProcessor
{
    public int ApplyToStream(int stream, float thresholdDb, CompressorConfig config)
    {
        int fxHandle = Bass.BASS_ChannelSetFX(stream, BASSFXType.BASS_FX_BFX_COMPRESSOR2, 0);
        if (fxHandle == 0)
        {
            Console.WriteLine($"[ERROR] BASS_FX_BFX_COMPRESSOR2 failed: {Bass.BASS_ErrorGetCode()}");
            return 0;
        }

        var compParam = new BASS_BFX_COMPRESSOR2
        {
            fGain = 0f,
            fThreshold = thresholdDb,
            fRatio = (float)config.Ratio,
            fAttack = (float)(config.AttackMs),
            fRelease = (float)(config.ReleaseMs),
        };

        bool ok = Bass.BASS_FXSetParameters(fxHandle, compParam);
        if (!ok)
        {
            Console.WriteLine($"[ERROR] Compressor BASS_FXSetParameters failed: {Bass.BASS_ErrorGetCode()}");
            Bass.BASS_ChannelRemoveFX(stream, fxHandle);
            return 0;
        }

        Console.WriteLine(
            $"[Compressor] Threshold: {thresholdDb:F1} dB, " +
            $"Ratio: {config.Ratio}:1, " +
            $"Attack: {config.AttackMs}ms, " +
            $"Release: {config.ReleaseMs}ms");

        return fxHandle;
    }
}
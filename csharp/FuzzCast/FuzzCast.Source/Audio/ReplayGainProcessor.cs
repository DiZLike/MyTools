using System.Globalization;
using Un4seen.Bass;
using Un4seen.Bass.AddOn.Fx;

namespace FuzzCast.Source.Audio;

public class ReplayGainProcessor
{
    public ReplayGainInfo? ExtractFromComment(string? comment)
    {
        if (string.IsNullOrEmpty(comment))
            return null;

        float? gain = null;
        float? peak = null;
        float? rms = null;

        var lines = comment.Split('\n', StringSplitOptions.RemoveEmptyEntries);

        foreach (var line in lines)
        {
            var parts = line.Split('=', 2);
            if (parts.Length != 2)
                continue;

            string key = parts[0].Trim().ToUpperInvariant();
            string value = parts[1].Trim();

            switch (key)
            {
                case "REPLAYGAIN_TRACK_GAIN":
                    gain = ParseDbValue(value);
                    break;
                case "REPLAYGAIN_TRACK_PEAK":
                    peak = ParseFloatValue(value);
                    break;
                case "REPLAYGAIN_TRACK_RMS":
                    rms = ParseDbValue(value);
                    break;
            }
        }

        if (gain.HasValue)
        {
            return new ReplayGainInfo
            {
                TrackGainDb = gain.Value,
                TrackPeak = peak ?? 1.0f,
                RmsDb = rms
            };
        }

        return null;
    }

    public int ApplyToStream(int stream, float gainLinear)
    {
        if (Math.Abs(gainLinear - 1.0f) < 0.001f)
            return 0;

        int fxHandle = Bass.BASS_ChannelSetFX(stream, BASSFXType.BASS_FX_BFX_VOLUME, 0);
        if (fxHandle == 0)
        {
            Console.WriteLine($"[ERROR] BASS_BFX_VOLUME failed: {Bass.BASS_ErrorGetCode()}");
            return 0;
        }

        var volParam = new BASS_BFX_VOLUME
        {
            lChannel = 0,
            fVolume = gainLinear
        };

        bool ok = Bass.BASS_FXSetParameters(fxHandle, volParam);
        if (!ok)
        {
            Console.WriteLine($"[ERROR] BASS_FXSetParameters failed: {Bass.BASS_ErrorGetCode()}");
            Bass.BASS_ChannelRemoveFX(stream, fxHandle);
            return 0;
        }

        Console.WriteLine(
            $"[ReplayGain] Applied {(float)(20 * Math.Log10(gainLinear)):F2} dB " +
            $"(linear: {gainLinear:F6})");

        return fxHandle;
    }

    private float? ParseDbValue(string value)
    {
        value = value.Replace(";", "").Replace("dB", "").Replace("db", "").Trim();
        return ParseFloatValue(value);
    }

    private float? ParseFloatValue(string value)
    {
        value = value.Replace(";", "").Trim();

        if (float.TryParse(value,
            NumberStyles.Float,
            CultureInfo.InvariantCulture,
            out float result))
        {
            return result;
        }
        return null;
    }
}
using System.Globalization;

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
        float? rmsLow = null;
        float? rmsMid = null;
        float? rmsHigh = null;

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
                case "REPLAYGAIN_TRACK_RMS_LOW":
                    rmsLow = ParseDbValue(value);
                    break;
                case "REPLAYGAIN_TRACK_RMS_MID":
                    rmsMid = ParseDbValue(value);
                    break;
                case "REPLAYGAIN_TRACK_RMS_HIGH":
                    rmsHigh = ParseDbValue(value);
                    break;
            }
        }

        if (gain.HasValue || rmsLow.HasValue || rmsMid.HasValue || rmsHigh.HasValue)
        {
            return new ReplayGainInfo
            {
                TrackGainDb = gain ?? 0f,
                TrackPeak = peak ?? 1.0f,
                RmsDb = rms,
                RmsLowDb = rmsLow,
                RmsMidDb = rmsMid,
                RmsHighDb = rmsHigh
            };
        }

        return null;
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
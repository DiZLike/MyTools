// DoubleLinkwitzRileyFilter.cs
namespace FuzzCast.ReplayGain.Services;

internal enum FilterType
{
    LowPass,
    HighPass
}

/// <summary>
/// Упрощённый Linkwitz-Riley фильтр на double для анализа.
/// Два каскада Biquad с Q = 0.7071.
/// </summary>
internal class DoubleLinkwitzRileyFilter
{
    private readonly DoubleBiquadFilter _stage1;
    private readonly DoubleBiquadFilter _stage2;

    public DoubleLinkwitzRileyFilter(int sampleRate, double frequency, FilterType type)
    {
        _stage1 = new DoubleBiquadFilter(sampleRate, frequency, type);
        _stage2 = new DoubleBiquadFilter(sampleRate, frequency, type);
    }

    public double Process(double input)
    {
        return _stage2.Process(_stage1.Process(input));
    }
}

internal class DoubleBiquadFilter
{
    private double _a0, _a1, _a2, _b1, _b2;
    private double _x1, _x2, _y1, _y2;

    public DoubleBiquadFilter(int sampleRate, double freq, FilterType type)
    {
        double omega = 2.0 * Math.PI * freq / sampleRate;
        double cos = Math.Cos(omega);
        double sin = Math.Sin(omega);
        double alpha = sin / (2.0 * 0.7071);

        if (type == FilterType.LowPass)
        {
            _a0 = (1.0 - cos) / 2.0;
            _a1 = 1.0 - cos;
            _a2 = (1.0 - cos) / 2.0;
            double norm = 1.0 + alpha;
            _a0 /= norm; _a1 /= norm; _a2 /= norm;
            _b1 = (-2.0 * cos) / norm;
            _b2 = (1.0 - alpha) / norm;
        }
        else
        {
            _a0 = (1.0 + cos) / 2.0;
            _a1 = -(1.0 + cos);
            _a2 = (1.0 + cos) / 2.0;
            double norm = 1.0 + alpha;
            _a0 /= norm; _a1 /= norm; _a2 /= norm;
            _b1 = (-2.0 * cos) / norm;
            _b2 = (1.0 - alpha) / norm;
        }
    }

    public double Process(double input)
    {
        double output = _a0 * input + _a1 * _x1 + _a2 * _x2 - _b1 * _y1 - _b2 * _y2;
        _x2 = _x1; _x1 = input;
        _y2 = _y1; _y1 = output;
        return output;
    }
}
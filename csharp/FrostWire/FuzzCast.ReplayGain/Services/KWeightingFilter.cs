namespace FuzzCast.ReplayGain.Services;

/// <summary>
/// K-weighting фильтр по ITU-R BS.1770-4.
/// Коэффициенты для 48 kHz из спецификации.
/// </summary>
public class KWeightingFilter
{
    // Коэффициенты фильтра (48 kHz)
    private const double B0 = 1.53512485958697;
    private const double B1 = -2.69169618940638;
    private const double B2 = 1.19839281085285;
    private const double A1 = -1.69065929318241;
    private const double A2 = 0.73248077421585;

    // Состояния для левого канала
    private double _x1L, _x2L, _y1L, _y2L;

    // Состояния для правого канала
    private double _x1R, _x2R, _y1R, _y2R;

    public double ProcessLeft(double sample)
    {
        // y[n] = B0*x[n] + B1*x[n-1] + B2*x[n-2] - A1*y[n-1] - A2*y[n-2]
        double output = B0 * sample + B1 * _x1L + B2 * _x2L - A1 * _y1L - A2 * _y2L;

        _x2L = _x1L;
        _x1L = sample;
        _y2L = _y1L;
        _y1L = output;

        return output;
    }

    public double ProcessRight(double sample)
    {
        double output = B0 * sample + B1 * _x1R + B2 * _x2R - A1 * _y1R - A2 * _y2R;

        _x2R = _x1R;
        _x1R = sample;
        _y2R = _y1R;
        _y1R = output;

        return output;
    }
}
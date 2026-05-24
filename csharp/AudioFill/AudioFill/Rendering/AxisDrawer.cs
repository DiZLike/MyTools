using System;
using System.Collections.Generic;
using System.Drawing;

namespace AudioFill.Rendering
{
    public static class AxisDrawer
    {
        public static void DrawFrequencyAxis(Graphics g, Rectangle rect, double freqMin, double freqMax, bool logScale)
        {
            int tickHeight = 4;

            using var pen = DarkTheme.AxisPen();
            using var brush = DarkTheme.TextPrimaryBrush;
            var font = DarkTheme.AxisFont;

            int xLeft = rect.Left;
            int xRight = rect.Right;
            int y = rect.Bottom;

            g.DrawLine(pen, xLeft, y, xRight, y);

            double[] ticks = logScale
                ? new double[] { 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000 }
                : GenerateLinearTicks(freqMin, freqMax, 8);

            foreach (double freq in ticks)
            {
                if (freq < freqMin || freq > freqMax) continue;

                double ratio = logScale
                    ? (Math.Log10(freq) - Math.Log10(freqMin)) / (Math.Log10(freqMax) - Math.Log10(freqMin))
                    : (freq - freqMin) / (freqMax - freqMin);

                int x = xLeft + (int)(ratio * (xRight - xLeft));

                g.DrawLine(pen, x, y, x, y - tickHeight);

                string label = freq >= 1000 ? $"{freq / 1000:0.#} кГц" : $"{freq:0} Гц";
                var size = g.MeasureString(label, font);
                g.DrawString(label, font, brush, x - size.Width / 2, y + 2);
            }
        }

        public static void DrawTimeAxis(Graphics g, Rectangle rect, double durationSec)
        {
            int tickWidth = 4;

            using var pen = DarkTheme.AxisPen();
            using var brush = DarkTheme.TextPrimaryBrush;
            var font = DarkTheme.AxisFont;

            int x = 50;
            int yTop = rect.Top;
            int yBottom = rect.Bottom;

            g.DrawLine(pen, x, yTop, x, yBottom);

            int desiredTicks = 8;
            double tickInterval = durationSec / desiredTicks;
            tickInterval = NiceRound(tickInterval);

            for (double t = 0; t <= durationSec + tickInterval / 2; t += tickInterval)
            {
                double ratio = durationSec > 0 ? t / durationSec : 0;
                int y = yBottom - (int)(ratio * (yBottom - yTop));

                g.DrawLine(pen, x, y, x + tickWidth, y);

                string label = durationSec > 120
                    ? $"{TimeSpan.FromSeconds(t):m\\:ss}"
                    : $"{t:0.#}с";
                var size = g.MeasureString(label, font);
                g.DrawString(label, font, brush, x - size.Width - 4, y - size.Height / 2);
            }
        }

        public static void DrawDbAxis(Graphics g, Rectangle rect, double dbMin, double dbMax)
        {
            DrawDbAxis(g, rect, dbMin, dbMax, 50, rect.Top, rect.Bottom);
        }

        public static void DrawDbAxis(Graphics g, Rectangle fullRect, double dbMin, double dbMax,
            int marginLeft, int marginTop, int chartBottom)
        {
            int tickWidth = 4;

            using var pen = DarkTheme.AxisPen();
            using var brush = DarkTheme.TextPrimaryBrush;
            var font = DarkTheme.AxisFont;

            int x = marginLeft;
            int yTop = marginTop;
            int yBottom = chartBottom;

            g.DrawLine(pen, x, yTop, x, yBottom);

            double range = dbMax - dbMin;
            double step = NiceRound(range / 8);

            for (double db = dbMin; db <= dbMax + step / 2; db += step)
            {
                double ratio = range > 0 ? (db - dbMin) / range : 0;
                int y = yBottom - (int)(ratio * (yBottom - yTop));

                g.DrawLine(pen, x, y, x + tickWidth, y);

                string label = $"{db:0}";
                var size = g.MeasureString(label, font);
                g.DrawString(label, font, brush, x - size.Width - 4, y - size.Height / 2);
            }
        }

        private static double[] GenerateLinearTicks(double min, double max, int count)
        {
            double range = max - min;
            double step = NiceRound(range / count);
            var list = new List<double>();
            double start = Math.Ceiling(min / step) * step;
            for (double v = start; v <= max; v += step)
                list.Add(v);
            return list.ToArray();
        }

        public static double NiceRound(double value)
        {
            if (value <= 0) return 1;
            double exp = Math.Pow(10, Math.Floor(Math.Log10(value)));
            double mant = value / exp;
            if (mant <= 1) mant = 1;
            else if (mant <= 2) mant = 2;
            else if (mant <= 5) mant = 5;
            else mant = 10;
            return mant * exp;
        }
    }
}
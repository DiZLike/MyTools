using System.Drawing;

namespace AudioFill.Rendering
{
    public static class SpectrogramColorMap
    {
        // Градиент: чёрный → синий → голубой → зелёный → жёлтый → красный → белый
        private static readonly Color[] Stops =
        {
            Color.FromArgb(0, 0, 0),       // -Inf .. -80 дБ
            Color.FromArgb(0, 0, 255),     // -80 .. -60
            Color.FromArgb(0, 204, 255),   // -60 .. -40
            Color.FromArgb(0, 255, 68),    // -40 .. -20
            Color.FromArgb(255, 221, 0),   // -20 .. -10
            Color.FromArgb(255, 34, 0),    // -10 .. 0
            Color.FromArgb(255, 255, 255), // 0 дБ
        };

        private static readonly double[] Thresholds = { -80, -60, -40, -20, -10, 0 };

        /// <summary>
        /// Преобразует уровень дБ в цвет. dbMin — нижняя граница (всё ниже = чёрный).
        /// </summary>
        public static Color GetColor(double db, double dbMin = -100, double dbMax = 0)
        {
            if (double.IsNaN(db) || double.IsInfinity(db) || db < dbMin)
                return Stops[0];

            if (db >= dbMax)
                return Stops[^1];

            // Линейная интерполяция между стопами
            int idx = 0;
            for (int i = 0; i < Thresholds.Length; i++)
            {
                if (db <= Thresholds[i])
                {
                    idx = i;
                    break;
                }
                idx = Thresholds.Length - 1;
            }

            if (idx == 0) return Stops[0];

            double tMin = idx == 1 ? dbMin : Thresholds[idx - 1];
            double tMax = Thresholds[idx];
            double t = (db - tMin) / (tMax - tMin);
            t = Math.Clamp(t, 0, 1);

            Color a = Stops[idx];
            Color b = Stops[idx + 1];
            return Color.FromArgb(
                (int)(a.R + (b.R - a.R) * t),
                (int)(a.G + (b.G - a.G) * t),
                (int)(a.B + (b.B - a.B) * t));
        }
    }
}
using AudioFill.Audio;
using AudioFill.Rendering;
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace AudioFill.Controls
{
    public class SpectrogramView : PictureBox
    {
        private Bitmap? _bitmapLinear;
        private Bitmap? _bitmapLog;
        private bool _logScale = true;
        private double _dbMin = -100;
        private double _dbMax = 0;
        private AnalysisResult? _result;
        private int _lastWidth;
        private int _lastHeight;

        private const int MarginLeft = 55;
        private const int MarginBottom = 30;
        private const int MarginTop = 10;
        private const int MarginRight = 10;

        public SpectrogramView()
        {
            BackColor = DarkTheme.ChartBack;
            DoubleBuffered = true;
            Resize += (s, e) => Invalidate();
        }

        public void SetData(AnalysisResult result)
        {
            _result = result;
            _bitmapLinear?.Dispose();
            _bitmapLog?.Dispose();
            _bitmapLinear = null;
            _bitmapLog = null;
            _lastWidth = 0;
            _lastHeight = 0;

            // Строим битмапы в фоне
            Task.Run(() =>
            {
                BuildBitmaps();
                BeginInvoke(() => Invalidate());
            });
        }

        public void SetScale(bool logScale)
        {
            if (_logScale == logScale) return;
            _logScale = logScale;
            Invalidate();
        }

        private void BuildBitmaps()
        {
            if (_result?.SpectrogramLines == null || _result.SpectrogramLines.Count == 0)
                return;

            int plotWidth = Math.Max(1, Width - MarginLeft - MarginRight);
            int plotHeight = Math.Max(1, Height - MarginTop - MarginBottom);

            // Не перестраиваем, если размер не изменился
            if (plotWidth == _lastWidth && plotHeight == _lastHeight && _bitmapLinear != null)
                return;

            _lastWidth = plotWidth;
            _lastHeight = plotHeight;

            int srcWidth = _result.SpectrogramLines[0].Length;
            int lineCount = _result.SpectrogramLines.Count;

            _bitmapLinear?.Dispose();
            _bitmapLog?.Dispose();

            _bitmapLinear = RenderSpectrogram(plotWidth, plotHeight, srcWidth, lineCount, false);
            _bitmapLog = RenderSpectrogram(plotWidth, plotHeight, srcWidth, lineCount, true);
        }

        private Bitmap RenderSpectrogram(int destWidth, int destHeight, int srcWidth, int lineCount, bool logScale)
        {
            var bmp = new Bitmap(destWidth, destHeight);
            int step = Math.Max(1, lineCount / destHeight);
            double nyquist = _result!.SampleRate / 2.0;
            double logMin = Math.Log10(20);
            double logMax = Math.Log10(nyquist);

            // Предварительно маппим столбцы: destX -> srcX
            int[] columnMap = new int[destWidth];
            for (int destX = 0; destX < destWidth; destX++)
            {
                double norm = (double)destX / destWidth;
                double freq = logScale
                    ? Math.Pow(10, logMin + norm * (logMax - logMin))
                    : norm * nyquist;
                int srcX = (int)(freq / nyquist * srcWidth);
                columnMap[destX] = Math.Clamp(srcX, 0, srcWidth - 1);
            }

            for (int destY = 0; destY < destHeight; destY++)
            {
                int lineIndex = lineCount - 1 - (destY * step);
                if (lineIndex < 0) lineIndex = 0;

                var spectrum = _result.SpectrogramLines[lineIndex];

                for (int destX = 0; destX < destWidth; destX++)
                {
                    int srcX = columnMap[destX];
                    double db = spectrum[srcX];
                    bmp.SetPixel(destX, destY, SpectrogramColorMap.GetColor(db, _dbMin, _dbMax));
                }
            }

            return bmp;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);

            var g = e.Graphics;
            g.Clear(DarkTheme.ChartBack);

            int plotHeight = Math.Max(1, Height - MarginTop - MarginBottom);
            var plotRect = new Rectangle(
                MarginLeft,
                MarginTop,
                Math.Max(1, Width - MarginLeft - MarginRight),
                plotHeight);

            var bmp = _logScale ? _bitmapLog : _bitmapLinear;
            if (bmp != null)
            {
                g.InterpolationMode = InterpolationMode.NearestNeighbor;
                g.PixelOffsetMode = PixelOffsetMode.Half;
                g.DrawImage(bmp, plotRect);
            }

            double nyquist = _result?.SampleRate / 2.0 ?? 22050;
            double duration = _result?.DurationSec ?? 0;

            g.SmoothingMode = SmoothingMode.AntiAlias;
            AxisDrawer.DrawFrequencyAxis(g, plotRect, 20, nyquist, _logScale);
            AxisDrawer.DrawTimeAxis(g, plotRect, duration);
        }
    }
}
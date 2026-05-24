using AudioFill.Audio;
using AudioFill.Rendering;
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace AudioFill.Controls
{
    public class FrequencyChartView : PictureBox
    {
        private AnalysisResult? _result;
        private bool _logScale = true;
        private double _dbMin = -100;
        private double _dbMax = 0;

        private const int MarginLeft = 50;
        private const int MarginBottom = 30;
        private const int MarginTop = 10;
        private const int MarginRight = 10;

        public FrequencyChartView()
        {
            BackColor = DarkTheme.ChartBack;
            DoubleBuffered = true;
        }

        public void SetData(AnalysisResult result)
        {
            _result = result;
            Invalidate();
        }

        public void SetScale(bool logScale)
        {
            if (_logScale == logScale) return;
            _logScale = logScale;
            Invalidate();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);

            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            var plotRect = new Rectangle(
                MarginLeft,
                MarginTop,
                Math.Max(1, Width - MarginLeft - MarginRight),
                Math.Max(1, Height - MarginTop - MarginBottom));

            double nyquist = _result?.SampleRate / 2.0 ?? 22050;
            AxisDrawer.DrawFrequencyAxis(g, plotRect, 20, nyquist, _logScale);
            AxisDrawer.DrawDbAxis(g, new Rectangle(0, 0, Width, Height), _dbMin, _dbMax,
                MarginLeft, MarginTop, Math.Max(1, Height - MarginBottom));

            DrawGrid(g, plotRect);

            if (_result?.AvgSpectrumDb != null)
            {
                DrawSpectrumCurve(g, plotRect, nyquist);
                DrawCutoffZone(g, plotRect, nyquist);
            }
        }

        private void DrawGrid(Graphics g, Rectangle rect)
        {
            using var pen = DarkTheme.GridPen(0.5f);
            double dbRange = _dbMax - _dbMin;
            double dbStep = AxisDrawer.NiceRound(dbRange / 8);
            for (double db = _dbMin; db <= _dbMax; db += dbStep)
            {
                float y = rect.Bottom - (float)((db - _dbMin) / dbRange * rect.Height);
                g.DrawLine(pen, rect.Left, y, rect.Right, y);
            }
        }

        private void DrawSpectrumCurve(Graphics g, Rectangle rect, double nyquist)
        {
            int fftBins = _result!.AvgSpectrumDb.Length;
            var points = new PointF[fftBins];
            double logMin = Math.Log10(20);

            for (int i = 0; i < fftBins; i++)
            {
                double freq = i * _result.SampleRate / (double)(fftBins * 2);
                double xNorm = _logScale
                    ? (Math.Log10(Math.Max(freq, 20)) - logMin) / (Math.Log10(nyquist) - logMin)
                    : freq / nyquist;

                float x = rect.Left + (float)(xNorm * rect.Width);
                float y = rect.Bottom - (float)((_result.AvgSpectrumDb[i] - _dbMin) / (_dbMax - _dbMin) * rect.Height);
                points[i] = new PointF(x, Math.Clamp(y, rect.Top, rect.Bottom));
            }

            using var pen = new Pen(DarkTheme.AccentBlue, 1.5f);
            g.DrawLines(pen, points);
        }

        private void DrawCutoffZone(Graphics g, Rectangle rect, double nyquist)
        {
            if (!_result!.CutoffDetected) return;

            double logMin = Math.Log10(20);
            double cutoffNorm = _logScale
                ? (Math.Log10(_result.CutoffFrequencyHz) - logMin) / (Math.Log10(nyquist) - logMin)
                : _result.CutoffFrequencyHz / nyquist;

            float cutoffX = rect.Left + (float)(cutoffNorm * rect.Width);
            cutoffX = Math.Clamp(cutoffX, rect.Left, rect.Right);

            using var dashPen = DarkTheme.AccentRedPen();
            g.DrawLine(dashPen, cutoffX, rect.Top, cutoffX, rect.Bottom);

            using var fillBrush = new SolidBrush(Color.FromArgb(40, DarkTheme.AccentRed));
            g.FillRectangle(fillBrush, cutoffX, rect.Top, rect.Right - cutoffX, rect.Height);

            string label = $"{_result.CutoffFrequencyHz:0.#} Гц";
            using var font = new Font("Segoe UI", 8, FontStyle.Bold);
            g.DrawString(label, font, DarkTheme.AccentRedBrush, cutoffX + 4, rect.Top + 4);
        }
    }
}
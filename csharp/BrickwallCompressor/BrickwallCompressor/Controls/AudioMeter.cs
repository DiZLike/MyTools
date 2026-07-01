using System;
using System.ComponentModel;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace BrickwallCompressor.Controls
{
    public enum MeterType
    {
        Peak,
        RMS
    }

    public class AudioMeter : Control
    {
        private float _currentLevel = 0.3f;
        private float _peakHoldLevel = 0.5f;

        private MeterType _meterType = MeterType.Peak;
        private Color _lowColor = Color.LimeGreen;
        private Color _midColor = Color.Yellow;
        private Color _highColor = Color.Red;
        private Color _peakHoldColor = Color.White;
        private Color _backgroundColor = Color.FromArgb(30, 30, 30);
        private Color _borderColor = Color.FromArgb(60, 60, 60);
        private Color _scaleTextColor = Color.Gray;
        private Color _scaleLineColor = Color.FromArgb(80, 80, 80);

        private float _lowThreshold = 0.7f;
        private float _midThreshold = 0.9f;

        private bool _showScale = true;
        private bool _showTypeLabel = true;

        public AudioMeter()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint |
                     ControlStyles.UserPaint |
                     ControlStyles.OptimizedDoubleBuffer |
                     ControlStyles.ResizeRedraw, true);

            Size = new Size(30, 200);
            DoubleBuffered = true;
        }

        [Browsable(false)]
        [DesignerSerializationVisibility(DesignerSerializationVisibility.Hidden)]
        public float CurrentLevel
        {
            get => _currentLevel;
            set
            {
                float clamped = Math.Clamp(value, 0f, 1f);
                if (Math.Abs(_currentLevel - clamped) > 0.001f)
                {
                    _currentLevel = clamped;
                    if (_currentLevel > _peakHoldLevel)
                        _peakHoldLevel = _currentLevel;
                    Invalidate();
                }
            }
        }

        [Category("Измеритель")]
        [Description("Тип измерителя: пиковый или RMS")]
        [DefaultValue(MeterType.Peak)]
        public MeterType Type
        {
            get => _meterType;
            set { _meterType = value; Invalidate(); }
        }

        [Category("Цвета")]
        [Description("Цвет шкалы в безопасной зоне")]
        public Color LowColor
        {
            get => _lowColor;
            set { _lowColor = value; Invalidate(); }
        }

        [Category("Цвета")]
        [Description("Цвет шкалы в средней зоне")]
        public Color MidColor
        {
            get => _midColor;
            set { _midColor = value; Invalidate(); }
        }

        [Category("Цвета")]
        [Description("Цвет шкалы в опасной зоне")]
        public Color HighColor
        {
            get => _highColor;
            set { _highColor = value; Invalidate(); }
        }

        [Category("Цвета")]
        [Description("Цвет полоски удержания пика")]
        public Color PeakHoldColor
        {
            get => _peakHoldColor;
            set { _peakHoldColor = value; Invalidate(); }
        }

        [Category("Цвета")]
        [Description("Цвет фона")]
        public Color MeterBackgroundColor
        {
            get => _backgroundColor;
            set { _backgroundColor = value; Invalidate(); }
        }

        [Category("Цвета")]
        [Description("Цвет рамки")]
        public Color MeterBorderColor
        {
            get => _borderColor;
            set { _borderColor = value; Invalidate(); }
        }

        [Category("Цвета")]
        [Description("Цвет текста шкалы")]
        public Color ScaleTextColor
        {
            get => _scaleTextColor;
            set { _scaleTextColor = value; Invalidate(); }
        }

        [Category("Цвета")]
        [Description("Цвет линий шкалы")]
        public Color ScaleLineColor
        {
            get => _scaleLineColor;
            set { _scaleLineColor = value; Invalidate(); }
        }

        [Category("Пороги")]
        [Description("Порог перехода от зелёного к жёлтому (0.0 - 1.0)")]
        [DefaultValue(0.7f)]
        public float LowThreshold
        {
            get => _lowThreshold;
            set { _lowThreshold = Math.Clamp(value, 0f, 1f); Invalidate(); }
        }

        [Category("Пороги")]
        [Description("Порог перехода от жёлтого к красному (0.0 - 1.0)")]
        [DefaultValue(0.9f)]
        public float MidThreshold
        {
            get => _midThreshold;
            set { _midThreshold = Math.Clamp(value, 0f, 1f); Invalidate(); }
        }

        [Category("Отображение")]
        [Description("Показывать шкалу децибел")]
        [DefaultValue(true)]
        public bool ShowScale
        {
            get => _showScale;
            set { _showScale = value; Invalidate(); }
        }

        [Category("Отображение")]
        [Description("Показывать надпись типа метра")]
        [DefaultValue(true)]
        public bool ShowTypeLabel
        {
            get => _showTypeLabel;
            set { _showTypeLabel = value; Invalidate(); }
        }

        [Browsable(false)]
        public float CurrentDb => _currentLevel > 0.0001f ? 20f * MathF.Log10(_currentLevel) : -80f;

        [Browsable(false)]
        public float PeakHoldDb => _peakHoldLevel > 0.0001f ? 20f * MathF.Log10(_peakHoldLevel) : -80f;

        public void UpdateTimer(float deltaTime)
        {
            _peakHoldLevel *= 0.99f;
            if (_peakHoldLevel < _currentLevel)
                _peakHoldLevel = _currentLevel;
            Invalidate();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            if (Width <= 0 || Height <= 0) return;

            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            int width = ClientSize.Width;
            int height = ClientSize.Height;

            using (var bgBrush = new SolidBrush(_backgroundColor))
                g.FillRectangle(bgBrush, 0, 0, width, height);

            using (var borderPen = new Pen(_borderColor))
                g.DrawRectangle(borderPen, 0, 0, width - 1, height - 1);

            int padding = 3;
            int barWidth = width - padding * 2;
            int barHeight = height - padding * 2;

            if (barWidth <= 0 || barHeight <= 0) return;

            if (_showScale)
                DrawScale(g, padding, barWidth, barHeight);

            if (_currentLevel > 0.001f)
                DrawLevel(g, padding, barWidth, barHeight);

            if (_peakHoldLevel > 0.001f && _meterType == MeterType.Peak)
                DrawPeakHold(g, padding, barWidth, barHeight);

            if (_showTypeLabel)
                DrawTypeLabel(g, padding, height);
        }

        private void DrawScale(Graphics g, int padding, int barWidth, int barHeight)
        {
            float[] dbMarkers = { 0, -6, -12, -18, -24, -30, -40, -60 };
            using (var scalePen = new Pen(_scaleLineColor, 1))
            using (var scaleFont = new Font("Arial", 7))
            using (var scaleBrush = new SolidBrush(_scaleTextColor))
            {
                foreach (float db in dbMarkers)
                {
                    float normalized = DbToNormalized(db);
                    int y = padding + (int)((1f - normalized) * barHeight);
                    g.DrawLine(scalePen, padding, y, padding + barWidth, y);
                    g.DrawString($"{db:F0}", scaleFont, scaleBrush, padding + 2, y - 6);
                }
            }
        }

        private void DrawLevel(Graphics g, int padding, int barWidth, int barHeight)
        {
            float db = CurrentDb;
            float normalized = DbToNormalized(db);
            int levelHeight = (int)(normalized * barHeight);
            int levelY = padding + barHeight - levelHeight;

            if (levelHeight <= 0) return;

            Rectangle levelRect = new Rectangle(padding, levelY, barWidth, levelHeight);
            Color color = GetLevelColor(normalized);

            using (var gradient = new LinearGradientBrush(
                levelRect, color, Color.FromArgb(40, color), LinearGradientMode.Vertical))
            {
                g.FillRectangle(gradient, levelRect);
            }
        }

        private void DrawPeakHold(Graphics g, int padding, int barWidth, int barHeight)
        {
            float peakDb = PeakHoldDb;
            float peakNormalized = DbToNormalized(peakDb);
            int peakY = padding + (int)((1f - peakNormalized) * barHeight);

            using (var peakPen = new Pen(_peakHoldColor, 2))
                g.DrawLine(peakPen, padding, peakY, padding + barWidth, peakY);
        }

        private void DrawTypeLabel(Graphics g, int padding, int height)
        {
            string typeText = _meterType == MeterType.Peak ? "PEAK" : "RMS";
            using (var typeFont = new Font("Arial", 7, FontStyle.Bold))
            using (var typeBrush = new SolidBrush(Color.White))
            {
                SizeF textSize = g.MeasureString(typeText, typeFont);
                g.DrawString(typeText, typeFont, typeBrush,
                    padding, height - textSize.Height - 2);
            }
        }

        private Color GetLevelColor(float normalized)
        {
            if (normalized < _lowThreshold) return _lowColor;
            if (normalized < _midThreshold) return _midColor;
            return _highColor;
        }

        private static float DbToNormalized(float db)
        {
            if (db <= -60f) return 0f;
            if (db >= 0f) return 1f;
            return (db + 60f) / 60f;
        }
    }
}
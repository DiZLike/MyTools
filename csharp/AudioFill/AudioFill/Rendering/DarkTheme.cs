using System.Drawing;
using System.Drawing.Drawing2D;

namespace AudioFill.Rendering
{
    public static class DarkTheme
    {
        // ───────── Фоны ─────────
        public static readonly Color FormBack = Color.FromArgb(24, 24, 27);     // #18181B — глубокий тёмный
        public static readonly Color ControlBack = Color.FromArgb(39, 39, 42);     // #27272A
        public static readonly Color ChartBack = Color.FromArgb(9, 9, 11);       // #09090B — почти чёрный
        public static readonly Color TextBoxBack = Color.FromArgb(30, 30, 34);     // #1E1E22
        public static readonly Color TabBack = Color.FromArgb(30, 30, 34);     // #1E1E22
        public static readonly Color TabSelected = Color.FromArgb(24, 24, 27);     // #18181B

        // ───────── Текст ─────────
        public static readonly Color TextPrimary = Color.FromArgb(228, 228, 231);  // #E4E4E7
        public static readonly Color TextMuted = Color.FromArgb(161, 161, 170);  // #A1A1AA
        public static readonly Color TextDisabled = Color.FromArgb(113, 113, 122);  // #71717A

        // ───────── Акценты ─────────
        public static readonly Color AccentBlue = Color.FromArgb(59, 130, 246);   // #3B82F6
        public static readonly Color AccentBlueHover = Color.FromArgb(37, 99, 235);    // #2563EB
        public static readonly Color AccentRed = Color.FromArgb(239, 68, 68);   // #EF4444
        public static readonly Color AccentGreen = Color.FromArgb(34, 197, 94);    // #22C55E
        public static readonly Color AccentYellow = Color.FromArgb(234, 179, 8);    // #EAB308

        // ───────── Границы и сетка ─────────
        public static readonly Color Border = Color.FromArgb(63, 63, 70);     // #3F3F46
        public static readonly Color GridLine = Color.FromArgb(40, 40, 44);     // #28282C
        public static readonly Color AxisLine = Color.FromArgb(82, 82, 91);     // #52525B

        // ───────── Кнопки ─────────
        public static readonly Color ButtonBack = Color.FromArgb(39, 39, 42);     // #27272A
        public static readonly Color ButtonHover = Color.FromArgb(63, 63, 70);     // #3F3F46
        public static readonly Color ButtonPressed = Color.FromArgb(24, 24, 27);     // #18181B

        // ───────── Шрифты ─────────
        public static Font AxisFont = new Font("Segoe UI", 7.5f, FontStyle.Regular);
        public static Font LogFont = new Font("Consolas", 9f, FontStyle.Regular);
        public static Font UIFont = new Font("Segoe UI", 9f, FontStyle.Regular);
        public static Font TitleFont = new Font("Segoe UI", 12f, FontStyle.Bold);

        // ───────── Кисти (создаются при использовании) ─────────
        public static SolidBrush ChartBackBrush => new SolidBrush(ChartBack);
        public static SolidBrush TextPrimaryBrush => new SolidBrush(TextPrimary);
        public static SolidBrush TextMutedBrush => new SolidBrush(TextMuted);
        public static SolidBrush AccentBlueBrush => new SolidBrush(AccentBlue);
        public static SolidBrush AccentRedBrush => new SolidBrush(AccentRed);
        public static SolidBrush AccentGreenBrush => new SolidBrush(AccentGreen);
        public static SolidBrush ButtonBackBrush => new SolidBrush(ButtonBack);

        public static Pen GridPen(float width = 1) => new Pen(GridLine, width);
        public static Pen AxisPen(float width = 1) => new Pen(AxisLine, width);
        public static Pen BorderPen(float width = 1) => new Pen(Border, width);
        public static Pen AccentRedPen(float w = 2) => new Pen(AccentRed, w) { DashStyle = DashStyle.Dash };
        public static Pen AccentBluePen(float w = 1.5f) => new Pen(AccentBlue, w);
    }
}
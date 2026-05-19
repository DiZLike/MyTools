using System.Drawing;
using System.Windows.Forms;

namespace IconFinder.Controls
{
    internal class DarkColorTable : ProfessionalColorTable
    {
        public override Color ToolStripDropDownBackground => Color.FromArgb(45, 45, 48);
        public override Color MenuBorder => Color.FromArgb(50, 50, 55);
        public override Color MenuItemBorder => Color.FromArgb(45, 45, 48);
        public override Color MenuItemSelected => Color.FromArgb(60, 60, 65);
        public override Color ImageMarginGradientBegin => Color.FromArgb(45, 45, 48);
        public override Color ImageMarginGradientMiddle => Color.FromArgb(45, 45, 48);
        public override Color ImageMarginGradientEnd => Color.FromArgb(45, 45, 48);
    }
}
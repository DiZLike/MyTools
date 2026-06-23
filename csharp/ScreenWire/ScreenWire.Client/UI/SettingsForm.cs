using System;
using System.Windows.Forms;

namespace ScreenWire.Client.UI
{
    public partial class SettingsForm : Form
    {
        public int FrameRate => (int)numFps.Value;
        public int JpegQuality => trkQ.Value;
        public bool ScaleToFit => chkScale.Checked;

        public SettingsForm() => InitializeComponent();

        public void SetDefaults(int fps, int q, bool scale)
        {
            numFps.Value = Math.Clamp(fps, 1, 60);
            trkQ.Value = Math.Clamp(q, 1, 100);
            lblQVal.Text = trkQ.Value.ToString();
            chkScale.Checked = scale;
        }

        private void TrkQ_Scroll(object s, EventArgs e) => lblQVal.Text = trkQ.Value.ToString();
    }
}
namespace ScreenWire.Client.UI
{
    partial class SettingsForm
    {
        private System.ComponentModel.IContainer components = null;
        private System.Windows.Forms.Label lblFps;
        private System.Windows.Forms.NumericUpDown numFps;
        private System.Windows.Forms.Label lblQ;
        private System.Windows.Forms.TrackBar trkQ;
        private System.Windows.Forms.Label lblQVal;
        private System.Windows.Forms.CheckBox chkScale;
        private System.Windows.Forms.Button btnOk;
        private System.Windows.Forms.Button btnCancel;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
                components.Dispose();
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            this.lblFps = new System.Windows.Forms.Label();
            this.numFps = new System.Windows.Forms.NumericUpDown();
            this.lblQ = new System.Windows.Forms.Label();
            this.trkQ = new System.Windows.Forms.TrackBar();
            this.lblQVal = new System.Windows.Forms.Label();
            this.chkScale = new System.Windows.Forms.CheckBox();
            this.btnOk = new System.Windows.Forms.Button();
            this.btnCancel = new System.Windows.Forms.Button();

            ((System.ComponentModel.ISupportInitialize)(this.numFps)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.trkQ)).BeginInit();
            this.SuspendLayout();

            this.lblFps.AutoSize = true;
            this.lblFps.Location = new System.Drawing.Point(12, 15);
            this.lblFps.Text = "FPS (1-60):";

            this.numFps.Location = new System.Drawing.Point(130, 13);
            this.numFps.Minimum = 1;
            this.numFps.Maximum = 60;
            this.numFps.Size = new System.Drawing.Size(60, 23);
            this.numFps.Value = 20;

            this.lblQ.AutoSize = true;
            this.lblQ.Location = new System.Drawing.Point(12, 50);
            this.lblQ.Text = "Качество JPEG:";

            this.trkQ.Location = new System.Drawing.Point(12, 70);
            this.trkQ.Minimum = 1;
            this.trkQ.Maximum = 100;
            this.trkQ.Size = new System.Drawing.Size(250, 45);
            this.trkQ.TickFrequency = 10;
            this.trkQ.Value = 50;
            this.trkQ.Scroll += new System.EventHandler(this.TrkQ_Scroll);

            this.lblQVal.AutoSize = true;
            this.lblQVal.Location = new System.Drawing.Point(268, 80);
            this.lblQVal.Text = "50";

            this.chkScale.AutoSize = true;
            this.chkScale.Checked = true;
            this.chkScale.Location = new System.Drawing.Point(12, 125);
            this.chkScale.Text = "Масштабировать";

            this.btnOk.Location = new System.Drawing.Point(130, 160);
            this.btnOk.Size = new System.Drawing.Size(80, 27);
            this.btnOk.Text = "OK";
            this.btnOk.DialogResult = System.Windows.Forms.DialogResult.OK;

            this.btnCancel.Location = new System.Drawing.Point(220, 160);
            this.btnCancel.Size = new System.Drawing.Size(80, 27);
            this.btnCancel.Text = "Отмена";
            this.btnCancel.DialogResult = System.Windows.Forms.DialogResult.Cancel;

            this.AcceptButton = this.btnOk;
            this.CancelButton = this.btnCancel;
            this.ClientSize = new System.Drawing.Size(314, 201);
            this.Controls.AddRange(new System.Windows.Forms.Control[] {
                this.lblFps, this.numFps, this.lblQ, this.trkQ, this.lblQVal,
                this.chkScale, this.btnOk, this.btnCancel
            });
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.MinimizeBox = false;
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterParent;
            this.Text = "Настройки";

            ((System.ComponentModel.ISupportInitialize)(this.numFps)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.trkQ)).EndInit();
            this.ResumeLayout(false);
            this.PerformLayout();
        }
    }
}
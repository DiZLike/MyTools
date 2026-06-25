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
            lblFps = new Label();
            numFps = new NumericUpDown();
            lblQ = new Label();
            trkQ = new TrackBar();
            lblQVal = new Label();
            chkScale = new CheckBox();
            btnOk = new Button();
            btnCancel = new Button();
            label1 = new Label();
            trkR = new TrackBar();
            lblRVal = new Label();
            ((System.ComponentModel.ISupportInitialize)numFps).BeginInit();
            ((System.ComponentModel.ISupportInitialize)trkQ).BeginInit();
            ((System.ComponentModel.ISupportInitialize)trkR).BeginInit();
            SuspendLayout();
            // 
            // lblFps
            // 
            lblFps.AutoSize = true;
            lblFps.Location = new Point(12, 15);
            lblFps.Name = "lblFps";
            lblFps.Size = new Size(63, 15);
            lblFps.TabIndex = 0;
            lblFps.Text = "FPS (1-60):";
            // 
            // numFps
            // 
            numFps.Location = new Point(130, 13);
            numFps.Maximum = new decimal(new int[] { 60, 0, 0, 0 });
            numFps.Minimum = new decimal(new int[] { 1, 0, 0, 0 });
            numFps.Name = "numFps";
            numFps.Size = new Size(60, 23);
            numFps.TabIndex = 1;
            numFps.Value = new decimal(new int[] { 20, 0, 0, 0 });
            // 
            // lblQ
            // 
            lblQ.AutoSize = true;
            lblQ.Location = new Point(12, 50);
            lblQ.Name = "lblQ";
            lblQ.Size = new Size(88, 15);
            lblQ.TabIndex = 2;
            lblQ.Text = "Качество JPEG:";
            // 
            // trkQ
            // 
            trkQ.AutoSize = false;
            trkQ.Location = new Point(12, 70);
            trkQ.Maximum = 100;
            trkQ.Minimum = 1;
            trkQ.Name = "trkQ";
            trkQ.Size = new Size(250, 25);
            trkQ.TabIndex = 3;
            trkQ.TickFrequency = 10;
            trkQ.Value = 50;
            trkQ.Scroll += TrkQ_Scroll;
            // 
            // lblQVal
            // 
            lblQVal.AutoSize = true;
            lblQVal.Location = new Point(268, 70);
            lblQVal.Name = "lblQVal";
            lblQVal.Size = new Size(19, 15);
            lblQVal.TabIndex = 4;
            lblQVal.Text = "50";
            // 
            // chkScale
            // 
            chkScale.AutoSize = true;
            chkScale.Checked = true;
            chkScale.CheckState = CheckState.Checked;
            chkScale.Location = new Point(12, 159);
            chkScale.Name = "chkScale";
            chkScale.Size = new Size(122, 19);
            chkScale.TabIndex = 5;
            chkScale.Text = "Масштабировать";
            // 
            // btnOk
            // 
            btnOk.DialogResult = DialogResult.OK;
            btnOk.Location = new Point(130, 184);
            btnOk.Name = "btnOk";
            btnOk.Size = new Size(80, 27);
            btnOk.TabIndex = 6;
            btnOk.Text = "OK";
            // 
            // btnCancel
            // 
            btnCancel.DialogResult = DialogResult.Cancel;
            btnCancel.Location = new Point(220, 184);
            btnCancel.Name = "btnCancel";
            btnCancel.Size = new Size(80, 27);
            btnCancel.TabIndex = 7;
            btnCancel.Text = "Отмена";
            // 
            // label1
            // 
            label1.AutoSize = true;
            label1.Location = new Point(12, 98);
            label1.Name = "label1";
            label1.Size = new Size(153, 15);
            label1.TabIndex = 8;
            label1.Text = "Уменьшение разрешения:";
            // 
            // trkR
            // 
            trkR.AutoSize = false;
            trkR.Location = new Point(12, 118);
            trkR.Maximum = 50;
            trkR.Minimum = 10;
            trkR.Name = "trkR";
            trkR.Size = new Size(250, 25);
            trkR.TabIndex = 9;
            trkR.Value = 10;
            trkR.Scroll += trkR_Scroll;
            // 
            // lblRVal
            // 
            lblRVal.AutoSize = true;
            lblRVal.Location = new Point(268, 118);
            lblRVal.Name = "lblRVal";
            lblRVal.Size = new Size(19, 15);
            lblRVal.TabIndex = 10;
            lblRVal.Text = "50";
            // 
            // SettingsForm
            // 
            AcceptButton = btnOk;
            CancelButton = btnCancel;
            ClientSize = new Size(313, 218);
            Controls.Add(label1);
            Controls.Add(trkR);
            Controls.Add(lblRVal);
            Controls.Add(lblFps);
            Controls.Add(numFps);
            Controls.Add(lblQ);
            Controls.Add(trkQ);
            Controls.Add(lblQVal);
            Controls.Add(chkScale);
            Controls.Add(btnOk);
            Controls.Add(btnCancel);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            Name = "SettingsForm";
            StartPosition = FormStartPosition.CenterParent;
            Text = "Настройки";
            ((System.ComponentModel.ISupportInitialize)numFps).EndInit();
            ((System.ComponentModel.ISupportInitialize)trkQ).EndInit();
            ((System.ComponentModel.ISupportInitialize)trkR).EndInit();
            ResumeLayout(false);
            PerformLayout();
        }

        private Label label1;
        private TrackBar trkR;
        private Label lblRVal;
    }
}
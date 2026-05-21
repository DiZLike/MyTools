namespace IconFinder.Forms
{
    partial class DonateForm
    {
        private System.ComponentModel.IContainer components = null;
        private System.Windows.Forms.Panel pnlButtons;
        private System.Windows.Forms.Button btnDonate;
        private System.Windows.Forms.Button btnLater;
        private System.Windows.Forms.Label lblTitle;
        private System.Windows.Forms.Label lblSubtitle;
        private System.Windows.Forms.Label lblMessage;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            System.ComponentModel.ComponentResourceManager resources = new System.ComponentModel.ComponentResourceManager(typeof(DonateForm));
            pnlButtons = new Panel();
            btnDonate = new Button();
            btnLater = new Button();
            lblTitle = new Label();
            lblSubtitle = new Label();
            lblMessage = new Label();
            pnlButtons.SuspendLayout();
            SuspendLayout();
            // 
            // pnlButtons
            // 
            pnlButtons.BackColor = Color.FromArgb(40, 40, 40);
            pnlButtons.Controls.Add(btnDonate);
            pnlButtons.Controls.Add(btnLater);
            pnlButtons.Dock = DockStyle.Bottom;
            pnlButtons.Location = new Point(0, 372);
            pnlButtons.Name = "pnlButtons";
            pnlButtons.Size = new Size(460, 100);
            pnlButtons.TabIndex = 0;
            // 
            // btnDonate
            // 
            btnDonate.BackColor = Color.FromArgb(0, 120, 215);
            btnDonate.Cursor = Cursors.Hand;
            btnDonate.FlatAppearance.BorderSize = 0;
            btnDonate.FlatStyle = FlatStyle.Flat;
            btnDonate.Font = new Font("Segoe UI", 11F, FontStyle.Bold);
            btnDonate.ForeColor = Color.White;
            btnDonate.Location = new Point(140, 12);
            btnDonate.Name = "btnDonate";
            btnDonate.Size = new Size(180, 40);
            btnDonate.TabIndex = 0;
            btnDonate.Text = "💝 Поддержать";
            btnDonate.UseVisualStyleBackColor = false;
            btnDonate.Click += BtnDonate_Click;
            // 
            // btnLater
            // 
            btnLater.BackColor = Color.FromArgb(55, 55, 60);
            btnLater.Cursor = Cursors.Hand;
            btnLater.FlatAppearance.BorderSize = 0;
            btnLater.FlatStyle = FlatStyle.Flat;
            btnLater.Font = new Font("Segoe UI", 9F);
            btnLater.ForeColor = Color.FromArgb(180, 180, 180);
            btnLater.Location = new Point(140, 58);
            btnLater.Name = "btnLater";
            btnLater.Size = new Size(180, 35);
            btnLater.TabIndex = 1;
            btnLater.Text = "Напомнить позже";
            btnLater.UseVisualStyleBackColor = false;
            btnLater.Click += BtnLater_Click;
            // 
            // lblTitle
            // 
            lblTitle.BackColor = Color.Transparent;
            lblTitle.Dock = DockStyle.Top;
            lblTitle.Font = new Font("Segoe UI", 16F, FontStyle.Bold);
            lblTitle.ForeColor = Color.White;
            lblTitle.Location = new Point(0, 0);
            lblTitle.Name = "lblTitle";
            lblTitle.Padding = new Padding(0, 20, 0, 0);
            lblTitle.Size = new Size(460, 60);
            lblTitle.TabIndex = 1;
            lblTitle.Text = "Icon Finder — это бесплатно";
            lblTitle.TextAlign = ContentAlignment.MiddleCenter;
            // 
            // lblSubtitle
            // 
            lblSubtitle.BackColor = Color.Transparent;
            lblSubtitle.Dock = DockStyle.Top;
            lblSubtitle.Font = new Font("Segoe UI", 11F, FontStyle.Italic);
            lblSubtitle.ForeColor = Color.FromArgb(160, 160, 160);
            lblSubtitle.Location = new Point(0, 60);
            lblSubtitle.Name = "lblSubtitle";
            lblSubtitle.Size = new Size(460, 35);
            lblSubtitle.TabIndex = 2;
            lblSubtitle.Text = "Но вы можете сказать «спасибо»";
            lblSubtitle.TextAlign = ContentAlignment.MiddleCenter;
            // 
            // lblMessage
            // 
            lblMessage.BackColor = Color.Transparent;
            lblMessage.Dock = DockStyle.Fill;
            lblMessage.Font = new Font("Segoe UI", 9F);
            lblMessage.ForeColor = Color.FromArgb(200, 200, 200);
            lblMessage.Location = new Point(0, 95);
            lblMessage.Name = "lblMessage";
            lblMessage.Padding = new Padding(25, 10, 25, 10);
            lblMessage.Size = new Size(460, 277);
            lblMessage.TabIndex = 3;
            lblMessage.Text = resources.GetString("lblMessage.Text");
            lblMessage.TextAlign = ContentAlignment.MiddleCenter;
            // 
            // DonateForm
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            BackColor = Color.FromArgb(32, 32, 32);
            ClientSize = new Size(460, 472);
            Controls.Add(lblMessage);
            Controls.Add(lblSubtitle);
            Controls.Add(lblTitle);
            Controls.Add(pnlButtons);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            Name = "DonateForm";
            StartPosition = FormStartPosition.CenterScreen;
            Text = "Поддержать IconFinder";
            TopMost = true;
            pnlButtons.ResumeLayout(false);
            ResumeLayout(false);
        }
    }
}
using System.Drawing;
using System.Windows.Forms;

namespace IconFinder.Controls
{
    partial class IconCard
    {
        private System.ComponentModel.IContainer components = null;
        private Panel cardPanel;
        private PictureBox picIcon;
        private Label lblName;
        private Button btnSave;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
                components.Dispose();
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            cardPanel = new Panel();
            lblExt = new Label();
            picIcon = new PictureBox();
            lblName = new Label();
            btnSave = new Button();
            cardPanel.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)picIcon).BeginInit();
            SuspendLayout();
            // 
            // cardPanel
            // 
            cardPanel.BackColor = Color.FromArgb(45, 45, 48);
            cardPanel.Controls.Add(lblExt);
            cardPanel.Controls.Add(picIcon);
            cardPanel.Controls.Add(lblName);
            cardPanel.Controls.Add(btnSave);
            cardPanel.Cursor = Cursors.Hand;
            cardPanel.Location = new Point(0, 0);
            cardPanel.Name = "cardPanel";
            cardPanel.Size = new Size(160, 140);
            cardPanel.TabIndex = 0;
            cardPanel.Click += cardPanel_Click;
            cardPanel.MouseEnter += cardPanel_MouseEnter;
            cardPanel.MouseLeave += cardPanel_MouseLeave;
            // 
            // lblExt
            // 
            lblExt.BackColor = Color.Transparent;
            lblExt.Font = new Font("Segoe UI", 9F, FontStyle.Bold, GraphicsUnit.Point, 204);
            lblExt.ForeColor = Color.FromArgb(200, 200, 200);
            lblExt.Location = new Point(5, 85);
            lblExt.Name = "lblExt";
            lblExt.Size = new Size(150, 20);
            lblExt.TabIndex = 3;
            lblExt.TextAlign = ContentAlignment.TopCenter;
            lblExt.Click += cardPanel_Click;
            lblExt.MouseEnter += cardPanel_MouseEnter;
            lblExt.MouseLeave += cardPanel_MouseLeave;
            // 
            // picIcon
            // 
            picIcon.BackColor = Color.Transparent;
            picIcon.Location = new Point(56, 12);
            picIcon.Name = "picIcon";
            picIcon.Size = new Size(48, 48);
            picIcon.SizeMode = PictureBoxSizeMode.Zoom;
            picIcon.TabIndex = 0;
            picIcon.TabStop = false;
            picIcon.Click += cardPanel_Click;
            picIcon.MouseEnter += cardPanel_MouseEnter;
            picIcon.MouseLeave += cardPanel_MouseLeave;
            // 
            // lblName
            // 
            lblName.BackColor = Color.Transparent;
            lblName.Font = new Font("Segoe UI", 8F);
            lblName.ForeColor = Color.FromArgb(200, 200, 200);
            lblName.Location = new Point(5, 68);
            lblName.Name = "lblName";
            lblName.Size = new Size(150, 17);
            lblName.TabIndex = 1;
            lblName.TextAlign = ContentAlignment.TopCenter;
            lblName.Click += cardPanel_Click;
            lblName.MouseEnter += cardPanel_MouseEnter;
            lblName.MouseLeave += cardPanel_MouseLeave;
            // 
            // btnSave
            // 
            btnSave.BackColor = Color.FromArgb(55, 55, 60);
            btnSave.Cursor = Cursors.Hand;
            btnSave.FlatAppearance.BorderSize = 0;
            btnSave.FlatStyle = FlatStyle.Flat;
            btnSave.Font = new Font("Segoe UI", 7F);
            btnSave.ForeColor = Color.FromArgb(180, 180, 180);
            btnSave.Location = new Point(40, 108);
            btnSave.Name = "btnSave";
            btnSave.Size = new Size(80, 22);
            btnSave.TabIndex = 2;
            btnSave.Text = "💾 Сохранить";
            btnSave.UseVisualStyleBackColor = false;
            btnSave.Click += btnSave_Click;
            btnSave.MouseEnter += btnSave_MouseEnter;
            btnSave.MouseLeave += btnSave_MouseLeave;
            // 
            // IconCard
            // 
            BackColor = Color.FromArgb(32, 32, 32);
            Controls.Add(cardPanel);
            Margin = new Padding(5);
            Name = "IconCard";
            Size = new Size(160, 140);
            cardPanel.ResumeLayout(false);
            ((System.ComponentModel.ISupportInitialize)picIcon).EndInit();
            ResumeLayout(false);
        }

        private Label lblExt;
    }
}
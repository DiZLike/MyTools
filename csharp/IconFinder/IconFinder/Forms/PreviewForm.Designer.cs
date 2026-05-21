// Файл: Forms/PreviewForm.Designer.cs
using System.Drawing;
using System.Windows.Forms;

namespace IconFinder.Forms
{
    partial class PreviewForm
    {
        private System.ComponentModel.IContainer components = null;
        private PictureBox picPreview;
        private Label lblFileName;
        private Label lblPath;
        private Label lblFormat;
        private Label lblDimensions;
        private Label lblFileSize;
        private Button btnClose;
        private Panel pnlInfo;
        private TableLayoutPanel tlpMain;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
                components.Dispose();
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            tlpMain = new TableLayoutPanel();
            picPreview = new PictureBox();
            pnlInfo = new Panel();
            lblFileSize = new Label();
            lblDimensions = new Label();
            lblFormat = new Label();
            lblPath = new Label();
            lblFileName = new Label();
            btnClose = new Button();
            tlpMain.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)picPreview).BeginInit();
            pnlInfo.SuspendLayout();
            SuspendLayout();
            // 
            // tlpMain
            // 
            tlpMain.ColumnCount = 2;
            tlpMain.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 60F));
            tlpMain.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 40F));
            tlpMain.Controls.Add(picPreview, 0, 0);
            tlpMain.Controls.Add(pnlInfo, 1, 0);
            tlpMain.Controls.Add(btnClose, 1, 1);
            tlpMain.Dock = DockStyle.Fill;
            tlpMain.Location = new Point(0, 0);
            tlpMain.Name = "tlpMain";
            tlpMain.Padding = new Padding(15);
            tlpMain.RowCount = 2;
            tlpMain.RowStyles.Add(new RowStyle(SizeType.Percent, 100F));
            tlpMain.RowStyles.Add(new RowStyle(SizeType.Absolute, 50F));
            tlpMain.Size = new Size(700, 500);
            tlpMain.TabIndex = 0;
            // 
            // picPreview
            // 
            picPreview.BackColor = Color.Transparent;
            picPreview.Dock = DockStyle.Fill;
            picPreview.Location = new Point(18, 18);
            picPreview.Name = "picPreview";
            picPreview.Size = new Size(396, 414);
            picPreview.SizeMode = PictureBoxSizeMode.Zoom;
            picPreview.TabIndex = 0;
            picPreview.TabStop = false;
            // 
            // pnlInfo
            // 
            pnlInfo.BackColor = Color.FromArgb(40, 40, 43);
            pnlInfo.Controls.Add(lblFileSize);
            pnlInfo.Controls.Add(lblDimensions);
            pnlInfo.Controls.Add(lblFormat);
            pnlInfo.Controls.Add(lblPath);
            pnlInfo.Controls.Add(lblFileName);
            pnlInfo.Dock = DockStyle.Fill;
            pnlInfo.Location = new Point(420, 18);
            pnlInfo.Name = "pnlInfo";
            pnlInfo.Padding = new Padding(15);
            pnlInfo.Size = new Size(262, 414);
            pnlInfo.TabIndex = 1;
            // 
            // lblFileSize
            // 
            lblFileSize.Dock = DockStyle.Top;
            lblFileSize.Font = new Font("Segoe UI", 9F);
            lblFileSize.ForeColor = Color.FromArgb(160, 160, 160);
            lblFileSize.Location = new Point(15, 140);
            lblFileSize.Name = "lblFileSize";
            lblFileSize.Size = new Size(232, 25);
            lblFileSize.TabIndex = 4;
            lblFileSize.Text = "Размер файла:";
            lblFileSize.TextAlign = ContentAlignment.MiddleLeft;
            // 
            // lblDimensions
            // 
            lblDimensions.Dock = DockStyle.Top;
            lblDimensions.Font = new Font("Segoe UI", 9F);
            lblDimensions.ForeColor = Color.FromArgb(160, 160, 160);
            lblDimensions.Location = new Point(15, 115);
            lblDimensions.Name = "lblDimensions";
            lblDimensions.Size = new Size(232, 25);
            lblDimensions.TabIndex = 3;
            lblDimensions.Text = "Размеры:";
            lblDimensions.TextAlign = ContentAlignment.MiddleLeft;
            // 
            // lblFormat
            // 
            lblFormat.Dock = DockStyle.Top;
            lblFormat.Font = new Font("Segoe UI", 9F, FontStyle.Bold);
            lblFormat.ForeColor = Color.FromArgb(100, 180, 255);
            lblFormat.Location = new Point(15, 90);
            lblFormat.Name = "lblFormat";
            lblFormat.Size = new Size(232, 25);
            lblFormat.TabIndex = 2;
            lblFormat.Text = "Формат:";
            lblFormat.TextAlign = ContentAlignment.MiddleLeft;
            // 
            // lblPath
            // 
            lblPath.Dock = DockStyle.Top;
            lblPath.Font = new Font("Segoe UI", 8F);
            lblPath.ForeColor = Color.FromArgb(120, 120, 120);
            lblPath.Location = new Point(15, 45);
            lblPath.Name = "lblPath";
            lblPath.Size = new Size(232, 45);
            lblPath.TabIndex = 1;
            lblPath.Text = "Путь:";
            // 
            // lblFileName
            // 
            lblFileName.Dock = DockStyle.Top;
            lblFileName.Font = new Font("Segoe UI", 11F, FontStyle.Bold);
            lblFileName.ForeColor = Color.FromArgb(240, 240, 240);
            lblFileName.Location = new Point(15, 15);
            lblFileName.Name = "lblFileName";
            lblFileName.Size = new Size(232, 30);
            lblFileName.TabIndex = 0;
            lblFileName.Text = "Имя файла";
            lblFileName.TextAlign = ContentAlignment.MiddleLeft;
            // 
            // btnClose
            // 
            btnClose.Anchor = AnchorStyles.Right;
            btnClose.BackColor = Color.FromArgb(55, 55, 60);
            btnClose.Cursor = Cursors.Hand;
            btnClose.FlatAppearance.BorderSize = 0;
            btnClose.FlatStyle = FlatStyle.Flat;
            btnClose.Font = new Font("Segoe UI", 9F);
            btnClose.ForeColor = Color.FromArgb(200, 200, 200);
            btnClose.Location = new Point(593, 445);
            btnClose.Name = "btnClose";
            btnClose.Size = new Size(89, 30);
            btnClose.TabIndex = 2;
            btnClose.Text = "Закрыть";
            btnClose.UseVisualStyleBackColor = false;
            btnClose.Click += btnClose_Click;
            // 
            // PreviewForm
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            BackColor = Color.FromArgb(32, 32, 32);
            ClientSize = new Size(700, 500);
            Controls.Add(tlpMain);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            Name = "PreviewForm";
            StartPosition = FormStartPosition.CenterParent;
            Text = "Предпросмотр иконки";
            tlpMain.ResumeLayout(false);
            ((System.ComponentModel.ISupportInitialize)picPreview).EndInit();
            pnlInfo.ResumeLayout(false);
            ResumeLayout(false);
        }
    }
}
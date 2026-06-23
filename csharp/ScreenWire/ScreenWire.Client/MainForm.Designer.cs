namespace ScreenWire.Client
{
    partial class MainForm
    {
        private System.ComponentModel.IContainer components = null;
        private System.Windows.Forms.MenuStrip menuStrip;
        private System.Windows.Forms.ToolStripMenuItem menuConnection;
        private System.Windows.Forms.ToolStripMenuItem menuConnect;
        private System.Windows.Forms.ToolStripMenuItem menuDisconnect;
        private System.Windows.Forms.ToolStripMenuItem menuView;
        private System.Windows.Forms.ToolStripMenuItem menuScaleToFit;
        private System.Windows.Forms.ToolStripMenuItem menuFullScreen;
        private System.Windows.Forms.ToolStripMenuItem menuSettings;
        private System.Windows.Forms.PictureBox pictureBox;
        private System.Windows.Forms.StatusStrip statusStrip;
        private System.Windows.Forms.ToolStripStatusLabel lblStatus;
        private System.Windows.Forms.ToolStripStatusLabel lblFps;
        private System.Windows.Forms.ToolStripStatusLabel lblResolution;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
                components.Dispose();
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            System.ComponentModel.ComponentResourceManager resources = new System.ComponentModel.ComponentResourceManager(typeof(MainForm));
            menuStrip = new MenuStrip();
            menuConnection = new ToolStripMenuItem();
            menuConnect = new ToolStripMenuItem();
            menuDisconnect = new ToolStripMenuItem();
            menuView = new ToolStripMenuItem();
            menuScaleToFit = new ToolStripMenuItem();
            menuFullScreen = new ToolStripMenuItem();
            menuSettings = new ToolStripMenuItem();
            настройкиToolStripMenuItem = new ToolStripMenuItem();
            обновитьСерверToolStripMenuItem = new ToolStripMenuItem();
            pictureBox = new PictureBox();
            statusStrip = new StatusStrip();
            lblStatus = new ToolStripStatusLabel();
            lblFps = new ToolStripStatusLabel();
            lblResolution = new ToolStripStatusLabel();
            toolStrip1 = new ToolStrip();
            menuStrip.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)pictureBox).BeginInit();
            statusStrip.SuspendLayout();
            SuspendLayout();
            // 
            // menuStrip
            // 
            menuStrip.Items.AddRange(new ToolStripItem[] { menuConnection, menuView, menuSettings });
            menuStrip.Location = new Point(0, 0);
            menuStrip.Name = "menuStrip";
            menuStrip.Size = new Size(800, 24);
            menuStrip.TabIndex = 2;
            // 
            // menuConnection
            // 
            menuConnection.DropDownItems.AddRange(new ToolStripItem[] { menuConnect, menuDisconnect });
            menuConnection.Name = "menuConnection";
            menuConnection.Size = new Size(97, 20);
            menuConnection.Text = "Подключение";
            // 
            // menuConnect
            // 
            menuConnect.Name = "menuConnect";
            menuConnect.Size = new Size(165, 22);
            menuConnect.Text = "Подключиться...";
            menuConnect.Click += MenuConnect_Click;
            // 
            // menuDisconnect
            // 
            menuDisconnect.Enabled = false;
            menuDisconnect.Name = "menuDisconnect";
            menuDisconnect.Size = new Size(165, 22);
            menuDisconnect.Text = "Отключиться";
            menuDisconnect.Click += MenuDisconnect_Click;
            // 
            // menuView
            // 
            menuView.DropDownItems.AddRange(new ToolStripItem[] { menuScaleToFit, menuFullScreen });
            menuView.Name = "menuView";
            menuView.Size = new Size(39, 20);
            menuView.Text = "Вид";
            // 
            // menuScaleToFit
            // 
            menuScaleToFit.Checked = true;
            menuScaleToFit.CheckOnClick = true;
            menuScaleToFit.CheckState = CheckState.Checked;
            menuScaleToFit.Name = "menuScaleToFit";
            menuScaleToFit.Size = new Size(170, 22);
            menuScaleToFit.Text = "Масштабировать";
            menuScaleToFit.Click += MenuScale_Click;
            // 
            // menuFullScreen
            // 
            menuFullScreen.Name = "menuFullScreen";
            menuFullScreen.Size = new Size(170, 22);
            menuFullScreen.Text = "Полный экран";
            menuFullScreen.Click += MenuFull_Click;
            // 
            // menuSettings
            // 
            menuSettings.DropDownItems.AddRange(new ToolStripItem[] { настройкиToolStripMenuItem, обновитьСерверToolStripMenuItem });
            menuSettings.Name = "menuSettings";
            menuSettings.Size = new Size(85, 20);
            menuSettings.Text = "Управление";
            // 
            // настройкиToolStripMenuItem
            // 
            настройкиToolStripMenuItem.Name = "настройкиToolStripMenuItem";
            настройкиToolStripMenuItem.Size = new Size(169, 22);
            настройкиToolStripMenuItem.Text = "Настройки";
            настройкиToolStripMenuItem.Click += MenuSettings_Click;
            // 
            // обновитьСерверToolStripMenuItem
            // 
            обновитьСерверToolStripMenuItem.Name = "обновитьСерверToolStripMenuItem";
            обновитьСерверToolStripMenuItem.Size = new Size(169, 22);
            обновитьСерверToolStripMenuItem.Text = "Обновить сервер";
            обновитьСерверToolStripMenuItem.Click += MenuUpdateServer_Click;
            // 
            // pictureBox
            // 
            pictureBox.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            pictureBox.BackColor = Color.Black;
            pictureBox.Location = new Point(0, 52);
            pictureBox.Name = "pictureBox";
            pictureBox.Size = new Size(800, 526);
            pictureBox.SizeMode = PictureBoxSizeMode.Zoom;
            pictureBox.TabIndex = 0;
            pictureBox.TabStop = false;
            pictureBox.KeyUp += PicKeyUp;
            pictureBox.KeyDown += PicKeyDown;
            pictureBox.MouseDown += PicMouseDown;
            pictureBox.MouseMove += PicMouseMove;
            pictureBox.MouseUp += PicMouseUp;
            pictureBox.MouseWheel += PicMouseWheel;
            // 
            // statusStrip
            // 
            statusStrip.Items.AddRange(new ToolStripItem[] { lblStatus, lblFps, lblResolution });
            statusStrip.Location = new Point(0, 578);
            statusStrip.Name = "statusStrip";
            statusStrip.Size = new Size(800, 22);
            statusStrip.TabIndex = 1;
            // 
            // lblStatus
            // 
            lblStatus.Name = "lblStatus";
            lblStatus.Size = new Size(95, 17);
            lblStatus.Text = "Не подключено";
            // 
            // lblFps
            // 
            lblFps.Name = "lblFps";
            lblFps.Size = new Size(35, 17);
            lblFps.Text = "0 FPS";
            // 
            // lblResolution
            // 
            lblResolution.Name = "lblResolution";
            lblResolution.Size = new Size(0, 17);
            // 
            // toolStrip1
            // 
            toolStrip1.Location = new Point(0, 24);
            toolStrip1.Name = "toolStrip1";
            toolStrip1.Size = new Size(800, 25);
            toolStrip1.TabIndex = 3;
            toolStrip1.Text = "toolStrip1";
            // 
            // MainForm
            // 
            ClientSize = new Size(800, 600);
            Controls.Add(toolStrip1);
            Controls.Add(pictureBox);
            Controls.Add(statusStrip);
            Controls.Add(menuStrip);
            Icon = (Icon)resources.GetObject("$this.Icon");
            MainMenuStrip = menuStrip;
            MinimumSize = new Size(320, 240);
            Name = "MainForm";
            StartPosition = FormStartPosition.CenterScreen;
            Text = "ScreenWire Client";
            FormClosing += MainForm_FormClosing;
            menuStrip.ResumeLayout(false);
            menuStrip.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)pictureBox).EndInit();
            statusStrip.ResumeLayout(false);
            statusStrip.PerformLayout();
            ResumeLayout(false);
            PerformLayout();
        }

        private ToolStripMenuItem настройкиToolStripMenuItem;
        private ToolStripMenuItem обновитьСерверToolStripMenuItem;
        private ToolStrip toolStrip1;
    }
}
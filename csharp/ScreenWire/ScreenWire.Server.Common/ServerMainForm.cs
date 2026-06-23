using ScreenWire.Server.Config;
using ScreenWire.Server.Network;
using System;
using System.Drawing;
using System.Reflection;
using System.Windows.Forms;

namespace ScreenWire.Server
{
    public partial class ServerMainForm : Form
    {
        private ServerConfig _config;
        private UdpServer _server;

        public ServerMainForm()
        {
            InitializeComponent();

            Version version = Assembly.GetExecutingAssembly().GetName().Version;
            string versionText = version.Major + "." + version.Minor + "." + version.Build;
            this.Text = "ScreenWire Server v" + versionText;

            _config = new ServerConfig();
            _config.Load();
            LoadSettingsToUI();

            StartServer();
            if (_config.StartMinimized) { WindowState = FormWindowState.Minimized; ShowInTaskbar = false; }
        }

        private void LoadSettingsToUI()
        {
            numPort.Value = _config.Port;
            txtPassword.Text = "";
            chkStartMinimized.Checked = _config.StartMinimized;
        }

        private void BtnSave_Click(object sender, EventArgs e)
        {
            _config.Port = (int)numPort.Value;
            _config.StartMinimized = chkStartMinimized.Checked;

            if (!string.IsNullOrEmpty(txtPassword.Text))
                _config.PasswordHash = Auth.Authenticator.ComputeStoredHash(txtPassword.Text);

            _config.Save();
            txtPassword.Clear();
            MessageBox.Show("Настройки сохранены.", "ScreenWire", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        private void StartServer()
        {
            if (_server != null) return;
            _server = new UdpServer(_config);
            _server.StatusChanged += (s, e) =>
            {
                if (InvokeRequired) { Invoke((Action)(() => OnStatusChanged(e.Status))); return; }
                OnStatusChanged(e.Status);
            };
            _server.Start();
        }

        private void OnStatusChanged(string status)
        {
            if (status == null) return;
            lblStatus.Text = status;
            lblStatus.ForeColor = status.Contains("Ошибка") ? Color.Red : Color.Green;
            string trayText = "ScreenWire - " + status;
            trayIcon.Text = trayText.Length > 63 ? trayText.Substring(0, 60) + "..." : trayText;
        }

        private void ShowSettings() { Show(); WindowState = FormWindowState.Normal; ShowInTaskbar = true; Activate(); }
        private void TrayIcon_DoubleClick(object sender, EventArgs e) => ShowSettings();
        private void MenuSettings_Click(object sender, EventArgs e) => ShowSettings();

        private void MenuExit_Click(object sender, EventArgs e)
        {
            trayIcon.Visible = false;
            _server?.Stop();
            Application.Exit();
        }

        private void ServerMainForm_FormClosing(object sender, FormClosingEventArgs e)
        {
            if (e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Hide(); ShowInTaskbar = false; }
        }

        private void ServerMainForm_Resize(object sender, EventArgs e)
        {
            if (WindowState == FormWindowState.Minimized) { Hide(); ShowInTaskbar = false; }
        }
    }
}
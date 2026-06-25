using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using ScreenWire.Client.Config;
using ScreenWire.Client.Network;
using ScreenWire.Client.UI;
using Timer = System.Windows.Forms.Timer;

namespace ScreenWire.Client;

public partial class MainForm : Form
{
    private UdpClient _client;
    private readonly ClientConfig _config = new();
    private readonly Timer _statsTimer = new();
    private int _serverW, _serverH;
    private int _frameCount;
    private DateTime _fpsTime;
    private FormBorderStyle _savedBorder;
    private bool _isFull;
    private byte _mouseFlags;
    private string _lastClip = "";
    private readonly Timer _clipTimer = new() { Interval = 500 };
    private MemoryStream _currentImageStream;

    public MainForm()
    {
        InitializeComponent();

        typeof(PictureBox).InvokeMember("DoubleBuffered",
            System.Reflection.BindingFlags.SetProperty |
            System.Reflection.BindingFlags.Instance |
            System.Reflection.BindingFlags.NonPublic,
            null, pictureBox, new object[] { true });

        _config.Load();

        _statsTimer.Tick += StatsTick;
        _clipTimer.Tick += ClipTick;

        menuScaleToFit.Checked = _config.ScaleToFit;
        ApplyScale();

        pictureBox.TabStop = true;
        KeyPreview = true;
        Icon = SystemIcons.Application;
    }

    private async void MenuConnect_Click(object sender, EventArgs e)
    {
        string pw;
        using (var f = new ConnectForm())
        {
            f.SetDefaults(_config.ServerAddress, _config.Port, _config.Password);
            if (f.ShowDialog(this) != DialogResult.OK) return;
            _config.ServerAddress = f.ServerAddress; _config.Port = f.Port;
            pw = f.Password; _config.Password = f.SavePassword ? pw : "";
            _config.Save();
        }
        await ConnectAsync(pw);
    }

    private async Task ConnectAsync(string password)
    {
        menuConnect.Enabled = false; lblStatus.Text = "Подключение...";
        _client?.Dispose(); _client = new UdpClient();
        _client.ScreenshotReceived += OnScreenshotReceived;
        _client.ScreenInfoReceived += OnScreenInfoReceived;
        _client.DisplayInfoReceived += OnDisplayInfoReceived;
        _client.ClipboardTextReceived += OnClipboardTextReceived;
        _client.ConnectionError += OnConnectionError;
        _client.StatusChanged += OnStatusChanged;
        _client.ConnectedChanged += OnConnectedChanged;
        if (!await _client.ConnectAsync(_config.ServerAddress, _config.Port, password))
        { menuConnect.Enabled = true; lblStatus.Text = "Не подключено"; }
    }

    private void OnScreenshotReceived(object sender, byte[] jpeg)
    {
        if (jpeg == null || jpeg.Length == 0) return;
        try
        {
            var newStream = new MemoryStream(jpeg);
            var oldStream = _currentImageStream;
            var oldImage = pictureBox.Image;
            pictureBox.ImageLocation = null;
            using (var ms = new MemoryStream(jpeg))
            {
                pictureBox.Image = Image.FromStream(ms);
            }
            _currentImageStream = newStream;
            oldImage?.Dispose(); oldStream?.Dispose();
            _frameCount++;
        }
        catch { }
    }

    private void OnScreenInfoReceived(object? sender, (int Width, int Height) info)
    {
        _serverW = info.Width; _serverH = info.Height;
        lblResolution.Text = $"{info.Width}x{info.Height}";
        if (!menuScaleToFit.Checked && !_isFull)
        {
            ClientSize = new Size(
                Math.Min(info.Width, Screen.PrimaryScreen!.WorkingArea.Width - 50),
                Math.Min(info.Height, Screen.PrimaryScreen!.WorkingArea.Height - 100));
        }
    }

    private void OnDisplayInfoReceived(object sender, byte[] data)
    {
        if (InvokeRequired) { Invoke(() => OnDisplayInfoReceived(sender, data)); return; }

        toolStrip1.Items.Clear();
        int count = data[0];

        for (int i = 0; i < count; i++)
        {
            int x = BitConverter.ToUInt16(data, 1 + i * 8);
            int y = BitConverter.ToUInt16(data, 1 + i * 8 + 2);
            int w = BitConverter.ToUInt16(data, 1 + i * 8 + 4);
            int h = BitConverter.ToUInt16(data, 1 + i * 8 + 6);
            string position = x == 0 ? "левый" : "правый";

            ToolStripButton mon = new ToolStripButton();
            mon.Click += Mon_Click;
            mon.Text = $"Монитор {i + 1}";
            mon.Tag = i;
            toolStrip1.Items.Add( mon );
        }
        ToolStripButton mon_all = new ToolStripButton();
        mon_all.Click += Mon_Click;
        mon_all.Text = "Все мониторы";
        mon_all.Tag = count;
        toolStrip1.Items.Add(mon_all);
    }

    private void Mon_Click(object sender, EventArgs e)
    {
        int idx = int.Parse((sender as ToolStripButton).Tag.ToString());
        SetDisplay(idx);
    }

    private void SetDisplay(int idx)
    {
        if (_client == null || !_client.Connected || idx < 0) return;
        _client.SendDisplaySelect(idx);
    }

    private void OnClipboardTextReceived(object? sender, string text)
    { if (!string.IsNullOrEmpty(text)) { _lastClip = text; try { Clipboard.SetText(text); } catch { } } }

    private void OnConnectionError(object sender, string error)
    { MessageBox.Show(error, "ScreenWire", MessageBoxButtons.OK, MessageBoxIcon.Error); }

    private void OnStatusChanged(object? sender, string status) => lblStatus.Text = status;

    private void OnConnectedChanged(object? sender, bool connected)
    { if (InvokeRequired) Invoke(() => OnConnected(connected)); else OnConnected(connected); }

    private void OnConnected(bool connected)
    {
        if (connected)
        {
            menuConnect.Enabled = false; menuDisconnect.Enabled = true;
            _frameCount = 0; _fpsTime = DateTime.Now;
            _clipTimer.Start(); _lastClip = Clipboard.GetText() ?? "";
            _client?.SendQuality(_config.JpegQuality);
            _client?.SendFpsRequest(_config.FrameRate);
            _client?.SendReductionRatio(_config.ReductionRatio);
            _statsTimer.Interval = 1000; _statsTimer.Start();
        }
        else Disconnect();
    }

    private void StatsTick(object? sender, EventArgs e)
    {
        double elapsed = (DateTime.Now - _fpsTime).TotalSeconds;
        if (elapsed >= 1.0) { lblFps.Text = $"{(int)(_frameCount / elapsed)} FPS"; _frameCount = 0; _fpsTime = DateTime.Now; }
    }

    private void ClipTick(object? sender, EventArgs e)
    {
        if (_client == null || !_client.Connected) return;
        try { if (Clipboard.ContainsText()) { string? text = Clipboard.GetText(); if (text != null && text != _lastClip) { _lastClip = text; _client.SendClipboardText(text); } } } catch { }
    }

    private void MenuDisconnect_Click(object? sender, EventArgs e) => Disconnect();

    private void Disconnect()
    {
        _statsTimer.Stop(); _clipTimer.Stop();
        _client?.Dispose(); _client = null;
        var oldImage = pictureBox.Image; var oldStream = _currentImageStream;
        pictureBox.Image = null; _currentImageStream = null;
        oldImage?.Dispose(); oldStream?.Dispose();
        menuConnect.Enabled = true; menuDisconnect.Enabled = false;
        lblStatus.Text = "Отключено"; lblFps.Text = "0 FPS"; lblResolution.Text = "";
    }

    // ---------- Мышь и клавиатура ----------

    private void PicMouseDown(object? sender, MouseEventArgs e)
    {
        pictureBox.Focus(); _mouseFlags = 0;
        if (e.Button == MouseButtons.Left) _mouseFlags |= Protocol.UdpProtocol.MouseLeftDown;
        else if (e.Button == MouseButtons.Right) _mouseFlags |= Protocol.UdpProtocol.MouseRightDown;
        else if (e.Button == MouseButtons.Middle) _mouseFlags |= Protocol.UdpProtocol.MouseMiddleDown;
        SendMouse(e.X, e.Y);
    }

    private void PicMouseUp(object? sender, MouseEventArgs e) { _mouseFlags = 0; SendMouse(e.X, e.Y); }

    private void PicMouseMove(object? sender, MouseEventArgs e)
    { byte sf = _mouseFlags; _mouseFlags = (byte)(sf | Protocol.UdpProtocol.MouseMove); SendMouse(e.X, e.Y); _mouseFlags = sf; }

    private void PicMouseWheel(object? sender, MouseEventArgs e)
    { byte sf = _mouseFlags; _mouseFlags = (byte)(sf | Protocol.UdpProtocol.MouseWheel); SendMouse(e.X, e.Y, (short)e.Delta); _mouseFlags = sf; }

    private void SendMouse(int controlX, int controlY, short wheel = 0)
    {
        if (_client == null || !_client.Connected || pictureBox.Image == null) return;
        short serverX, serverY;
        if (pictureBox.SizeMode == PictureBoxSizeMode.Zoom)
        {
            int imgW = pictureBox.Image.Width, imgH = pictureBox.Image.Height;
            int boxW = pictureBox.ClientSize.Width, boxH = pictureBox.ClientSize.Height;
            double scale = Math.Min((double)boxW / imgW, (double)boxH / imgH);
            int displayedW = (int)(imgW * scale), displayedH = (int)(imgH * scale);
            int offsetX = (boxW - displayedW) / 2, offsetY = (boxH - displayedH) / 2;
            double picX = controlX - offsetX, picY = controlY - offsetY;
            if (picX < 0 || picY < 0 || picX >= displayedW || picY >= displayedH) return;
            serverX = (short)(picX / scale); serverY = (short)(picY / scale);
        }
        else if (pictureBox.SizeMode == PictureBoxSizeMode.StretchImage)
        {
            int imgW = pictureBox.Image.Width, imgH = pictureBox.Image.Height;
            int boxW = pictureBox.ClientSize.Width, boxH = pictureBox.ClientSize.Height;
            if (boxW == 0 || boxH == 0) return;
            serverX = (short)((long)controlX * imgW / boxW); serverY = (short)((long)controlY * imgH / boxH);
        }
        else
        {
            int imgW = pictureBox.Image.Width, imgH = pictureBox.Image.Height;
            int boxW = pictureBox.ClientSize.Width, boxH = pictureBox.ClientSize.Height;
            int offsetX = 0, offsetY = 0;
            if (pictureBox.SizeMode == PictureBoxSizeMode.CenterImage)
            { offsetX = Math.Max(0, (boxW - imgW) / 2); offsetY = Math.Max(0, (boxH - imgH) / 2); }
            int picX = controlX - offsetX, picY = controlY - offsetY;
            if (picX < 0 || picY < 0 || picX >= imgW || picY >= imgH) return;
            serverX = (short)picX; serverY = (short)picY;
        }
        _client.SendMouseEvent(_mouseFlags, serverX, serverY, wheel);
    }

    private void PicKeyDown(object? sender, KeyEventArgs e)
    {
        if (_client == null || !_client.Connected) return;
        if (e.Control) _client.SendKeyboardEvent(Protocol.UdpProtocol.KeyDown, (byte)Keys.ControlKey);
        if (e.Alt) _client.SendKeyboardEvent(Protocol.UdpProtocol.KeyDown, (byte)Keys.Menu);
        if (e.Shift) _client.SendKeyboardEvent(Protocol.UdpProtocol.KeyDown, (byte)Keys.ShiftKey);
        if (e.KeyCode == Keys.F11 || e.KeyCode == Keys.F10 || e.KeyCode == Keys.Escape) return;
        _client.SendKeyboardEvent(Protocol.UdpProtocol.KeyDown, (byte)e.KeyValue);
        e.Handled = true; e.SuppressKeyPress = true;
    }

    private void PicKeyUp(object? sender, KeyEventArgs e)
    {
        if (_client == null || !_client.Connected) return;
        if (e.Control) _client.SendKeyboardEvent(0, (byte)Keys.ControlKey);
        if (e.Alt) _client.SendKeyboardEvent(0, (byte)Keys.Menu);
        if (e.Shift) _client.SendKeyboardEvent(0, (byte)Keys.ShiftKey);
        _client.SendKeyboardEvent(0, (byte)e.KeyValue);
        e.Handled = true; e.SuppressKeyPress = true;
    }

    // ---------- Меню ----------

    private void MenuScale_Click(object? sender, EventArgs e)
    { _config.ScaleToFit = menuScaleToFit.Checked; _config.Save(); ApplyScale(); }

    private void ApplyScale()
    {
        pictureBox.SizeMode = menuScaleToFit.Checked ? PictureBoxSizeMode.Zoom : PictureBoxSizeMode.Normal;
        if (!menuScaleToFit.Checked && _serverW > 0 && !_isFull)
            ClientSize = new Size(Math.Min(_serverW, Screen.PrimaryScreen!.WorkingArea.Width - 50),
                                  Math.Min(_serverH, Screen.PrimaryScreen!.WorkingArea.Height - 100));
    }

    private void MenuFull_Click(object? sender, EventArgs e) => ToggleFull();

    private void ToggleFull()
    {
        if (!_isFull) { _savedBorder = FormBorderStyle; FormBorderStyle = FormBorderStyle.None; WindowState = FormWindowState.Maximized; menuStrip.Visible = false; statusStrip.Visible = false; _isFull = true; }
        else { FormBorderStyle = _savedBorder; WindowState = FormWindowState.Normal; menuStrip.Visible = true; statusStrip.Visible = true; _isFull = false; }
    }

    private void MenuSettings_Click(object? sender, EventArgs e)
    {
        using var f = new SettingsForm();
        f.SetDefaults(_config.FrameRate, _config.JpegQuality, _config.ScaleToFit, _config.ReductionRatio);
        if (f.ShowDialog(this) != DialogResult.OK) return;
        _config.FrameRate = f.FrameRate;
        _config.JpegQuality = f.JpegQuality;
        _config.ReductionRatio = f.ReductionRatio;
        _config.ScaleToFit = f.ScaleToFit;
        _config.Save();
        menuScaleToFit.Checked = _config.ScaleToFit;
        ApplyScale();
        _client?.SendFpsRequest(_config.FrameRate);
        _client?.SendQuality(_config.JpegQuality);
        _client?.SendReductionRatio(_config.ReductionRatio);
    }

    private async void MenuUpdateServer_Click(object? sender, EventArgs e)
    {
        if (_client == null || !_client.Connected) { MessageBox.Show("Сначала подключитесь к серверу.", "ScreenWire", MessageBoxButtons.OK, MessageBoxIcon.Information); return; }
        using var dialog = new OpenFileDialog { Title = "Выберите ZIP-архив с обновлением сервера", Filter = "ZIP архивы (*.zip)|*.zip|Все файлы (*.*)|*.*", DefaultExt = "zip" };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        menuStrip.Enabled = false;
        try
        {
            bool success = await _client.SendUpdateAsync(dialog.FileName, msg => { if (InvokeRequired) Invoke(() => lblStatus.Text = msg); else lblStatus.Text = msg; });
            MessageBox.Show(success ? "Обновление успешно отправлено на сервер.\n\nСервер автоматически перезапустится с новой версией.\nТекущее подключение будет разорвано." : "Не удалось отправить обновление на сервер.\nПроверьте статус в строке состояния.", "ScreenWire", MessageBoxButtons.OK, success ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
        }
        catch (Exception ex) { MessageBox.Show("Ошибка при отправке обновления: " + ex.Message, "ScreenWire", MessageBoxButtons.OK, MessageBoxIcon.Error); }
        finally { menuStrip.Enabled = true; }
    }

    private void MainForm_FormClosing(object? sender, FormClosingEventArgs e) { Disconnect(); _config.Save(); }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (keyData == Keys.F11) { ToggleFull(); return true; }
        if (keyData == Keys.Escape && _isFull) { ToggleFull(); return true; }
        return base.ProcessCmdKey(ref msg, keyData);
    }
}
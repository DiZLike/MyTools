using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using IconFinder.Services;
using SkiaSharp;
using IconConverter = IconFinder.Services.IconConverter;

namespace IconFinder.Controls
{
    public partial class IconCard : UserControl
    {
        private readonly IconInfo _iconInfo;
        private readonly IconService _iconService;
        private ContextMenuStrip _formatPopup;

        public event EventHandler<IconInfo> IconClicked;

        public IconCard(IconInfo iconInfo, IconService iconService)
        {
            InitializeComponent();
            _iconInfo = iconInfo;
            _iconService = iconService;
            LoadIconInfo();
            CreateFormatPopup();
        }

        private void CreateFormatPopup()
        {
            _formatPopup = new ContextMenuStrip
            {
                BackColor = Color.FromArgb(45, 45, 48),
                ShowImageMargin = false,
                ShowCheckMargin = false,
                Renderer = new DarkToolStripRenderer()
            };

            foreach (var fmt in new[] { "PNG", "ICO", "WebP" })
            {
                var item = new ToolStripMenuItem
                {
                    Text = fmt,
                    ForeColor = Color.FromArgb(200, 200, 200),
                    Font = new Font("Segoe UI", 8),
                    BackColor = Color.FromArgb(45, 45, 48),
                    Padding = new Padding(8, 4, 8, 4)
                };
                item.MouseEnter += (s, e) => item.BackColor = Color.FromArgb(60, 60, 65);
                item.MouseLeave += (s, e) => item.BackColor = Color.FromArgb(45, 45, 48);
                item.Click += (s, e) => ConvertAndSave(fmt);
                _formatPopup.Items.Add(item);
            }
        }

        private void LoadIconInfo()
        {
            var fileName = Path.GetFileName(_iconInfo.FilePath);
            lblName.Text = fileName.Length > 28 ? fileName.Substring(0, 25) + "..." : fileName;
        }

        public void LoadThumbnail()
        {
            if (picIcon.Image != null) return;
            try
            {
                var data = _iconService.GetIconData(_iconInfo.FilePath);
                if (data == null) return;

                var ext = Path.GetExtension(_iconInfo.FilePath).ToLower();

                if (ext == ".webp")
                {
                    using var skBitmap = SKBitmap.Decode(data);
                    if (skBitmap == null) return;
                    var scale = Math.Min(64f / skBitmap.Width, 64f / skBitmap.Height);
                    var w = Math.Max(1, (int)(skBitmap.Width * scale));
                    var h = Math.Max(1, (int)(skBitmap.Height * scale));
                    using var resized = skBitmap.Resize(new SKImageInfo(w, h), new SKSamplingOptions(SKFilterMode.Linear, SKMipmapMode.Linear));
                    if (resized == null) return;
                    using var image = SKImage.FromBitmap(resized);
                    using var pngData = image.Encode(SKEncodedImageFormat.Png, 80);
                    using var ms = new MemoryStream(pngData.ToArray());
                    picIcon.Image = new Bitmap(ms);
                }
                else
                {
                    using var ms = new MemoryStream(data);
                    using var original = new Bitmap(ms);
                    var scale = Math.Min(64f / original.Width, 64f / original.Height);
                    picIcon.Image = new Bitmap(original, (int)(original.Width * scale), (int)(original.Height * scale));
                }
            }
            catch (Exception ex) { Logger.Log($"Thumbnail error: {_iconInfo.FilePath} - {ex.Message}"); }
        }

        private void cardPanel_Click(object sender, EventArgs e) => IconClicked?.Invoke(this, _iconInfo);
        private void cardPanel_MouseEnter(object sender, EventArgs e) => cardPanel.BackColor = Color.FromArgb(60, 60, 65);
        private void cardPanel_MouseLeave(object sender, EventArgs e) => cardPanel.BackColor = Color.FromArgb(45, 45, 48);
        private void btnSave_Click(object sender, EventArgs e) => _formatPopup.Show(btnSave.PointToScreen(new Point(0, btnSave.Height)), ToolStripDropDownDirection.BelowRight);
        private void btnSave_MouseEnter(object sender, EventArgs e) => btnSave.BackColor = Color.FromArgb(70, 70, 75);
        private void btnSave_MouseLeave(object sender, EventArgs e) => btnSave.BackColor = Color.FromArgb(55, 55, 60);

        private async void ConvertAndSave(string format)
        {
            try
            {
                _formatPopup.Close();
                var ext = $".{format.ToLower()}";
                var fileName = Path.GetFileNameWithoutExtension(_iconInfo.FilePath) + ext;

                using var sfd = new SaveFileDialog { FileName = fileName, Filter = $"{format} Files|*{ext}", Title = $"Сохранить как {format}..." };
                if (sfd.ShowDialog() == DialogResult.OK)
                {
                    var sourceData = _iconService.GetIconData(_iconInfo.FilePath);
                    if (sourceData == null) return;
                    var convertedData = await System.Threading.Tasks.Task.Run(() => IconConverter.ConvertTo(sourceData, ext));
                    if (convertedData != null)
                    {
                        File.WriteAllBytes(sfd.FileName, convertedData);
                        Logger.Log($"Saved: {sfd.FileName} ({convertedData.Length} bytes)");
                    }
                }
            }
            catch (Exception ex) { Logger.Log($"Convert error: {ex.Message}"); }
        }

        private static string FormatSize(int bytes) => bytes switch
        {
            < 1024 => $"{bytes} B",
            < 1024 * 1024 => $"{bytes / 1024.0:F1} KB",
            _ => $"{bytes / (1024.0 * 1024):F1} MB"
        };
    }
}
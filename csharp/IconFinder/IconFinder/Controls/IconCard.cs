using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using IconFinder.Monitors;
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
        private bool _isDragging = false;

        public event EventHandler<IconInfo> IconClicked;

        public IconCard(IconInfo iconInfo, IconService iconService)
        {
            InitializeComponent();
            _iconInfo = iconInfo;
            _iconService = iconService;

            // Drag & Drop
            picIcon.MouseDown += PicIcon_MouseDown;
            picIcon.MouseMove += PicIcon_MouseMove;

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

            var ext = Path.GetExtension(_iconInfo.FilePath).ToLower();

            if (ext == ".svg")
            {
                var svgItem = new ToolStripMenuItem
                {
                    Text = "SVG (оригинал)",
                    ForeColor = Color.FromArgb(180, 220, 180),
                    Font = new Font("Segoe UI", 8, FontStyle.Bold),
                    BackColor = Color.FromArgb(45, 45, 48),
                    Padding = new Padding(8, 4, 8, 4)
                };
                svgItem.MouseEnter += (s, e) => svgItem.BackColor = Color.FromArgb(60, 60, 65);
                svgItem.MouseLeave += (s, e) => svgItem.BackColor = Color.FromArgb(45, 45, 48);
                svgItem.Click += (s, e) => SaveOriginal();
                _formatPopup.Items.Add(svgItem);
                _formatPopup.Items.Add(new ToolStripSeparator());
            }

            // Создаем пункты меню с подменю для каждого формата
            foreach (var fmt in new[] { "PNG", "ICO", "WebP" })
            {
                var formatItem = CreateFormatMenuItem(fmt);
                _formatPopup.Items.Add(formatItem);
            }
        }
        private ToolStripMenuItem CreateFormatMenuItem(string format)
        {
            var formatItem = new ToolStripMenuItem
            {
                Text = format,
                ForeColor = Color.FromArgb(200, 200, 200),
                Font = new Font("Segoe UI", 8),
                BackColor = Color.FromArgb(45, 45, 48),
                Padding = new Padding(8, 4, 8, 4)
            };
            formatItem.MouseEnter += (s, e) => formatItem.BackColor = Color.FromArgb(60, 60, 65);
            formatItem.MouseLeave += (s, e) => formatItem.BackColor = Color.FromArgb(45, 45, 48);
            // Создаем подменю с размерами
            var sizeSubMenu = CreateSizeSubMenu(format);
            formatItem.DropDownItems.AddRange(sizeSubMenu.ToArray<ToolStripItem>());

            return formatItem;
        }

        private List<ToolStripItem> CreateSizeSubMenu(string format)
        {
            var items = new List<ToolStripItem>();

            // Определяем размеры в зависимости от формата
            int[] sizes;
            string sizeFormat;

            if (format == "ICO")
            {
                sizes = new[] { 16, 24, 32, 48, 64, 96, 128, 256 };
                sizeFormat = "{0}×{0}";
            }
            else // PNG, WebP
            {
                sizes = new[] { 16, 24, 32, 48, 64, 96, 128, 256, 512 };
                sizeFormat = "{0}px";
            }

            // Получаем размеры исходного изображения
            var sourceData = _iconService.GetIconData(_iconInfo.FilePath);
            var dimensions = sourceData != null ? IconConverter.GetImageDimensions(sourceData) : (0, 0);
            var isSvg = Path.GetExtension(_iconInfo.FilePath).ToLower() == ".svg";
            var maxDimension = Math.Max(dimensions.Item1, dimensions.Item2);

            // Добавляем стандартные размеры
            foreach (var size in sizes)
            {
                // Для SVG показываем все размеры, для растровых - только не превышающие исходник
                if (!isSvg && size > maxDimension)
                    continue;

                var item = new ToolStripMenuItem
                {
                    Text = string.Format(sizeFormat, size),
                    ForeColor = Color.FromArgb(200, 200, 200),
                    Font = new Font("Segoe UI", 8),
                    BackColor = Color.FromArgb(45, 45, 48),
                    Padding = new Padding(8, 4, 8, 4)
                };
                item.MouseEnter += (s, e) => item.BackColor = Color.FromArgb(60, 60, 65);
                item.MouseLeave += (s, e) => item.BackColor = Color.FromArgb(45, 45, 48);
                item.Click += async (s, e) => await ConvertAndSave(format, size);
                items.Add(item);
            }

            return items;
        }

        private void LoadIconInfo()
        {
            var fileName = Path.GetFileName(_iconInfo.FilePath);
            var fileNameWithoutExt = Path.GetFileNameWithoutExtension(_iconInfo.FilePath);
            var displayName = fileNameWithoutExt.Length > 20 ? fileNameWithoutExt[..20] + "..." : fileNameWithoutExt;
            lblName.Text = $"{displayName}";
            lblExt.Text = $"{Path.GetExtension(fileName).Trim('.').ToUpper()}";
        }

        public void LoadThumbnail()
        {
            if (picIcon.Image != null) return;
            try
            {
                var data = _iconService.GetIconData(_iconInfo.FilePath);
                if (data == null) return;

                var ext = Path.GetExtension(_iconInfo.FilePath).ToLower();

                if (ext == ".svg")
                {
                    LoadSvgThumbnail(data);
                }
                else if (ext == ".webp")
                {
                    LoadWebpThumbnail(data);
                }
                else
                {
                    LoadRasterThumbnail(data);
                }
            }
            catch (Exception ex)
            {
                Logger.Log($"Thumbnail error: {_iconInfo.FilePath} - {ex.Message}");
            }
        }

        private void LoadSvgThumbnail(byte[] data)
        {
            using var svg = new Svg.Skia.SKSvg();
            using var stream = new MemoryStream(data);
            var picture = svg.Load(stream);
            if (picture == null) return;

            var scale = Math.Min(64f / picture.CullRect.Width, 64f / picture.CullRect.Height);
            var w = Math.Max(1, (int)(picture.CullRect.Width * scale));
            var h = Math.Max(1, (int)(picture.CullRect.Height * scale));

            using var surface = SKSurface.Create(new SKImageInfo(w, h));
            var canvas = surface.Canvas;
            canvas.Clear(SKColors.Transparent);
            canvas.Scale(scale);
            canvas.DrawPicture(picture);

            using var image = surface.Snapshot();
            using var pngData = image.Encode(SKEncodedImageFormat.Png, 80);
            using var ms = new MemoryStream(pngData.ToArray());
            picIcon.Image = new Bitmap(ms);
        }

        private void LoadWebpThumbnail(byte[] data)
        {
            using var skBitmap = SKBitmap.Decode(data);
            if (skBitmap == null) return;
            var scale = Math.Min(64f / skBitmap.Width, 64f / skBitmap.Height);
            var w = Math.Max(1, (int)(skBitmap.Width * scale));
            var h = Math.Max(1, (int)(skBitmap.Height * scale));
            using var resized = skBitmap.Resize(new SKImageInfo(w, h), new SKSamplingOptions(SKFilterMode.Nearest, SKMipmapMode.None));
            if (resized == null) return;
            using var image = SKImage.FromBitmap(resized);
            using var pngData = image.Encode(SKEncodedImageFormat.Png, 80);
            using var ms = new MemoryStream(pngData.ToArray());
            picIcon.Image = new Bitmap(ms);
        }

        private void LoadRasterThumbnail(byte[] data)
        {
            using var ms = new MemoryStream(data);
            using var original = new Bitmap(ms);
            var scale = Math.Min(64f / original.Width, 64f / original.Height);
            var w = (int)(original.Width * scale);
            var h = (int)(original.Height * scale);

            // Создаем новый Bitmap и отключаем сглаживание
            var resized = new Bitmap(w, h);
            using var g = Graphics.FromImage(resized);
            g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.NearestNeighbor;
            g.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.Half;
            g.DrawImage(original, 0, 0, w, h);

            picIcon.Image = resized;
        }

        // ========== Drag & Drop ==========
        private void PicIcon_MouseDown(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
            {
                _isDragging = true;
            }
        }

        private void PicIcon_MouseMove(object sender, MouseEventArgs e)
        {
            if (!_isDragging) return;

            if (Math.Abs(e.X - (picIcon.Width / 2)) > 5 || Math.Abs(e.Y - (picIcon.Height / 2)) > 5)
            {
                _isDragging = false;
                StartDrag();
            }
        }

        private void StartDrag()
        {
            try
            {
                var data = _iconService.GetIconData(_iconInfo.FilePath);
                if (data == null) return;

                var tempDir = Path.Combine(Path.GetTempPath(), "IconFinder");
                Directory.CreateDirectory(tempDir);
                var fileName = Path.GetFileName(_iconInfo.FilePath);
                var tempPath = Path.Combine(tempDir, fileName);
                File.WriteAllBytes(tempPath, data);

                var dataObj = new DataObject();
                dataObj.SetData(DataFormats.FileDrop, new string[] { tempPath });
                DoDragDrop(dataObj, DragDropEffects.Copy);
                UsingMonitor.Info.AddDrug();
                UsingMonitor.CheckUsing();
            }
            catch (Exception ex)
            {
                Logger.Log($"Drag error: {ex.Message}");
            }
        }

        private void cardPanel_Click(object sender, EventArgs e) => IconClicked?.Invoke(this, _iconInfo);
        private void cardPanel_MouseEnter(object sender, EventArgs e) => cardPanel.BackColor = Color.FromArgb(60, 60, 65);
        private void cardPanel_MouseLeave(object sender, EventArgs e) => cardPanel.BackColor = Color.FromArgb(45, 45, 48);

        private void btnSave_Click(object sender, EventArgs e) =>
            _formatPopup.Show(btnSave.PointToScreen(new Point(0, btnSave.Height)), ToolStripDropDownDirection.BelowRight);
        private void btnSave_MouseEnter(object sender, EventArgs e) => btnSave.BackColor = Color.FromArgb(70, 70, 75);
        private void btnSave_MouseLeave(object sender, EventArgs e) => btnSave.BackColor = Color.FromArgb(55, 55, 60);

        private void SaveOriginal()
        {
            _formatPopup.Close();
            using var sfd = new SaveFileDialog
            {
                FileName = Path.GetFileName(_iconInfo.FilePath),
                Filter = $"Original Files|*{Path.GetExtension(_iconInfo.FilePath)}",
                Title = "Сохранить оригинал"
            };

            if (sfd.ShowDialog() == DialogResult.OK)
            {
                var data = _iconService.GetIconData(_iconInfo.FilePath);
                if (data != null)
                {
                    File.WriteAllBytes(sfd.FileName, data);
                    Logger.Log($"Original saved: {sfd.FileName} ({data.Length} bytes)");
                    UsingMonitor.Info.AddSvg();
                }
            }
        }

        private async Task ConvertAndSave(string format, int size)
        {
            try
            {
                // Закрываем все меню
                _formatPopup.Close();

                var ext = $".{format.ToLower()}";
                var sizeStr = format == "ICO" ? $"{size}x{size}" : $"{size}px";
                var fileName = $"{Path.GetFileNameWithoutExtension(_iconInfo.FilePath)}_{sizeStr}{ext}";

                using var sfd = new SaveFileDialog
                {
                    FileName = fileName,
                    Filter = $"{format} Files|*{ext}",
                    Title = $"Сохранить {format} {sizeStr}"
                };

                if (sfd.ShowDialog() == DialogResult.OK)
                {
                    var sourceData = _iconService.GetIconData(_iconInfo.FilePath);
                    if (sourceData == null) return;

                    var convertedData = await Task.Run(() =>
                        IconConverter.ConvertTo(sourceData, ext, svgSize: size, targetSize: size));

                    if (convertedData != null)
                    {
                        File.WriteAllBytes(sfd.FileName, convertedData);
                        Logger.Log($"Saved {format} {sizeStr}: {sfd.FileName} ({convertedData.Length} bytes)");
                        UsingMonitor.CheckUsing();
                    }
                }
            }
            catch (Exception ex)
            {
                Logger.Log($"Convert error: {ex.Message}");
            }
        }

        private static string FormatSize(int bytes) => bytes switch
        {
            < 1024 => $"{bytes} B",
            < 1024 * 1024 => $"{bytes / 1024.0:F1} KB",
            _ => $"{bytes / (1024.0 * 1024):F1} MB"
        };
    }
}
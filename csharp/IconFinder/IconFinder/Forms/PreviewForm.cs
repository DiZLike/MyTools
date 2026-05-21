using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using IconFinder.Services;
using SkiaSharp;
using IconConverter = IconFinder.Services.IconConverter;

namespace IconFinder.Forms
{
    public partial class PreviewForm : Form
    {
        private readonly IconInfo _iconInfo;
        private readonly IconService _iconService;

        public PreviewForm(IconInfo iconInfo, IconService iconService)
        {
            InitializeComponent();
            _iconInfo = iconInfo;
            _iconService = iconService;

            LoadIconPreview();
        }

        private void LoadIconPreview()
        {
            try
            {
                var data = _iconService.GetIconData(_iconInfo.FilePath);
                if (data == null) return;

                var ext = Path.GetExtension(_iconInfo.FilePath).ToLower();
                var dimensions = IconConverter.GetImageDimensions(data);

                lblFileName.Text = Path.GetFileName(_iconInfo.FilePath);
                lblPath.Text = _iconInfo.FilePath;
                lblFormat.Text = $"Формат: {ext.Trim('.').ToUpper()}";
                lblDimensions.Text = ext == ".svg"
                    ? $"Размер: {dimensions.Width}×{dimensions.Height} (вектор)"
                    : $"Размер: {dimensions.Width}×{dimensions.Height} px";
                lblFileSize.Text = $"Размер файла: {FormatSize(data.Length)}";

                if (ext == ".svg")
                    LoadSvgPreview(data);
                else if (ext == ".webp")
                    LoadWebpPreview(data);
                else
                    LoadRasterPreview(data);
            }
            catch (Exception ex)
            {
                Logger.Log($"Preview error: {ex.Message}");
            }
        }

        private void LoadSvgPreview(byte[] data)
        {
            using var svg = new Svg.Skia.SKSvg();
            using var stream = new MemoryStream(data);
            var picture = svg.Load(stream);
            if (picture == null) return;

            var maxSize = Math.Min(picPreview.Width, picPreview.Height);
            var scale = Math.Min(
                (float)maxSize / picture.CullRect.Width,
                (float)maxSize / picture.CullRect.Height);

            var w = Math.Max(1, (int)(picture.CullRect.Width * scale));
            var h = Math.Max(1, (int)(picture.CullRect.Height * scale));

            using var surface = SKSurface.Create(new SKImageInfo(w, h));
            var canvas = surface.Canvas;
            canvas.Clear(SKColors.Transparent);
            canvas.Scale(scale);
            canvas.DrawPicture(picture);

            using var image = surface.Snapshot();
            using var pngData = image.Encode(SKEncodedImageFormat.Png, 100);
            using var ms = new MemoryStream(pngData.ToArray());

            // Отключаем сглаживание при загрузке в PictureBox
            var bitmap = new Bitmap(ms);
            picPreview.Image = bitmap;
        }

        private void LoadWebpPreview(byte[] data)
        {
            using var skBitmap = SKBitmap.Decode(data);
            if (skBitmap == null) return;

            var maxSize = Math.Min(picPreview.Width, picPreview.Height);
            var scale = Math.Min(
                (float)maxSize / skBitmap.Width,
                (float)maxSize / skBitmap.Height);

            var w = Math.Max(1, (int)(skBitmap.Width * scale));
            var h = Math.Max(1, (int)(skBitmap.Height * scale));

            // Используем NearestNeighbor для пиксельной чёткости
            using var resized = skBitmap.Resize(
                new SKImageInfo(w, h),
                new SKSamplingOptions(SKFilterMode.Nearest, SKMipmapMode.None));

            if (resized == null) return;

            using var image = SKImage.FromBitmap(resized);
            using var pngData = image.Encode(SKEncodedImageFormat.Png, 100);
            using var ms = new MemoryStream(pngData.ToArray());
            picPreview.Image = new Bitmap(ms);
        }

        private void LoadRasterPreview(byte[] data)
        {
            using var ms = new MemoryStream(data);
            using var original = new Bitmap(ms);

            var maxSize = Math.Min(picPreview.Width, picPreview.Height);
            var scale = Math.Min(
                (float)maxSize / original.Width,
                (float)maxSize / original.Height);

            var w = (int)(original.Width * scale);
            var h = (int)(original.Height * scale);

            var resized = new Bitmap(w, h);
            using (var g = Graphics.FromImage(resized))
            {
                // Отключаем сглаживание для пиксельной чёткости
                g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.NearestNeighbor;
                g.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.Half;
                g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.None;
                g.CompositingQuality = System.Drawing.Drawing2D.CompositingQuality.HighSpeed;
                g.DrawImage(original, 0, 0, w, h);
            }

            picPreview.Image = resized;
        }

        private static string FormatSize(int bytes) => bytes switch
        {
            < 1024 => $"{bytes} B",
            < 1024 * 1024 => $"{bytes / 1024.0:F1} KB",
            _ => $"{bytes / (1024.0 * 1024):F1} MB"
        };

        private void btnClose_Click(object sender, EventArgs e) => Close();
    }
}
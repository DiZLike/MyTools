using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Windows.Forms;

namespace ScreenWire.Server.Capture
{
    public abstract class BaseScreenCaptor : IScreenCaptor
    {
        protected Rectangle _bounds;
        protected Bitmap _bitmap;
        protected byte[] _pixelBuffer;
        protected bool _disposed;

        protected readonly ImageCodecInfo _jpeg;
        protected readonly EncoderParameters _jpegParams;

        protected BaseScreenCaptor(int displayIndex)
        {
            _bounds = GetDisplayBounds(displayIndex);
            _pixelBuffer = new byte[_bounds.Width * _bounds.Height * 3];
            _bitmap = new Bitmap(_bounds.Width, _bounds.Height, PixelFormat.Format24bppRgb);

            _jpeg = GetEncoder();
            _jpegParams = new EncoderParameters(1);
            _jpegParams.Param[0] = new EncoderParameter(Encoder.Quality, (long)50);
        }

        public abstract byte[] CaptureScreen(int quality, float reductionRatio);

        public static Rectangle GetDisplayBounds(int index)
        {
            Screen[] screens = Screen.AllScreens;
            var sorted = new List<Screen>(screens);
            sorted.Sort((a, b) => a.Bounds.X.CompareTo(b.Bounds.X));

            if (index < 0 || index >= sorted.Count)
                return SystemInformation.VirtualScreen;
            return sorted[index].Bounds;
        }

        public static int GetDisplayCount()
        {
            return Screen.AllScreens.Length;
        }

        public static List<Screen> GetSortedScreens()
        {
            Screen[] screens = Screen.AllScreens;
            var sorted = new List<Screen>(screens);
            sorted.Sort((a, b) => a.Bounds.X.CompareTo(b.Bounds.X));
            return sorted;
        }

        protected byte[] CompressToJpeg(Bitmap source, int quality, float reductionRatio)
        {
            Bitmap target = source;
            bool needsDispose = false;

            try
            {
                if (reductionRatio > 1) // Если нужно масштабирование
                {
                    int newWidth = (int)(source.Width / reductionRatio);
                    int newHeight = (int)(source.Height / reductionRatio);

                    // Минимальный размер кадра
                    newWidth = Math.Max(1, newWidth);
                    newHeight = Math.Max(1, newHeight);

                    target = new Bitmap(newWidth, newHeight, PixelFormat.Format24bppRgb);
                    needsDispose = true;

                    using (var graphics = Graphics.FromImage(target))
                    {
                        graphics.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBilinear;
                        graphics.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.HighSpeed;
                        graphics.CompositingQuality = System.Drawing.Drawing2D.CompositingQuality.HighSpeed;
                        graphics.DrawImage(source, 0, 0, newWidth, newHeight);
                    }
                }

                UpdateJpegQuality(quality);
                using (var ms = new MemoryStream())
                {
                    target.Save(ms, _jpeg, _jpegParams);
                    return ms.ToArray();
                }
            }
            finally
            {
                if (needsDispose)
                    target.Dispose();
            }
        }

        protected void UpdateJpegQuality(int q)
        {
            _jpegParams.Param[0] = new EncoderParameter(Encoder.Quality, (long)Math.Max(1, Math.Min(100, q)));
        }

        protected static ImageCodecInfo GetEncoder()
        {
            foreach (ImageCodecInfo c in ImageCodecInfo.GetImageEncoders())
                if (c.FormatID == ImageFormat.Jpeg.Guid) return c;
            return null;
        }

        public virtual void Dispose()
        {
            _disposed = true;
            _pixelBuffer = null;
            if (_bitmap != null) { _bitmap.Dispose(); _bitmap = null; }
        }
    }
}
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;

namespace ScreenWire.Server.Capture
{
    public class GdiScreenCaptor : BaseScreenCaptor
    {
        private IntPtr _desktopHwnd;

        [DllImport("user32.dll")]
        private static extern IntPtr GetDesktopWindow();
        [DllImport("user32.dll")]
        private static extern IntPtr GetWindowDC(IntPtr hwnd);
        [DllImport("user32.dll")]
        private static extern void ReleaseDC(IntPtr hwnd, IntPtr dc);
        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateCompatibleDC(IntPtr hdc);
        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateCompatibleBitmap(IntPtr hdc, int width, int height);
        [DllImport("gdi32.dll")]
        private static extern IntPtr SelectObject(IntPtr hdc, IntPtr hgdiobj);
        [DllImport("gdi32.dll")]
        private static extern bool BitBlt(IntPtr hdcDest, int xDest, int yDest, int width, int height,
            IntPtr hdcSrc, int xSrc, int ySrc, uint rop);
        [DllImport("gdi32.dll")]
        private static extern bool DeleteDC(IntPtr hdc);
        [DllImport("gdi32.dll")]
        private static extern bool DeleteObject(IntPtr hObject);
        [DllImport("gdi32.dll")]
        private static extern int GetDIBits(IntPtr hdc, IntPtr hbmp, uint uStartScan, uint cScanLines,
            byte[] lpvBits, ref BITMAPINFO lpbi, uint uUsage);

        [StructLayout(LayoutKind.Sequential)]
        private struct BITMAPINFO
        {
            public int biSize, biWidth, biHeight;
            public short biPlanes, biBitCount;
            public int biCompression, biSizeImage, biXPelsPerMeter, biYPelsPerMeter, biClrUsed, biClrImportant;
        }

        private const uint SRCCOPY = 0x00CC0020;
        private const uint DIB_RGB_COLORS = 0;

        public GdiScreenCaptor(int displayIndex) : base(displayIndex)
        {
            _desktopHwnd = GetDesktopWindow();
        }

        public override byte[] CaptureScreen(int quality)
        {
            if (_disposed) return null;

            IntPtr desktopDC = IntPtr.Zero, memoryDC = IntPtr.Zero, hbitmap = IntPtr.Zero, oldBitmap = IntPtr.Zero;
            try
            {
                desktopDC = GetWindowDC(_desktopHwnd);
                if (desktopDC == IntPtr.Zero) return null;

                memoryDC = CreateCompatibleDC(desktopDC);
                if (memoryDC == IntPtr.Zero) return null;

                hbitmap = CreateCompatibleBitmap(desktopDC, _bounds.Width, _bounds.Height);
                if (hbitmap == IntPtr.Zero) return null;

                oldBitmap = SelectObject(memoryDC, hbitmap);

                if (!BitBlt(memoryDC, 0, 0, _bounds.Width, _bounds.Height,
                           desktopDC, _bounds.X, _bounds.Y, SRCCOPY))
                    return null;

                BITMAPINFO bmi = new BITMAPINFO();
                bmi.biSize = Marshal.SizeOf(typeof(BITMAPINFO));
                bmi.biWidth = _bounds.Width;
                bmi.biHeight = -_bounds.Height;
                bmi.biPlanes = 1;
                bmi.biBitCount = 24;
                bmi.biCompression = 0;

                int bufLen = _bounds.Width * _bounds.Height * 3;
                if (_pixelBuffer == null || _pixelBuffer.Length != bufLen)
                    _pixelBuffer = new byte[bufLen];

                GetDIBits(memoryDC, hbitmap, 0, (uint)_bounds.Height, _pixelBuffer, ref bmi, DIB_RGB_COLORS);

                var bmpData = _bitmap.LockBits(new Rectangle(0, 0, _bounds.Width, _bounds.Height),
                    ImageLockMode.WriteOnly, PixelFormat.Format24bppRgb);
                Marshal.Copy(_pixelBuffer, 0, bmpData.Scan0, _pixelBuffer.Length);
                _bitmap.UnlockBits(bmpData);

                UpdateJpegQuality(quality);
                using (var ms = new MemoryStream())
                {
                    _bitmap.Save(ms, _jpeg, _jpegParams);
                    return ms.ToArray();
                }
            }
            catch { return null; }
            finally
            {
                if (oldBitmap != IntPtr.Zero && memoryDC != IntPtr.Zero) SelectObject(memoryDC, oldBitmap);
                if (hbitmap != IntPtr.Zero) DeleteObject(hbitmap);
                if (memoryDC != IntPtr.Zero) DeleteDC(memoryDC);
                if (desktopDC != IntPtr.Zero) ReleaseDC(_desktopHwnd, desktopDC);
            }
        }
    }
}
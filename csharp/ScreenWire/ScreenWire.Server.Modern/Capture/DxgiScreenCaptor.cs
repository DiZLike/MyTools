using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using SharpDX;
using SharpDX.Direct3D11;
using SharpDX.DXGI;
using Device = SharpDX.Direct3D11.Device;
using MapFlags = SharpDX.Direct3D11.MapFlags;

namespace ScreenWire.Server.Capture
{
    public class DxgiScreenCaptor : BaseScreenCaptor
    {
        private Factory1? _factory;
        private Adapter1? _adapter;
        private Device? _device;
        private Output? _output;
        private Output1? _output1;
        private OutputDuplication? _duplication;
        private Texture2D? _stagingTexture;
        private bool _initialized;
        private readonly object _lockObj = new();

        public DxgiScreenCaptor(int displayIndex) : base(displayIndex)
        {
            Initialize(displayIndex);
        }

        private void Initialize(int displayIndex)
        {
            try
            {
                _factory = new Factory1();
                _adapter = _factory.GetAdapter1(0);
                _device = new Device(_adapter, DeviceCreationFlags.None, SharpDX.Direct3D.FeatureLevel.Level_11_0);

                var output = GetOutput(displayIndex);
                if (output == null)
                    throw new InvalidOperationException($"Монитор с индексом {displayIndex} не найден");

                _output = output;
                _output1 = output.QueryInterface<Output1>();

                _duplication = _output1.DuplicateOutput(_device);

                var desc = _output.Description;
                var textureDesc = new Texture2DDescription
                {
                    Width = desc.DesktopBounds.Right - desc.DesktopBounds.Left,
                    Height = desc.DesktopBounds.Bottom - desc.DesktopBounds.Top,
                    MipLevels = 1,
                    ArraySize = 1,
                    Format = Format.B8G8R8A8_UNorm,
                    SampleDescription = new SampleDescription(1, 0),
                    Usage = ResourceUsage.Staging,
                    BindFlags = BindFlags.None,
                    CpuAccessFlags = CpuAccessFlags.Read,
                    OptionFlags = ResourceOptionFlags.None
                };

                _stagingTexture = new Texture2D(_device, textureDesc);
                _initialized = true;
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"DXGI init error: {ex.Message}");
                _initialized = false;
            }
        }

        private Output? GetOutput(int displayIndex)
        {
            if (_adapter == null) return null;

            int currentIndex = 0;
            int outputCount = _adapter.GetOutputCount();

            for (int i = 0; i < outputCount; i++)
            {
                if (currentIndex == displayIndex || displayIndex < 0)
                    return _adapter.GetOutput(i);
                currentIndex++;
            }

            return outputCount > 0 ? _adapter.GetOutput(0) : null;
        }

        public override byte[] CaptureScreen(int quality, float reductionRatio)
        {
            if (_disposed || !_initialized || _duplication == null || _device == null)
                return Array.Empty<byte>();

            lock (_lockObj)
            {
                try
                {
                    OutputDuplicateFrameInformation frameInfo;
                    SharpDX.DXGI.Resource? desktopResource = null;

                    try
                    {
                        var result = _duplication.TryAcquireNextFrame(1000, out frameInfo, out desktopResource);

                        if (result.Failure)
                        {
                            if (result.Code == SharpDX.DXGI.ResultCode.WaitTimeout.Result)
                                return Array.Empty<byte>();

                            Reinitialize();
                            return Array.Empty<byte>();
                        }
                    }
                    catch (SharpDXException ex) when (ex.ResultCode == SharpDX.DXGI.ResultCode.WaitTimeout)
                    {
                        return Array.Empty<byte>();
                    }
                    catch
                    {
                        Reinitialize();
                        return Array.Empty<byte>();
                    }

                    if (desktopResource == null)
                    {
                        _duplication.ReleaseFrame();
                        return Array.Empty<byte>();
                    }

                    using (desktopResource)
                    {
                        using var desktopTexture = desktopResource.QueryInterface<Texture2D>();
                        _device.ImmediateContext.CopyResource(desktopTexture, _stagingTexture);

                        var dataBox = _device.ImmediateContext.MapSubresource(
                            _stagingTexture, 0, MapMode.Read, MapFlags.None, out DataStream dataStream);

                        try
                        {
                            var bounds = _output?.Description.DesktopBounds;
                            int width = bounds?.Right - bounds?.Left ?? _bounds.Width;
                            int height = bounds?.Bottom - bounds?.Top ?? _bounds.Height;

                            using var bitmap = new Bitmap(width, height, PixelFormat.Format32bppArgb);
                            var bitmapData = bitmap.LockBits(
                                new Rectangle(0, 0, width, height),
                                ImageLockMode.WriteOnly,
                                PixelFormat.Format32bppArgb);

                            // ИСПРАВЛЕНО: копируем строки без инверсии
                            byte[] rowData = new byte[bitmapData.Stride];
                            for (int y = 0; y < height; y++)
                            {
                                // Читаем строку напрямую, без переворота
                                dataStream.Position = y * dataBox.RowPitch;
                                dataStream.Read(rowData, 0, bitmapData.Stride);

                                System.Runtime.InteropServices.Marshal.Copy(
                                    rowData, 0,
                                    IntPtr.Add(bitmapData.Scan0, y * bitmapData.Stride),
                                    bitmapData.Stride);
                            }

                            bitmap.UnlockBits(bitmapData);

                            return CompressToJpeg(bitmap, quality, reductionRatio);
                        }
                        finally
                        {
                            _device.ImmediateContext.UnmapSubresource(_stagingTexture, 0);
                            _duplication.ReleaseFrame();
                        }
                    }
                }
                catch (Exception ex)
                {
                    System.Diagnostics.Debug.WriteLine($"DXGI capture error: {ex.Message}");
                    Reinitialize();
                    return Array.Empty<byte>();
                }
            }
        }

        private void Reinitialize()
        {
            try
            {
                _duplication?.Dispose();
                _duplication = null;

                if (_output1 != null && _device != null)
                {
                    _duplication = _output1.DuplicateOutput(_device);
                }
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"DXGI reinit error: {ex.Message}");
            }
        }

        public override void Dispose()
        {
            lock (_lockObj)
            {
                _duplication?.Dispose();
                _stagingTexture?.Dispose();
                _output1?.Dispose();
                _output?.Dispose();
                _device?.Dispose();
                _adapter?.Dispose();
                _factory?.Dispose();

                _duplication = null;
                _stagingTexture = null;
                _output1 = null;
                _output = null;
                _device = null;
                _adapter = null;
                _factory = null;
            }
            base.Dispose();
        }
    }
}
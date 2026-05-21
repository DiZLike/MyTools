using System;
using System.IO;
using IconFinder.Monitors;
using SkiaSharp;

namespace IconFinder.Services
{
    public static class IconConverter
    {
        private const int DefaultSvgSize = 512;

        public static byte[] ConvertToPng(byte[] sourceData, int? svgSize = null, int targetSize = 512)
        {
            if (IsSvg(sourceData))
            {
                using var svg = new Svg.Skia.SKSvg();
                using var stream = new MemoryStream(sourceData);
                var picture = svg.Load(stream);
                if (picture == null) return null;

                var actualSize = svgSize ?? targetSize;
                var svgScale = Math.Min(
                    (float)actualSize / picture.CullRect.Width,
                    (float)actualSize / picture.CullRect.Height);

                var w = Math.Max(1, (int)(picture.CullRect.Width * svgScale));
                var h = Math.Max(1, (int)(picture.CullRect.Height * svgScale));

                using var surface = SKSurface.Create(new SKImageInfo(w, h));
                var canvas = surface.Canvas;
                canvas.Clear(SKColors.Transparent);
                canvas.Scale(svgScale);
                canvas.DrawPicture(picture);

                using var snapshot = surface.Snapshot();
                using var pngData = snapshot.Encode(SKEncodedImageFormat.Png, 100);
                UsingMonitor.Info.AddPng();
                return pngData.ToArray();
            }

            // Для растровых изображений
            using var skBitmap = SKBitmap.Decode(sourceData);
            if (skBitmap == null) return null;

            // Не увеличиваем размер выше исходного
            var size = Math.Min(targetSize, Math.Max(skBitmap.Width, skBitmap.Height));
            if (size == skBitmap.Width && size == skBitmap.Height)
            {
                // Если исходный размер уже подходит
                using var skImage = SKImage.FromBitmap(skBitmap);
                using var data = skImage.Encode(SKEncodedImageFormat.Png, 100);
                UsingMonitor.Info.AddPng();
                return data.ToArray();
            }

            var rasterScale = Math.Min((float)size / skBitmap.Width, (float)size / skBitmap.Height);
            var newWidth = Math.Max(1, (int)(skBitmap.Width * rasterScale));
            var newHeight = Math.Max(1, (int)(skBitmap.Height * rasterScale));

            using var resized = skBitmap.Resize(
                new SKImageInfo(newWidth, newHeight),
                new SKSamplingOptions(SKFilterMode.Linear, SKMipmapMode.Linear));

            if (resized == null) return null;

            using var skImage2 = SKImage.FromBitmap(resized);
            using var data2 = skImage2.Encode(SKEncodedImageFormat.Png, 100);
            UsingMonitor.Info.AddPng();
            return data2.ToArray();
        }

        public static byte[] ConvertToIco(byte[] sourceData, int? svgSize = null, int targetSize = 256)
        {
            byte[] rasterData;
            if (IsSvg(sourceData))
            {
                rasterData = ConvertToPng(sourceData, svgSize, targetSize);
                if (rasterData == null) return null;
            }
            else
            {
                // Для растровых используем ConvertToPng с ограничением размера
                rasterData = ConvertToPng(sourceData, null, targetSize);
                if (rasterData == null) return null;
            }

            using var skBitmap = SKBitmap.Decode(rasterData);
            if (skBitmap == null) return null;

            // Создаем квадратную иконку
            var size = Math.Min(targetSize, Math.Min(skBitmap.Width, skBitmap.Height));
            if (skBitmap.Width != size || skBitmap.Height != size)
            {
                using var resized = skBitmap.Resize(
                    new SKImageInfo(size, size),
                    new SKSamplingOptions(SKFilterMode.Linear, SKMipmapMode.Linear));

                if (resized == null) return null;

                using var icoImage = SKImage.FromBitmap(resized);
                using var pngData = icoImage.Encode(SKEncodedImageFormat.Png, 100);
                var imageData = pngData.ToArray();

                return CreateIcoFile(size, imageData);
            }
            else
            {
                using var icoImage = SKImage.FromBitmap(skBitmap);
                using var pngData = icoImage.Encode(SKEncodedImageFormat.Png, 100);
                var imageData = pngData.ToArray();

                return CreateIcoFile(size, imageData);
            }
        }

        private static byte[] CreateIcoFile(int size, byte[] imageData)
        {
            using var ms = new MemoryStream();
            using var writer = new BinaryWriter(ms);

            // ICO Header
            writer.Write((short)0);  // reserved
            writer.Write((short)1);  // ICO type
            writer.Write((short)1);  // 1 icon

            // Icon entry
            writer.Write((byte)Math.Min(size, 255));  // width (max 255)
            writer.Write((byte)Math.Min(size, 255));  // height (max 255)
            writer.Write((byte)0);     // color palette
            writer.Write((byte)0);     // reserved
            writer.Write((short)0);    // color planes
            writer.Write((short)32);   // bits per pixel
            writer.Write(imageData.Length);  // size of image data
            writer.Write(22);          // offset (6 + 16)

            // Image data
            writer.Write(imageData);

            UsingMonitor.Info.AddIco();
            return ms.ToArray();
        }

        public static byte[] ConvertToWebp(byte[] sourceData, int? svgSize = null, int targetSize = 512)
        {
            byte[] rasterData;
            if (IsSvg(sourceData))
            {
                rasterData = ConvertToPng(sourceData, svgSize, targetSize);
                if (rasterData == null) return null;
            }
            else
            {
                rasterData = ConvertToPng(sourceData, null, targetSize);
                if (rasterData == null) return null;
            }

            using var skBitmap = SKBitmap.Decode(rasterData);
            if (skBitmap == null) return null;
            using var skImage = SKImage.FromBitmap(skBitmap);
            using var webpData = skImage.Encode(SKEncodedImageFormat.Webp, 90);
            UsingMonitor.Info.AddWebp();
            return webpData.ToArray();
        }

        public static byte[] ConvertTo(byte[] sourceData, string targetFormat, int? svgSize = null, int targetSize = 512) => targetFormat.ToLower() switch
        {
            ".png" => ConvertToPng(sourceData, svgSize, targetSize),
            ".ico" => ConvertToIco(sourceData, svgSize, targetSize),
            ".webp" => ConvertToWebp(sourceData, svgSize, targetSize),
            _ => sourceData
        };

        public static (int Width, int Height) GetImageDimensions(byte[] data)
        {
            if (IsSvg(data))
            {
                try
                {
                    using var svg = new Svg.Skia.SKSvg();
                    using var stream = new MemoryStream(data);
                    var picture = svg.Load(stream);
                    if (picture != null)
                        return ((int)picture.CullRect.Width, (int)picture.CullRect.Height);
                }
                catch { }
                return (0, 0); // SVG считается бесконечно масштабируемым
            }

            using var skBitmap = SKBitmap.Decode(data);
            if (skBitmap != null)
                return (skBitmap.Width, skBitmap.Height);

            return (0, 0);
        }

        private static bool IsSvg(byte[] data)
        {
            if (data.Length < 4) return false;
            return (data[0] == '<' && data[1] == 's' && data[2] == 'v' && data[3] == 'g')
                || (data[0] == '<' && data[1] == '?' && data[2] == 'x' && data[3] == 'm');
        }
    }
}
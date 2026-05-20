using System;
using System.IO;
using SkiaSharp;

namespace IconFinder.Services
{
    public static class IconConverter
    {
        private const int DefaultSvgSize = 512;

        public static byte[] ConvertToPng(byte[] sourceData, int? svgSize = null)
        {
            if (IsSvg(sourceData))
            {
                using var svg = new Svg.Skia.SKSvg();
                using var stream = new MemoryStream(sourceData);
                var picture = svg.Load(stream);
                if (picture == null) return null;

                var targetSize = svgSize ?? DefaultSvgSize;
                var scale = Math.Min(
                    (float)targetSize / picture.CullRect.Width,
                    (float)targetSize / picture.CullRect.Height);

                var w = Math.Max(1, (int)(picture.CullRect.Width * scale));
                var h = Math.Max(1, (int)(picture.CullRect.Height * scale));

                using var surface = SKSurface.Create(new SKImageInfo(w, h));
                var canvas = surface.Canvas;
                canvas.Clear(SKColors.Transparent);
                canvas.Scale(scale);
                canvas.DrawPicture(picture);

                using var snapshot = surface.Snapshot();
                using var pngData = snapshot.Encode(SKEncodedImageFormat.Png, 100);
                return pngData.ToArray();
            }

            using var skBitmap = SKBitmap.Decode(sourceData);
            if (skBitmap == null) return null;
            using var skImage = SKImage.FromBitmap(skBitmap);
            using var data = skImage.Encode(SKEncodedImageFormat.Png, 100);
            return data.ToArray();
        }

        public static byte[] ConvertToIco(byte[] sourceData, int? svgSize = null)
        {
            byte[] rasterData;
            if (IsSvg(sourceData))
            {
                rasterData = ConvertToPng(sourceData, svgSize);
                if (rasterData == null) return null;
            }
            else
            {
                rasterData = sourceData;
            }

            using var skBitmap = SKBitmap.Decode(rasterData);
            if (skBitmap == null) return null;

            var sizes = new[] { 256, 128, 64, 48, 32, 16 };
            using var ms = new MemoryStream();
            using var writer = new BinaryWriter(ms);

            writer.Write((short)0);
            writer.Write((short)1);
            writer.Write((short)sizes.Length);

            var images = new byte[sizes.Length][];
            var offsets = new int[sizes.Length];
            int offset = 6 + 16 * sizes.Length;

            for (int i = 0; i < sizes.Length; i++)
            {
                var size = Math.Min(sizes[i], Math.Min(skBitmap.Width, skBitmap.Height));
                using var resized = skBitmap.Resize(
                    new SKImageInfo(size, size),
                    new SKSamplingOptions(SKFilterMode.Linear, SKMipmapMode.Linear));

                if (resized == null) continue;

                using var icoImage = SKImage.FromBitmap(resized);
                using var pngData = icoImage.Encode(SKEncodedImageFormat.Png, 100);
                images[i] = pngData.ToArray();
                offsets[i] = offset;
                offset += images[i].Length;
            }

            for (int i = 0; i < sizes.Length; i++)
            {
                if (images[i] == null) continue;

                var size = Math.Min(sizes[i], Math.Min(skBitmap.Width, skBitmap.Height));
                writer.Write((byte)size);
                writer.Write((byte)size);
                writer.Write((byte)0);
                writer.Write((byte)0);
                writer.Write((short)0);
                writer.Write((short)32);
                writer.Write(images[i].Length);
                writer.Write(offsets[i]);
            }

            foreach (var img in images)
            {
                if (img != null)
                    writer.Write(img);
            }

            return ms.ToArray();
        }

        public static byte[] ConvertToWebp(byte[] sourceData, int? svgSize = null)
        {
            if (IsSvg(sourceData))
            {
                var pngData = ConvertToPng(sourceData, svgSize);
                if (pngData == null) return null;
                sourceData = pngData;
            }

            using var skBitmap = SKBitmap.Decode(sourceData);
            if (skBitmap == null) return null;
            using var skImage = SKImage.FromBitmap(skBitmap);
            using var webpData = skImage.Encode(SKEncodedImageFormat.Webp, 90);
            return webpData.ToArray();
        }

        public static byte[] ConvertTo(byte[] sourceData, string targetFormat, int? svgSize = null) => targetFormat.ToLower() switch
        {
            ".png" => ConvertToPng(sourceData, svgSize),
            ".ico" => ConvertToIco(sourceData, svgSize),
            ".webp" => ConvertToWebp(sourceData, svgSize),
            _ => sourceData
        };

        private static bool IsSvg(byte[] data)
        {
            if (data.Length < 4) return false;
            return (data[0] == '<' && data[1] == 's' && data[2] == 'v' && data[3] == 'g')
                || (data[0] == '<' && data[1] == '?' && data[2] == 'x' && data[3] == 'm');
        }
    }
}
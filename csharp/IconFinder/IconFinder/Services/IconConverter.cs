using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using SkiaSharp;

namespace IconFinder.Services
{
    public static class IconConverter
    {
        public static byte[] ConvertToPng(byte[] sourceData)
        {
            using var skBitmap = SKBitmap.Decode(sourceData);
            if (skBitmap == null) return null;
            using var image = SKImage.FromBitmap(skBitmap);
            using var data = image.Encode(SKEncodedImageFormat.Png, 100);
            return data.ToArray();
        }

        public static byte[] ConvertToIco(byte[] sourceData)
        {
            using var skBitmap = SKBitmap.Decode(sourceData);
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
                using var resized = skBitmap.Resize(new SKImageInfo(size, size), new SKSamplingOptions(SKFilterMode.Linear, SKMipmapMode.Linear));
                using var image = SKImage.FromBitmap(resized);
                using var pngData = image.Encode(SKEncodedImageFormat.Png, 100);
                images[i] = pngData.ToArray();
                offsets[i] = offset;
                offset += images[i].Length;
            }

            for (int i = 0; i < sizes.Length; i++)
            {
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

            foreach (var img in images) writer.Write(img);
            return ms.ToArray();
        }

        public static byte[] ConvertToWebp(byte[] sourceData)
        {
            using var skBitmap = SKBitmap.Decode(sourceData);
            if (skBitmap == null) return null;
            using var image = SKImage.FromBitmap(skBitmap);
            using var data = image.Encode(SKEncodedImageFormat.Webp, 90);
            return data.ToArray();
        }

        public static byte[] ConvertTo(byte[] sourceData, string targetFormat) => targetFormat.ToLower() switch
        {
            ".png" => ConvertToPng(sourceData),
            ".ico" => ConvertToIco(sourceData),
            ".webp" => ConvertToWebp(sourceData),
            _ => sourceData
        };
    }
}
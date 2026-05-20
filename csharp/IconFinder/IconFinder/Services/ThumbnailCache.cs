using System;
using System.Collections.Concurrent;
using System.Drawing;
using System.IO;
using SkiaSharp;

namespace IconFinder.Services
{
    public class ThumbnailCache : IDisposable
    {
        private readonly ConcurrentDictionary<string, Image> _cache = new();
        private readonly IconService _iconService;
        private readonly int _maxCachedImages = 200;
        private readonly int _thumbnailSize = 64;

        public ThumbnailCache(IconService iconService)
        {
            _iconService = iconService;
        }

        public Image GetThumbnail(string path)
        {
            if (_cache.TryGetValue(path, out var cached))
                return cached;

            var image = LoadThumbnail(path);
            if (image == null) return null;

            if (_cache.Count >= _maxCachedImages)
            {
                foreach (var key in _cache.Keys)
                {
                    if (_cache.TryRemove(key, out var old))
                    {
                        old?.Dispose();
                        break;
                    }
                }
            }

            _cache[path] = image;
            return image;
        }

        private Image LoadThumbnail(string path)
        {
            try
            {
                var data = _iconService.GetIconData(path);
                if (data == null) return null;

                var ext = Path.GetExtension(path).ToLower();

                if (ext == ".svg")
                    return LoadSvgThumbnail(data);
                else
                    return LoadRasterThumbnail(data);
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Error loading {path}: {ex.Message}");
                return null;
            }
        }

        private Image LoadSvgThumbnail(byte[] data)
        {
            using var svg = new Svg.Skia.SKSvg();
            using var stream = new MemoryStream(data);
            var picture = svg.Load(stream);
            if (picture == null) return null;

            var scale = Math.Min(
                (float)_thumbnailSize / picture.CullRect.Width,
                (float)_thumbnailSize / picture.CullRect.Height);

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
            return new Bitmap(ms);
        }

        private Image LoadRasterThumbnail(byte[] data)
        {
            using var original = SKBitmap.Decode(data);
            if (original == null) return null;

            var scale = Math.Min(
                (float)_thumbnailSize / original.Width,
                (float)_thumbnailSize / original.Height);

            var newWidth = Math.Max(1, (int)(original.Width * scale));
            var newHeight = Math.Max(1, (int)(original.Height * scale));

            using var resized = original.Resize(
                new SKImageInfo(newWidth, newHeight),
                new SKSamplingOptions(SKFilterMode.Linear, SKMipmapMode.Linear));

            if (resized == null) return null;

            using var image = SKImage.FromBitmap(resized);
            using var pngData = image.Encode(SKEncodedImageFormat.Png, 80);
            using var ms = new MemoryStream(pngData.ToArray());
            return new Bitmap(ms);
        }

        public void Dispose()
        {
            foreach (var image in _cache.Values)
                image?.Dispose();
            _cache.Clear();
        }
    }
}
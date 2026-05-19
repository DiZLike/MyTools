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
                if (data == null)
                {
                    System.Diagnostics.Debug.WriteLine($"No data: {path}");
                    return null;
                }

                using var original = SKBitmap.Decode(data);
                if (original == null)
                {
                    System.Diagnostics.Debug.WriteLine($"Cannot decode: {path}");
                    return null;
                }

                var scale = Math.Min(
                    (float)_thumbnailSize / original.Width,
                    (float)_thumbnailSize / original.Height
                );

                var newWidth = Math.Max(1, (int)(original.Width * scale));
                var newHeight = Math.Max(1, (int)(original.Height * scale));

                using var resized = original.Resize(
                    new SKImageInfo(newWidth, newHeight),
                    new SKSamplingOptions(SKFilterMode.Linear, SKMipmapMode.Linear)
                );

                if (resized == null)
                {
                    System.Diagnostics.Debug.WriteLine($"Cannot resize: {path}");
                    return null;
                }

                using var image = SKImage.FromBitmap(resized);
                if (image == null)
                {
                    System.Diagnostics.Debug.WriteLine($"Cannot create SKImage: {path}");
                    return null;
                }

                using var pngData = image.Encode(SKEncodedImageFormat.Png, 80);
                if (pngData == null || pngData.Size == 0)
                {
                    System.Diagnostics.Debug.WriteLine($"Cannot encode PNG: {path}");
                    return null;
                }

                using var ms = new MemoryStream(pngData.ToArray());
                var bitmap = new Bitmap(ms);

                System.Diagnostics.Debug.WriteLine($"OK: {path} ({bitmap.Width}x{bitmap.Height})");
                return bitmap;
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Error loading {path}: {ex.Message}");
                return null;
            }
        }

        public void Dispose()
        {
            foreach (var image in _cache.Values)
                image?.Dispose();
            _cache.Clear();
        }
    }
}
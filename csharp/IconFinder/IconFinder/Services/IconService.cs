// Файл: IconService.cs - Полная замена класса

using Microsoft.Data.Sqlite;
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Threading;

namespace IconFinder.Services
{
    public class IconInfo
    {
        public string FilePath { get; set; }
        public long Offset { get; set; }
        public int SizeCompressed { get; set; }
        public int SizeOriginal { get; set; }
        public int Compression { get; set; }
    }

    public class TocEntry
    {
        public long Offset { get; set; }
        public int SizeCompressed { get; set; }
        public int SizeOriginal { get; set; }
        public int Compression { get; set; }
        public byte[] SharedPrefix { get; set; }
    }

    public class IconService : IDisposable
    {
        private const int COMPRESSION_NONE = 0;
        private const int COMPRESSION_ZLIB = 1;
        private const int COMPRESSION_BROTLI = 2;
        private const int COMPRESSION_SHARED_BROTLI = 3;
        private const int COMPRESSION_SHARED_ZLIB = 4;

        private readonly string _dbPath;
        private readonly string _datPath;
        private Dictionary<string, TocEntry> _toc;
        private List<string> _allPaths;
        private Random _random = new();
        private FileStream _dataStream;
        private readonly ReaderWriterLockSlim _tocLock = new ReaderWriterLockSlim();

        public int TotalCount
        {
            get
            {
                _tocLock.EnterReadLock();
                try
                {
                    return _toc?.Count ?? 0;
                }
                finally
                {
                    _tocLock.ExitReadLock();
                }
            }
        }

        public IconService(string dbPath, string datPath)
        {
            _dbPath = Path.GetFullPath(dbPath);
            _datPath = Path.GetFullPath(datPath);
            Logger.Log($"IconService init: db={_dbPath}, dat={_datPath}");
            _dataStream = new FileStream(_datPath, FileMode.Open, FileAccess.Read, FileShare.Read, 16 * 1024 * 1024);
            LoadToc();
        }

        private void LoadToc()
        {
            _tocLock.EnterWriteLock();
            try
            {
                _toc = new Dictionary<string, TocEntry>(StringComparer.OrdinalIgnoreCase);
                _allPaths = new List<string>();

                var magic = new byte[4];
                _dataStream.ReadExactly(magic, 0, 4);
                if (Encoding.ASCII.GetString(magic) != "ICN4")
                    throw new InvalidDataException($"Invalid MAGIC: expected ICN4, got {Encoding.ASCII.GetString(magic)}");

                Span<byte> header = stackalloc byte[14];
                _dataStream.ReadExactly(header);
                var count = BitConverter.ToUInt32(header[..4]);
                var dataStart = BitConverter.ToUInt64(header.Slice(4, 8));
                var prefixLen = BitConverter.ToUInt16(header.Slice(12, 2));

                Logger.Log($"Entries: {count}, data_start: {dataStart}, prefix_len: {prefixLen}");

                byte[] sharedPrefix = null;
                if (prefixLen > 0)
                {
                    sharedPrefix = new byte[prefixLen];
                    _dataStream.ReadExactly(sharedPrefix, 0, prefixLen);
                    Logger.Log($"Shared prefix loaded: {prefixLen} bytes");
                }

                for (int i = 0; i < count; i++)
                {
                    var pathLen = ReadUInt16();
                    var path = ReadString(pathLen);
                    var offset = ReadInt64();
                    var sizeCompressed = ReadInt32();
                    var sizeOriginal = ReadInt32();
                    var compression = ReadByte();

                    var normalizedPath = NormalizePath(path);
                    _toc[normalizedPath] = new TocEntry
                    {
                        Offset = offset,
                        SizeCompressed = sizeCompressed,
                        SizeOriginal = sizeOriginal,
                        Compression = compression,
                        SharedPrefix = sharedPrefix
                    };
                    _allPaths.Add(normalizedPath);
                }

                Logger.Log($"TOC loaded: {_toc.Count} entries");
            }
            finally
            {
                _tocLock.ExitWriteLock();
            }
        }

        private ushort ReadUInt16()
        {
            Span<byte> buf = stackalloc byte[2];
            _dataStream.ReadExactly(buf);
            return BitConverter.ToUInt16(buf);
        }

        private int ReadInt32()
        {
            Span<byte> buf = stackalloc byte[4];
            _dataStream.ReadExactly(buf);
            return BitConverter.ToInt32(buf);
        }

        private long ReadInt64()
        {
            Span<byte> buf = stackalloc byte[8];
            _dataStream.ReadExactly(buf);
            return BitConverter.ToInt64(buf);
        }

        private byte ReadByte()
        {
            var b = _dataStream.ReadByte();
            if (b == -1) throw new EndOfStreamException();
            return (byte)b;
        }

        private string ReadString(int length)
        {
            Span<byte> buf = length <= 256 ? stackalloc byte[length] : new byte[length];
            _dataStream.ReadExactly(buf);
            return Encoding.UTF8.GetString(buf);
        }

        private static string NormalizePath(string path)
        {
            if (path.StartsWith("icons/", StringComparison.OrdinalIgnoreCase) ||
                path.StartsWith("icons\\", StringComparison.OrdinalIgnoreCase))
                path = path[6..];
            return path.Replace('\\', '/');
        }

        /// <summary>
        /// Поиск иконок.
        /// </summary>
        /// <param name="query">Поисковый запрос (слова через пробел)</param>
        /// <param name="mode">
        /// "wide"   — поиск по icon_tags + pack_tags (макс. находимость)
        /// "normal" — поиск только по icon_tags (по умолчанию)
        /// "exact"  — точная фраза в icon_tags
        /// </param>
        /// <param name="limit">Максимум результатов</param>
        public List<IconInfo> Search(string query, int limit = 10000, string mode = "normal", bool prefix = true)
        {
            var results = new List<IconInfo>();
            var words = query.Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            if (words.Length == 0) return results;

            using var conn = new SqliteConnection($"Data Source={_dbPath}");
            conn.Open();

            string ftsQuery;
            if (mode == "exact")
            {
                ftsQuery = $"icon_tags: \"{query.Replace("\"", "\"\"")}\"";
            }
            else if (mode == "wide")
            {
                ftsQuery = string.Join(" OR ", words.Select(w => prefix ? $"{w}*" : w));
            }
            else // normal
            {
                ftsQuery = string.Join(" OR ", words.Select(w => prefix ? $"icon_tags: {w}*" : $"icon_tags: {w}"));
            }

            _tocLock.EnterReadLock();
            try
            {
                using var cmd = conn.CreateCommand();
                cmd.CommandText = @"
                    SELECT i.filepath 
                    FROM icons_fts f 
                    JOIN icons i ON f.rowid = i.id 
                    WHERE icons_fts MATCH @query 
                    LIMIT @limit";
                cmd.Parameters.AddWithValue("@query", ftsQuery);
                cmd.Parameters.AddWithValue("@limit", limit);

                using var reader = cmd.ExecuteReader();
                while (reader.Read())
                {
                    var normalizedPath = NormalizePath(reader.GetString(0));
                    if (_toc.TryGetValue(normalizedPath, out var entry))
                        results.Add(new IconInfo
                        {
                            FilePath = normalizedPath,
                            Offset = entry.Offset,
                            SizeCompressed = entry.SizeCompressed,
                            SizeOriginal = entry.SizeOriginal,
                            Compression = entry.Compression
                        });
                }
            }
            finally
            {
                _tocLock.ExitReadLock();
            }

            Logger.Log($"Search '{query}' [{mode}]: {results.Count} results");
            return results;
        }

        public List<IconInfo> GetRandomIcons(int count = 30)
        {
            var results = new List<IconInfo>();
            _tocLock.EnterReadLock();
            try
            {
                var indices = new HashSet<int>();
                while (results.Count < count && indices.Count < _allPaths.Count)
                {
                    var idx = _random.Next(_allPaths.Count);
                    if (indices.Add(idx) && _toc.TryGetValue(_allPaths[idx], out var entry))
                        results.Add(new IconInfo
                        {
                            FilePath = _allPaths[idx],
                            Offset = entry.Offset,
                            SizeCompressed = entry.SizeCompressed,
                            SizeOriginal = entry.SizeOriginal,
                            Compression = entry.Compression
                        });
                }
            }
            finally
            {
                _tocLock.ExitReadLock();
            }
            return results;
        }

        public byte[] GetIconData(string path)
        {
            path = NormalizePath(path);

            _tocLock.EnterReadLock();
            TocEntry entry;
            try
            {
                if (!_toc.TryGetValue(path, out entry))
                    return null;
            }
            finally
            {
                _tocLock.ExitReadLock();
            }

            byte[] compressed;
            lock (_dataStream)
            {
                compressed = new byte[entry.SizeCompressed];
                _dataStream.Seek(entry.Offset, SeekOrigin.Begin);
                _dataStream.ReadExactly(compressed, 0, entry.SizeCompressed);
            }

            return Decompress(compressed, entry);
        }

        private byte[] Decompress(byte[] data, TocEntry entry)
        {
            switch (entry.Compression)
            {
                case COMPRESSION_NONE:
                    return data;
                case COMPRESSION_ZLIB:
                    return ZlibDecompress(data);
                case COMPRESSION_BROTLI:
                    return BrotliDecompress(data);
                case COMPRESSION_SHARED_BROTLI:
                    return Concat(entry.SharedPrefix, BrotliDecompress(data));
                case COMPRESSION_SHARED_ZLIB:
                    return Concat(entry.SharedPrefix, ZlibDecompress(data));
                default:
                    throw new InvalidDataException($"Unknown compression method: {entry.Compression}");
            }
        }

        private static byte[] ZlibDecompress(byte[] data)
        {
            if (data.Length < 2)
                throw new InvalidDataException("Zlib data too short");
            using var input = new MemoryStream(data, 2, data.Length - 2);
            using var output = new MemoryStream();
            using var deflate = new DeflateStream(input, CompressionMode.Decompress);
            deflate.CopyTo(output);
            return output.ToArray();
        }

        private static byte[] BrotliDecompress(byte[] data)
        {
            using var input = new MemoryStream(data);
            using var output = new MemoryStream();
            using var brotli = new BrotliStream(input, CompressionMode.Decompress);
            brotli.CopyTo(output);
            return output.ToArray();
        }

        private static byte[] Concat(byte[] a, byte[] b)
        {
            var result = new byte[a.Length + b.Length];
            Buffer.BlockCopy(a, 0, result, 0, a.Length);
            Buffer.BlockCopy(b, 0, result, a.Length, b.Length);
            return result;
        }

        public void Dispose()
        {
            Logger.Log("IconService disposed");
            _tocLock?.Dispose();
            _dataStream?.Dispose();
        }
    }
}
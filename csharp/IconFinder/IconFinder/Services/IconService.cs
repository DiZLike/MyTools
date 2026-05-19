using System;
using System.Collections.Generic;
using System.Data.SQLite;
using System.IO;

namespace IconFinder.Services
{
    public class IconService : IDisposable
    {
        private readonly string _dbPath;
        private readonly string _datPath;
        private Dictionary<string, (long offset, int size)> _toc;
        private List<string> _allPaths;
        private Random _random = new();
        private FileStream _dataStream;

        public int TotalCount => _toc?.Count ?? 0;

        public IconService(string dbPath, string datPath)
        {
            _dbPath = Path.GetFullPath(dbPath);
            _datPath = Path.GetFullPath(datPath);
            Logger.Log($"IconService init: db={_dbPath}, dat={_datPath}");
            _dataStream = new FileStream(_datPath, FileMode.Open, FileAccess.Read, FileShare.Read);
            LoadToc();
        }

        private void LoadToc()
        {
            _toc = new(StringComparer.OrdinalIgnoreCase);
            _allPaths = new();

            var magic = new byte[4];
            _dataStream.ReadExactly(magic, 0, 4);
            if (System.Text.Encoding.ASCII.GetString(magic) != "ICON")
                throw new InvalidDataException("Invalid file format");

            var headerBytes = new byte[16];
            _dataStream.ReadExactly(headerBytes, 0, 16);
            var count = BitConverter.ToUInt32(headerBytes, 4);
            Logger.Log($"TOC entries: {count}");

            for (int i = 0; i < count; i++)
            {
                var pathLenBytes = new byte[2];
                _dataStream.ReadExactly(pathLenBytes, 0, 2);
                var pathLen = BitConverter.ToUInt16(pathLenBytes, 0);
                var pathBytes = new byte[pathLen];
                _dataStream.ReadExactly(pathBytes, 0, pathLen);
                var path = System.Text.Encoding.UTF8.GetString(pathBytes);
                var offsetBytes = new byte[8];
                _dataStream.ReadExactly(offsetBytes, 0, 8);
                var offset = BitConverter.ToInt64(offsetBytes, 0);
                var sizeBytes = new byte[4];
                _dataStream.ReadExactly(sizeBytes, 0, 4);
                var size = BitConverter.ToInt32(sizeBytes, 0);

                var normalizedPath = NormalizePath(path);
                _toc[normalizedPath] = (offset, size);
                _allPaths.Add(normalizedPath);
            }
            Logger.Log($"TOC loaded: {_toc.Count} entries");
        }

        private static string NormalizePath(string path)
        {
            if (path.StartsWith("icons/", StringComparison.OrdinalIgnoreCase) ||
                path.StartsWith("icons\\", StringComparison.OrdinalIgnoreCase))
                path = path[6..];
            return path.Replace('\\', '/');
        }

        public List<IconInfo> Search(string query, int limit = 500)
        {
            var results = new List<IconInfo>();
            var words = query.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            if (words.Length == 0) return results;

            using var conn = new SQLiteConnection($"Data Source={_dbPath};Version=3;");
            conn.Open();

            var conditions = new List<string>();
            var parameters = new List<SQLiteParameter>();
            for (int i = 0; i < words.Length; i++)
            {
                conditions.Add($"search_text LIKE @p{i}");
                parameters.Add(new SQLiteParameter($"@p{i}", $"%{words[i]}%"));
            }

            using var cmd = conn.CreateCommand();
            cmd.CommandText = $"SELECT filepath FROM icons WHERE {string.Join(" AND ", conditions)} LIMIT @limit";
            cmd.Parameters.AddRange(parameters.ToArray());
            cmd.Parameters.AddWithValue("@limit", limit);

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                var normalizedPath = NormalizePath(reader.GetString(0));
                if (_toc.TryGetValue(normalizedPath, out var info))
                    results.Add(new IconInfo { FilePath = normalizedPath, Offset = info.offset, Size = info.size });
            }
            Logger.Log($"Search '{query}': {results.Count} results");
            return results;
        }

        public List<IconInfo> GetRandomIcons(int count = 30)
        {
            var results = new List<IconInfo>();
            var indices = new HashSet<int>();
            while (results.Count < count && indices.Count < _allPaths.Count)
            {
                var idx = _random.Next(_allPaths.Count);
                if (indices.Add(idx) && _toc.TryGetValue(_allPaths[idx], out var info))
                    results.Add(new IconInfo { FilePath = _allPaths[idx], Offset = info.offset, Size = info.size });
            }
            return results;
        }

        public byte[] GetIconData(string path)
        {
            path = NormalizePath(path);
            if (!_toc.TryGetValue(path, out var info)) return null;

            lock (_dataStream)
            {
                var data = new byte[info.size];
                _dataStream.Seek(info.offset, SeekOrigin.Begin);
                _dataStream.ReadExactly(data, 0, info.size);
                return data;
            }
        }

        public void Dispose()
        {
            Logger.Log("IconService disposed");
            _dataStream?.Dispose();
        }
    }
}
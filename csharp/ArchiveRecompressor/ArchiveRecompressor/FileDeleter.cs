using System;
using System.Collections.Generic;
using System.IO;

namespace ArchiveRecompressor
{
    public static class FileDeleter
    {
        public static void DeleteOriginalArchives(List<(string orig, string sevenZ)> pairs, string label)
        {
            if (pairs.Count == 0) return;

            var count = 0;
            long total = 0;

            foreach (var (orig, _) in pairs)
            {
                try
                {
                    if (File.Exists(orig))
                    {
                        total += new FileInfo(orig).Length;
                        File.Delete(orig);
                        count++;
                    }
                }
                catch { }
            }

            Console.WriteLine($"\n{label}: удалено {count} файлов, освобождено {ArchiveConverter.FormatSize(total)}");
        }
    }
}
using System;
using System.Collections.Generic;
using System.IO;

namespace Mp3ToOpus
{
    public static class FileDeleter
    {
        public static void DeleteMp3Files(List<(string mp3, string opus)> pairs, string label)
        {
            if (pairs.Count == 0) return;

            var count = 0;
            long total = 0;

            foreach (var (mp3, _) in pairs)
            {
                try
                {
                    if (File.Exists(mp3))
                    {
                        total += new FileInfo(mp3).Length;
                        File.Delete(mp3);
                        count++;
                    }
                }
                catch { }
            }

            Console.WriteLine($"\n{label}: удалено {count} файлов, освобождено {AudioConverter.FormatSize(total)}");
        }
    }
}
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Mp3ToOpus
{
    public static class FileScanner
    {
        public static List<string> FindAudioFiles(string folder, string[] extensions = null)
        {
            extensions ??= new[] { ".mp3" };
            var patterns = extensions.Select(e => $"*{e}").ToArray();

            using var progress = new FileSearchProgress();
            var found = 0;
            var files = new List<string>();
            var startTime = DateTime.Now;

            foreach (var pattern in patterns)
            {
                foreach (var file in Directory.EnumerateFiles(folder, pattern, SearchOption.AllDirectories))
                {
                    files.Add(file);
                    found++;
                    progress.Update(file, found);
                }
            }

            progress.Finish(found, DateTime.Now - startTime);
            return files;
        }
    }
}
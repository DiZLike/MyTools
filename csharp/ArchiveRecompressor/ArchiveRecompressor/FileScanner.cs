using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace ArchiveRecompressor
{
    public static class FileScanner
    {
        // Расширения архивов, которые 7z умеет распаковывать
        private static readonly HashSet<string> ArchiveExtensions = new(StringComparer.OrdinalIgnoreCase)
        {
            ".zip", ".rar", ".tar", ".gz", ".bz2", ".bzip2", ".xz", ".lzma", ".lz",
            ".cab", ".arj", ".lzh", ".lha", ".iso", ".z", ".taz", ".tbz", ".tbz2", ".tgz",
            ".txz", ".tlz", ".001", ".wim", ".swm", ".esd", ".fat", ".ntfs", ".vhd", ".vmdk",
            ".dmg", ".hfs", ".xar", ".cpio", ".rpm", ".deb", ".chm", ".hxs", ".msi", ".doc",
            ".xls", ".ppt", ".msp", ".squashfs", ".cramfs", ".scap", ".uefi"
        };

        public static List<string> FindArchiveFiles(string folder)
        {
            using var progress = new FileSearchProgress();
            var found = 0;
            var files = new List<string>();
            var startTime = DateTime.Now;

            foreach (var ext in ArchiveExtensions)
            {
                var pattern = $"*{ext}";
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

        public static bool IsArchiveFile(string path)
        {
            var ext = Path.GetExtension(path);
            return ArchiveExtensions.Contains(ext);
        }
    }
}
using System;
using System.Collections.Generic;

namespace ByteHound.Models
{
    public class FileSystemItem
    {
        public string Name { get; set; }
        public string FullPath { get; set; }
        public long SizeBytes { get; set; }
        public bool IsFile { get; set; }
        public string Extension { get; set; }
        public DateTime Created { get; set; }
        public DateTime Modified { get; set; }
        public bool IsAccessible { get; set; } = true;
        public List<FileSystemItem> Children { get; set; } = new List<FileSystemItem>();

        public string FormattedSize
        {
            get
            {
                string[] sizes = { "B", "KB", "MB", "GB", "TB" };
                double len = SizeBytes;
                int order = 0;
                while (len >= 1024 && order < sizes.Length - 1)
                {
                    order++;
                    len /= 1024;
                }
                return $"{len:0.##} {sizes[order]}";
            }
        }

        public string SizePercentage(FileSystemItem parent)
        {
            if (parent == null || parent.SizeBytes == 0)
                return "0%";
            double percent = (double)SizeBytes / parent.SizeBytes * 100;
            return $"{percent:0.0}%";
        }
    }
}
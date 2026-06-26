using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using ByteHound.Models;

namespace ByteHound.Services
{
    public class ScanProgress
    {
        public int FilesFound { get; set; }
        public int FoldersFound { get; set; }
        public string CurrentPath { get; set; }
    }

    public class DiskScanner
    {
        private int _fileCount;
        private int _folderCount;
        private readonly object _lockObj = new object();

        public async Task<FileSystemItem> ScanAsync(
            string path,
            IProgress<ScanProgress> progress,
            CancellationToken cancellationToken)
        {
            _fileCount = 0;
            _folderCount = 0;

            return await Task.Run(() => ScanDirectory(path, progress, cancellationToken),
                cancellationToken);
        }

        private FileSystemItem ScanDirectory(
            string path,
            IProgress<ScanProgress> progress,
            CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();

            var dirInfo = new DirectoryInfo(path);
            var item = new FileSystemItem
            {
                Name = string.IsNullOrEmpty(dirInfo.Name) ? dirInfo.FullName : dirInfo.Name,
                FullPath = dirInfo.FullName,
                IsFile = false,
                Created = dirInfo.CreationTime,
                Modified = dirInfo.LastWriteTime,
                Extension = ""
            };

            // Сканируем файлы
            try
            {
                foreach (var file in dirInfo.EnumerateFiles())
                {
                    ct.ThrowIfCancellationRequested();
                    try
                    {
                        var fileItem = new FileSystemItem
                        {
                            Name = file.Name,
                            FullPath = file.FullName,
                            SizeBytes = file.Length,
                            IsFile = true,
                            Extension = file.Extension.ToLower(),
                            Created = file.CreationTime,
                            Modified = file.LastWriteTime,
                            IsAccessible = true
                        };
                        item.Children.Add(fileItem);
                        item.SizeBytes += file.Length;

                        lock (_lockObj)
                        {
                            _fileCount++;
                        }
                        progress?.Report(new ScanProgress
                        {
                            FilesFound = _fileCount,
                            FoldersFound = _folderCount,
                            CurrentPath = file.FullName
                        });
                    }
                    catch
                    {
                        // Пропускаем недоступные файлы
                    }
                }
            }
            catch (UnauthorizedAccessException)
            {
                item.IsAccessible = false;
            }
            catch (DirectoryNotFoundException)
            {
                item.IsAccessible = false;
            }

            // Сканируем подпапки
            try
            {
                foreach (var dir in dirInfo.EnumerateDirectories())
                {
                    ct.ThrowIfCancellationRequested();
                    try
                    {
                        var childItem = ScanDirectory(dir.FullName, progress, ct);
                        item.Children.Add(childItem);
                        item.SizeBytes += childItem.SizeBytes;

                        lock (_lockObj)
                        {
                            _folderCount++;
                        }
                        progress?.Report(new ScanProgress
                        {
                            FilesFound = _fileCount,
                            FoldersFound = _folderCount,
                            CurrentPath = dir.FullName
                        });
                    }
                    catch (OperationCanceledException)
                    {
                        throw;
                    }
                    catch
                    {
                        item.Children.Add(new FileSystemItem
                        {
                            Name = dir.Name,
                            FullPath = dir.FullName,
                            IsFile = false,
                            IsAccessible = false
                        });
                    }
                }
            }
            catch (UnauthorizedAccessException)
            {
                item.IsAccessible = false;
            }
            catch (DirectoryNotFoundException)
            {
                item.IsAccessible = false;
            }

            // Сортировка: папки сверху, по убыванию размера
            item.Children = item.Children
                .OrderByDescending(x => x.IsFile ? 0 : 1)
                .ThenByDescending(x => x.SizeBytes)
                .ToList();

            return item;
        }
    }
}
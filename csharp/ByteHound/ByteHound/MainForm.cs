using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using ByteHound.Models;
using ByteHound.Services;

namespace ByteHound
{
    public partial class MainForm : Form
    {
        private DiskScanner _scanner;
        private CancellationTokenSource _cts;
        private FileSystemItem _rootItem;
        private bool _isScanning;
        private string _selectedPath;

        // Константы для иконок
        private const int ICON_FOLDER = 0;
        private const int ICON_FOLDER_LOCKED = 1;
        private const int ICON_FILE = 2;
        private const int ICON_FILE_LARGE = 3;

        // Порог для "большого" файла
        private const long LARGE_FILE_THRESHOLD = 1024L * 1024 * 1024; // 1 GB

        public MainForm()
        {
            InitializeComponent();
            _scanner = new DiskScanner();
            ClearInfo();
            SetupContextMenuIcons();
        }

        /// <summary>
        /// Настройка иконок контекстного меню
        /// </summary>
        private void SetupContextMenuIcons()
        {
            // Используем системные иконки, если доступны
            try
            {
                openExplorerMenuItem.Image = SystemIcons.Application.ToBitmap();
                deleteMenuItem.Image = SystemIcons.Error.ToBitmap();
                copyPathMenuItem.Image = SystemIcons.Information.ToBitmap();
            }
            catch
            {
                // Игнорируем ошибки с иконками меню
            }
        }

        private async void BrowseButton_Click(object sender, EventArgs e)
        {
            using (var dialog = new FolderBrowserDialog())
            {
                dialog.Description = "Выберите папку или диск для анализа";
                dialog.ShowNewFolderButton = false;
                dialog.RootFolder = Environment.SpecialFolder.MyComputer;

                if (dialog.ShowDialog() == DialogResult.OK)
                {
                    _selectedPath = dialog.SelectedPath;
                    pathTextBox.Text = _selectedPath;
                    scanButton.Enabled = true;
                    statusLabel.Text = $"Выбрано: {_selectedPath}";
                }
            }
        }

        private async void ScanButton_Click(object sender, EventArgs e)
        {
            if (_isScanning || string.IsNullOrEmpty(_selectedPath))
                return;

            _isScanning = true;
            scanButton.Enabled = false;
            browseButton.Enabled = false;
            cancelButton.Enabled = true;
            toolStripProgressBar.Visible = true;
            toolStripProgressBar.Style = ProgressBarStyle.Marquee;
            treeView.Nodes.Clear();
            ClearInfo();
            statusLabel.Text = "Сканирование...";

            _cts = new CancellationTokenSource();
            var progress = new Progress<ScanProgress>(p =>
            {
                statusLabel.Text = $"Сканирование... Файлов: {p.FilesFound:N0}, Папок: {p.FoldersFound:N0}";
            });

            try
            {
                _rootItem = await _scanner.ScanAsync(_selectedPath, progress, _cts.Token);

                if (_rootItem != null)
                {
                    BuildTreeView(_rootItem);
                    var totalFiles = CountAllFiles(_rootItem);
                    var totalFolders = CountAllFolders(_rootItem) - 1; // Вычитаем корневую
                    statusLabel.Text = $"Готово. Всего: {totalFiles:N0} файлов, {totalFolders:N0} папок, занято {_rootItem.FormattedSize}";
                }
                else
                {
                    statusLabel.Text = "Сканирование завершено, но данные не получены";
                }
            }
            catch (OperationCanceledException)
            {
                statusLabel.Text = "Сканирование отменено пользователем";
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Ошибка при сканировании: {ex.Message}",
                    "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
                statusLabel.Text = "Ошибка сканирования";
            }
            finally
            {
                _isScanning = false;
                scanButton.Enabled = true;
                browseButton.Enabled = true;
                cancelButton.Enabled = false;
                toolStripProgressBar.Visible = false;
                _cts?.Dispose();
                _cts = null;
            }
        }

        private void CancelButton_Click(object sender, EventArgs e)
        {
            _cts?.Cancel();
        }

        private void BuildTreeView(FileSystemItem item)
        {
            treeView.BeginUpdate();
            try
            {
                treeView.Nodes.Clear();
                var rootNode = CreateTreeNode(item);
                treeView.Nodes.Add(rootNode);
                rootNode.Expand();
            }
            finally
            {
                treeView.EndUpdate();
            }
        }

        private TreeNode CreateTreeNode(FileSystemItem item)
        {
            string sizeText = item.FormattedSize;
            string text = $"{item.Name}  ({sizeText})";

            var node = new TreeNode(text)
            {
                Tag = item
            };

            // Установка иконки
            if (item.IsFile)
            {
                node.ImageIndex = item.SizeBytes >= LARGE_FILE_THRESHOLD
                    ? ICON_FILE_LARGE
                    : ICON_FILE;
                node.SelectedImageIndex = node.ImageIndex;
            }
            else
            {
                node.ImageIndex = item.IsAccessible
                    ? ICON_FOLDER
                    : ICON_FOLDER_LOCKED;
                node.SelectedImageIndex = node.ImageIndex;
            }

            // Цвет для недоступных элементов
            if (!item.IsAccessible)
            {
                node.ForeColor = Color.Gray;
            }

            // Добавляем плейсхолдер для папок с содержимым
            if (!item.IsFile && item.IsAccessible && item.Children.Count > 0)
            {
                node.Nodes.Add(new TreeNode("Загрузка...") { Tag = "placeholder" });
            }

            return node;
        }

        private void TreeView_BeforeExpand(object sender, TreeViewCancelEventArgs e)
        {
            var node = e.Node;
            if (node.Tag is FileSystemItem item && !item.IsFile && item.IsAccessible)
            {
                if (node.Nodes.Count == 1 && node.Nodes[0].Tag?.ToString() == "placeholder")
                {
                    Cursor.Current = Cursors.WaitCursor;
                    node.Nodes.Clear();

                    treeView.BeginUpdate();
                    try
                    {
                        foreach (var child in item.Children)
                        {
                            var childNode = CreateTreeNode(child);
                            node.Nodes.Add(childNode);
                        }
                    }
                    finally
                    {
                        treeView.EndUpdate();
                        Cursor.Current = Cursors.Default;
                    }
                }
            }
        }

        private void TreeView_AfterSelect(object sender, TreeViewEventArgs e)
        {
            var node = e.Node;
            if (node?.Tag is FileSystemItem item)
            {
                DisplayItemInfo(item);
            }
            else
            {
                ClearInfo();
            }
        }

        private void DisplayItemInfo(FileSystemItem item)
        {
            // Заголовок с обрезкой
            infoTitle.Text = TruncateText(item.Name, 50);
            toolTip.SetToolTip(infoTitle, item.Name);

            infoType.Text = $"Тип: {(item.IsFile ? "📄 Файл" : "📁 Папка")}";

            infoName.Text = $"Имя: {TruncateText(item.Name, 45)}";
            toolTip.SetToolTip(infoName, item.Name);

            // Путь с переносом
            string path = item.FullPath;
            infoPath.Text = $"Путь: {TruncatePath(path, 70)}";
            toolTip.SetToolTip(infoPath, path);

            infoSize.Text = $"Размер: {item.FormattedSize}";

            if (!item.IsFile)
            {
                int fileCount = CountFilesInFolder(item);
                int folderCount = CountFoldersInFolder(item);
                infoFiles.Text = $"Файлов: {fileCount:N0}";
                infoFolders.Text = $"Подпапок: {folderCount:N0}";
            }
            else
            {
                infoFiles.Text = $"Расширение: {(string.IsNullOrEmpty(item.Extension) ? "нет" : item.Extension)}";
                infoFolders.Text = $"Изменён: {item.Modified:dd.MM.yyyy HH:mm}";
            }

            infoCreated.Text = $"Создан: {item.Created:dd.MM.yyyy HH:mm}";
        }

        private void ClearInfo()
        {
            infoTitle.Text = "Информация";
            infoType.Text = "Выберите элемент";
            infoName.Text = "";
            infoPath.Text = "";
            infoSize.Text = "";
            infoFiles.Text = "";
            infoFolders.Text = "";
            infoCreated.Text = "";

            toolTip.SetToolTip(infoTitle, "");
            toolTip.SetToolTip(infoName, "");
            toolTip.SetToolTip(infoPath, "");
        }

        private void TreeView_MouseClick(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right)
            {
                var node = treeView.GetNodeAt(e.Location);
                if (node != null)
                {
                    treeView.SelectedNode = node;
                }
            }
        }

        private void OpenExplorerMenuItem_Click(object sender, EventArgs e)
        {
            if (treeView.SelectedNode?.Tag is FileSystemItem item)
            {
                try
                {
                    if (item.IsFile)
                    {
                        Process.Start("explorer.exe", $"/select,\"{item.FullPath}\"");
                    }
                    else
                    {
                        Process.Start("explorer.exe", item.FullPath);
                    }
                    statusLabel.Text = $"Открыто в проводнике: {item.Name}";
                }
                catch (Exception ex)
                {
                    MessageBox.Show($"Не удалось открыть проводник: {ex.Message}",
                        "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
            }
        }

        private void DeleteMenuItem_Click(object sender, EventArgs e)
        {
            if (treeView.SelectedNode?.Tag is FileSystemItem item)
            {
                string type = item.IsFile ? "файл" : "папку";
                var result = MessageBox.Show(
                    $"Вы уверены, что хотите удалить {type} \"{item.Name}\" ({item.FormattedSize})?\n\n" +
                    "Это действие нельзя отменить!",
                    "Подтверждение удаления",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Warning,
                    MessageBoxDefaultButton.Button2);

                if (result == DialogResult.Yes)
                {
                    try
                    {
                        if (item.IsFile)
                        {
                            File.Delete(item.FullPath);
                        }
                        else
                        {
                            Directory.Delete(item.FullPath, true);
                        }

                        var node = treeView.SelectedNode;
                        UpdateParentSizes(node, item.SizeBytes);
                        node.Remove();
                        ClearInfo();

                        statusLabel.Text = $"Удалено: {item.Name}";
                    }
                    catch (Exception ex)
                    {
                        MessageBox.Show($"Не удалось удалить: {ex.Message}",
                            "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    }
                }
            }
        }

        private void UpdateParentSizes(TreeNode node, long removedSize)
        {
            var parent = node.Parent;
            while (parent != null)
            {
                if (parent.Tag is FileSystemItem parentItem)
                {
                    parentItem.SizeBytes = Math.Max(0, parentItem.SizeBytes - removedSize);
                    UpdateTreeNodeText(parent);
                }
                parent = parent.Parent;
            }
        }

        private void UpdateTreeNodeText(TreeNode node)
        {
            if (node.Tag is FileSystemItem item)
            {
                string text = $"{item.Name}  ({item.FormattedSize})";
                node.Text = text;
            }
        }

        private void CopyPathMenuItem_Click(object sender, EventArgs e)
        {
            if (treeView.SelectedNode?.Tag is FileSystemItem item)
            {
                Clipboard.SetText(item.FullPath);
                statusLabel.Text = $"Путь скопирован: {item.Name}";
            }
        }

        private FileSystemItem FilterItem(FileSystemItem item, string filter)
        {
            if (item.Name.ToLower().Contains(filter))
            {
                return item;
            }

            if (!item.IsFile)
            {
                var filteredChildren = new List<FileSystemItem>();
                foreach (var child in item.Children)
                {
                    var filtered = FilterItem(child, filter);
                    if (filtered != null)
                    {
                        filteredChildren.Add(filtered);
                    }
                }

                if (filteredChildren.Count > 0)
                {
                    return new FileSystemItem
                    {
                        Name = item.Name,
                        FullPath = item.FullPath,
                        IsFile = false,
                        IsAccessible = item.IsAccessible,
                        SizeBytes = filteredChildren.Sum(x => x.SizeBytes),
                        Children = filteredChildren
                    };
                }
            }

            return null;
        }

        private void TreeView_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Delete)
            {
                DeleteMenuItem_Click(sender, e);
                e.Handled = true;
                e.SuppressKeyPress = true;
            }
            else if (e.Control && e.KeyCode == Keys.C)
            {
                CopyPathMenuItem_Click(sender, e);
                e.Handled = true;
                e.SuppressKeyPress = true;
            }
        }

        private void MainForm_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.Control && e.KeyCode == Keys.O)
            {
                BrowseButton_Click(sender, e);
                e.Handled = true;
            }
            else if (e.KeyCode == Keys.F5)
            {
                if (!_isScanning && !string.IsNullOrEmpty(_selectedPath))
                {
                    ScanButton_Click(sender, e);
                }
                e.Handled = true;
            }
            else if (e.KeyCode == Keys.Escape)
            {
                if (_isScanning)
                {
                    CancelButton_Click(sender, e);
                }
                e.Handled = true;
            }
        }

        private void MainForm_Resize(object sender, EventArgs e)
        {
            // Обновляем максимальную ширину для информационных лейблов
            int maxWidth = Math.Max(200, infoPanel.Width - 30);
            infoTitle.MaximumSize = new Size(maxWidth, 0);
            infoName.MaximumSize = new Size(maxWidth, 0);
            infoType.MaximumSize = new Size(maxWidth, 0);
            infoPath.MaximumSize = new Size(maxWidth, 60);
            infoSize.MaximumSize = new Size(maxWidth, 0);
            infoFiles.MaximumSize = new Size(maxWidth, 0);
            infoFolders.MaximumSize = new Size(maxWidth, 0);
            infoCreated.MaximumSize = new Size(maxWidth, 0);
        }

        #region Вспомогательные методы

        private int CountAllFiles(FileSystemItem item)
        {
            int count = item.IsFile ? 1 : 0;
            foreach (var child in item.Children)
            {
                count += CountAllFiles(child);
            }
            return count;
        }

        private int CountAllFolders(FileSystemItem item)
        {
            int count = item.IsFile ? 0 : 1;
            foreach (var child in item.Children)
            {
                if (!child.IsFile)
                {
                    count += CountAllFolders(child);
                }
            }
            return count;
        }

        private int CountFilesInFolder(FileSystemItem folder)
        {
            int count = 0;
            foreach (var child in folder.Children)
            {
                if (child.IsFile)
                    count++;
                else
                    count += CountFilesInFolder(child);
            }
            return count;
        }

        private int CountFoldersInFolder(FileSystemItem folder)
        {
            int count = 0;
            foreach (var child in folder.Children)
            {
                if (!child.IsFile)
                {
                    count++;
                    count += CountFoldersInFolder(child);
                }
            }
            return count;
        }

        private string TruncateText(string text, int maxLength)
        {
            if (string.IsNullOrEmpty(text))
                return "";
            if (text.Length <= maxLength)
                return text;
            return text.Substring(0, maxLength - 3) + "...";
        }

        private string TruncatePath(string path, int maxLength)
        {
            if (string.IsNullOrEmpty(path))
                return "";
            if (path.Length <= maxLength)
                return path;
            return "..." + path.Substring(path.Length - maxLength + 3);
        }

        #endregion
    }
}
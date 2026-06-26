using System.Drawing;
using System.Windows.Forms;

namespace ByteHound
{
    partial class MainForm
    {
        private System.ComponentModel.IContainer components = null;
        private TreeView treeView;
        private TextBox pathTextBox;
        private Button browseButton;
        private Button scanButton;
        private Button cancelButton;
        private Panel infoPanel;
        private Panel topPanel;
        private SplitContainer splitContainer;
        private Label infoTitle;
        private Label infoType;
        private Label infoName;
        private Label infoPath;
        private Label infoSize;
        private Label infoFiles;
        private Label infoFolders;
        private Label infoCreated;
        private ContextMenuStrip contextMenu;
        private ToolStripMenuItem openExplorerMenuItem;
        private ToolStripMenuItem deleteMenuItem;
        private ToolStripMenuItem copyPathMenuItem;
        private ImageList iconList;
        private StatusStrip statusStrip;
        private ToolStripStatusLabel statusLabel;
        private ToolStripProgressBar toolStripProgressBar;
        private ToolTip toolTip;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            components = new System.ComponentModel.Container();
            topPanel = new Panel();
            pathTextBox = new TextBox();
            browseButton = new Button();
            scanButton = new Button();
            cancelButton = new Button();
            splitContainer = new SplitContainer();
            treeView = new TreeView();
            contextMenu = new ContextMenuStrip(components);
            openExplorerMenuItem = new ToolStripMenuItem();
            deleteMenuItem = new ToolStripMenuItem();
            copyPathMenuItem = new ToolStripMenuItem();
            iconList = new ImageList(components);
            infoPanel = new Panel();
            infoTitle = new Label();
            infoType = new Label();
            infoName = new Label();
            infoPath = new Label();
            infoSize = new Label();
            infoFiles = new Label();
            infoFolders = new Label();
            infoCreated = new Label();
            statusStrip = new StatusStrip();
            statusLabel = new ToolStripStatusLabel();
            toolStripProgressBar = new ToolStripProgressBar();
            toolTip = new ToolTip(components);
            topPanel.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)splitContainer).BeginInit();
            splitContainer.Panel1.SuspendLayout();
            splitContainer.Panel2.SuspendLayout();
            splitContainer.SuspendLayout();
            contextMenu.SuspendLayout();
            infoPanel.SuspendLayout();
            statusStrip.SuspendLayout();
            SuspendLayout();
            // 
            // topPanel
            // 
            topPanel.Controls.Add(pathTextBox);
            topPanel.Controls.Add(browseButton);
            topPanel.Controls.Add(scanButton);
            topPanel.Controls.Add(cancelButton);
            topPanel.Dock = DockStyle.Top;
            topPanel.Location = new Point(0, 0);
            topPanel.Name = "topPanel";
            topPanel.Padding = new Padding(10);
            topPanel.Size = new Size(1100, 50);
            topPanel.TabIndex = 0;
            // 
            // pathTextBox
            // 
            pathTextBox.Location = new Point(10, 15);
            pathTextBox.Name = "pathTextBox";
            pathTextBox.ReadOnly = true;
            pathTextBox.Size = new Size(500, 23);
            pathTextBox.TabIndex = 0;
            pathTextBox.Text = "Выберите папку для сканирования...";
            // 
            // browseButton
            // 
            browseButton.Location = new Point(520, 14);
            browseButton.Name = "browseButton";
            browseButton.Size = new Size(130, 25);
            browseButton.TabIndex = 1;
            browseButton.Text = "📁 Выбрать папку";
            browseButton.UseVisualStyleBackColor = true;
            browseButton.Click += BrowseButton_Click;
            // 
            // scanButton
            // 
            scanButton.Enabled = false;
            scanButton.Location = new Point(660, 14);
            scanButton.Name = "scanButton";
            scanButton.Size = new Size(120, 25);
            scanButton.TabIndex = 2;
            scanButton.Text = "▶ Сканировать";
            scanButton.UseVisualStyleBackColor = true;
            scanButton.Click += ScanButton_Click;
            // 
            // cancelButton
            // 
            cancelButton.Enabled = false;
            cancelButton.ForeColor = Color.Red;
            cancelButton.Location = new Point(790, 14);
            cancelButton.Name = "cancelButton";
            cancelButton.Size = new Size(80, 25);
            cancelButton.TabIndex = 3;
            cancelButton.Text = "■ Стоп";
            cancelButton.UseVisualStyleBackColor = true;
            cancelButton.Click += CancelButton_Click;
            // 
            // splitContainer
            // 
            splitContainer.Dock = DockStyle.Fill;
            splitContainer.Location = new Point(0, 50);
            splitContainer.Name = "splitContainer";
            // 
            // splitContainer.Panel1
            // 
            splitContainer.Panel1.Controls.Add(treeView);
            // 
            // splitContainer.Panel2
            // 
            splitContainer.Panel2.Controls.Add(infoPanel);
            splitContainer.Size = new Size(1100, 564);
            splitContainer.SplitterDistance = 750;
            splitContainer.TabIndex = 1;
            // 
            // treeView
            // 
            treeView.ContextMenuStrip = contextMenu;
            treeView.Dock = DockStyle.Fill;
            treeView.Font = new Font("Segoe UI", 9.5F);
            treeView.FullRowSelect = true;
            treeView.HideSelection = false;
            treeView.ImageIndex = 0;
            treeView.ImageList = iconList;
            treeView.Location = new Point(0, 0);
            treeView.Name = "treeView";
            treeView.SelectedImageIndex = 0;
            treeView.Size = new Size(750, 564);
            treeView.TabIndex = 0;
            treeView.BeforeExpand += TreeView_BeforeExpand;
            treeView.AfterSelect += TreeView_AfterSelect;
            treeView.KeyDown += TreeView_KeyDown;
            treeView.MouseClick += TreeView_MouseClick;
            // 
            // contextMenu
            // 
            contextMenu.Items.AddRange(new ToolStripItem[] { openExplorerMenuItem, deleteMenuItem, copyPathMenuItem });
            contextMenu.Name = "contextMenu";
            contextMenu.Size = new Size(200, 70);
            // 
            // openExplorerMenuItem
            // 
            openExplorerMenuItem.Name = "openExplorerMenuItem";
            openExplorerMenuItem.Size = new Size(199, 22);
            openExplorerMenuItem.Text = "Открыть в проводнике";
            openExplorerMenuItem.Click += OpenExplorerMenuItem_Click;
            // 
            // deleteMenuItem
            // 
            deleteMenuItem.ForeColor = Color.Red;
            deleteMenuItem.Name = "deleteMenuItem";
            deleteMenuItem.Size = new Size(199, 22);
            deleteMenuItem.Text = "Удалить";
            deleteMenuItem.Click += DeleteMenuItem_Click;
            // 
            // copyPathMenuItem
            // 
            copyPathMenuItem.Name = "copyPathMenuItem";
            copyPathMenuItem.Size = new Size(199, 22);
            copyPathMenuItem.Text = "Копировать путь";
            copyPathMenuItem.Click += CopyPathMenuItem_Click;
            // 
            // iconList
            // 
            iconList.ColorDepth = ColorDepth.Depth32Bit;
            iconList.ImageSize = new Size(16, 16);
            iconList.TransparentColor = Color.Transparent;
            // 
            // infoPanel
            // 
            infoPanel.Controls.Add(infoTitle);
            infoPanel.Controls.Add(infoType);
            infoPanel.Controls.Add(infoName);
            infoPanel.Controls.Add(infoPath);
            infoPanel.Controls.Add(infoSize);
            infoPanel.Controls.Add(infoFiles);
            infoPanel.Controls.Add(infoFolders);
            infoPanel.Controls.Add(infoCreated);
            infoPanel.Dock = DockStyle.Fill;
            infoPanel.Location = new Point(0, 0);
            infoPanel.Name = "infoPanel";
            infoPanel.Padding = new Padding(15);
            infoPanel.Size = new Size(346, 564);
            infoPanel.TabIndex = 0;
            // 
            // infoTitle
            // 
            infoTitle.AutoSize = true;
            infoTitle.Font = new Font("Segoe UI", 14F, FontStyle.Bold);
            infoTitle.Location = new Point(30, 30);
            infoTitle.MaximumSize = new Size(400, 0);
            infoTitle.Name = "infoTitle";
            infoTitle.Size = new Size(138, 25);
            infoTitle.TabIndex = 0;
            infoTitle.Text = "Информация";
            toolTip.SetToolTip(infoTitle, "Информация о выбранном элементе");
            // 
            // infoType
            // 
            infoType.AutoSize = true;
            infoType.Location = new Point(30, 70);
            infoType.MaximumSize = new Size(400, 0);
            infoType.Name = "infoType";
            infoType.Size = new Size(0, 15);
            infoType.TabIndex = 1;
            // 
            // infoName
            // 
            infoName.AutoSize = true;
            infoName.Location = new Point(30, 95);
            infoName.MaximumSize = new Size(400, 0);
            infoName.Name = "infoName";
            infoName.Size = new Size(0, 15);
            infoName.TabIndex = 2;
            // 
            // infoPath
            // 
            infoPath.Location = new Point(15, 121);
            infoPath.MaximumSize = new Size(400, 60);
            infoPath.Name = "infoPath";
            infoPath.Size = new Size(319, 40);
            infoPath.TabIndex = 3;
            // 
            // infoSize
            // 
            infoSize.AutoSize = true;
            infoSize.Font = new Font("Segoe UI", 11F, FontStyle.Bold);
            infoSize.Location = new Point(30, 170);
            infoSize.MaximumSize = new Size(400, 0);
            infoSize.Name = "infoSize";
            infoSize.Size = new Size(0, 20);
            infoSize.TabIndex = 4;
            // 
            // infoFiles
            // 
            infoFiles.AutoSize = true;
            infoFiles.Location = new Point(30, 200);
            infoFiles.MaximumSize = new Size(400, 0);
            infoFiles.Name = "infoFiles";
            infoFiles.Size = new Size(0, 15);
            infoFiles.TabIndex = 5;
            // 
            // infoFolders
            // 
            infoFolders.AutoSize = true;
            infoFolders.Location = new Point(30, 225);
            infoFolders.MaximumSize = new Size(400, 0);
            infoFolders.Name = "infoFolders";
            infoFolders.Size = new Size(0, 15);
            infoFolders.TabIndex = 6;
            // 
            // infoCreated
            // 
            infoCreated.AutoSize = true;
            infoCreated.Location = new Point(30, 250);
            infoCreated.MaximumSize = new Size(400, 0);
            infoCreated.Name = "infoCreated";
            infoCreated.Size = new Size(0, 15);
            infoCreated.TabIndex = 7;
            // 
            // statusStrip
            // 
            statusStrip.Items.AddRange(new ToolStripItem[] { statusLabel, toolStripProgressBar });
            statusStrip.Location = new Point(0, 614);
            statusStrip.Name = "statusStrip";
            statusStrip.Size = new Size(1100, 22);
            statusStrip.TabIndex = 2;
            // 
            // statusLabel
            // 
            statusLabel.Name = "statusLabel";
            statusLabel.Size = new Size(1085, 17);
            statusLabel.Spring = true;
            statusLabel.Text = "Готов";
            statusLabel.TextAlign = ContentAlignment.MiddleLeft;
            // 
            // toolStripProgressBar
            // 
            toolStripProgressBar.Name = "toolStripProgressBar";
            toolStripProgressBar.Size = new Size(200, 20);
            toolStripProgressBar.Visible = false;
            // 
            // toolTip
            // 
            toolTip.AutoPopDelay = 5000;
            toolTip.InitialDelay = 500;
            toolTip.ReshowDelay = 100;
            // 
            // MainForm
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            ClientSize = new Size(1100, 636);
            Controls.Add(splitContainer);
            Controls.Add(statusStrip);
            Controls.Add(topPanel);
            KeyPreview = true;
            MinimumSize = new Size(800, 500);
            Name = "MainForm";
            StartPosition = FormStartPosition.CenterScreen;
            Text = "ByteHound - Анализатор дискового пространства";
            KeyDown += MainForm_KeyDown;
            Resize += MainForm_Resize;
            topPanel.ResumeLayout(false);
            topPanel.PerformLayout();
            splitContainer.Panel1.ResumeLayout(false);
            splitContainer.Panel2.ResumeLayout(false);
            ((System.ComponentModel.ISupportInitialize)splitContainer).EndInit();
            splitContainer.ResumeLayout(false);
            contextMenu.ResumeLayout(false);
            infoPanel.ResumeLayout(false);
            infoPanel.PerformLayout();
            statusStrip.ResumeLayout(false);
            statusStrip.PerformLayout();
            ResumeLayout(false);
            PerformLayout();
        }

        /// <summary>
        /// Инициализация иконок для TreeView
        /// </summary>
        private void InitIconList()
        {
            this.iconList.ImageSize = new Size(16, 16);
            this.iconList.ColorDepth = ColorDepth.Depth32Bit;

            // Индекс 0: Папка (жёлтая)
            this.iconList.Images.Add("folder", CreateFolderIcon());

            // Индекс 1: Папка недоступна (серая)
            this.iconList.Images.Add("folder_locked", CreateLockedFolderIcon());

            // Индекс 2: Файл
            this.iconList.Images.Add("file", CreateFileIcon());

            // Индекс 3: Большой файл (>1GB)
            this.iconList.Images.Add("file_large", CreateLargeFileIcon());
        }

        /// <summary>
        /// Создание иконки папки (жёлтая)
        /// </summary>
        private Image CreateFolderIcon()
        {
            Bitmap bmp = new Bitmap(16, 16);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.Transparent);
                // Основная папка
                g.FillRectangle(Brushes.Gold, 1, 3, 14, 11);
                g.DrawRectangle(Pens.DarkGoldenrod, 1, 3, 14, 11);
                // Верхняя часть
                g.FillRectangle(Brushes.Goldenrod, 1, 1, 7, 4);
                g.DrawRectangle(Pens.DarkGoldenrod, 1, 1, 7, 4);
                // Блик
                g.DrawLine(Pens.LightYellow, 2, 4, 13, 4);
            }
            return bmp;
        }

        /// <summary>
        /// Создание иконки недоступной папки (серая)
        /// </summary>
        private Image CreateLockedFolderIcon()
        {
            Bitmap bmp = new Bitmap(16, 16);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.Transparent);
                // Основная папка
                g.FillRectangle(Brushes.LightGray, 1, 3, 14, 11);
                g.DrawRectangle(Pens.Gray, 1, 3, 14, 11);
                // Верхняя часть
                g.FillRectangle(Brushes.DarkGray, 1, 1, 7, 4);
                g.DrawRectangle(Pens.Gray, 1, 1, 7, 4);
                // Замок
                g.FillRectangle(Brushes.Gray, 6, 6, 5, 5);
                g.DrawRectangle(Pens.DarkGray, 6, 6, 5, 5);
            }
            return bmp;
        }

        /// <summary>
        /// Создание иконки файла
        /// </summary>
        private Image CreateFileIcon()
        {
            Bitmap bmp = new Bitmap(16, 16);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.Transparent);
                // Тело файла
                g.FillRectangle(Brushes.White, 2, 1, 12, 14);
                g.DrawRectangle(Pens.CornflowerBlue, 2, 1, 12, 14);
                // Загнутый уголок
                Point[] points = { new Point(10, 1), new Point(14, 5), new Point(10, 5) };
                g.FillPolygon(Brushes.LightSteelBlue, points);
                g.DrawLine(Pens.CornflowerBlue, 10, 1, 14, 5);
                g.DrawLine(Pens.CornflowerBlue, 10, 1, 10, 5);
                g.DrawLine(Pens.CornflowerBlue, 10, 5, 14, 5);
                // Линии текста
                g.DrawLine(Pens.LightGray, 4, 8, 11, 8);
                g.DrawLine(Pens.LightGray, 4, 10, 11, 10);
                g.DrawLine(Pens.LightGray, 4, 12, 8, 12);
            }
            return bmp;
        }

        /// <summary>
        /// Создание иконки большого файла (красная)
        /// </summary>
        private Image CreateLargeFileIcon()
        {
            Bitmap bmp = new Bitmap(16, 16);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.Transparent);
                // Тело файла
                g.FillRectangle(Brushes.MistyRose, 2, 1, 12, 14);
                g.DrawRectangle(Pens.Red, 2, 1, 12, 14);
                // Загнутый уголок
                Point[] points = { new Point(10, 1), new Point(14, 5), new Point(10, 5) };
                g.FillPolygon(Brushes.LightPink, points);
                g.DrawLine(Pens.Red, 10, 1, 14, 5);
                g.DrawLine(Pens.Red, 10, 1, 10, 5);
                g.DrawLine(Pens.Red, 10, 5, 14, 5);
                // Восклицательный знак
                g.DrawString("!", new Font("Arial", 8, FontStyle.Bold),
                    Brushes.Red, 5, 5);
            }
            return bmp;
        }
    }
}
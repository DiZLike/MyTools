using IconFinder.Controls;
using IconFinder.Monitors;
using IconFinder.Services;
using IconFinder.Singletons;
using System.IO.Compression;
using Timer = System.Windows.Forms.Timer;

namespace IconFinder.Forms
{
    public partial class MainForm : Form
    {
        private const bool EnableTranslationServer = true;

        private IconService _iconService;
        private LibreTranslateService _ltService;
        private List<IconInfo> _currentResults;
        private int _displayedCount = 0;
        private const int PageSize = 30;
        private Timer _searchTimer;
        private bool _isLoading = false;
        private bool _isRandomMode = true;

        public MainForm()
        {
            InitializeComponent();
            LoadUsingMonitor();
            Text = ProgramMeta.Title;
            Logger.Log("MainForm started");

            // Загружаем словарь
            var dictPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Data", "ru-en.dict");
            Translator.LoadDictionary(dictPath);

            InitializeSearch();
            LoadRandomIcons();

            // Всё остальное — после показа формы
            this.Shown += MainForm_Shown;

        }

        private async void MainForm_Shown(object sender, EventArgs e)
        {
            if (EnableTranslationServer)
            {
                // Распаковка архивов с прогрессом
                var extracted = await ExtractArchivesWithProgress();
                if (!extracted)
                {
                    lblStatus.Text = "Ошибка распаковки";
                    return;
                }

                // Запуск сервера перевода
                await StartTranslateServer();
            }
            UsingMonitor.Info.AddRun();
        }
        private async void LoadUsingMonitor()
        {
            await UsingMonitor.Load();
        }

        private async Task<bool> ExtractArchivesWithProgress()
        {
            var archives = new (string archiveName, string extractDir)[]
            {
        ("python.zip", Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Data", "Python")),
        ("argos-translate.zip", Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".local", "share"))
            };

            // Собираем список того, что реально нужно распаковать
            var toExtract = new List<(string archiveName, string extractDir)>();
            foreach (var (archiveName, extractDir) in archives)
            {
                var archivePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Data", archiveName);

                if (Directory.Exists(extractDir) && Directory.GetFiles(extractDir, "*", SearchOption.AllDirectories).Length > 0)
                {
                    Logger.Log($"{archiveName} already extracted to {extractDir}");
                    continue;
                }

                if (!File.Exists(archivePath))
                {
                    Logger.Log($"{archiveName} not found at {archivePath}");
                    lblStatus.Text = $"Архив {archiveName} не найден";
                    return false;
                }

                toExtract.Add((archiveName, extractDir));
            }

            if (toExtract.Count == 0)
                return true;

            // Один вопрос за всё
            var message = "Для работы перевода необходимо распаковать:\n\n";
            foreach (var (name, dir) in toExtract)
                message += $"• {name} → {dir}\n";
            message += "\nЭто займёт некоторое время и выполняется только один раз.\nПродолжить?";

            var result = MessageBox.Show(
                message,
                "Первая настройка",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Information);

            if (result != DialogResult.Yes)
                return false;

            // Распаковываем
            foreach (var (archiveName, extractDir) in toExtract)
            {
                var archivePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Data", archiveName);

                lblStatus.Text = $"Распаковка {archiveName}...";
                progressBar.Visible = true;
                progressBar.Value = 0;

                try
                {
                    await Task.Run(() => ExtractZipWithProgress(archivePath, extractDir));
                }
                catch (Exception ex)
                {
                    Logger.Log($"Extract error for {archiveName}: {ex.Message}");
                    lblStatus.Text = $"Ошибка распаковки {archiveName}";
                    progressBar.Visible = false;
                    return false;
                }

                progressBar.Visible = false;
                Logger.Log($"{archiveName} extracted successfully to {extractDir}");
            }

            lblStatus.Text = "Распаковка завершена ✓";

            // Удаляем архивы
            foreach (var (archiveName, _) in toExtract)
            {
                var archivePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Data", archiveName);
                if (File.Exists(archivePath))
                {
                    try
                    {
                        File.Delete(archivePath);
                        Logger.Log($"Deleted archive: {archiveName}");
                    }
                    catch (Exception ex)
                    {
                        Logger.Log($"Failed to delete {archiveName}: {ex.Message}");
                    }
                }
            }

            return true;
        }

        private void ExtractZipWithProgress(string archivePath, string extractDir)
        {
            Directory.CreateDirectory(extractDir);

            // Подсчитываем общее количество файлов
            int totalEntries;
            using (var archive = ZipFile.OpenRead(archivePath))
            {
                totalEntries = archive.Entries.Count(e => !string.IsNullOrEmpty(e.Name));
            }

            int processed = 0;
            int lastPercent = -1;

            using (var archive = ZipFile.OpenRead(archivePath))
            {
                foreach (var entry in archive.Entries)
                {
                    if (string.IsNullOrEmpty(entry.Name))
                        continue;

                    var destPath = Path.GetFullPath(Path.Combine(extractDir, entry.FullName));

                    // Безопасность: проверяем, что путь внутри целевой директории
                    if (!destPath.StartsWith(extractDir, StringComparison.Ordinal))
                        continue;

                    Directory.CreateDirectory(Path.GetDirectoryName(destPath)!);
                    entry.ExtractToFile(destPath, overwrite: true);

                    processed++;
                    var percent = (int)((double)processed / totalEntries * 100);

                    // Обновляем прогресс только когда процент изменился (уменьшаем количество вызовов Invoke)
                    if (percent != lastPercent)
                    {
                        lastPercent = percent;
                        this.Invoke(new Action(() =>
                        {
                            progressBar.Value = Math.Min(percent, 100);
                            lblStatus.Text = $"Распаковка: {processed}/{totalEntries} ({percent}%)";
                        }));
                    }
                }
            }

            Logger.Log($"Extracted {processed} files from {Path.GetFileName(archivePath)}");
        }

        private async Task StartTranslateServer()
        {
            _ltService = new LibreTranslateService(AppDomain.CurrentDomain.BaseDirectory);
            Translator.SetTranslateService(_ltService);

            lblStatus.Text = "Запуск сервера перевода...";
            progressBar.Visible = true;
            progressBar.Style = ProgressBarStyle.Marquee;

            var started = await _ltService.StartAsync();

            progressBar.Visible = false;
            lblStatus.Text = started
                ? $"Перевод: ✓"
                : $"Перевод: словарь";
        }

        private void InitializeSearch()
        {
            try
            {
                if (!File.Exists(@"Data\icons.db") || !File.Exists(@"Data\icons.dat"))
                    throw new Exception("Отсутствуют файлы данных");
                _iconService = new IconService(@"Data\icons.db", @"Data\icons.dat");
                lblTotalIcons.Text = $"Загружено иконок: {_iconService.TotalCount:N0}";
                Logger.Log($"Initialized: {_iconService.TotalCount} icons");
            }
            catch (Exception ex)
            {
                Logger.Log($"Init ERROR: {ex.Message}");
                lblStatus.Text = $"Ошибка: {ex.Message}";
                MessageBox.Show($"Ошибка загрузки данных: {ex.Message}", "Ошибка",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
                this.Close();
                Application.Exit();
            }

            _searchTimer = new Timer { Interval = 300 };
            _searchTimer.Tick += SearchTimer_Tick;

            txtSearch.TextChanged += TxtSearch_TextChanged;
            txtSearch.KeyPress += TxtSearch_KeyPress; // Добавляем обработчик
            btnShowMore.Click += BtnShowMore_Click;

            pnlResults.MouseEnter += (s, e) => pnlResults.Focus();
            pnlResults.MouseWheel += PnlResults_MouseWheel;
            pnlResults.Scroll += (s, e) => CheckScrollBottom();
        }

        private void PnlResults_MouseWheel(object sender, MouseEventArgs e) => CheckScrollBottom();

        private void CheckScrollBottom()
        {
            if (!pnlResults.VerticalScroll.Visible) return;
            var maxScroll = pnlResults.VerticalScroll.Maximum - pnlResults.VerticalScroll.LargeChange;
            if (pnlResults.VerticalScroll.Value >= maxScroll - 100)
            {
                if (_isRandomMode && !_isLoading)
                    LoadMoreRandomIcons();
                else if (!_isRandomMode)
                    LoadMoreResults();
            }
        }

        private async void LoadRandomIcons()
        {
            if (_isLoading) return;
            try
            {
                _isLoading = true;
                _isRandomMode = true;
                lblStatus.Text = "Загрузка...";

                _currentResults = await Task.Run(() => _iconService.GetRandomIcons(PageSize));
                _displayedCount = 0;
                pnlResults.Controls.Clear();
                lblStatus.Text = "Случайные иконки";
                LoadMoreResults();
            }
            catch (Exception ex)
            {
                Logger.Log($"LoadRandom ERROR: {ex.Message}");
                lblStatus.Text = $"Ошибка: {ex.Message}";
            }
            finally { _isLoading = false; }
        }

        private async void LoadMoreRandomIcons()
        {
            if (_isLoading) return;
            try
            {
                _isLoading = true;
                var newIcons = await Task.Run(() => _iconService.GetRandomIcons(PageSize));
                _currentResults.AddRange(newIcons);
                LoadMoreResults();
            }
            finally { _isLoading = false; }
        }

        private void TxtSearch_KeyPress(object sender, KeyPressEventArgs e)
        {
            // Разрешаем только буквы, цифры, пробел и backspace
            if (!char.IsLetterOrDigit(e.KeyChar) && e.KeyChar != ' ' && e.KeyChar != (char)Keys.Back)
            {
                e.Handled = true; // Блокируем ввод
            }
        }

        private void TxtSearch_TextChanged(object sender, EventArgs e)
        {
            _searchTimer.Stop();

            var query = txtSearch.Text.Trim();

            // Если поле пустое - показываем случайные иконки
            if (string.IsNullOrEmpty(query))
            {
                ClearResults();
                LoadRandomIcons();
                return;
            }

            // Удаляем недопустимые символы (на случай вставки из буфера обмена)
            var filteredQuery = new string(query.Where(c => char.IsLetterOrDigit(c) || c == ' ').ToArray());

            if (filteredQuery != query)
            {
                // Обновляем текст в поле, если были недопустимые символы
                txtSearch.Text = filteredQuery;
                txtSearch.SelectionStart = filteredQuery.Length;
                return; // TextChanged вызовется снова
            }

            // Запускаем поиск только если 2 и более символов
            if (filteredQuery.Length >= 2)
            {
                _searchTimer.Start();
            }
            else
            {
                lblStatus.Text = "Введите минимум 2 символа для поиска";
            }
        }

        private async void SearchTimer_Tick(object sender, EventArgs e)
        {
            _searchTimer.Stop();
            var query = txtSearch.Text.Trim();

            // Дополнительная проверка на случай изменения текста во время таймера
            if (string.IsNullOrEmpty(query) || query.Length < 2)
            {
                ClearResults();
                LoadRandomIcons();
                return;
            }

            await PerformSearch(query);
        }

        private async Task PerformSearch(string query)
        {
            if (_isLoading) return;
            try
            {
                _isLoading = true;
                _isRandomMode = false;
                lblStatus.Text = "Поиск...";

                var translatedQuery = await Translator.TranslateAsync(query);
                if (translatedQuery != query)
                    Logger.Log($"Translated: '{query}' → '{translatedQuery}'");

                _currentResults = await Task.Run(() => _iconService.Search(translatedQuery));
                _displayedCount = 0;
                pnlResults.Controls.Clear();

                if (_currentResults.Count == 0)
                {
                    lblStatus.Text = "Ничего не найдено";
                    btnShowMore.Visible = false;
                    return;
                }

                lblStatus.Text = $"Найдено: {_currentResults.Count:N0}";
                LoadMoreResults();
            }
            catch (Exception ex)
            {
                Logger.Log($"Search ERROR: {ex.Message}");
                lblStatus.Text = $"Ошибка поиска: {ex.Message}";
            }
            finally { _isLoading = false; }
        }

        private void LoadMoreResults()
        {
            if (_currentResults == null || _displayedCount >= _currentResults.Count) return;

            var batch = _currentResults.Skip(_displayedCount).Take(PageSize).ToList();

            pnlResults.SuspendLayout();
            foreach (var icon in batch)
            {
                var card = new IconCard(icon, _iconService);
                card.IconClicked += Card_IconClicked;
                card.Margin = new Padding(5);
                pnlResults.Controls.Add(card);
            }
            pnlResults.ResumeLayout(true);

            _displayedCount += batch.Count;

            btnShowMore.Visible = _isRandomMode || _displayedCount < _currentResults.Count;
            btnShowMore.Text = _isRandomMode
                ? "Показать еще"
                : $"Показать еще ({_currentResults.Count - _displayedCount})";

            lblStatus.Text = _isRandomMode
                ? $"Случайные иконки (показано: {_displayedCount:N0})"
                : $"Показано: {_displayedCount:N0} из {_currentResults.Count:N0}";

            // Загружаем миниатюры асинхронно
            this.BeginInvoke(new Action(async () =>
            {
                foreach (Control c in pnlResults.Controls)
                {
                    if (c is IconCard card && card.Visible)
                    {
                        await card.LoadThumbnailAsync();
                    }
                }
            }));
        }

        private void BtnShowMore_Click(object sender, EventArgs e)
        {
            if (_isRandomMode) LoadMoreRandomIcons();
            else LoadMoreResults();
        }

        private void Card_IconClicked(object sender, IconInfo icon)
        {
            Logger.Log($"Clicked: {icon.FilePath}");
            var preview = new PreviewForm(icon, _iconService);
            preview.ShowDialog();
        }

        private void ClearResults()
        {
            foreach (Control c in pnlResults.Controls)
                if (c is IconCard card)
                    card.IconClicked -= Card_IconClicked;

            _currentResults = null;
            _displayedCount = 0;
            pnlResults.Controls.Clear();
            btnShowMore.Visible = false;
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            Logger.Log("MainForm closing");
            UsingMonitor.Save();
            Translator.SaveNewWords();
            _ltService?.Dispose();
            _iconService?.Dispose();
            base.OnFormClosing(e);
        }
    }
}
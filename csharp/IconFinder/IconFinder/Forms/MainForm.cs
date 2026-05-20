using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Forms;
using IconFinder.Controls;
using IconFinder.Services;
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
            Logger.Log("MainForm started");

            // Загружаем словарь (всегда, быстро)
            var dictPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Data", "ru-en.dict");
            Translator.LoadDictionary(dictPath);

            InitializeSearch();
            LoadRandomIcons();

            // Всё остальное — после показа формы
            this.Shown += MainForm_Shown;
        }

        private async void MainForm_Shown(object sender, EventArgs e)
        {
            // Распаковка Python (если нужно)
            if (EnableTranslationServer)
                ExtractPythonIfNeeded();

            // Запуск сервера перевода (если включен)
            if (EnableTranslationServer)
                await StartTranslateServer();
        }

        private void ExtractPythonIfNeeded()
        {
            var pythonDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Data", "Python");
            var pythonZip = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Data", "python.zip");

            if (Directory.Exists(pythonDir) && Directory.GetFiles(pythonDir).Length > 0)
                return;

            if (!File.Exists(pythonZip))
            {
                Logger.Log("Python archive not found");
                return;
            }

            var result = MessageBox.Show(
                "Для работы перевода необходимо распаковать файлы Python (≈500 МБ).\n" +
                "Это займёт 1-2 минуты и выполняется только один раз.\n\n" +
                "Продолжить?",
                "Первая настройка",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Information);

            if (result != DialogResult.Yes)
                return;

            lblStatus.Text = "Распаковка Python...";

            Task.Run(() =>
            {
                try
                {
                    Directory.CreateDirectory(pythonDir);

                    var tempDir = Path.Combine(Path.GetTempPath(), "IconFinder_Python_Extract");
                    if (Directory.Exists(tempDir))
                        Directory.Delete(tempDir, true);
                    Directory.CreateDirectory(tempDir);

                    var tempZip = Path.Combine(tempDir, "python.zip");
                    File.Copy(pythonZip, tempZip, overwrite: true);

                    using (var archive = ZipFile.OpenRead(tempZip))
                    {
                        foreach (var entry in archive.Entries)
                        {
                            var destPath = Path.GetFullPath(Path.Combine(pythonDir, entry.FullName));
                            if (!destPath.StartsWith(pythonDir, StringComparison.Ordinal))
                                continue;

                            if (string.IsNullOrEmpty(entry.Name))
                                Directory.CreateDirectory(destPath);
                            else
                            {
                                Directory.CreateDirectory(Path.GetDirectoryName(destPath)!);
                                entry.ExtractToFile(destPath, overwrite: true);
                            }
                        }
                    }

                    try { Directory.Delete(tempDir, true); } catch { }
                    File.Delete(pythonZip);
                    Logger.Log("Python extracted");
                }
                catch (Exception ex)
                {
                    Logger.Log($"Extract error: {ex.Message}");
                }
            });
        }

        private async Task StartTranslateServer()
        {
            _ltService = new LibreTranslateService(AppDomain.CurrentDomain.BaseDirectory);
            Translator.SetTranslateService(_ltService);

            lblStatus.Text = "Запуск сервера перевода...";

            var started = await _ltService.StartAsync();

            lblStatus.Text = started
                ? $"Загружено иконок: {_iconService?.TotalCount ?? 0:N0} | Перевод: ✓"
                : $"Загружено иконок: {_iconService?.TotalCount ?? 0:N0} | Перевод: словарь";
        }

        private void InitializeSearch()
        {
            try
            {
                _iconService = new IconService(@"Data\icons.db", @"Data\icons.dat");
                lblStatus.Text = $"Загружено иконок: {_iconService.TotalCount:N0}";
                Logger.Log($"Initialized: {_iconService.TotalCount} icons");
            }
            catch (Exception ex)
            {
                Logger.Log($"Init ERROR: {ex.Message}");
                lblStatus.Text = $"Ошибка: {ex.Message}";
                MessageBox.Show($"Ошибка загрузки данных: {ex.Message}", "Ошибка",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }

            _searchTimer = new Timer { Interval = 300 };
            _searchTimer.Tick += SearchTimer_Tick;

            txtSearch.TextChanged += TxtSearch_TextChanged;
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

        private void TxtSearch_TextChanged(object sender, EventArgs e)
        {
            _searchTimer.Stop();
            if (string.IsNullOrEmpty(txtSearch.Text.Trim()))
            {
                ClearResults();
                LoadRandomIcons();
                return;
            }
            _searchTimer.Start();
        }

        private async void SearchTimer_Tick(object sender, EventArgs e)
        {
            _searchTimer.Stop();
            var query = txtSearch.Text.Trim();
            if (string.IsNullOrEmpty(query))
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

            // Загружаем миниатюры
            this.BeginInvoke(new Action(() =>
            {
                foreach (Control c in pnlResults.Controls)
                    if (c is IconCard card && card.Visible)
                        card.LoadThumbnail();
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
            Translator.SaveNewWords();
            _ltService?.Dispose();
            _iconService?.Dispose();
            base.OnFormClosing(e);
        }
    }
}
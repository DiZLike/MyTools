using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows.Forms;
using IconFinder.Controls;
using IconFinder.Services;
using Timer = System.Windows.Forms.Timer;

namespace IconFinder.Forms
{
    public partial class MainForm : Form
    {
        private IconService _iconService;
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
            InitializeSearch();
            LoadRandomIcons();
        }

        private void InitializeSearch()
        {
            try
            {
                _iconService = new IconService(
                    @"Data\icons.db",
                    @"Data\icons.dat"
                );
                lblStatus.Text = $"Загружено иконок: {_iconService.TotalCount:N0}";
                Logger.Log($"Initialized: {_iconService.TotalCount} icons");
            }
            catch (Exception ex)
            {
                Logger.Log($"Init ERROR: {ex.Message}");
                lblStatus.Text = $"Ошибка: {ex.Message}";
                MessageBox.Show($"Ошибка загрузки данных: {ex.Message}", "Ошибка", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }

            _searchTimer = new Timer { Interval = 300 };
            _searchTimer.Tick += SearchTimer_Tick;

            txtSearch.TextChanged += TxtSearch_TextChanged;
            btnShowMore.Click += BtnShowMore_Click;

            // Скролл: фокус + колесико
            pnlResults.MouseEnter += (s, e) => pnlResults.Focus();
            pnlResults.MouseWheel += PnlResults_MouseWheel;
            pnlResults.Scroll += (s, e) => CheckScrollBottom();
        }

        private void PnlResults_MouseWheel(object sender, MouseEventArgs e)
        {
            CheckScrollBottom();
        }

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

                _currentResults = await System.Threading.Tasks.Task.Run(() => _iconService.GetRandomIcons(PageSize));
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
                var newIcons = await System.Threading.Tasks.Task.Run(() => _iconService.GetRandomIcons(PageSize));
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

        private async System.Threading.Tasks.Task PerformSearch(string query)
        {
            if (_isLoading) return;
            try
            {
                _isLoading = true;
                _isRandomMode = false;
                lblStatus.Text = "Поиск...";

                _currentResults = await System.Threading.Tasks.Task.Run(() => _iconService.Search(query));
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
            Logger.Log($"LoadMoreResults: {batch.Count} cards");

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

            if (_isRandomMode)
            {
                btnShowMore.Visible = true;
                btnShowMore.Text = "Показать еще";
                lblStatus.Text = $"Случайные иконки (показано: {_displayedCount:N0})";
            }
            else
            {
                btnShowMore.Visible = _displayedCount < _currentResults.Count;
                btnShowMore.Text = $"Показать еще ({_currentResults.Count - _displayedCount})";
                lblStatus.Text = $"Показано: {_displayedCount:N0} из {_currentResults.Count:N0}";
            }

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
            _iconService?.Dispose();
            base.OnFormClosing(e);
        }
    }
}
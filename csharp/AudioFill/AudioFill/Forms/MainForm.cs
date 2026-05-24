using AudioFill.Audio;
using AudioFill.Audio.Restore;
using AudioFill.Logging;
using AudioFill.Rendering;
using NAudio.Wave;
using System;
using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace AudioFill.Forms
{
    public partial class MainForm : Form
    {
        private string? _currentFile;
        private AnalysisResult? _lastResult;
        private float[]? _restoredLeft;
        private float[]? _restoredRight;
        private CancellationTokenSource? _cts;
        private Button? _activeTabButton;
        private int _restoreProgress;

        [DllImport("dwmapi.dll", PreserveSig = true)]
        private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);
        private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
        private const int DWMWA_CAPTION_COLOR = 35;

        public MainForm()
        {
            InitializeComponent();
            ApplyDarkTheme();
            BindEvents();
        }

        private void ApplyDarkTheme()
        {
            EnableDarkTitleBar();
            BackColor = DarkTheme.FormBack;
            ForeColor = DarkTheme.TextPrimary;

            panelSettings.BackColor = DarkTheme.ControlBack;
            panelTabs.BackColor = DarkTheme.FormBack;
            panelContent.BackColor = DarkTheme.FormBack;
            panelRestore.BackColor = DarkTheme.FormBack;

            foreach (Control ctrl in panelSettings.Controls) StyleControl(ctrl);
            StyleTabButton(btnTabSpectrogram);
            StyleTabButton(btnTabFrequency);
            StyleTabButton(btnTabLog);
            StyleTabButton(btnTabRestore);

            foreach (Control ctrl in panelRestore.Controls)
            {
                if (ctrl is Label lbl) lbl.ForeColor = DarkTheme.TextPrimary;
                else if (ctrl is Button btn)
                {
                    btn.BackColor = DarkTheme.ButtonBack;
                    btn.ForeColor = DarkTheme.TextPrimary;
                    btn.FlatAppearance.BorderColor = DarkTheme.Border;
                    btn.FlatAppearance.MouseOverBackColor = DarkTheme.ButtonHover;
                    btn.FlatAppearance.MouseDownBackColor = DarkTheme.ButtonPressed;
                }
            }

            txtLog.BackColor = DarkTheme.TextBoxBack;
            txtLog.ForeColor = DarkTheme.TextPrimary;
            progressBar.BackColor = DarkTheme.ControlBack;
            progressBar.ForeColor = DarkTheme.AccentBlue;
            lblStatus.BackColor = DarkTheme.FormBack;
            lblStatus.ForeColor = DarkTheme.TextMuted;
            SetActiveTab(btnTabSpectrogram);
        }

        private void EnableDarkTitleBar()
        {
            if (Environment.OSVersion.Version.Build >= 19041)
            {
                int useDarkMode = 1;
                DwmSetWindowAttribute(Handle, DWMWA_USE_IMMERSIVE_DARK_MODE, ref useDarkMode, sizeof(int));
                int captionColor = Color.FromArgb(24, 24, 27).ToArgb();
                DwmSetWindowAttribute(Handle, DWMWA_CAPTION_COLOR, ref captionColor, sizeof(int));
            }
        }

        private void StyleControl(Control ctrl)
        {
            switch (ctrl)
            {
                case Button btn:
                    btn.BackColor = DarkTheme.ButtonBack;
                    btn.ForeColor = DarkTheme.TextPrimary;
                    btn.FlatAppearance.BorderColor = DarkTheme.Border;
                    btn.FlatAppearance.MouseOverBackColor = DarkTheme.ButtonHover;
                    btn.FlatAppearance.MouseDownBackColor = DarkTheme.ButtonPressed;
                    break;
                case Label lbl: lbl.ForeColor = DarkTheme.TextMuted; break;
                case ComboBox cmb: cmb.BackColor = DarkTheme.ControlBack; cmb.ForeColor = DarkTheme.TextPrimary; break;
                case NumericUpDown nud: nud.BackColor = DarkTheme.ControlBack; nud.ForeColor = DarkTheme.TextPrimary; break;
                case GroupBox gb:
                    gb.ForeColor = DarkTheme.TextMuted;
                    foreach (Control inner in gb.Controls)
                        if (inner is RadioButton rb) rb.ForeColor = DarkTheme.TextPrimary;
                    break;
            }
        }

        private void StyleTabButton(Button btn)
        {
            btn.FlatStyle = FlatStyle.Flat;
            btn.FlatAppearance.BorderSize = 0;
            btn.Cursor = Cursors.Hand;
            btn.BackColor = DarkTheme.FormBack;
            btn.ForeColor = DarkTheme.TextMuted;
            btn.TextAlign = ContentAlignment.MiddleCenter;
        }

        private void SetActiveTab(Button btn)
        {
            if (_activeTabButton != null)
            {
                _activeTabButton.BackColor = DarkTheme.FormBack;
                _activeTabButton.ForeColor = DarkTheme.TextMuted;
            }
            _activeTabButton = btn;
            btn.BackColor = DarkTheme.ControlBack;
            btn.ForeColor = DarkTheme.TextPrimary;
            spectrogramView.Visible = (btn == btnTabSpectrogram);
            frequencyChartView.Visible = (btn == btnTabFrequency);
            txtLog.Visible = (btn == btnTabLog);
            panelRestore.Visible = (btn == btnTabRestore);
        }

        private void BindEvents()
        {
            btnOpen.Click += BtnOpen_Click;
            btnAnalyze.Click += BtnAnalyze_Click;
            btnSaveLog.Click += BtnSaveLog_Click;
            btnSaveCsv.Click += BtnSaveCsv_Click;
            btnSaveSpectrogram.Click += BtnSaveSpectrogram_Click;
            FormClosing += (s, e) => _cts?.Cancel();

            numThreshold.ValueChanged += NumThreshold_ValueChanged;

            rbLogScale.CheckedChanged += (s, e) =>
            {
                if (rbLogScale.Checked) { spectrogramView.SetScale(true); frequencyChartView.SetScale(true); }
            };
            rbLinearScale.CheckedChanged += (s, e) =>
            {
                if (rbLinearScale.Checked) { spectrogramView.SetScale(false); frequencyChartView.SetScale(false); }
            };

            btnTabSpectrogram.Click += (s, e) => SetActiveTab(btnTabSpectrogram);
            btnTabFrequency.Click += (s, e) => SetActiveTab(btnTabFrequency);
            btnTabLog.Click += (s, e) => SetActiveTab(btnTabLog);
            btnTabRestore.Click += (s, e) => SetActiveTab(btnTabRestore);

            trkEnvelope.ValueChanged += (s, e) => lblEnvelopeVal.Text = $"{trkEnvelope.Value}%";
            numBands.ValueChanged += (s, e) => UpdateRestoreStatus();
            numNoise.ValueChanged += (s, e) => UpdateRestoreStatus();

            btnRestore.Click += BtnRestore_Click;
            btnPlayRestored.Click += BtnPlayRestored_Click;
            btnSaveRestored.Click += BtnSaveRestored_Click;
        }

        private void UpdateRestoreStatus()
        {
            if (_lastResult?.CutoffDetected == true)
                lblRestoreStatus.Text = $"Частота среза: {_lastResult.CutoffFrequencyHz} Гц | Полос: {numBands.Value} | Шум: {numNoise.Value}%";
        }

        private void BtnOpen_Click(object? sender, EventArgs e)
        {
            using var dlg = new OpenFileDialog
            {
                Filter = "Аудиофайлы|*.mp3;*.wav;*.flac;*.aac;*.wma;*.ogg;*.m4a|Все файлы|*.*",
                Title = "Выберите аудиофайл"
            };
            if (dlg.ShowDialog() == DialogResult.OK)
            {
                _currentFile = dlg.FileName;
                lblFileInfo.Text = $"📁 {Path.GetFileName(_currentFile)}";
                btnAnalyze.Enabled = true;
            }
        }

        private async void BtnAnalyze_Click(object? sender, EventArgs e)
        {
            if (string.IsNullOrEmpty(_currentFile)) return;

            _cts = new CancellationTokenSource();
            var token = _cts.Token;

            btnAnalyze.Enabled = false;
            btnOpen.Enabled = false;
            progressBar.Style = ProgressBarStyle.Marquee;
            lblStatus.Text = "⏳ Анализ...";

            int fftSize = int.Parse(cmbFftSize.SelectedItem!.ToString()!);
            int windowType = cmbWindow.SelectedIndex;
            double overlap = cmbOverlap.SelectedIndex switch { 0 => 0, 1 => 0.25, 2 => 0.5, 3 => 0.75, _ => 0.5 };
            var analyzer = new AudioAnalyzer(fftSize, overlap, windowType, (double)numThreshold.Value);

            try
            {
                // Читаем сэмплы для реставрации (стерео!)
                float[] originalLeft, originalRight;
                using (var reader = new MediaFoundationReader(_currentFile))
                {
                    int channels = reader.WaveFormat.Channels;
                    using var resampler = new MediaFoundationResampler(reader, new WaveFormat(48000, channels));
                    var all = ReadAllSamples(resampler.ToSampleProvider());
                    int frames = all.Length / channels;
                    originalLeft = new float[frames];
                    originalRight = new float[frames];
                    for (int i = 0; i < frames; i++)
                    {
                        originalLeft[i] = all[i * channels];
                        originalRight[i] = channels > 1 ? all[i * channels + 1] : all[i * channels];
                    }
                }

                _lastResult = await Task.Run(() => analyzer.Analyze(_currentFile, pct =>
                {
                    if (token.IsCancellationRequested) return;
                    BeginInvoke(() =>
                    {
                        if (progressBar.Style != ProgressBarStyle.Continuous)
                        {
                            progressBar.Style = ProgressBarStyle.Continuous;
                            progressBar.Value = 0;
                        }
                        progressBar.Value = Math.Min(pct, 100);
                    });
                }), token);

                if (token.IsCancellationRequested) return;

                _lastResult.OriginalLeft = originalLeft;
                _lastResult.OriginalRight = originalRight;

                spectrogramView.SetData(_lastResult);
                frequencyChartView.SetData(_lastResult);
                UpdateLogAndStatus();

                btnSaveLog.Enabled = true;
                btnSaveCsv.Enabled = true;
                btnSaveSpectrogram.Enabled = true;
                btnRestore.Enabled = _lastResult.CutoffDetected;
                UpdateRestoreStatus();

                SetActiveTab(_lastResult.CutoffDetected ? btnTabFrequency : btnTabSpectrogram);
            }
            catch (OperationCanceledException) { lblStatus.Text = "🚫 Отменён"; }
            catch (Exception ex) { MessageBox.Show($"Ошибка: {ex.Message}"); lblStatus.Text = "❌ Ошибка"; }
            finally
            {
                btnAnalyze.Enabled = true;
                btnOpen.Enabled = true;
                progressBar.Style = ProgressBarStyle.Continuous;
                progressBar.Value = 0;
            }
        }

        private void NumThreshold_ValueChanged(object? sender, EventArgs e)
        {
            if (_lastResult == null) return;
            AudioAnalyzer.RecalculateCutoff(_lastResult, (double)numThreshold.Value);
            frequencyChartView.Invalidate();
            UpdateLogAndStatus();
            btnRestore.Enabled = _lastResult.CutoffDetected;
            UpdateRestoreStatus();
        }

        private void UpdateLogAndStatus()
        {
            if (_lastResult == null) return;
            string w = cmbWindow.SelectedItem!.ToString()!;
            double o = cmbOverlap.SelectedIndex switch { 0 => 0, 1 => 0.25, 2 => 0.5, 3 => 0.75, _ => 0.5 };
            int f = int.Parse(cmbFftSize.SelectedItem!.ToString()!);
            string log = CutoffLogger.FormatLog(_lastResult, f, w, o, rbLogScale.Checked, (double)numThreshold.Value);
            txtLog.Text = log;
            CutoffLogger.SaveLog(log, _currentFile!);
            CutoffLogger.SaveCsv(_lastResult, _currentFile!);
            lblStatus.Text = _lastResult.CutoffDetected
                ? $"🔴 Срез: {_lastResult.CutoffFrequencyHz} Гц"
                : "🟢 Нет среза";
        }

        private void BtnSaveLog_Click(object? sender, EventArgs e)
        {
            if (_lastResult != null && _currentFile != null)
            {
                CutoffLogger.SaveLog(txtLog.Text, _currentFile);
                lblStatus.Text = "💾 Лог сохранён";
            }
        }

        private void BtnSaveCsv_Click(object? sender, EventArgs e)
        {
            if (_lastResult != null && _currentFile != null)
            {
                CutoffLogger.SaveCsv(_lastResult, _currentFile);
                lblStatus.Text = "📊 CSV экспортирован";
            }
        }

        private void BtnSaveSpectrogram_Click(object? sender, EventArgs e)
        {
            if (_lastResult == null || _currentFile == null) return;
            using var dlg = new SaveFileDialog
            {
                Filter = "PNG|*.png",
                FileName = Path.GetFileNameWithoutExtension(_currentFile) + "_spectrogram.png"
            };
            if (dlg.ShowDialog() == DialogResult.OK)
            {
                using var bmp = new Bitmap(spectrogramView.Width, spectrogramView.Height);
                spectrogramView.DrawToBitmap(bmp, new Rectangle(0, 0, spectrogramView.Width, spectrogramView.Height));
                bmp.Save(dlg.FileName, System.Drawing.Imaging.ImageFormat.Png);
                lblStatus.Text = "🖼 Сохранено";
            }
        }

        // ==================== РЕСТАВРАЦИЯ (СТЕРЕО) ====================

        private async void BtnRestore_Click(object? sender, EventArgs e)
        {
            if (_lastResult?.OriginalLeft == null || !_lastResult.CutoffDetected) return;

            btnRestore.Enabled = false;
            btnPlayRestored.Enabled = false;
            btnSaveRestored.Enabled = false;

            bool isStereo = _lastResult.OriginalRight != null &&
                            _lastResult.OriginalRight.Length > 0 &&
                            _lastResult.Channels > 1;

            double env = (double)trkEnvelope.Value / 100.0;
            int bands = (int)numBands.Value;
            double noise = (double)numNoise.Value / 100.0;
            int sr = 48000;
            double cut = _lastResult.CutoffFrequencyHz;

            var progress = new Progress<RestoreProgress>(p =>
            {
                if (IsDisposed) return;
                BeginInvoke(() =>
                {
                    if (progressBar.IsHandleCreated) progressBar.Value = p.Percent;
                    if (lblStatus.IsHandleCreated)
                    {
                        string remaining = p.Remaining.TotalSeconds > 1
                            ? $" | Осталось ~{p.Remaining.TotalSeconds:F0}с"
                            : "";
                        lblStatus.Text = $"{p.Step} — {p.Percent}%{remaining}";
                    }
                });
            });

            progressBar.Style = ProgressBarStyle.Continuous;
            progressBar.Value = 0;
            lblStatus.Text = "Восстановление... 0%";

            try
            {
                await Task.Run(() =>
                {
                    var restorer = new AudioRestorer(sr, cut, _lastResult)
                    {
                        EnvelopeLevel = env,
                        NoiseAmount = noise,
                        CutoffLevelDb = _lastResult.CutoffLevelDb,
                        Strategy = new NoiseStrategy()
                    };

                    if (isStereo)
                    {
                        (_restoredLeft, _restoredRight) = restorer.RestoreStereo(
                            _lastResult.OriginalLeft!,
                            _lastResult.OriginalRight!,
                            progress
                        );
                    }
                    else
                    {
                        (_restoredLeft, _restoredRight) = restorer.RestoreStereo(
                            _lastResult.OriginalLeft!,
                            null,
                            progress
                        );
                    }

                    AppendDebugLog(restorer.DebugLog);
                });

                progressBar.Value = 0;
                lblStatus.Text = $"Реставрация завершена ({(isStereo ? "стерео" : "моно")})";
                lblRestoreStatus.Text = $"Готово! Полос: {bands} | Шум: {noise * 100:0}% | Уровень: {env * 100:0}%";
                btnPlayRestored.Enabled = true;
                btnSaveRestored.Enabled = true;
            }
            catch (Exception ex)
            {
                lblRestoreStatus.Text = $"Ошибка: {ex.Message}";
                lblStatus.Text = "❌ Ошибка";
                progressBar.Value = 0;
            }
            finally
            {
                btnRestore.Enabled = true;
            }
        }

        private void AppendDebugLog(List<string> log)
        {
            if (log.Count == 0) return;
            BeginInvoke(() =>
            {
                txtLog.AppendText(string.Join(Environment.NewLine, log) + Environment.NewLine);
            });
        }

        private void BtnPlayRestored_Click(object? sender, EventArgs e)
        {
            if (_restoredLeft == null) return;
            string tmp = Path.Combine(Path.GetTempPath(), "audiofill_preview.wav");
            SaveStereoWav(tmp, _restoredLeft, _restoredRight ?? _restoredLeft, 48000);
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = tmp,
                    UseShellExecute = true
                });
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Не удалось открыть: {ex.Message}");
            }
        }

        private void BtnSaveRestored_Click(object? sender, EventArgs e)
        {
            if (_restoredLeft == null || _currentFile == null) return;
            using var dlg = new SaveFileDialog
            {
                Filter = "WAV|*.wav",
                FileName = Path.GetFileNameWithoutExtension(_currentFile) + "_restored.wav"
            };
            if (dlg.ShowDialog() == DialogResult.OK)
            {
                SaveStereoWav(dlg.FileName, _restoredLeft, _restoredRight ?? _restoredLeft, 48000);
                lblRestoreStatus.Text = "Сохранено!";
            }
        }

        private static float[] ReadAllSamples(ISampleProvider p)
        {
            var s = new List<float>();
            var b = new float[4096];
            int r;
            while ((r = p.Read(b, 0, b.Length)) > 0)
                s.AddRange(b.Take(r));
            return s.ToArray();
        }

        private static void SaveStereoWav(string path, float[] l, float[] r, int rate)
        {
            int len = Math.Max(l.Length, r.Length);
            using var w = new WaveFileWriter(path, new WaveFormat(rate, 2));
            var buf = new float[2];
            for (int i = 0; i < len; i++)
            {
                buf[0] = i < l.Length ? Math.Clamp(l[i], -1f, 1f) : 0f;
                buf[1] = i < r.Length ? Math.Clamp(r[i], -1f, 1f) : 0f;
                w.WriteSamples(buf, 0, 2);
            }
        }
    }
}
using BrickwallCompressor.Audio;
using BrickwallCompressor.Controls;
using BrickwallCompressor.Core;
using System;
using System.Drawing;
using System.Windows.Forms;

namespace BrickwallCompressor
{
    public partial class MainForm : Form
    {
        private AudioEngine _audioEngine;
        private System.Windows.Forms.Timer _updateTimer;
        private System.Windows.Forms.Timer _meterTimer;
        private int _currentBand = 0; // 0=Low, 1=Mid, 2=High

        public MainForm()
        {
            InitializeComponent();
            _audioEngine = new AudioEngine();
            SetupTimers();
            SetupMeters();
            LoadBandSettings(0);
        }

        private void SetupTimers()
        {
            _updateTimer = new System.Windows.Forms.Timer { Interval = 50 };
            _updateTimer.Tick += UpdateTimer_Tick;

            _meterTimer = new System.Windows.Forms.Timer { Interval = 25 };
            _meterTimer.Tick += MeterTimer_Tick;
        }

        private void SetupMeters()
        {
            ReplacePlaceholder(ref meterLowIn, pnlLowIn, MeterType.Peak, Color.FromArgb(0, 255, 136));
            ReplacePlaceholder(ref meterLowOut, pnlLowOut, MeterType.Peak, Color.FromArgb(0, 255, 136));
            ReplacePlaceholder(ref meterMidIn, pnlMidIn, MeterType.Peak, Color.FromArgb(255, 200, 0));
            ReplacePlaceholder(ref meterMidOut, pnlMidOut, MeterType.Peak, Color.FromArgb(255, 200, 0));
            ReplacePlaceholder(ref meterHighIn, pnlHighIn, MeterType.Peak, Color.FromArgb(0, 180, 255));
            ReplacePlaceholder(ref meterHighOut, pnlHighOut, MeterType.Peak, Color.FromArgb(0, 180, 255));
            ReplacePlaceholder(ref meterInputPeak, pnlInputPeak, MeterType.Peak, Color.White);
            ReplacePlaceholder(ref meterInputRms, pnlInputRms, MeterType.RMS, Color.White);
            ReplacePlaceholder(ref meterOutputPeak, pnlOutputPeak, MeterType.Peak, Color.FromArgb(255, 100, 100));
            ReplacePlaceholder(ref meterOutputRms, pnlOutputRms, MeterType.RMS, Color.FromArgb(255, 100, 100));
        }

        private void ReplacePlaceholder(ref AudioMeter meter, Panel placeholder, MeterType type, Color peakColor)
        {
            var parent = placeholder.Parent;
            var location = placeholder.Location;
            var size = placeholder.Size;

            parent.Controls.Remove(placeholder);
            placeholder.Dispose();

            meter = new AudioMeter
            {
                Type = type,
                Location = location,
                Size = size,
                LowThreshold = 0.6f,
                MidThreshold = 0.85f,
                PeakHoldColor = peakColor
            };

            parent.Controls.Add(meter);
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            try
            {
                _audioEngine.Initialize(this.Handle);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Ошибка инициализации: " + ex.Message);
            }
        }

        // ===== ВЫБОР ПОЛОСЫ =====

        private void cmbBand_SelectedIndexChanged(object sender, EventArgs e)
        {
            SaveBandSettings(_currentBand);
            _currentBand = cmbBand.SelectedIndex;
            LoadBandSettings(_currentBand);

            string[] names = { "НИЗКИЕ", "СРЕДНИЕ", "ВЫСОКИЕ" };
            Color[] colors = { Color.FromArgb(0, 255, 136), Color.FromArgb(255, 200, 0), Color.FromArgb(0, 180, 255) };
            gbCompressor.Text = "КОМПРЕССОР (" + names[_currentBand] + ")";
            gbCompressor.ForeColor = colors[_currentBand];
        }

        private void SaveBandSettings(int band)
        {
            var comp = GetCompressor(band);
            // В реальном приложении здесь сохранение в настройки
        }

        private void LoadBandSettings(int band)
        {
            var comp = GetCompressor(band);

            // Загружаем параметры полосы в ползунки
            SetTrackBarSilent(tbThreshold, (int)GetThreshold(comp));
            SetTrackBarSilent(tbRatio, (int)(GetRatio(comp) * 10));
            SetTrackBarSilent(tbAttack, (int)(GetAttack(comp) * 10));
            SetTrackBarSilent(tbRelease, (int)GetRelease(comp));
            SetTrackBarSilent(tbKnee, (int)GetKnee(comp));
            SetTrackBarSilent(tbMakeup, (int)GetMakeup(comp));

            // Обновляем подписи
            UpdateThresholdLabel();
            UpdateRatioLabel();
            UpdateAttackLabel();
            UpdateReleaseLabel();
            UpdateKneeLabel();
            UpdateMakeupLabel();
        }

        private PeakCompressor GetCompressor(int band)
        {
            return band switch
            {
                0 => _audioEngine.Pipeline.ThreeBand.LowCompressor,
                1 => _audioEngine.Pipeline.ThreeBand.MidCompressor,
                2 => _audioEngine.Pipeline.ThreeBand.HighCompressor,
                _ => _audioEngine.Pipeline.ThreeBand.LowCompressor
            };
        }

        private void SetTrackBarSilent(TrackBar tb, int value)
        {
            tb.Value = Math.Clamp(value, tb.Minimum, tb.Maximum);
        }

        private float GetThreshold(PeakCompressor c) => -18f; // Упрощённо
        private float GetRatio(PeakCompressor c) => 3f;
        private float GetAttack(PeakCompressor c) => 15f;
        private float GetRelease(PeakCompressor c) => 100f;
        private float GetKnee(PeakCompressor c) => 6f;
        private float GetMakeup(PeakCompressor c) => 0f;

        private void UpdateThresholdLabel() => lblThresholdValue.Text = $"{tbThreshold.Value} dB";
        private void UpdateRatioLabel() => lblRatioValue.Text = $"{tbRatio.Value / 10f:F1}:1";
        private void UpdateAttackLabel() => lblAttackValue.Text = $"{tbAttack.Value / 10f:F1} ms";
        private void UpdateReleaseLabel() => lblReleaseValue.Text = $"{tbRelease.Value} ms";
        private void UpdateKneeLabel() => lblKneeValue.Text = $"{tbKnee.Value} dB";
        private void UpdateMakeupLabel() => lblMakeupValue.Text = $"{tbMakeup.Value} dB";

        // ===== СОБЫТИЯ =====

        private void btnLoadFile_Click(object sender, EventArgs e)
        {
            using (var ofd = new OpenFileDialog())
            {
                ofd.Filter = "Аудио файлы|*.mp3;*.wav;*.flac;*.ogg|Все файлы|*.*";
                if (ofd.ShowDialog() == DialogResult.OK)
                {
                    try
                    {
                        _audioEngine.LoadFile(ofd.FileName);
                        _updateTimer.Start();
                        _meterTimer.Start();
                        UpdatePlaybackState();
                    }
                    catch (Exception ex)
                    {
                        MessageBox.Show("Ошибка загрузки: " + ex.Message);
                    }
                }
            }
        }

        private void btnPlayPause_Click(object sender, EventArgs e)
        {
            if (_audioEngine.IsPlaying)
            {
                _audioEngine.Pause();
                _updateTimer.Stop();
                _meterTimer.Stop();
            }
            else
            {
                _audioEngine.Play();
                _updateTimer.Start();
                _meterTimer.Start();
            }
            UpdatePlaybackState();
        }

        private void btnStop_Click(object sender, EventArgs e)
        {
            _audioEngine.Stop();
            _updateTimer.Stop();
            _meterTimer.Stop();
            UpdatePlaybackState();
            lblPosition.Text = "00:00";
            progressBar.Value = 0;
            ResetAllMeters();
        }

        private void UpdatePlaybackState()
        {
            btnPlayPause.Text = _audioEngine.IsPlaying ? "⏸" : "▶";
            btnPlayPause.BackColor = _audioEngine.IsPlaying ?
                Color.FromArgb(180, 100, 20) : Color.FromArgb(62, 62, 66);
        }

        private void ResetAllMeters()
        {
            meterLowIn.CurrentLevel = meterLowOut.CurrentLevel = 0;
            meterMidIn.CurrentLevel = meterMidOut.CurrentLevel = 0;
            meterHighIn.CurrentLevel = meterHighOut.CurrentLevel = 0;
            meterInputPeak.CurrentLevel = meterInputRms.CurrentLevel = 0;
            meterOutputPeak.CurrentLevel = meterOutputRms.CurrentLevel = 0;
        }

        // ===== ПОЛЗУНКИ =====

        private void tbThreshold_Scroll(object sender, EventArgs e)
        {
            float value = tbThreshold.Value;
            lblThresholdValue.Text = $"{value:F0} dB";
            GetCompressor(_currentBand).SetThreshold(value);
        }

        private void tbRatio_Scroll(object sender, EventArgs e)
        {
            float value = tbRatio.Value / 10f;
            lblRatioValue.Text = $"{value:F1}:1";
            GetCompressor(_currentBand).SetRatio(value);
        }

        private void tbAttack_Scroll(object sender, EventArgs e)
        {
            float value = tbAttack.Value / 10f;
            lblAttackValue.Text = $"{value:F1} ms";
            GetCompressor(_currentBand).SetAttack(value);
        }

        private void tbRelease_Scroll(object sender, EventArgs e)
        {
            float value = tbRelease.Value;
            lblReleaseValue.Text = $"{value:F0} ms";
            GetCompressor(_currentBand).SetRelease(value);
        }

        private void tbKnee_Scroll(object sender, EventArgs e)
        {
            float value = tbKnee.Value;
            lblKneeValue.Text = $"{value:F0} dB";
            GetCompressor(_currentBand).SetKneeWidth(value);
        }

        private void tbMakeup_Scroll(object sender, EventArgs e)
        {
            float value = tbMakeup.Value;
            lblMakeupValue.Text = $"{value:F0} dB";
            GetCompressor(_currentBand).SetMakeupGain(value);
        }

        private void tbCeiling_Scroll(object sender, EventArgs e)
        {
            float value = tbCeiling.Value / 10f;
            lblCeilingValue.Text = $"{value:F1} dB";
            _audioEngine.Pipeline.ThreeBand.Limiter.SetCeiling(value);
        }

        private void tbLookahead_Scroll(object sender, EventArgs e)
        {
            float value = tbLookahead.Value / 10f;
            lblLookaheadValue.Text = $"{value:F1} ms";
            _audioEngine.Pipeline.ThreeBand.Limiter.SetLookahead(value);
        }

        private void btnBypass_CheckedChanged(object sender, EventArgs e) { }

        // ===== ТАЙМЕРЫ =====

        private void UpdateTimer_Tick(object sender, EventArgs e)
        {
            double pos = _audioEngine.GetPosition();
            double len = _audioEngine.GetLength();

            if (len > 0)
            {
                lblPosition.Text = FormatTime(pos);
                lblLength.Text = FormatTime(len);
                progressBar.Maximum = 1000;
                progressBar.Value = (int)((pos / len) * 1000);
            }

            lblLowGR.Text = $"{_audioEngine.Pipeline.ThreeBand.LowCompressor.CurrentGainReduction:F1} dB";
            lblMidGR.Text = $"{_audioEngine.Pipeline.ThreeBand.MidCompressor.CurrentGainReduction:F1} dB";
            lblHighGR.Text = $"{_audioEngine.Pipeline.ThreeBand.HighCompressor.CurrentGainReduction:F1} dB";
            lblLimitGR.Text = $"{_audioEngine.Pipeline.ThreeBand.Limiter.CurrentGainReduction:F1} dB";
        }

        private void MeterTimer_Tick(object sender, EventArgs e)
        {
            _audioEngine.Pipeline.UpdateMeters();

            // Метры полос
            meterLowIn.CurrentLevel = _audioEngine.Pipeline.ThreeBand.LowInputMeter.PeakLevel;
            meterLowOut.CurrentLevel = _audioEngine.Pipeline.ThreeBand.LowOutputMeter.PeakLevel;
            meterMidIn.CurrentLevel = _audioEngine.Pipeline.ThreeBand.MidInputMeter.PeakLevel;
            meterMidOut.CurrentLevel = _audioEngine.Pipeline.ThreeBand.MidOutputMeter.PeakLevel;
            meterHighIn.CurrentLevel = _audioEngine.Pipeline.ThreeBand.HighInputMeter.PeakLevel;
            meterHighOut.CurrentLevel = _audioEngine.Pipeline.ThreeBand.HighOutputMeter.PeakLevel;

            // Мастер метры
            meterInputPeak.CurrentLevel = _audioEngine.Pipeline.ThreeBand.MasterOutputMeter.PeakLevel;
            meterInputRms.CurrentLevel = _audioEngine.Pipeline.ThreeBand.MasterOutputMeter.RmsLevel;
            meterOutputPeak.CurrentLevel = _audioEngine.Pipeline.ThreeBand.MasterOutputMeter.PeakLevel;
            meterOutputRms.CurrentLevel = _audioEngine.Pipeline.ThreeBand.MasterOutputMeter.RmsLevel;

            float deltaTime = 0.025f;
            meterLowIn.UpdateTimer(deltaTime); meterLowOut.UpdateTimer(deltaTime);
            meterMidIn.UpdateTimer(deltaTime); meterMidOut.UpdateTimer(deltaTime);
            meterHighIn.UpdateTimer(deltaTime); meterHighOut.UpdateTimer(deltaTime);
            meterInputPeak.UpdateTimer(deltaTime); meterInputRms.UpdateTimer(deltaTime);
            meterOutputPeak.UpdateTimer(deltaTime); meterOutputRms.UpdateTimer(deltaTime);
        }

        private static string FormatTime(double seconds)
        {
            int min = (int)(seconds / 60);
            int sec = (int)(seconds % 60);
            return $"{min:D2}:{sec:D2}";
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            _updateTimer?.Stop();
            _meterTimer?.Stop();
            _audioEngine?.Dispose();
            base.OnFormClosing(e);
        }
    }
}
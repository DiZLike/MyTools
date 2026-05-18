using System;
using System.Windows.Forms;
using gmesharp;

namespace GmePlayerWinForms
{
    public partial class MainForm : Form
    {
        private NAudioPlayer? _player;
        private System.Windows.Forms.Timer _updateTimer;
        private bool _isDragging = false;
        private FlowLayoutPanel? _voicesPanel;
        private int[] _voiceMuteState; // 0 = audible, 1 = muted

        public MainForm()
        {
            InitializeComponent();
            InitializeTimer();
            UpdateUIState();
            this.FormClosing += MainForm_FormClosing;
        }

        private void MainForm_FormClosing(object? sender, FormClosingEventArgs e)
        {
            _updateTimer?.Stop();
            _player?.Dispose();
        }

        private void InitializeTimer()
        {
            _updateTimer = new System.Windows.Forms.Timer();
            _updateTimer.Interval = 100;
            _updateTimer.Tick += UpdateTimer_Tick;
            _updateTimer.Start();
        }

        private void UpdateTimer_Tick(object? sender, EventArgs e)
        {
            if (_player != null && !_isDragging && _player.IsPlaying)
            {
                try
                {
                    UpdatePositionDisplay();
                }
                catch { }
            }
        }

        private void UpdatePositionDisplay()
        {
            if (_player == null) return;

            int position = _player.PositionMs;
            if (position >= 0 && position <= trackPosition.Maximum)
            {
                trackPosition.Value = position;
            }
            UpdateTimeLabel();
            UpdateStatusLabel();
        }

        private void UpdateTimeLabel()
        {
            if (_player == null) return;

            int current = _player.PositionMs;
            var info = _player.GetTrackInfo(_player.CurrentTrack);
            int total = info?.PlayLength ?? 0;
            lblTime.Text = $"{FormatTime(current)} / {FormatTime(total)}";
        }

        private void UpdateStatusLabel()
        {
            if (_player == null) return;

            lblStatus.Text = $"Track: {_player.CurrentTrack + 1}/{_player.TrackCount} | " +
                            $"Voices: {_player.VoiceCount} | " +
                            $"Type: {_player.EmulatorType}";
        }

        private static string FormatTime(int ms)
        {
            if (ms < 0) return "--:--";
            int seconds = ms / 1000;
            return $"{seconds / 60:D2}:{seconds % 60:D2}";
        }

        private void OpenFile(string filePath)
        {
            try
            {
                _player?.Dispose();
                _player = null;
                _voiceMuteState = null;

                var gmePlayer = new GmePlayer(filePath, 44100);
                _player = new NAudioPlayer(gmePlayer);

                _player.TrackChanged += OnTrackChanged;
                _player.PlaybackChanged += OnPlaybackChanged;
                _player.TrackEnded += OnTrackEnded;

                listTracks.BeginUpdate();
                listTracks.Items.Clear();
                for (int i = 0; i < _player.TrackCount; i++)
                {
                    var info = _player.GetTrackInfo(i);
                    listTracks.Items.Add($"{i + 1}. {info?.Song ?? "Unknown"}");
                }
                listTracks.EndUpdate();

                var firstTrackInfo = _player.GetTrackInfo(0);
                trackPosition.Maximum = firstTrackInfo?.PlayLength > 0 ?
                    firstTrackInfo.PlayLength : 300000;

                // Инициализируем массив состояния голосов (все включены по умолчанию)
                _voiceMuteState = new int[_player.VoiceCount];
                for (int i = 0; i < _voiceMuteState.Length; i++)
                    _voiceMuteState[i] = 0; // 0 = not muted

                UpdateTrackInfo();
                UpdateVoices();
                UpdateUIState();
                Text = $"GME Player - {Path.GetFileName(filePath)}";

                _player.PlayTrack(0);
                listTracks.SelectedIndex = 0;
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error opening file:\n{ex.Message}",
                    "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void UpdateTrackInfo()
        {
            if (_player == null) return;

            var info = _player.GetTrackInfo(_player.CurrentTrack);
            lblTrackInfo.Text = info != null
                ? $"System: {info.System}\r\n" +
                  $"Game: {info.Game}\r\n" +
                  $"Song: {info.Song}\r\n" +
                  $"Author: {info.Author}\r\n" +
                  $"Copyright: {info.Copyright}"
                : "No track information available";
        }

        private void UpdateVoices()
        {
            if (_player == null || _voiceMuteState == null) return;

            // Очищаем старую панель голосов
            _voicesPanel?.Controls.Clear();

            int voiceCount = _player.VoiceCount;
            if (voiceCount <= 0) return;

            // Переинициализируем массив состояния голосов если изменилось их количество
            if (_voiceMuteState.Length != voiceCount)
            {
                _voiceMuteState = new int[voiceCount];
                for (int i = 0; i < voiceCount; i++)
                    _voiceMuteState[i] = 0; // 0 = not muted
            }

            // Создаём панель голосов если её нет
            if (_voicesPanel == null)
            {
                _voicesPanel = new FlowLayoutPanel
                {
                    Location = new System.Drawing.Point(12, 250),
                    Size = new System.Drawing.Size(400, 110),
                    AutoScroll = true,
                    BorderStyle = BorderStyle.FixedSingle,
                    BackColor = Color.FromArgb(55, 55, 60),
                    ForeColor = Color.FromArgb(200, 200, 200)
                };
                this.Controls.Add(_voicesPanel);
                _voicesPanel.BringToFront();
            }

            // Добавляем чекбоксы для каждого голоса с учётом сохранённого состояния
            for (int i = 0; i < voiceCount; i++)
            {
                var chk = new CheckBox
                {
                    Text = _player.GetVoiceName(i),
                    Checked = _voiceMuteState[i] == 0, // Checked = not muted
                    AutoSize = true,
                    Margin = new Padding(5),
                    Tag = i,
                    ForeColor = Color.FromArgb(200, 200, 200),
                    BackColor = Color.FromArgb(55, 55, 60)
                };
                chk.CheckedChanged += VoiceCheckBox_CheckedChanged;
                _voicesPanel.Controls.Add(chk);
            }
        }

        private void VoiceCheckBox_CheckedChanged(object? sender, EventArgs e)
        {
            if (_player == null || _voiceMuteState == null || sender is not CheckBox chk) return;

            int voiceIndex = (int)(chk.Tag ?? -1);
            if (voiceIndex >= 0 && voiceIndex < _voiceMuteState.Length)
            {
                // Сохраняем состояние: 0 = not muted, 1 = muted
                _voiceMuteState[voiceIndex] = chk.Checked ? 0 : 1;
                _player.MuteVoice(voiceIndex, !chk.Checked);
            }
        }

        private void UpdateUIState()
        {
            bool hasFile = _player != null;
            bool isPlaying = _player?.IsPlaying ?? false;

            btnPlay.Enabled = hasFile && !isPlaying;
            btnPause.Enabled = hasFile && isPlaying;
            btnStop.Enabled = hasFile && isPlaying;
            btnNext.Enabled = hasFile && (_player?.TrackCount ?? 0) > 1;
            btnPrev.Enabled = hasFile && (_player?.TrackCount ?? 0) > 1;
            listTracks.Enabled = hasFile;
            trackPosition.Enabled = hasFile;
            chkLoop.Enabled = hasFile;

            UpdateStatusLabel();
        }

        private void OnTrackChanged(int trackIndex)
        {
            if (InvokeRequired)
            {
                BeginInvoke(() => OnTrackChanged(trackIndex));
                return;
            }

            listTracks.SelectedIndex = trackIndex;
            UpdateTrackInfo();
            // Обновляем голоса но СОХРАНЯЕМ их состояние
            UpdateVoices();
            
            // Обновляем Maximum для trackPosition в зависимости от длины трека
            var info = _player?.GetTrackInfo(trackIndex);
            if (info != null && info.PlayLength > 0)
            {
                trackPosition.Maximum = info.PlayLength;
            }
            
            UpdateUIState();
        }

        private void OnPlaybackChanged(bool isPlaying)
        {
            if (InvokeRequired)
            {
                BeginInvoke(() => OnPlaybackChanged(isPlaying));
                return;
            }

            UpdateUIState();
        }

        private void OnTrackEnded()
        {
            if (InvokeRequired)
            {
                BeginInvoke(() => OnTrackEnded());
                return;
            }

            if (_player == null) return;

            // Проверка: если все голоса отключены, не переключаемся (игнорируем событие)
            if (_voiceMuteState != null && AreAllVoicesMuted())
            {
                // Просто останавливаемся без переключения
                _player.Stop();
                UpdateUIState();
                return;
            }

            if (chkLoop.Checked)
            {
                _player.PlayTrack(_player.CurrentTrack);
            }
            else if (_player.CurrentTrack < _player.TrackCount - 1)
            {
                _player.Next();
            }
            else
            {
                _player.Stop();
                UpdateUIState();
            }
        }

        private bool AreAllVoicesMuted()
        {
            if (_voiceMuteState == null || _voiceMuteState.Length == 0)
                return false;

            foreach (int state in _voiceMuteState)
            {
                if (state == 0) // Если хотя бы один голос включен
                    return false;
            }
            return true; // Все голоса отключены
        }

        private void btnOpen_Click(object? sender, EventArgs e)
        {
            using var dialog = new OpenFileDialog
            {
                Filter = "Game Music Files|*.nsf;*.spc;*.gbs;*.vgm;*.vgz;*.hes;*.ay;*.kss;*.sap|" +
                        "All Files|*.*",
                Title = "Open Game Music File"
            };

            if (dialog.ShowDialog() == DialogResult.OK)
            {
                OpenFile(dialog.FileName);
            }
        }

        private void btnPlay_Click(object? sender, EventArgs e)
        {
            if (_player == null) return;

            if (!_player.IsPlaying)
            {
                if (listTracks.SelectedIndex >= 0)
                    _player.PlayTrack(listTracks.SelectedIndex);
                else
                    _player.Resume();
            }
        }

        private void btnPause_Click(object? sender, EventArgs e)
        {
            if (_player?.IsPlaying == true)
                _player.Pause();
        }

        private void btnStop_Click(object? sender, EventArgs e)
        {
            _player?.Stop();
            UpdateUIState();
        }

        private void btnNext_Click(object? sender, EventArgs e)
        {
            _player?.Next();
        }

        private void btnPrev_Click(object? sender, EventArgs e)
        {
            _player?.Prev();
        }

        private void listTracks_SelectedIndexChanged(object? sender, EventArgs e)
        {
            if (listTracks.SelectedIndex >= 0 && _player != null &&
                listTracks.SelectedIndex != _player.CurrentTrack)
            {
                _player.PlayTrack(listTracks.SelectedIndex);
            }
        }

        private void trackVolume_Scroll(object? sender, EventArgs e)
        {
            if (_player != null)
            {
                _player.Volume = trackVolume.Value / 100f;
                lblVolume.Text = $"{trackVolume.Value}%";
            }
        }

        private void trackPosition_MouseDown(object? sender, MouseEventArgs e)
        {
            _isDragging = true;
        }

        private void trackPosition_MouseUp(object? sender, MouseEventArgs e)
        {
            _isDragging = false;
        }

        private void trackPosition_Scroll(object? sender, EventArgs e)
        {
            if (_isDragging && _player != null)
            {
                UpdateTimeLabel();
            }
        }
    }
}

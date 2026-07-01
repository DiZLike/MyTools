using BrickwallCompressor.Controls;
using System.ComponentModel;
using System.Drawing;
using System.Windows.Forms;

namespace BrickwallCompressor
{
    partial class MainForm
    {
        private IContainer components = null;

        #region Контролы

        private Button btnLoadFile;
        private Button btnPlayPause;
        private Button btnStop;
        private Label lblPosition;
        private Label lblLength;
        private TrackBar progressBar;
        private CheckBox btnBypass;

        private ComboBox cmbBand;
        private Label lblBand;

        private GroupBox gbCompressor;
        private Label lblThreshold;
        private TrackBar tbThreshold;
        private Label lblThresholdValue;
        private Label lblRatio;
        private TrackBar tbRatio;
        private Label lblRatioValue;
        private Label lblAttack;
        private TrackBar tbAttack;
        private Label lblAttackValue;
        private Label lblRelease;
        private TrackBar tbRelease;
        private Label lblReleaseValue;
        private Label lblKnee;
        private TrackBar tbKnee;
        private Label lblKneeValue;
        private Label lblMakeup;
        private TrackBar tbMakeup;
        private Label lblMakeupValue;

        private GroupBox gbLimiter;
        private Label lblCeiling;
        private TrackBar tbCeiling;
        private Label lblCeilingValue;
        private Label lblLookahead;
        private TrackBar tbLookahead;
        private Label lblLookaheadValue;

        private GroupBox gbBands;
        private Label lblLowTitle;
        private Label lblLowGR;
        private Label lblMidTitle;
        private Label lblMidGR;
        private Label lblHighTitle;
        private Label lblHighGR;
        private Label lblLimitTitle;
        private Label lblLimitGR;

        private GroupBox gbInputMeters;
        private GroupBox gbOutputMeters;
        private Label lblInputPeakTitle;
        private Label lblInputRmsTitle;
        private Label lblOutputPeakTitle;
        private Label lblOutputRmsTitle;
        private Panel pnlInputPeak;
        private Panel pnlInputRms;
        private Panel pnlOutputPeak;
        private Panel pnlOutputRms;

        private GroupBox gbLowMeters;
        private Label lblLowInTitle;
        private Panel pnlLowIn;
        private Label lblLowOutTitle;
        private Panel pnlLowOut;

        private GroupBox gbMidMeters;
        private Label lblMidInTitle;
        private Panel pnlMidIn;
        private Label lblMidOutTitle;
        private Panel pnlMidOut;

        private GroupBox gbHighMeters;
        private Label lblHighInTitle;
        private Panel pnlHighIn;
        private Label lblHighOutTitle;
        private Panel pnlHighOut;

        private AudioMeter meterInputPeak;
        private AudioMeter meterInputRms;
        private AudioMeter meterOutputPeak;
        private AudioMeter meterOutputRms;

        private AudioMeter meterLowIn;
        private AudioMeter meterLowOut;
        private AudioMeter meterMidIn;
        private AudioMeter meterMidOut;
        private AudioMeter meterHighIn;
        private AudioMeter meterHighOut;

        #endregion

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
                components.Dispose();
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            this.components = new Container();
            this.SuspendLayout();

            // ===== ФОРМА =====
            this.Text = "FuzzCast Trinity - 3-Band Compressor";
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;
            this.BackColor = Color.FromArgb(45, 45, 48);
            this.ForeColor = Color.White;
            this.ClientSize = new Size(900, 620);

            // ===== ВЕРХНЯЯ ПАНЕЛЬ =====
            btnLoadFile = new Button
            {
                Text = "Загрузить...",
                Location = new Point(10, 10),
                Size = new Size(95, 28),
                BackColor = Color.FromArgb(62, 62, 66),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                FlatAppearance = { BorderSize = 0 }
            };
            btnLoadFile.Click += btnLoadFile_Click;

            btnPlayPause = new Button
            {
                Text = "▶",
                Location = new Point(110, 10),
                Size = new Size(35, 28),
                BackColor = Color.FromArgb(62, 62, 66),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                FlatAppearance = { BorderSize = 0 }
            };
            btnPlayPause.Click += btnPlayPause_Click;

            btnStop = new Button
            {
                Text = "■",
                Location = new Point(150, 10),
                Size = new Size(35, 28),
                BackColor = Color.FromArgb(62, 62, 66),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                FlatAppearance = { BorderSize = 0 }
            };
            btnStop.Click += btnStop_Click;

            lblPosition = new Label
            {
                Text = "00:00",
                Location = new Point(195, 16),
                Size = new Size(42, 16),
                TextAlign = ContentAlignment.MiddleCenter
            };

            progressBar = new TrackBar
            {
                Location = new Point(240, 10),
                Size = new Size(350, 28),
                TickStyle = TickStyle.None,
                Maximum = 1000
            };

            lblLength = new Label
            {
                Text = "00:00",
                Location = new Point(595, 16),
                Size = new Size(42, 16),
                TextAlign = ContentAlignment.MiddleCenter
            };

            btnBypass = new CheckBox
            {
                Text = "BYPASS",
                Location = new Point(650, 10),
                Size = new Size(85, 28),
                Appearance = Appearance.Button,
                BackColor = Color.FromArgb(62, 62, 66),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat
            };
            btnBypass.CheckedChanged += btnBypass_CheckedChanged;

            lblBand = new Label
            {
                Text = "Полоса:",
                Location = new Point(750, 14),
                Size = new Size(50, 20)
            };

            cmbBand = new ComboBox
            {
                Location = new Point(800, 12),
                Size = new Size(85, 24),
                DropDownStyle = ComboBoxStyle.DropDownList,
                BackColor = Color.FromArgb(62, 62, 66),
                ForeColor = Color.White
            };
            cmbBand.Items.AddRange(new object[] { "Низкие", "Средние", "Высокие" });
            cmbBand.SelectedIndex = 0;
            cmbBand.SelectedIndexChanged += cmbBand_SelectedIndexChanged;

            // ===== КОМПРЕССОР =====
            gbCompressor = new GroupBox
            {
                Text = "КОМПРЕССОР (НИЗКИЕ)",
                Location = new Point(10, 50),
                Size = new Size(340, 275),
                ForeColor = Color.FromArgb(0, 255, 136)
            };

            lblThreshold = new Label();
            tbThreshold = new TrackBar();
            lblThresholdValue = new Label();
            lblRatio = new Label();
            tbRatio = new TrackBar();
            lblRatioValue = new Label();
            lblAttack = new Label();
            tbAttack = new TrackBar();
            lblAttackValue = new Label();
            lblRelease = new Label();
            tbRelease = new TrackBar();
            lblReleaseValue = new Label();
            lblKnee = new Label();
            tbKnee = new TrackBar();
            lblKneeValue = new Label();
            lblMakeup = new Label();
            tbMakeup = new TrackBar();
            lblMakeupValue = new Label();

            SetupParameterRow(lblThreshold, tbThreshold, lblThresholdValue,
                "Threshold", 20, -60, 0, -18, "dB", gbCompressor, tbThreshold_Scroll);
            SetupParameterRow(lblRatio, tbRatio, lblRatioValue,
                "Ratio", 60, 10, 200, 30, ":1", gbCompressor, tbRatio_Scroll);
            SetupParameterRow(lblAttack, tbAttack, lblAttackValue,
                "Attack", 100, 1, 500, 150, "ms", gbCompressor, tbAttack_Scroll);
            SetupParameterRow(lblRelease, tbRelease, lblReleaseValue,
                "Release", 140, 10, 1000, 100, "ms", gbCompressor, tbRelease_Scroll);
            SetupParameterRow(lblKnee, tbKnee, lblKneeValue,
                "Knee", 180, 0, 20, 6, "dB", gbCompressor, tbKnee_Scroll);
            SetupParameterRow(lblMakeup, tbMakeup, lblMakeupValue,
                "Makeup", 220, 0, 20, 0, "dB", gbCompressor, tbMakeup_Scroll);

            // ===== ЛИМИТЕР =====
            gbLimiter = new GroupBox
            {
                Text = "ЛИМИТЕР",
                Location = new Point(10, 335),
                Size = new Size(340, 100),
                ForeColor = Color.FromArgb(255, 160, 0)
            };

            lblCeiling = new Label();
            tbCeiling = new TrackBar();
            lblCeilingValue = new Label();
            lblLookahead = new Label();
            tbLookahead = new TrackBar();
            lblLookaheadValue = new Label();

            SetupParameterRow(lblCeiling, tbCeiling, lblCeilingValue,
                "Ceiling", 20, -30, 0, -3, "dB", gbLimiter, tbCeiling_Scroll);
            SetupParameterRow(lblLookahead, tbLookahead, lblLookaheadValue,
                "Lookahead", 60, 1, 50, 10, "ms", gbLimiter, tbLookahead_Scroll);

            // ===== ИНДИКАТОРЫ ПОЛОС =====
            gbBands = new GroupBox
            {
                Text = "ПОДАВЛЕНИЕ",
                Location = new Point(10, 445),
                Size = new Size(340, 130),
                ForeColor = Color.FromArgb(200, 200, 200)
            };

            lblLowTitle = CreateBandLabel("Низкие:", Color.FromArgb(0, 255, 136), 15, 20);
            lblLowGR = CreateBandValueLabel("0.0 dB", Color.FromArgb(0, 255, 136), 80, 20);

            lblMidTitle = CreateBandLabel("Средние:", Color.FromArgb(255, 200, 0), 15, 45);
            lblMidGR = CreateBandValueLabel("0.0 dB", Color.FromArgb(255, 200, 0), 80, 45);

            lblHighTitle = CreateBandLabel("Высокие:", Color.FromArgb(0, 180, 255), 15, 70);
            lblHighGR = CreateBandValueLabel("0.0 dB", Color.FromArgb(0, 180, 255), 80, 70);

            lblLimitTitle = CreateBandLabel("Лимитер:", Color.FromArgb(255, 100, 100), 15, 95);
            lblLimitGR = CreateBandValueLabel("0.0 dB", Color.FromArgb(255, 100, 100), 80, 95);

            gbBands.Controls.AddRange(new Control[] {
                lblLowTitle, lblLowGR,
                lblMidTitle, lblMidGR,
                lblHighTitle, lblHighGR,
                lblLimitTitle, lblLimitGR
            });

            // ===== МЕТРЫ ПОЛОС =====
            gbLowMeters = new GroupBox
            {
                Text = "НИЗКИЕ",
                Location = new Point(370, 50),
                Size = new Size(100, 370),
                ForeColor = Color.FromArgb(0, 255, 136)
            };
            lblLowInTitle = CreateMeterLabel("IN", 5, 18);
            pnlLowIn = CreateMeterPanel(5, 35);
            lblLowOutTitle = CreateMeterLabel("OUT", 55, 18);
            pnlLowOut = CreateMeterPanel(55, 35);
            gbLowMeters.Controls.AddRange(new Control[] {
                lblLowInTitle, pnlLowIn, lblLowOutTitle, pnlLowOut
            });

            gbMidMeters = new GroupBox
            {
                Text = "СРЕДНИЕ",
                Location = new Point(480, 50),
                Size = new Size(100, 370),
                ForeColor = Color.FromArgb(255, 200, 0)
            };
            lblMidInTitle = CreateMeterLabel("IN", 5, 18);
            pnlMidIn = CreateMeterPanel(5, 35);
            lblMidOutTitle = CreateMeterLabel("OUT", 55, 18);
            pnlMidOut = CreateMeterPanel(55, 35);
            gbMidMeters.Controls.AddRange(new Control[] {
                lblMidInTitle, pnlMidIn, lblMidOutTitle, pnlMidOut
            });

            gbHighMeters = new GroupBox
            {
                Text = "ВЫСОКИЕ",
                Location = new Point(590, 50),
                Size = new Size(100, 370),
                ForeColor = Color.FromArgb(0, 180, 255)
            };
            lblHighInTitle = CreateMeterLabel("IN", 5, 18);
            pnlHighIn = CreateMeterPanel(5, 35);
            lblHighOutTitle = CreateMeterLabel("OUT", 55, 18);
            pnlHighOut = CreateMeterPanel(55, 35);
            gbHighMeters.Controls.AddRange(new Control[] {
                lblHighInTitle, pnlHighIn, lblHighOutTitle, pnlHighOut
            });

            // ===== МАСТЕР МЕТРЫ =====
            gbInputMeters = new GroupBox
            {
                Text = "ВХОД",
                Location = new Point(700, 50),
                Size = new Size(95, 240),
                ForeColor = Color.FromArgb(200, 200, 200)
            };
            lblInputPeakTitle = CreateMeterLabel("PEAK", 8, 18);
            pnlInputPeak = CreateMeterPanel(8, 35);
            lblInputRmsTitle = CreateMeterLabel("RMS", 50, 18);
            pnlInputRms = CreateMeterPanel(50, 35);
            gbInputMeters.Controls.AddRange(new Control[] {
                lblInputPeakTitle, pnlInputPeak, lblInputRmsTitle, pnlInputRms
            });

            gbOutputMeters = new GroupBox
            {
                Text = "ВЫХОД",
                Location = new Point(700, 300),
                Size = new Size(95, 240),
                ForeColor = Color.FromArgb(255, 100, 100)
            };
            lblOutputPeakTitle = CreateMeterLabel("PEAK", 8, 18);
            pnlOutputPeak = CreateMeterPanel(8, 35);
            lblOutputRmsTitle = CreateMeterLabel("RMS", 50, 18);
            pnlOutputRms = CreateMeterPanel(50, 35);
            gbOutputMeters.Controls.AddRange(new Control[] {
                lblOutputPeakTitle, pnlOutputPeak, lblOutputRmsTitle, pnlOutputRms
            });

            // ===== ДОБАВЛЯЕМ ВСЁ НА ФОРМУ =====
            this.Controls.AddRange(new Control[] {
                btnLoadFile, btnPlayPause, btnStop,
                lblPosition, progressBar, lblLength, btnBypass,
                lblBand, cmbBand,
                gbCompressor, gbLimiter, gbBands,
                gbLowMeters, gbMidMeters, gbHighMeters,
                gbInputMeters, gbOutputMeters
            });

            this.ResumeLayout(false);
        }

        private Label CreateBandLabel(string text, Color color, int x, int y)
        {
            return new Label
            {
                Text = text,
                Location = new Point(x, y),
                Size = new Size(65, 18),
                ForeColor = color,
                TextAlign = ContentAlignment.MiddleRight
            };
        }

        private Label CreateBandValueLabel(string text, Color color, int x, int y)
        {
            return new Label
            {
                Text = text,
                Location = new Point(x, y),
                Size = new Size(90, 18),
                ForeColor = color,
                Font = new Font("Consolas", 11, FontStyle.Bold),
                TextAlign = ContentAlignment.MiddleLeft
            };
        }

        private Label CreateMeterLabel(string text, int x, int y)
        {
            return new Label
            {
                Text = text,
                Location = new Point(x, y),
                Size = new Size(35, 15),
                TextAlign = ContentAlignment.MiddleCenter,
                Font = new Font("Arial", 7, FontStyle.Bold),
                ForeColor = Color.Gray
            };
        }

        private Panel CreateMeterPanel(int x, int y)
        {
            return new Panel
            {
                Location = new Point(x, y),
                Size = new Size(35, 320),
                BackColor = Color.FromArgb(20, 20, 20),
                BorderStyle = BorderStyle.FixedSingle
            };
        }

        private void SetupParameterRow(Label label, TrackBar trackBar, Label valueLabel,
            string text, int yPos, int min, int max, int defaultValue, string suffix,
            GroupBox parent, System.EventHandler scrollHandler)
        {
            label.Text = text + ":";
            label.Location = new Point(15, yPos + 3);
            label.Size = new Size(75, 16);
            label.ForeColor = Color.LightGray;

            trackBar.Minimum = min;
            trackBar.Maximum = max;
            trackBar.TickFrequency = Math.Max(1, (max - min) / 10);
            trackBar.Location = new Point(95, yPos);
            trackBar.Size = new Size(170, 24);
            trackBar.TickStyle = TickStyle.None;
            trackBar.Value = defaultValue;
            trackBar.Scroll += scrollHandler;

            valueLabel.Location = new Point(270, yPos + 3);
            valueLabel.Size = new Size(65, 16);
            valueLabel.TextAlign = ContentAlignment.MiddleRight;
            valueLabel.ForeColor = Color.FromArgb(0, 212, 255);

            if (suffix == ":1")
                valueLabel.Text = $"{defaultValue / 10f:F1}:1";
            else if (suffix == "ms" && defaultValue <= 500)
                valueLabel.Text = $"{defaultValue / 10f:F1} ms";
            else if (suffix == "ms")
                valueLabel.Text = $"{defaultValue} ms";
            else
                valueLabel.Text = $"{defaultValue} {suffix}";

            parent.Controls.AddRange(new Control[] { label, trackBar, valueLabel });
        }
    }
}
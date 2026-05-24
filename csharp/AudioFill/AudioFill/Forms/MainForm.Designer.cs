using AudioFill.Controls;

namespace AudioFill.Forms
{
    partial class MainForm
    {
        private System.ComponentModel.IContainer components = null;

        private Panel panelContent;
        private Panel panelTabs;
        private Button btnTabSpectrogram;
        private Button btnTabFrequency;
        private Button btnTabLog;
        private Button btnTabRestore;

        private SpectrogramView spectrogramView;
        private FrequencyChartView frequencyChartView;
        private TextBox txtLog;

        private Panel panelRestore;
        private TrackBar trkEnvelope;
        private Label lblEnvelope;
        private Label lblEnvelopeVal;
        private Button btnRestore;
        private Button btnPlayRestored;
        private Button btnSaveRestored;
        private Label lblRestoreStatus;
        private Label lblBands;
        private NumericUpDown numBands;
        private Label lblNoise;
        private NumericUpDown numNoise;

        private Panel panelSettings;
        private Button btnOpen;
        private Button btnAnalyze;
        private Button btnSaveLog;
        private Button btnSaveCsv;
        private Button btnSaveSpectrogram;
        private ComboBox cmbFftSize;
        private ComboBox cmbWindow;
        private ComboBox cmbOverlap;
        private RadioButton rbLogScale;
        private RadioButton rbLinearScale;
        private NumericUpDown numThreshold;
        private ProgressBar progressBar;
        private GroupBox groupScale;
        private Label lblFileInfo;
        private Label lblFftSize;
        private Label lblWindow;
        private Label lblOverlap;
        private Label lblThreshold;
        private Label lblStatus;

        protected override void Dispose(bool disposing)
        {
            if (disposing && components != null) components.Dispose();
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            panelContent = new Panel();
            panelRestore = new Panel();
            lblParamsTitle = new Label();
            lblBands = new Label();
            numBands = new NumericUpDown();
            lblNoise = new Label();
            numNoise = new NumericUpDown();
            lblEnvelope = new Label();
            trkEnvelope = new TrackBar();
            lblEnvelopeVal = new Label();
            btnRestore = new Button();
            btnPlayRestored = new Button();
            btnSaveRestored = new Button();
            lblRestoreStatus = new Label();
            spectrogramView = new SpectrogramView();
            frequencyChartView = new FrequencyChartView();
            txtLog = new TextBox();
            panelTabs = new Panel();
            btnTabSpectrogram = new Button();
            btnTabFrequency = new Button();
            btnTabLog = new Button();
            btnTabRestore = new Button();
            panelSettings = new Panel();
            lblFileInfo = new Label();
            btnOpen = new Button();
            btnAnalyze = new Button();
            lblFftSize = new Label();
            cmbFftSize = new ComboBox();
            lblWindow = new Label();
            cmbWindow = new ComboBox();
            lblOverlap = new Label();
            cmbOverlap = new ComboBox();
            lblThreshold = new Label();
            numThreshold = new NumericUpDown();
            groupScale = new GroupBox();
            rbLinearScale = new RadioButton();
            rbLogScale = new RadioButton();
            btnSaveLog = new Button();
            btnSaveCsv = new Button();
            btnSaveSpectrogram = new Button();
            progressBar = new ProgressBar();
            lblStatus = new Label();
            panelContent.SuspendLayout();
            panelRestore.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)numBands).BeginInit();
            ((System.ComponentModel.ISupportInitialize)numNoise).BeginInit();
            ((System.ComponentModel.ISupportInitialize)trkEnvelope).BeginInit();
            ((System.ComponentModel.ISupportInitialize)spectrogramView).BeginInit();
            ((System.ComponentModel.ISupportInitialize)frequencyChartView).BeginInit();
            panelTabs.SuspendLayout();
            panelSettings.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)numThreshold).BeginInit();
            groupScale.SuspendLayout();
            SuspendLayout();
            // 
            // panelContent
            // 
            panelContent.Controls.Add(panelRestore);
            panelContent.Controls.Add(spectrogramView);
            panelContent.Controls.Add(frequencyChartView);
            panelContent.Controls.Add(txtLog);
            panelContent.Location = new Point(0, 131);
            panelContent.Name = "panelContent";
            panelContent.Size = new Size(1100, 542);
            panelContent.TabIndex = 0;
            // 
            // panelRestore
            // 
            panelRestore.AutoScroll = true;
            panelRestore.Controls.Add(lblParamsTitle);
            panelRestore.Controls.Add(lblBands);
            panelRestore.Controls.Add(numBands);
            panelRestore.Controls.Add(lblNoise);
            panelRestore.Controls.Add(numNoise);
            panelRestore.Controls.Add(lblEnvelope);
            panelRestore.Controls.Add(trkEnvelope);
            panelRestore.Controls.Add(lblEnvelopeVal);
            panelRestore.Controls.Add(btnRestore);
            panelRestore.Controls.Add(btnPlayRestored);
            panelRestore.Controls.Add(btnSaveRestored);
            panelRestore.Controls.Add(lblRestoreStatus);
            panelRestore.Location = new Point(0, 0);
            panelRestore.Name = "panelRestore";
            panelRestore.Size = new Size(1100, 542);
            panelRestore.TabIndex = 3;
            panelRestore.Visible = false;
            // 
            // lblParamsTitle
            // 
            lblParamsTitle.AutoSize = true;
            lblParamsTitle.Font = new Font("Segoe UI", 9F, FontStyle.Bold);
            lblParamsTitle.Location = new Point(20, 15);
            lblParamsTitle.Name = "lblParamsTitle";
            lblParamsTitle.Size = new Size(154, 15);
            lblParamsTitle.TabIndex = 0;
            lblParamsTitle.Text = "Параметры реставрации:";
            // 
            // lblBands
            // 
            lblBands.AutoSize = true;
            lblBands.Font = new Font("Segoe UI", 9F);
            lblBands.Location = new Point(20, 46);
            lblBands.Name = "lblBands";
            lblBands.Size = new Size(85, 15);
            lblBands.TabIndex = 1;
            lblBands.Text = "Полос сдвига:";
            // 
            // numBands
            // 
            numBands.BorderStyle = BorderStyle.FixedSingle;
            numBands.Font = new Font("Segoe UI", 9F);
            numBands.Location = new Point(20, 64);
            numBands.Maximum = new decimal(new int[] { 48, 0, 0, 0 });
            numBands.Minimum = new decimal(new int[] { 1, 0, 0, 0 });
            numBands.Name = "numBands";
            numBands.Size = new Size(85, 23);
            numBands.TabIndex = 2;
            numBands.Value = new decimal(new int[] { 24, 0, 0, 0 });
            // 
            // lblNoise
            // 
            lblNoise.AutoSize = true;
            lblNoise.Font = new Font("Segoe UI", 9F);
            lblNoise.Location = new Point(111, 46);
            lblNoise.Name = "lblNoise";
            lblNoise.Size = new Size(49, 15);
            lblNoise.TabIndex = 3;
            lblNoise.Text = "Шум %:";
            // 
            // numNoise
            // 
            numNoise.BorderStyle = BorderStyle.FixedSingle;
            numNoise.Font = new Font("Segoe UI", 9F);
            numNoise.Location = new Point(111, 64);
            numNoise.Maximum = new decimal(new int[] { 50, 0, 0, 0 });
            numNoise.Name = "numNoise";
            numNoise.Size = new Size(85, 23);
            numNoise.TabIndex = 4;
            numNoise.Value = new decimal(new int[] { 15, 0, 0, 0 });
            // 
            // lblEnvelope
            // 
            lblEnvelope.AutoSize = true;
            lblEnvelope.Font = new Font("Segoe UI", 9F);
            lblEnvelope.Location = new Point(20, 95);
            lblEnvelope.Name = "lblEnvelope";
            lblEnvelope.Size = new Size(124, 15);
            lblEnvelope.TabIndex = 5;
            lblEnvelope.Text = "Уровень заполнения:";
            // 
            // trkEnvelope
            // 
            trkEnvelope.Location = new Point(20, 113);
            trkEnvelope.Maximum = 200;
            trkEnvelope.Name = "trkEnvelope";
            trkEnvelope.Size = new Size(250, 45);
            trkEnvelope.TabIndex = 6;
            trkEnvelope.TickFrequency = 20;
            trkEnvelope.Value = 100;
            // 
            // lblEnvelopeVal
            // 
            lblEnvelopeVal.AutoSize = true;
            lblEnvelopeVal.Font = new Font("Segoe UI", 9F, FontStyle.Bold);
            lblEnvelopeVal.Location = new Point(280, 116);
            lblEnvelopeVal.Name = "lblEnvelopeVal";
            lblEnvelopeVal.Size = new Size(38, 15);
            lblEnvelopeVal.TabIndex = 7;
            lblEnvelopeVal.Text = "100%";
            // 
            // btnRestore
            // 
            btnRestore.Cursor = Cursors.Hand;
            btnRestore.Enabled = false;
            btnRestore.FlatStyle = FlatStyle.Flat;
            btnRestore.Font = new Font("Segoe UI", 9F);
            btnRestore.Location = new Point(20, 164);
            btnRestore.Name = "btnRestore";
            btnRestore.Size = new Size(140, 36);
            btnRestore.TabIndex = 8;
            btnRestore.Text = "🔄 Восстановить";
            // 
            // btnPlayRestored
            // 
            btnPlayRestored.Cursor = Cursors.Hand;
            btnPlayRestored.Enabled = false;
            btnPlayRestored.FlatStyle = FlatStyle.Flat;
            btnPlayRestored.Font = new Font("Segoe UI", 9F);
            btnPlayRestored.Location = new Point(170, 164);
            btnPlayRestored.Name = "btnPlayRestored";
            btnPlayRestored.Size = new Size(140, 36);
            btnPlayRestored.TabIndex = 9;
            btnPlayRestored.Text = "▶ Предпрослушать";
            // 
            // btnSaveRestored
            // 
            btnSaveRestored.Cursor = Cursors.Hand;
            btnSaveRestored.Enabled = false;
            btnSaveRestored.FlatStyle = FlatStyle.Flat;
            btnSaveRestored.Font = new Font("Segoe UI", 9F);
            btnSaveRestored.Location = new Point(320, 164);
            btnSaveRestored.Name = "btnSaveRestored";
            btnSaveRestored.Size = new Size(140, 36);
            btnSaveRestored.TabIndex = 10;
            btnSaveRestored.Text = "💾 Сохранить WAV";
            // 
            // lblRestoreStatus
            // 
            lblRestoreStatus.AutoSize = true;
            lblRestoreStatus.Font = new Font("Segoe UI", 9F);
            lblRestoreStatus.Location = new Point(20, 209);
            lblRestoreStatus.Name = "lblRestoreStatus";
            lblRestoreStatus.Size = new Size(197, 15);
            lblRestoreStatus.TabIndex = 11;
            lblRestoreStatus.Text = "Сначала выполните анализ файла";
            // 
            // spectrogramView
            // 
            spectrogramView.BackColor = Color.FromArgb(9, 9, 11);
            spectrogramView.Dock = DockStyle.Fill;
            spectrogramView.Location = new Point(0, 0);
            spectrogramView.Name = "spectrogramView";
            spectrogramView.Size = new Size(1100, 542);
            spectrogramView.TabIndex = 0;
            spectrogramView.TabStop = false;
            // 
            // frequencyChartView
            // 
            frequencyChartView.BackColor = Color.FromArgb(9, 9, 11);
            frequencyChartView.Dock = DockStyle.Fill;
            frequencyChartView.Location = new Point(0, 0);
            frequencyChartView.Name = "frequencyChartView";
            frequencyChartView.Size = new Size(1100, 542);
            frequencyChartView.TabIndex = 1;
            frequencyChartView.TabStop = false;
            frequencyChartView.Visible = false;
            // 
            // txtLog
            // 
            txtLog.BorderStyle = BorderStyle.None;
            txtLog.Dock = DockStyle.Fill;
            txtLog.Font = new Font("Consolas", 9F);
            txtLog.Location = new Point(0, 0);
            txtLog.Multiline = true;
            txtLog.Name = "txtLog";
            txtLog.ReadOnly = true;
            txtLog.ScrollBars = ScrollBars.Vertical;
            txtLog.Size = new Size(1100, 542);
            txtLog.TabIndex = 2;
            txtLog.Visible = false;
            // 
            // panelTabs
            // 
            panelTabs.Controls.Add(btnTabSpectrogram);
            panelTabs.Controls.Add(btnTabFrequency);
            panelTabs.Controls.Add(btnTabLog);
            panelTabs.Controls.Add(btnTabRestore);
            panelTabs.Dock = DockStyle.Top;
            panelTabs.Location = new Point(0, 100);
            panelTabs.Name = "panelTabs";
            panelTabs.Size = new Size(1100, 30);
            panelTabs.TabIndex = 1;
            // 
            // btnTabSpectrogram
            // 
            btnTabSpectrogram.Cursor = Cursors.Hand;
            btnTabSpectrogram.FlatAppearance.BorderSize = 0;
            btnTabSpectrogram.FlatStyle = FlatStyle.Flat;
            btnTabSpectrogram.Font = new Font("Segoe UI", 9F);
            btnTabSpectrogram.Location = new Point(0, 0);
            btnTabSpectrogram.Name = "btnTabSpectrogram";
            btnTabSpectrogram.Size = new Size(130, 30);
            btnTabSpectrogram.TabIndex = 0;
            btnTabSpectrogram.Text = "Спектрограмма";
            btnTabSpectrogram.UseVisualStyleBackColor = false;
            // 
            // btnTabFrequency
            // 
            btnTabFrequency.Cursor = Cursors.Hand;
            btnTabFrequency.FlatAppearance.BorderSize = 0;
            btnTabFrequency.FlatStyle = FlatStyle.Flat;
            btnTabFrequency.Font = new Font("Segoe UI", 9F);
            btnTabFrequency.Location = new Point(130, 0);
            btnTabFrequency.Name = "btnTabFrequency";
            btnTabFrequency.Size = new Size(60, 30);
            btnTabFrequency.TabIndex = 1;
            btnTabFrequency.Text = "АЧХ";
            btnTabFrequency.UseVisualStyleBackColor = false;
            // 
            // btnTabLog
            // 
            btnTabLog.Cursor = Cursors.Hand;
            btnTabLog.FlatAppearance.BorderSize = 0;
            btnTabLog.FlatStyle = FlatStyle.Flat;
            btnTabLog.Font = new Font("Segoe UI", 9F);
            btnTabLog.Location = new Point(190, 0);
            btnTabLog.Name = "btnTabLog";
            btnTabLog.Size = new Size(60, 30);
            btnTabLog.TabIndex = 2;
            btnTabLog.Text = "Лог";
            btnTabLog.UseVisualStyleBackColor = false;
            // 
            // btnTabRestore
            // 
            btnTabRestore.Cursor = Cursors.Hand;
            btnTabRestore.FlatAppearance.BorderSize = 0;
            btnTabRestore.FlatStyle = FlatStyle.Flat;
            btnTabRestore.Font = new Font("Segoe UI", 9F);
            btnTabRestore.Location = new Point(250, 0);
            btnTabRestore.Name = "btnTabRestore";
            btnTabRestore.Size = new Size(100, 30);
            btnTabRestore.TabIndex = 3;
            btnTabRestore.Text = "Реставрация";
            btnTabRestore.UseVisualStyleBackColor = false;
            // 
            // panelSettings
            // 
            panelSettings.Controls.Add(lblFileInfo);
            panelSettings.Controls.Add(btnOpen);
            panelSettings.Controls.Add(btnAnalyze);
            panelSettings.Controls.Add(lblFftSize);
            panelSettings.Controls.Add(cmbFftSize);
            panelSettings.Controls.Add(lblWindow);
            panelSettings.Controls.Add(cmbWindow);
            panelSettings.Controls.Add(lblOverlap);
            panelSettings.Controls.Add(cmbOverlap);
            panelSettings.Controls.Add(lblThreshold);
            panelSettings.Controls.Add(numThreshold);
            panelSettings.Controls.Add(groupScale);
            panelSettings.Controls.Add(btnSaveLog);
            panelSettings.Controls.Add(btnSaveCsv);
            panelSettings.Controls.Add(btnSaveSpectrogram);
            panelSettings.Dock = DockStyle.Top;
            panelSettings.Location = new Point(0, 0);
            panelSettings.Name = "panelSettings";
            panelSettings.Size = new Size(1100, 100);
            panelSettings.TabIndex = 4;
            // 
            // lblFileInfo
            // 
            lblFileInfo.AutoSize = true;
            lblFileInfo.Font = new Font("Segoe UI", 9F);
            lblFileInfo.Location = new Point(16, 12);
            lblFileInfo.Name = "lblFileInfo";
            lblFileInfo.Size = new Size(97, 15);
            lblFileInfo.TabIndex = 0;
            lblFileInfo.Text = "Файл не выбран";
            // 
            // btnOpen
            // 
            btnOpen.Cursor = Cursors.Hand;
            btnOpen.FlatStyle = FlatStyle.Flat;
            btnOpen.Font = new Font("Segoe UI", 9F);
            btnOpen.Location = new Point(16, 48);
            btnOpen.Name = "btnOpen";
            btnOpen.Size = new Size(130, 30);
            btnOpen.TabIndex = 1;
            btnOpen.Text = "📂 Открыть файл";
            btnOpen.UseVisualStyleBackColor = false;
            // 
            // btnAnalyze
            // 
            btnAnalyze.Cursor = Cursors.Hand;
            btnAnalyze.Enabled = false;
            btnAnalyze.FlatStyle = FlatStyle.Flat;
            btnAnalyze.Font = new Font("Segoe UI", 9F);
            btnAnalyze.Location = new Point(154, 48);
            btnAnalyze.Name = "btnAnalyze";
            btnAnalyze.Size = new Size(130, 30);
            btnAnalyze.TabIndex = 2;
            btnAnalyze.Text = "▶ Анализировать";
            btnAnalyze.UseVisualStyleBackColor = false;
            // 
            // lblFftSize
            // 
            lblFftSize.AutoSize = true;
            lblFftSize.Font = new Font("Segoe UI", 8F);
            lblFftSize.Location = new Point(300, 14);
            lblFftSize.Name = "lblFftSize";
            lblFftSize.Size = new Size(69, 13);
            lblFftSize.TabIndex = 3;
            lblFftSize.Text = "Размер БПФ";
            // 
            // cmbFftSize
            // 
            cmbFftSize.DropDownStyle = ComboBoxStyle.DropDownList;
            cmbFftSize.FlatStyle = FlatStyle.Flat;
            cmbFftSize.Font = new Font("Segoe UI", 9F);
            cmbFftSize.Items.AddRange(new object[] { "512", "1024", "2048", "4096", "8192", "16384" });
            cmbFftSize.Location = new Point(300, 50);
            cmbFftSize.Name = "cmbFftSize";
            cmbFftSize.Size = new Size(80, 23);
            cmbFftSize.TabIndex = 4;
            // 
            // lblWindow
            // 
            lblWindow.AutoSize = true;
            lblWindow.Font = new Font("Segoe UI", 8F);
            lblWindow.Location = new Point(392, 14);
            lblWindow.Name = "lblWindow";
            lblWindow.Size = new Size(36, 13);
            lblWindow.TabIndex = 5;
            lblWindow.Text = "Окно";
            // 
            // cmbWindow
            // 
            cmbWindow.DropDownStyle = ComboBoxStyle.DropDownList;
            cmbWindow.FlatStyle = FlatStyle.Flat;
            cmbWindow.Font = new Font("Segoe UI", 9F);
            cmbWindow.Items.AddRange(new object[] { "Hann", "Hamming", "Blackman", "Rect" });
            cmbWindow.Location = new Point(392, 50);
            cmbWindow.Name = "cmbWindow";
            cmbWindow.Size = new Size(90, 23);
            cmbWindow.TabIndex = 6;
            // 
            // lblOverlap
            // 
            lblOverlap.AutoSize = true;
            lblOverlap.Font = new Font("Segoe UI", 8F);
            lblOverlap.Location = new Point(494, 14);
            lblOverlap.Name = "lblOverlap";
            lblOverlap.Size = new Size(73, 13);
            lblOverlap.TabIndex = 7;
            lblOverlap.Text = "Перекрытие";
            // 
            // cmbOverlap
            // 
            cmbOverlap.DropDownStyle = ComboBoxStyle.DropDownList;
            cmbOverlap.FlatStyle = FlatStyle.Flat;
            cmbOverlap.Font = new Font("Segoe UI", 9F);
            cmbOverlap.Items.AddRange(new object[] { "0%", "25%", "50%", "75%" });
            cmbOverlap.Location = new Point(494, 50);
            cmbOverlap.Name = "cmbOverlap";
            cmbOverlap.Size = new Size(70, 23);
            cmbOverlap.TabIndex = 8;
            // 
            // lblThreshold
            // 
            lblThreshold.AutoSize = true;
            lblThreshold.Font = new Font("Segoe UI", 8F);
            lblThreshold.Location = new Point(576, 14);
            lblThreshold.Name = "lblThreshold";
            lblThreshold.Size = new Size(62, 13);
            lblThreshold.TabIndex = 9;
            lblThreshold.Text = "Порог (дБ)";
            // 
            // numThreshold
            // 
            numThreshold.BorderStyle = BorderStyle.FixedSingle;
            numThreshold.Font = new Font("Segoe UI", 9F);
            numThreshold.Location = new Point(576, 50);
            numThreshold.Maximum = new decimal(new int[] { 10, 0, 0, int.MinValue });
            numThreshold.Minimum = new decimal(new int[] { 100, 0, 0, int.MinValue });
            numThreshold.Name = "numThreshold";
            numThreshold.Size = new Size(60, 23);
            numThreshold.TabIndex = 10;
            numThreshold.Value = new decimal(new int[] { 40, 0, 0, int.MinValue });
            // 
            // groupScale
            // 
            groupScale.Controls.Add(rbLinearScale);
            groupScale.Controls.Add(rbLogScale);
            groupScale.Font = new Font("Segoe UI", 9F);
            groupScale.Location = new Point(656, 32);
            groupScale.Name = "groupScale";
            groupScale.Size = new Size(221, 52);
            groupScale.TabIndex = 11;
            groupScale.TabStop = false;
            groupScale.Text = "Шкала частот";
            // 
            // rbLinearScale
            // 
            rbLinearScale.AutoSize = true;
            rbLinearScale.Font = new Font("Segoe UI", 9F);
            rbLinearScale.Location = new Point(136, 20);
            rbLinearScale.Name = "rbLinearScale";
            rbLinearScale.Size = new Size(79, 19);
            rbLinearScale.TabIndex = 0;
            rbLinearScale.Text = "Линейная";
            // 
            // rbLogScale
            // 
            rbLogScale.AutoSize = true;
            rbLogScale.Checked = true;
            rbLogScale.Font = new Font("Segoe UI", 9F);
            rbLogScale.Location = new Point(8, 20);
            rbLogScale.Name = "rbLogScale";
            rbLogScale.Size = new Size(127, 19);
            rbLogScale.TabIndex = 1;
            rbLogScale.TabStop = true;
            rbLogScale.Text = "Логарифмическая";
            // 
            // btnSaveLog
            // 
            btnSaveLog.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            btnSaveLog.Cursor = Cursors.Hand;
            btnSaveLog.Enabled = false;
            btnSaveLog.FlatStyle = FlatStyle.Flat;
            btnSaveLog.Font = new Font("Segoe UI", 9F);
            btnSaveLog.Location = new Point(1760, 48);
            btnSaveLog.Name = "btnSaveLog";
            btnSaveLog.Size = new Size(100, 30);
            btnSaveLog.TabIndex = 12;
            btnSaveLog.Text = "💾 Лог";
            btnSaveLog.UseVisualStyleBackColor = false;
            // 
            // btnSaveCsv
            // 
            btnSaveCsv.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            btnSaveCsv.Cursor = Cursors.Hand;
            btnSaveCsv.Enabled = false;
            btnSaveCsv.FlatStyle = FlatStyle.Flat;
            btnSaveCsv.Font = new Font("Segoe UI", 9F);
            btnSaveCsv.Location = new Point(1868, 48);
            btnSaveCsv.Name = "btnSaveCsv";
            btnSaveCsv.Size = new Size(100, 30);
            btnSaveCsv.TabIndex = 13;
            btnSaveCsv.Text = "📊 CSV";
            btnSaveCsv.UseVisualStyleBackColor = false;
            // 
            // btnSaveSpectrogram
            // 
            btnSaveSpectrogram.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            btnSaveSpectrogram.Cursor = Cursors.Hand;
            btnSaveSpectrogram.Enabled = false;
            btnSaveSpectrogram.FlatStyle = FlatStyle.Flat;
            btnSaveSpectrogram.Font = new Font("Segoe UI", 8F);
            btnSaveSpectrogram.Location = new Point(1760, 82);
            btnSaveSpectrogram.Name = "btnSaveSpectrogram";
            btnSaveSpectrogram.Size = new Size(208, 24);
            btnSaveSpectrogram.TabIndex = 14;
            btnSaveSpectrogram.Text = "🖼 Спектрограмма (PNG)";
            btnSaveSpectrogram.UseVisualStyleBackColor = false;
            // 
            // progressBar
            // 
            progressBar.Dock = DockStyle.Bottom;
            progressBar.Location = new Point(0, 672);
            progressBar.Name = "progressBar";
            progressBar.Size = new Size(1100, 4);
            progressBar.TabIndex = 2;
            // 
            // lblStatus
            // 
            lblStatus.Dock = DockStyle.Bottom;
            lblStatus.Font = new Font("Segoe UI", 9F);
            lblStatus.Location = new Point(0, 676);
            lblStatus.Name = "lblStatus";
            lblStatus.Size = new Size(1100, 24);
            lblStatus.TabIndex = 3;
            lblStatus.Text = "Готов";
            lblStatus.TextAlign = ContentAlignment.MiddleLeft;
            // 
            // MainForm
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            ClientSize = new Size(1100, 700);
            Controls.Add(panelContent);
            Controls.Add(panelTabs);
            Controls.Add(progressBar);
            Controls.Add(lblStatus);
            Controls.Add(panelSettings);
            MinimumSize = new Size(900, 600);
            Name = "MainForm";
            StartPosition = FormStartPosition.CenterScreen;
            Text = "AudioFill";
            panelContent.ResumeLayout(false);
            panelContent.PerformLayout();
            panelRestore.ResumeLayout(false);
            panelRestore.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)numBands).EndInit();
            ((System.ComponentModel.ISupportInitialize)numNoise).EndInit();
            ((System.ComponentModel.ISupportInitialize)trkEnvelope).EndInit();
            ((System.ComponentModel.ISupportInitialize)spectrogramView).EndInit();
            ((System.ComponentModel.ISupportInitialize)frequencyChartView).EndInit();
            panelTabs.ResumeLayout(false);
            panelSettings.ResumeLayout(false);
            panelSettings.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)numThreshold).EndInit();
            groupScale.ResumeLayout(false);
            groupScale.PerformLayout();
            ResumeLayout(false);
        }

        private Label lblParamsTitle;
    }
}
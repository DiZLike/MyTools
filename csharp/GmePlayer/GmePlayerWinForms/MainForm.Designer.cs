namespace GmePlayerWinForms
{
    partial class MainForm
    {
        private System.ComponentModel.IContainer components = null;

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
            btnOpen = new Button();
            btnPlay = new Button();
            btnPause = new Button();
            btnStop = new Button();
            btnNext = new Button();
            btnPrev = new Button();
            trackPosition = new TrackBar();
            trackVolume = new TrackBar();
            lblTime = new Label();
            lblTrackInfo = new Label();
            lblStatus = new Label();
            listTracks = new ListBox();
            chkLoop = new CheckBox();
            lblVolume = new Label();
            ((System.ComponentModel.ISupportInitialize)trackPosition).BeginInit();
            ((System.ComponentModel.ISupportInitialize)trackVolume).BeginInit();
            SuspendLayout();

            // 
            // btnOpen
            // 
            btnOpen.FlatAppearance.BorderColor = Color.FromArgb(80, 80, 80);
            btnOpen.FlatAppearance.MouseDownBackColor = Color.FromArgb(60, 60, 60);
            btnOpen.FlatAppearance.MouseOverBackColor = Color.FromArgb(70, 70, 70);
            btnOpen.FlatStyle = FlatStyle.Flat;
            btnOpen.Font = new Font("Segoe UI", 10F, FontStyle.Regular);
            btnOpen.ForeColor = Color.FromArgb(200, 200, 200);
            btnOpen.Location = new Point(12, 15);
            btnOpen.Name = "btnOpen";
            btnOpen.Size = new Size(90, 34);
            btnOpen.TabIndex = 0;
            btnOpen.Text = "📂 Open";
            btnOpen.UseVisualStyleBackColor = false;
            btnOpen.BackColor = Color.FromArgb(50, 50, 50);
            btnOpen.Click += btnOpen_Click;

            // 
            // btnPlay
            // 
            btnPlay.FlatAppearance.BorderColor = Color.FromArgb(80, 80, 80);
            btnPlay.FlatAppearance.MouseDownBackColor = Color.FromArgb(60, 60, 60);
            btnPlay.FlatAppearance.MouseOverBackColor = Color.FromArgb(70, 70, 70);
            btnPlay.FlatStyle = FlatStyle.Flat;
            btnPlay.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            btnPlay.ForeColor = Color.FromArgb(100, 200, 100);
            btnPlay.Location = new Point(108, 15);
            btnPlay.Name = "btnPlay";
            btnPlay.Size = new Size(50, 34);
            btnPlay.TabIndex = 1;
            btnPlay.Text = "▶";
            btnPlay.UseVisualStyleBackColor = false;
            btnPlay.BackColor = Color.FromArgb(50, 50, 50);
            btnPlay.Click += btnPlay_Click;

            // 
            // btnPause
            // 
            btnPause.FlatAppearance.BorderColor = Color.FromArgb(80, 80, 80);
            btnPause.FlatAppearance.MouseDownBackColor = Color.FromArgb(60, 60, 60);
            btnPause.FlatAppearance.MouseOverBackColor = Color.FromArgb(70, 70, 70);
            btnPause.FlatStyle = FlatStyle.Flat;
            btnPause.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            btnPause.ForeColor = Color.FromArgb(255, 200, 100);
            btnPause.Location = new Point(164, 15);
            btnPause.Name = "btnPause";
            btnPause.Size = new Size(50, 34);
            btnPause.TabIndex = 2;
            btnPause.Text = "⏸";
            btnPause.UseVisualStyleBackColor = false;
            btnPause.BackColor = Color.FromArgb(50, 50, 50);
            btnPause.Click += btnPause_Click;

            // 
            // btnStop
            // 
            btnStop.FlatAppearance.BorderColor = Color.FromArgb(80, 80, 80);
            btnStop.FlatAppearance.MouseDownBackColor = Color.FromArgb(60, 60, 60);
            btnStop.FlatAppearance.MouseOverBackColor = Color.FromArgb(70, 70, 70);
            btnStop.FlatStyle = FlatStyle.Flat;
            btnStop.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            btnStop.ForeColor = Color.FromArgb(255, 120, 120);
            btnStop.Location = new Point(220, 15);
            btnStop.Name = "btnStop";
            btnStop.Size = new Size(50, 34);
            btnStop.TabIndex = 3;
            btnStop.Text = "⏹";
            btnStop.UseVisualStyleBackColor = false;
            btnStop.BackColor = Color.FromArgb(50, 50, 50);
            btnStop.Click += btnStop_Click;

            // 
            // btnNext
            // 
            btnNext.FlatAppearance.BorderColor = Color.FromArgb(80, 80, 80);
            btnNext.FlatAppearance.MouseDownBackColor = Color.FromArgb(60, 60, 60);
            btnNext.FlatAppearance.MouseOverBackColor = Color.FromArgb(70, 70, 70);
            btnNext.FlatStyle = FlatStyle.Flat;
            btnNext.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            btnNext.ForeColor = Color.FromArgb(200, 200, 200);
            btnNext.Location = new Point(332, 15);
            btnNext.Name = "btnNext";
            btnNext.Size = new Size(50, 34);
            btnNext.TabIndex = 4;
            btnNext.Text = "⏭";
            btnNext.UseVisualStyleBackColor = false;
            btnNext.BackColor = Color.FromArgb(50, 50, 50);
            btnNext.Click += btnNext_Click;

            // 
            // btnPrev
            // 
            btnPrev.FlatAppearance.BorderColor = Color.FromArgb(80, 80, 80);
            btnPrev.FlatAppearance.MouseDownBackColor = Color.FromArgb(60, 60, 60);
            btnPrev.FlatAppearance.MouseOverBackColor = Color.FromArgb(70, 70, 70);
            btnPrev.FlatStyle = FlatStyle.Flat;
            btnPrev.Font = new Font("Segoe UI", 12F, FontStyle.Bold);
            btnPrev.ForeColor = Color.FromArgb(200, 200, 200);
            btnPrev.Location = new Point(276, 15);
            btnPrev.Name = "btnPrev";
            btnPrev.Size = new Size(50, 34);
            btnPrev.TabIndex = 5;
            btnPrev.Text = "⏮";
            btnPrev.UseVisualStyleBackColor = false;
            btnPrev.BackColor = Color.FromArgb(50, 50, 50);
            btnPrev.Click += btnPrev_Click;

            // 
            // trackPosition
            // 
            trackPosition.BackColor = Color.FromArgb(45, 45, 48);
            trackPosition.Location = new Point(12, 60);
            trackPosition.Maximum = 300000;
            trackPosition.Name = "trackPosition";
            trackPosition.Size = new Size(550, 45);
            trackPosition.TabIndex = 6;
            trackPosition.TickFrequency = 60000;
            trackPosition.MouseDown += trackPosition_MouseDown;
            trackPosition.MouseUp += trackPosition_MouseUp;

            // 
            // trackVolume
            // 
            trackVolume.BackColor = Color.FromArgb(45, 45, 48);
            trackVolume.Location = new Point(568, 60);
            trackVolume.Maximum = 100;
            trackVolume.Name = "trackVolume";
            trackVolume.Size = new Size(104, 45);
            trackVolume.TabIndex = 7;
            trackVolume.TickFrequency = 25;
            trackVolume.Value = 80;
            trackVolume.Scroll += trackVolume_Scroll;

            // 
            // lblTime
            // 
            lblTime.AutoSize = true;
            lblTime.Font = new Font("Segoe UI", 9F, FontStyle.Regular);
            lblTime.ForeColor = Color.FromArgb(180, 180, 180);
            lblTime.Location = new Point(12, 95);
            lblTime.Name = "lblTime";
            lblTime.Size = new Size(72, 15);
            lblTime.TabIndex = 8;
            lblTime.Text = "00:00 / 00:00";

            // 
            // lblTrackInfo
            // 
            lblTrackInfo.BackColor = Color.FromArgb(55, 55, 60);
            lblTrackInfo.BorderStyle = BorderStyle.FixedSingle;
            lblTrackInfo.ForeColor = Color.FromArgb(200, 200, 200);
            lblTrackInfo.Location = new Point(12, 120);
            lblTrackInfo.Name = "lblTrackInfo";
            lblTrackInfo.Padding = new Padding(8);
            lblTrackInfo.Size = new Size(400, 120);
            lblTrackInfo.TabIndex = 9;
            lblTrackInfo.Text = "No file loaded";

            // 
            // lblStatus
            // 
            lblStatus.AutoSize = true;
            lblStatus.Font = new Font("Segoe UI", 9F, FontStyle.Regular);
            lblStatus.ForeColor = Color.FromArgb(150, 150, 150);
            lblStatus.Location = new Point(12, 405);
            lblStatus.Name = "lblStatus";
            lblStatus.Size = new Size(78, 15);
            lblStatus.TabIndex = 10;
            lblStatus.Text = "Ready to play";

            // 
            // listTracks
            // 
            listTracks.BackColor = Color.FromArgb(55, 55, 60);
            listTracks.BorderStyle = BorderStyle.FixedSingle;
            listTracks.Font = new Font("Segoe UI", 9F, FontStyle.Regular);
            listTracks.ForeColor = Color.FromArgb(200, 200, 200);
            listTracks.Location = new Point(422, 120);
            listTracks.Name = "listTracks";
            listTracks.Size = new Size(260, 250);
            listTracks.TabIndex = 11;
            listTracks.SelectedIndexChanged += listTracks_SelectedIndexChanged;

            // 
            // chkLoop
            // 
            chkLoop.AutoSize = true;
            chkLoop.Font = new Font("Segoe UI", 9F, FontStyle.Regular);
            chkLoop.ForeColor = Color.FromArgb(200, 200, 200);
            chkLoop.Location = new Point(12, 370);
            chkLoop.Name = "chkLoop";
            chkLoop.Size = new Size(84, 19);
            chkLoop.TabIndex = 12;
            chkLoop.Text = "Loop Track";
            chkLoop.UseVisualStyleBackColor = true;
            chkLoop.BackColor = Color.FromArgb(45, 45, 48);

            // 
            // lblVolume
            // 
            lblVolume.AutoSize = true;
            lblVolume.Font = new Font("Segoe UI", 9F, FontStyle.Regular);
            lblVolume.ForeColor = Color.FromArgb(180, 180, 180);
            lblVolume.Location = new Point(678, 65);
            lblVolume.Name = "lblVolume";
            lblVolume.Size = new Size(29, 15);
            lblVolume.TabIndex = 14;
            lblVolume.Text = "80%";

            // 
            // MainForm
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            BackColor = Color.FromArgb(45, 45, 48);
            ClientSize = new Size(700, 440);
            Controls.Add(lblVolume);
            Controls.Add(chkLoop);
            Controls.Add(listTracks);
            Controls.Add(lblStatus);
            Controls.Add(lblTrackInfo);
            Controls.Add(lblTime);
            Controls.Add(trackVolume);
            Controls.Add(trackPosition);
            Controls.Add(btnPrev);
            Controls.Add(btnNext);
            Controls.Add(btnStop);
            Controls.Add(btnPause);
            Controls.Add(btnPlay);
            Controls.Add(btnOpen);
            ForeColor = Color.FromArgb(200, 200, 200);
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            Name = "MainForm";
            StartPosition = FormStartPosition.CenterScreen;
            Text = "GME Player";
            ((System.ComponentModel.ISupportInitialize)trackPosition).EndInit();
            ((System.ComponentModel.ISupportInitialize)trackVolume).EndInit();
            ResumeLayout(false);
            PerformLayout();
        }

        private System.Windows.Forms.Button btnOpen;
        private System.Windows.Forms.Button btnPlay;
        private System.Windows.Forms.Button btnPause;
        private System.Windows.Forms.Button btnStop;
        private System.Windows.Forms.Button btnNext;
        private System.Windows.Forms.Button btnPrev;
        private System.Windows.Forms.TrackBar trackPosition;
        private System.Windows.Forms.TrackBar trackVolume;
        private System.Windows.Forms.Label lblTime;
        private System.Windows.Forms.Label lblTrackInfo;
        private System.Windows.Forms.Label lblStatus;
        private System.Windows.Forms.ListBox listTracks;
        private System.Windows.Forms.CheckBox chkLoop;
        private System.Windows.Forms.Label lblVolume;
    }
}
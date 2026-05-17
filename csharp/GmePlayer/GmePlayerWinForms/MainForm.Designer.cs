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
            this.btnOpen = new System.Windows.Forms.Button();
            this.btnPlay = new System.Windows.Forms.Button();
            this.btnPause = new System.Windows.Forms.Button();
            this.btnStop = new System.Windows.Forms.Button();
            this.btnNext = new System.Windows.Forms.Button();
            this.btnPrev = new System.Windows.Forms.Button();
            this.trackPosition = new System.Windows.Forms.TrackBar();
            this.trackVolume = new System.Windows.Forms.TrackBar();
            this.lblTime = new System.Windows.Forms.Label();
            this.lblTrackInfo = new System.Windows.Forms.Label();
            this.lblStatus = new System.Windows.Forms.Label();
            this.listTracks = new System.Windows.Forms.ListBox();
            this.chkLoop = new System.Windows.Forms.CheckBox();
            this.lblVolume = new System.Windows.Forms.Label();
            ((System.ComponentModel.ISupportInitialize)(this.trackPosition)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.trackVolume)).BeginInit();
            this.SuspendLayout();
            // 
            // btnOpen
            // 
            this.btnOpen.Location = new System.Drawing.Point(12, 12);
            this.btnOpen.Name = "btnOpen";
            this.btnOpen.Size = new System.Drawing.Size(80, 30);
            this.btnOpen.TabIndex = 0;
            this.btnOpen.Text = "📂 Open";
            this.btnOpen.UseVisualStyleBackColor = true;
            this.btnOpen.Click += new System.EventHandler(this.btnOpen_Click);
            // 
            // btnPlay
            // 
            this.btnPlay.Font = new System.Drawing.Font("Segoe UI", 12F, System.Drawing.FontStyle.Bold);
            this.btnPlay.Location = new System.Drawing.Point(98, 12);
            this.btnPlay.Name = "btnPlay";
            this.btnPlay.Size = new System.Drawing.Size(50, 30);
            this.btnPlay.TabIndex = 1;
            this.btnPlay.Text = "▶";
            this.btnPlay.UseVisualStyleBackColor = true;
            this.btnPlay.Click += new System.EventHandler(this.btnPlay_Click);
            // 
            // btnPause
            // 
            this.btnPause.Font = new System.Drawing.Font("Segoe UI", 12F, System.Drawing.FontStyle.Bold);
            this.btnPause.Location = new System.Drawing.Point(154, 12);
            this.btnPause.Name = "btnPause";
            this.btnPause.Size = new System.Drawing.Size(50, 30);
            this.btnPause.TabIndex = 2;
            this.btnPause.Text = "⏸";
            this.btnPause.UseVisualStyleBackColor = true;
            this.btnPause.Click += new System.EventHandler(this.btnPause_Click);
            // 
            // btnStop
            // 
            this.btnStop.Font = new System.Drawing.Font("Segoe UI", 12F, System.Drawing.FontStyle.Bold);
            this.btnStop.Location = new System.Drawing.Point(210, 12);
            this.btnStop.Name = "btnStop";
            this.btnStop.Size = new System.Drawing.Size(50, 30);
            this.btnStop.TabIndex = 3;
            this.btnStop.Text = "⏹";
            this.btnStop.UseVisualStyleBackColor = true;
            this.btnStop.Click += new System.EventHandler(this.btnStop_Click);
            // 
            // btnNext
            // 
            this.btnNext.Font = new System.Drawing.Font("Segoe UI", 12F, System.Drawing.FontStyle.Bold);
            this.btnNext.Location = new System.Drawing.Point(266, 12);
            this.btnNext.Name = "btnNext";
            this.btnNext.Size = new System.Drawing.Size(50, 30);
            this.btnNext.TabIndex = 4;
            this.btnNext.Text = "⏭";
            this.btnNext.UseVisualStyleBackColor = true;
            this.btnNext.Click += new System.EventHandler(this.btnNext_Click);
            // 
            // btnPrev
            // 
            this.btnPrev.Font = new System.Drawing.Font("Segoe UI", 12F, System.Drawing.FontStyle.Bold);
            this.btnPrev.Location = new System.Drawing.Point(322, 12);
            this.btnPrev.Name = "btnPrev";
            this.btnPrev.Size = new System.Drawing.Size(50, 30);
            this.btnPrev.TabIndex = 5;
            this.btnPrev.Text = "⏮";
            this.btnPrev.UseVisualStyleBackColor = true;
            this.btnPrev.Click += new System.EventHandler(this.btnPrev_Click);
            // 
            // trackPosition
            // 
            this.trackPosition.Location = new System.Drawing.Point(12, 55);
            this.trackPosition.Maximum = 300000;
            this.trackPosition.Name = "trackPosition";
            this.trackPosition.Size = new System.Drawing.Size(550, 45);
            this.trackPosition.TabIndex = 6;
            this.trackPosition.TickFrequency = 60000;
            this.trackPosition.MouseDown += new System.Windows.Forms.MouseEventHandler(this.trackPosition_MouseDown);
            this.trackPosition.MouseUp += new System.Windows.Forms.MouseEventHandler(this.trackPosition_MouseUp);
            // 
            // trackVolume
            // 
            this.trackVolume.Location = new System.Drawing.Point(568, 55);
            this.trackVolume.Maximum = 100;
            this.trackVolume.Name = "trackVolume";
            this.trackVolume.Size = new System.Drawing.Size(104, 45);
            this.trackVolume.TabIndex = 7;
            this.trackVolume.TickFrequency = 25;
            this.trackVolume.Value = 80;
            this.trackVolume.Scroll += new System.EventHandler(this.trackVolume_Scroll);
            // 
            // lblTime
            // 
            this.lblTime.AutoSize = true;
            this.lblTime.Location = new System.Drawing.Point(12, 85);
            this.lblTime.Name = "lblTime";
            this.lblTime.Size = new System.Drawing.Size(59, 15);
            this.lblTime.TabIndex = 8;
            this.lblTime.Text = "00:00 / 00:00";
            // 
            // lblTrackInfo
            // 
            this.lblTrackInfo.BackColor = System.Drawing.Color.WhiteSmoke;
            this.lblTrackInfo.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.lblTrackInfo.Location = new System.Drawing.Point(12, 110);
            this.lblTrackInfo.Name = "lblTrackInfo";
            this.lblTrackInfo.Padding = new System.Windows.Forms.Padding(5);
            this.lblTrackInfo.Size = new System.Drawing.Size(400, 100);
            this.lblTrackInfo.TabIndex = 9;
            this.lblTrackInfo.Text = "No file loaded";
            // 
            // lblStatus
            // 
            this.lblStatus.AutoSize = true;
            this.lblStatus.Location = new System.Drawing.Point(12, 370);
            this.lblStatus.Name = "lblStatus";
            this.lblStatus.Size = new System.Drawing.Size(81, 15);
            this.lblStatus.TabIndex = 10;
            this.lblStatus.Text = "Ready to play";
            // 
            // listTracks
            // 
            this.listTracks.FormattingEnabled = true;
            this.listTracks.ItemHeight = 15;
            this.listTracks.Location = new System.Drawing.Point(420, 110);
            this.listTracks.Name = "listTracks";
            this.listTracks.Size = new System.Drawing.Size(252, 229);
            this.listTracks.TabIndex = 11;
            this.listTracks.SelectedIndexChanged += new System.EventHandler(this.listTracks_SelectedIndexChanged);
            // 
            // chkLoop
            // 
            this.chkLoop.AutoSize = true;
            this.chkLoop.Location = new System.Drawing.Point(12, 225);
            this.chkLoop.Name = "chkLoop";
            this.chkLoop.Size = new System.Drawing.Size(85, 19);
            this.chkLoop.TabIndex = 12;
            this.chkLoop.Text = "Loop Track";
            this.chkLoop.UseVisualStyleBackColor = true;
            // 
            // lblVolume
            // 
            this.lblVolume.AutoSize = true;
            this.lblVolume.Location = new System.Drawing.Point(678, 55);
            this.lblVolume.Name = "lblVolume";
            this.lblVolume.Size = new System.Drawing.Size(27, 15);
            this.lblVolume.TabIndex = 14;
            this.lblVolume.Text = "80%";
            // 
            // MainForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(7F, 15F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(684, 396);
            this.Controls.Add(this.lblVolume);
            this.Controls.Add(this.chkLoop);
            this.Controls.Add(this.listTracks);
            this.Controls.Add(this.lblStatus);
            this.Controls.Add(this.lblTrackInfo);
            this.Controls.Add(this.lblTime);
            this.Controls.Add(this.trackVolume);
            this.Controls.Add(this.trackPosition);
            this.Controls.Add(this.btnPrev);
            this.Controls.Add(this.btnNext);
            this.Controls.Add(this.btnStop);
            this.Controls.Add(this.btnPause);
            this.Controls.Add(this.btnPlay);
            this.Controls.Add(this.btnOpen);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;
            this.Name = "MainForm";
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "GME Player";
            ((System.ComponentModel.ISupportInitialize)(this.trackPosition)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.trackVolume)).EndInit();
            this.ResumeLayout(false);
            this.PerformLayout();
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
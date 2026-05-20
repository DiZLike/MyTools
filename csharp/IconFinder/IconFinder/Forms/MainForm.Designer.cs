using System.Drawing;
using System.Windows.Forms;

namespace IconFinder.Forms
{
    partial class MainForm
    {
        private System.ComponentModel.IContainer components = null;
        private TextBox txtSearch;
        private Label lblSearchIcon;
        private FlowLayoutPanel pnlResults;
        private Label lblStatus;
        private Button btnShowMore;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
                components.Dispose();
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            System.ComponentModel.ComponentResourceManager resources = new System.ComponentModel.ComponentResourceManager(typeof(MainForm));
            txtSearch = new TextBox();
            lblSearchIcon = new Label();
            pnlResults = new FlowLayoutPanel();
            lblStatus = new Label();
            btnShowMore = new Button();
            lblTotalIcons = new Label();
            SuspendLayout();
            // 
            // txtSearch
            // 
            txtSearch.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            txtSearch.BackColor = Color.FromArgb(45, 45, 48);
            txtSearch.BorderStyle = BorderStyle.FixedSingle;
            txtSearch.Font = new Font("Segoe UI", 13F);
            txtSearch.ForeColor = Color.FromArgb(240, 240, 240);
            txtSearch.Location = new Point(24, 25);
            txtSearch.Name = "txtSearch";
            txtSearch.PlaceholderText = "Поиск иконок...";
            txtSearch.Size = new Size(1012, 31);
            txtSearch.TabIndex = 0;
            // 
            // lblSearchIcon
            // 
            lblSearchIcon.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            lblSearchIcon.Font = new Font("Segoe UI", 14F);
            lblSearchIcon.Location = new Point(1042, 22);
            lblSearchIcon.Name = "lblSearchIcon";
            lblSearchIcon.Size = new Size(35, 35);
            lblSearchIcon.TabIndex = 1;
            lblSearchIcon.Text = "🔍";
            lblSearchIcon.TextAlign = ContentAlignment.MiddleCenter;
            // 
            // pnlResults
            // 
            pnlResults.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            pnlResults.AutoScroll = true;
            pnlResults.BackColor = Color.FromArgb(32, 32, 32);
            pnlResults.Location = new Point(20, 80);
            pnlResults.Name = "pnlResults";
            pnlResults.Padding = new Padding(5);
            pnlResults.Size = new Size(1060, 540);
            pnlResults.TabIndex = 2;
            // 
            // lblStatus
            // 
            lblStatus.Anchor = AnchorStyles.Bottom | AnchorStyles.Left;
            lblStatus.Font = new Font("Segoe UI", 9F);
            lblStatus.ForeColor = Color.FromArgb(160, 160, 160);
            lblStatus.Location = new Point(24, 655);
            lblStatus.Name = "lblStatus";
            lblStatus.Size = new Size(400, 20);
            lblStatus.TabIndex = 3;
            lblStatus.Text = "Готов к поиску";
            lblStatus.TextAlign = ContentAlignment.MiddleLeft;
            // 
            // btnShowMore
            // 
            btnShowMore.Anchor = AnchorStyles.Bottom | AnchorStyles.Right;
            btnShowMore.BackColor = Color.FromArgb(0, 120, 215);
            btnShowMore.Cursor = Cursors.Hand;
            btnShowMore.FlatAppearance.BorderSize = 0;
            btnShowMore.FlatStyle = FlatStyle.Flat;
            btnShowMore.Font = new Font("Segoe UI", 9F);
            btnShowMore.ForeColor = Color.White;
            btnShowMore.Location = new Point(917, 650);
            btnShowMore.Name = "btnShowMore";
            btnShowMore.Size = new Size(160, 30);
            btnShowMore.TabIndex = 4;
            btnShowMore.Text = "Показать еще";
            btnShowMore.UseVisualStyleBackColor = false;
            btnShowMore.Visible = false;
            // 
            // lblTotalIcons
            // 
            lblTotalIcons.Anchor = AnchorStyles.Bottom | AnchorStyles.Left;
            lblTotalIcons.Font = new Font("Segoe UI", 9F);
            lblTotalIcons.ForeColor = Color.FromArgb(160, 160, 160);
            lblTotalIcons.Location = new Point(24, 634);
            lblTotalIcons.Name = "lblTotalIcons";
            lblTotalIcons.Size = new Size(400, 20);
            lblTotalIcons.TabIndex = 3;
            lblTotalIcons.Text = "Иконок";
            lblTotalIcons.TextAlign = ContentAlignment.MiddleLeft;
            // 
            // MainForm
            // 
            BackColor = Color.FromArgb(32, 32, 32);
            ClientSize = new Size(1100, 692);
            Controls.Add(lblTotalIcons);
            Controls.Add(txtSearch);
            Controls.Add(lblSearchIcon);
            Controls.Add(pnlResults);
            Controls.Add(lblStatus);
            Controls.Add(btnShowMore);
            Icon = (Icon)resources.GetObject("$this.Icon");
            MinimumSize = new Size(800, 600);
            Name = "MainForm";
            Padding = new Padding(20);
            StartPosition = FormStartPosition.CenterScreen;
            Text = "IconFinder";
            ResumeLayout(false);
            PerformLayout();
        }

        private Label lblTotalIcons;
    }
}
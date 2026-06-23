namespace ScreenWire.Client.UI
{
    partial class ConnectForm
    {
        private System.ComponentModel.IContainer components = null;
        private System.Windows.Forms.Label lblServer;
        private System.Windows.Forms.Label lblPort;
        private System.Windows.Forms.Label lblPassword;
        private System.Windows.Forms.TextBox txtServer;
        private System.Windows.Forms.TextBox txtPassword;
        private System.Windows.Forms.NumericUpDown numPort;
        private System.Windows.Forms.CheckBox chkSave;
        private System.Windows.Forms.Button btnConnect;
        private System.Windows.Forms.Button btnCancel;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
                components.Dispose();
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            lblServer = new Label();
            txtServer = new TextBox();
            lblPort = new Label();
            numPort = new NumericUpDown();
            lblPassword = new Label();
            txtPassword = new TextBox();
            chkSave = new CheckBox();
            btnConnect = new Button();
            btnCancel = new Button();
            ((System.ComponentModel.ISupportInitialize)numPort).BeginInit();
            SuspendLayout();
            // 
            // lblServer
            // 
            lblServer.AutoSize = true;
            lblServer.Location = new Point(12, 15);
            lblServer.Name = "lblServer";
            lblServer.Size = new Size(50, 15);
            lblServer.TabIndex = 0;
            lblServer.Text = "Сервер:";
            // 
            // txtServer
            // 
            txtServer.Location = new Point(100, 12);
            txtServer.Name = "txtServer";
            txtServer.Size = new Size(200, 23);
            txtServer.TabIndex = 1;
            // 
            // lblPort
            // 
            lblPort.AutoSize = true;
            lblPort.Location = new Point(12, 45);
            lblPort.Name = "lblPort";
            lblPort.Size = new Size(38, 15);
            lblPort.TabIndex = 2;
            lblPort.Text = "Порт:";
            // 
            // numPort
            // 
            numPort.Location = new Point(100, 43);
            numPort.Maximum = new decimal(new int[] { 65535, 0, 0, 0 });
            numPort.Minimum = new decimal(new int[] { 1, 0, 0, 0 });
            numPort.Name = "numPort";
            numPort.Size = new Size(80, 23);
            numPort.TabIndex = 3;
            numPort.Value = new decimal(new int[] { 9090, 0, 0, 0 });
            // 
            // lblPassword
            // 
            lblPassword.AutoSize = true;
            lblPassword.Location = new Point(12, 75);
            lblPassword.Name = "lblPassword";
            lblPassword.Size = new Size(52, 15);
            lblPassword.TabIndex = 6;
            lblPassword.Text = "Пароль:";
            // 
            // txtPassword
            // 
            txtPassword.Location = new Point(100, 72);
            txtPassword.Name = "txtPassword";
            txtPassword.Size = new Size(200, 23);
            txtPassword.TabIndex = 7;
            txtPassword.UseSystemPasswordChar = true;
            // 
            // chkSave
            // 
            chkSave.AutoSize = true;
            chkSave.Location = new Point(100, 102);
            chkSave.Name = "chkSave";
            chkSave.Size = new Size(127, 19);
            chkSave.TabIndex = 8;
            chkSave.Text = "Сохранить пароль";
            // 
            // btnConnect
            // 
            btnConnect.DialogResult = DialogResult.OK;
            btnConnect.Location = new Point(100, 135);
            btnConnect.Name = "btnConnect";
            btnConnect.Size = new Size(104, 27);
            btnConnect.TabIndex = 9;
            btnConnect.Text = "Подключиться";
            // 
            // btnCancel
            // 
            btnCancel.DialogResult = DialogResult.Cancel;
            btnCancel.Location = new Point(210, 135);
            btnCancel.Name = "btnCancel";
            btnCancel.Size = new Size(90, 27);
            btnCancel.TabIndex = 10;
            btnCancel.Text = "Отмена";
            // 
            // ConnectForm
            // 
            AcceptButton = btnConnect;
            CancelButton = btnCancel;
            ClientSize = new Size(314, 175);
            Controls.Add(lblServer);
            Controls.Add(txtServer);
            Controls.Add(lblPort);
            Controls.Add(numPort);
            Controls.Add(lblPassword);
            Controls.Add(txtPassword);
            Controls.Add(chkSave);
            Controls.Add(btnConnect);
            Controls.Add(btnCancel);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            Name = "ConnectForm";
            StartPosition = FormStartPosition.CenterParent;
            Text = "Подключение";
            ((System.ComponentModel.ISupportInitialize)numPort).EndInit();
            ResumeLayout(false);
            PerformLayout();
        }
    }
}
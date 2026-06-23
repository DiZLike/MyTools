using System.Windows.Forms;

namespace ScreenWire.Client.UI
{
    public partial class ConnectForm : Form
    {
        public string ServerAddress => txtServer.Text.Trim();
        public int Port => (int)numPort.Value;
        public string Password => txtPassword.Text;
        public bool SavePassword => chkSave.Checked;

        public ConnectForm() => InitializeComponent();

        public void SetDefaults(string server, int port, string password)
        {
            txtServer.Text = server;
            numPort.Value = port;
            txtPassword.Text = password;
            chkSave.Checked = !string.IsNullOrEmpty(password);
        }
    }
}
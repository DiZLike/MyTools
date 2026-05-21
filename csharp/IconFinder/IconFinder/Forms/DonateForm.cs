using System;
using System.Diagnostics;
using System.Windows.Forms;

namespace IconFinder.Forms
{
    public partial class DonateForm : Form
    {
        // ЗАМЕНИТЕ НА СВОИ ССЫЛКИ!
        private const string DONATE_URL = "https://donatepay.ru/don/dizlike91?goal=Icon Finder";
        private const string DONATE_URL_ALT = "https://donatepay.ru/don/dizlike91?goal=Icon Finder";

        public DonateForm()
        {
            InitializeComponent();
        }

        private void BtnDonate_Click(object sender, EventArgs e)
        {
            try
            {
                Process.Start(new ProcessStartInfo(DONATE_URL) { UseShellExecute = true });
            }
            catch
            {
                try
                {
                    Process.Start(new ProcessStartInfo(DONATE_URL_ALT) { UseShellExecute = true });
                }
                catch
                {
                    MessageBox.Show(
                        "Не удалось открыть страницу. Вы можете поддержать проект напрямую:\n\n" +
                        DONATE_URL,
                        "Ссылка для доната",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information);
                }
            }
            this.Close();
        }

        private void BtnLater_Click(object sender, EventArgs e)
        {
            this.Close();
        }
    }
}
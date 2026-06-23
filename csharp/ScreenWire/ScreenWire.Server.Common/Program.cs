using System;
using System.IO;
using System.Windows.Forms;

namespace ScreenWire.Server
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            string updateDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "_update");
            try
            {
                if (Directory.Exists(updateDir))
                    Directory.Delete(updateDir, true);
            }
            catch { }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            Application.ThreadException += (s, e) =>
            {
                LogError(e.Exception);
                MessageBox.Show("Ошибка: " + e.Exception.Message, "ScreenWire Server", MessageBoxButtons.OK, MessageBoxIcon.Error);
            };

            AppDomain.CurrentDomain.UnhandledException += (s, e) =>
            {
                var ex = e.ExceptionObject as Exception;
                LogError(ex);
                MessageBox.Show("Критическая ошибка: " + (ex?.Message ?? e.ExceptionObject.ToString()), "ScreenWire Server", MessageBoxButtons.OK, MessageBoxIcon.Error);
            };

            Application.Run(new ServerMainForm());
        }

        private static void LogError(Exception ex)
        {
            if (ex == null) return;
            try
            {
                string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "server_error.log");
                using (var sw = new StreamWriter(path, true, System.Text.Encoding.UTF8))
                {
                    sw.WriteLine("=== " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " ===");
                    sw.WriteLine(ex.ToString());
                    sw.WriteLine();
                    sw.Flush();
                }
            }
            catch { }
        }
    }
}
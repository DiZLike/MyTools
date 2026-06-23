using ScreenWire.Server.Protocol;
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Threading;

namespace ScreenWire.Server.Update
{
    public class UpdateManager : IDisposable
    {
        private TcpListener _listener;
        private volatile bool _running;
        private string _serverDir;
        private string _tempDir;
        private string _zipPath;
        private string _extractDir;
        private int _port;
        private Thread _listenThread;
        private volatile bool _updateReady;
        private volatile bool _zipExtracted;
        private volatile bool _installStarted;

        public event EventHandler<UpdateStatusEventArgs> StatusChanged;

        public UpdateManager()
        {
            _serverDir = AppDomain.CurrentDomain.BaseDirectory;
            _tempDir = Path.Combine(_serverDir, "_update");
            _zipPath = Path.Combine(_tempDir, "update.zip");
            _extractDir = Path.Combine(_tempDir, "files");
        }

        public int StartListener()
        {
            try
            {
                _listener = new TcpListener(IPAddress.Any, 0);
                _listener.Start();
                _port = ((IPEndPoint)_listener.LocalEndpoint).Port;
                _running = true;

                if (Directory.Exists(_tempDir))
                    Directory.Delete(_tempDir, true);
                Directory.CreateDirectory(_extractDir);

                _listenThread = new Thread(ListenWithTimeout) { IsBackground = true };
                _listenThread.Start();

                RaiseStatus(UdpProtocol.UpdateStatusReady, UdpProtocol.UpdateErrorNone,
                    "Готов принимать обновление на порту " + _port);

                return _port;
            }
            catch (Exception ex)
            {
                RaiseStatus(UdpProtocol.UpdateStatusError, UdpProtocol.UpdateErrorExtract, ex.Message);
                return -1;
            }
        }

        private void ListenWithTimeout()
        {
            try
            {
                DateTime startTime = DateTime.Now;
                const int timeoutSeconds = 120;

                while (_running && (DateTime.Now - startTime).TotalSeconds < timeoutSeconds)
                {
                    if (_listener.Pending())
                    {
                        using (TcpClient client = _listener.AcceptTcpClient())
                        using (NetworkStream ns = client.GetStream())
                        {
                            client.ReceiveTimeout = 30000;
                            client.SendTimeout = 30000;

                            RaiseStatus(UdpProtocol.UpdateStatusReceiving, UdpProtocol.UpdateErrorNone,
                                "Получение файла обновления...");

                            using (FileStream fs = new FileStream(_zipPath, FileMode.Create, FileAccess.Write))
                            {
                                byte[] buffer = new byte[8192];
                                int bytesRead;
                                long totalBytes = 0;
                                DateTime lastProgress = DateTime.Now;

                                while ((bytesRead = ns.Read(buffer, 0, buffer.Length)) > 0)
                                {
                                    fs.Write(buffer, 0, bytesRead);
                                    totalBytes += bytesRead;

                                    if ((DateTime.Now - lastProgress).TotalMilliseconds > 500)
                                    {
                                        RaiseStatus(UdpProtocol.UpdateStatusReceiving,
                                            UdpProtocol.UpdateErrorNone,
                                            "Получено: " + FormatSize(totalBytes));
                                        lastProgress = DateTime.Now;
                                    }
                                }
                            }

                            RaiseStatus(UdpProtocol.UpdateStatusVerifying, UdpProtocol.UpdateErrorNone,
                                "Проверка архива...");

                            if (!VerifyZip(_zipPath))
                            {
                                RaiseStatus(UdpProtocol.UpdateStatusError,
                                    UdpProtocol.UpdateErrorInvalidZip,
                                    "Неверный формат ZIP-архива");
                                return;
                            }

                            RaiseStatus(UdpProtocol.UpdateStatusVerifying, UdpProtocol.UpdateErrorNone,
                                "Распаковка обновления...");

                            if (!ExtractZip(_zipPath, _extractDir))
                            {
                                RaiseStatus(UdpProtocol.UpdateStatusError,
                                    UdpProtocol.UpdateErrorExtract,
                                    "Ошибка распаковки архива");
                                return;
                            }

                            string[] exeFiles = Directory.GetFiles(_extractDir, "*.exe", SearchOption.AllDirectories);
                            if (exeFiles.Length == 0)
                            {
                                RaiseStatus(UdpProtocol.UpdateStatusError,
                                    UdpProtocol.UpdateErrorNoExe,
                                    "В архиве нет исполняемого файла");
                                return;
                            }

                            _zipExtracted = true;
                            _updateReady = true;

                            RaiseStatus(UdpProtocol.UpdateStatusVerifying, UdpProtocol.UpdateErrorNone,
                                "Обновление распаковано, готово к установке");

                            InstallUpdate();

                            return;
                        }
                    }
                    else
                    {
                        Thread.Sleep(100);
                    }
                }

                if (_running)
                {
                    RaiseStatus(UdpProtocol.UpdateStatusError, UdpProtocol.UpdateErrorTimeout,
                        "Таймаут ожидания обновления");
                }
            }
            catch (Exception ex)
            {
                RaiseStatus(UdpProtocol.UpdateStatusError, UdpProtocol.UpdateErrorExtract, ex.Message);
            }
        }

        public bool InstallUpdate()
        {
            if (_installStarted)
                return false;
            _installStarted = true;

            if (!_updateReady || !_zipExtracted)
            {
                RaiseStatus(UdpProtocol.UpdateStatusError, UdpProtocol.UpdateErrorInstall,
                    "Обновление не готово");
                return false;
            }

            try
            {
                RaiseStatus(UdpProtocol.UpdateStatusInstalling, UdpProtocol.UpdateErrorNone,
                    "Создание скрипта установки...");

                string batPath = Path.Combine(_tempDir, "update.bat");
                CreateUpdateBatch(batPath, _serverDir, _extractDir, _tempDir);

                RaiseStatus(UdpProtocol.UpdateStatusSuccess, UdpProtocol.UpdateErrorNone,
                    "Обновление запущено. Сервер будет перезапущен.");

                Thread.Sleep(1500);

                // Исправленный запуск bat-файла
                var processInfo = new System.Diagnostics.ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = "/C \"" + batPath + "\"",
                    WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden,
                    CreateNoWindow = true,
                    UseShellExecute = true
                };

                System.Diagnostics.Process.Start(processInfo);

                Thread.Sleep(500);

                // Завершаем текущий процесс
                Environment.Exit(0);
                return true;
            }
            catch (Exception ex)
            {
                RaiseStatus(UdpProtocol.UpdateStatusError, UdpProtocol.UpdateErrorInstall, ex.Message);
                return false;
            }
        }

        private void CreateUpdateBatch(string batPath, string appDir, string extractDir, string tempDir)
        {
            string exeName = AppDomain.CurrentDomain.FriendlyName;
            string logPath = Path.Combine(appDir, "update.log");

            var bat = new StringBuilder();
            bat.AppendLine("@echo off");
            bat.AppendLine("chcp 65001 >nul");
            bat.AppendLine("set LOG=\"" + logPath + "\"");
            bat.AppendLine("echo ============================================ > %LOG%");
            bat.AppendLine("echo ScreenWire Server Update >> %LOG%");
            bat.AppendLine("echo %DATE% %TIME% >> %LOG%");
            bat.AppendLine("echo ============================================ >> %LOG%");
            bat.AppendLine("echo. >> %LOG%");
            bat.AppendLine("echo Server path: \"" + appDir + "\" >> %LOG%");
            bat.AppendLine("echo Extract path: \"" + extractDir + "\" >> %LOG%");
            bat.AppendLine("echo. >> %LOG%");
            bat.AppendLine("echo Waiting for server to close... >> %LOG%");
            bat.AppendLine(":wait");
            bat.AppendLine("ping 127.0.0.1 -n 3 >nul");
            bat.AppendLine("tasklist /fi \"IMAGENAME eq " + exeName + "\" 2>nul | find /i \"" + exeName + "\" >nul");
            bat.AppendLine("if %errorlevel% equ 0 goto wait");
            bat.AppendLine("echo Server stopped. >> %LOG%");
            bat.AppendLine("echo. >> %LOG%");
            bat.AppendLine("ping 127.0.0.1 -n 4 >nul");
            bat.AppendLine("echo. >> %LOG%");
            bat.AppendLine("echo Copying new files... >> %LOG%");
            bat.AppendLine("xcopy /y /e /h /r \"" + extractDir + "\\*\" \"" + appDir + "\" >> %LOG% 2>&1");
            bat.AppendLine("set COPYRESULT=%errorlevel%");
            bat.AppendLine("echo. >> %LOG%");
            bat.AppendLine("if %COPYRESULT% equ 0 (");
            bat.AppendLine("    echo Copy SUCCESS >> %LOG%");
            bat.AppendLine(") else (");
            bat.AppendLine("    echo Copy FAILED with error %COPYRESULT% >> %LOG%");
            bat.AppendLine(")");
            bat.AppendLine("echo. >> %LOG%");
            bat.AppendLine("echo Starting server... >> %LOG%");
            bat.AppendLine("start \"\" \"" + Path.Combine(appDir, exeName) + "\" >> %LOG% 2>&1");
            bat.AppendLine("echo. >> %LOG%");
            bat.AppendLine("echo ============================================ >> %LOG%");
            bat.AppendLine("echo Update complete >> %LOG%");
            bat.AppendLine("echo ============================================ >> %LOG%");
            bat.AppendLine("start notepad %LOG%");
            bat.AppendLine("exit");

            // Используем UTF-8 без BOM для bat-файла
            File.WriteAllText(batPath, bat.ToString(), new UTF8Encoding(false));
        }

        private bool VerifyZip(string zipPath)
        {
            try
            {
                if (!File.Exists(zipPath)) return false;
                FileInfo fi = new FileInfo(zipPath);
                if (fi.Length == 0) return false;

                using (FileStream fs = new FileStream(zipPath, FileMode.Open, FileAccess.Read))
                {
                    byte[] sig = new byte[4];
                    if (fs.Read(sig, 0, 4) < 4) return false;
                    if (sig[0] != 0x50 || sig[1] != 0x4B) return false;
                }

                return true;
            }
            catch
            {
                return false;
            }
        }

        private string Find7Zip()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;

            string path = Path.Combine(baseDir, "7za.exe");
            if (File.Exists(path))
                return path;

            path = Path.Combine(baseDir, "7z.exe");
            if (File.Exists(path))
                return path;

            return null;
        }

        private bool ExtractZip(string zipPath, string destDir)
        {
            string sevenZipPath = Find7Zip();

            if (!string.IsNullOrEmpty(sevenZipPath))
            {
                return ExtractWith7Zip(sevenZipPath, zipPath, destDir);
            }
            else
            {
                return ExtractWithShell(zipPath, destDir);
            }
        }

        private bool ExtractWith7Zip(string sevenZipPath, string zipPath, string destDir)
        {
            try
            {
                System.Diagnostics.Process p = new System.Diagnostics.Process();
                p.StartInfo.FileName = sevenZipPath;
                p.StartInfo.Arguments = "x \"" + zipPath + "\" -o\"" + destDir + "\" -y";
                p.StartInfo.WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden;
                p.StartInfo.UseShellExecute = false;
                p.StartInfo.CreateNoWindow = true;
                p.StartInfo.RedirectStandardOutput = true;
                p.StartInfo.RedirectStandardError = true;
                p.Start();
                p.WaitForExit(30000);

                string[] files = Directory.GetFiles(destDir, "*.*", SearchOption.AllDirectories);
                return files.Length > 0;
            }
            catch
            {
                return false;
            }
        }

        private bool ExtractWithShell(string zipPath, string destDir)
        {
            try
            {
                Type shellType = Type.GetTypeFromProgID("Shell.Application");
                if (shellType == null) return false;

                object shell = Activator.CreateInstance(shellType);

                object source = shellType.InvokeMember("NameSpace",
                    BindingFlags.InvokeMethod,
                    null, shell, new object[] { zipPath });

                object target = shellType.InvokeMember("NameSpace",
                    BindingFlags.InvokeMethod,
                    null, shell, new object[] { destDir });

                if (source == null || target == null) return false;

                object items = source.GetType().InvokeMember("Items",
                    BindingFlags.InvokeMethod | BindingFlags.GetProperty,
                    null, source, null);

                target.GetType().InvokeMember("CopyHere",
                    BindingFlags.InvokeMethod,
                    null, target, new object[] { items, 16 });

                DateTime start = DateTime.Now;
                while ((DateTime.Now - start).TotalSeconds < 30)
                {
                    string[] files = Directory.GetFiles(destDir, "*.*", SearchOption.AllDirectories);
                    if (files.Length > 0)
                    {
                        Thread.Sleep(1000);
                        return true;
                    }
                    Thread.Sleep(300);
                }

                return false;
            }
            catch
            {
                return false;
            }
        }

        private void RaiseStatus(byte status, byte error, string message)
        {
            var handler = StatusChanged;
            if (handler != null)
            {
                handler(this, new UpdateStatusEventArgs(status, error, message));
            }
        }

        private static string FormatSize(long bytes)
        {
            if (bytes < 1024) return bytes + " B";
            if (bytes < 1024 * 1024) return (bytes / 1024.0).ToString("F1") + " KB";
            return (bytes / (1024.0 * 1024.0)).ToString("F1") + " MB";
        }

        public void Stop()
        {
            _running = false;
            try { _listener?.Stop(); } catch { }
        }

        public void Dispose()
        {
            Stop();
        }
    }

    public class UpdateStatusEventArgs : EventArgs
    {
        public byte Status { get; }
        public byte ErrorCode { get; }
        public string Message { get; }

        public UpdateStatusEventArgs(byte status, byte errorCode, string message)
        {
            Status = status;
            ErrorCode = errorCode;
            Message = message;
        }
    }
}
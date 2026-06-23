using System;
using System.IO;
using System.Text;

namespace ScreenWire.Server.Config
{
    public class ServerConfig
    {
        private readonly string _path;
        public int Port { get; set; } = 9090;
        public string PasswordHash { get; set; } = "";
        public bool StartMinimized { get; set; } = true;
        public bool AutoStartServer { get; set; } = true;
        public string CaptureMethod { get; set; } = "gdi";

        public ServerConfig() : this(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "server.ini")) { }
        public ServerConfig(string path) => _path = path;

        public void Load()
        {
            if (!File.Exists(_path)) return;
            foreach (var line in File.ReadAllLines(_path, Encoding.UTF8))
            {
                var parts = line.Split(new[] { '=' }, 2);
                if (parts.Length != 2) continue;
                var k = parts[0].Trim().ToLowerInvariant();
                var v = parts[1].Trim();
                switch (k)
                {
                    case "port": if (int.TryParse(v, out int p) && p > 0) Port = p; break;
                    case "passwordhash": PasswordHash = v; break;
                    case "startminimized": StartMinimized = v.ToLowerInvariant() == "true"; break;
                    case "autostartserver": AutoStartServer = v.ToLowerInvariant() == "true"; break;
                    case "capturemethod": CaptureMethod = v.ToLowerInvariant(); break;
                }
            }
        }

        public void Save()
        {
            var sb = new StringBuilder();
            sb.AppendLine("Port=" + Port);
            sb.AppendLine("PasswordHash=" + PasswordHash);
            sb.AppendLine("StartMinimized=" + StartMinimized);
            sb.AppendLine("AutoStartServer=" + AutoStartServer);
            sb.AppendLine("CaptureMethod=" + CaptureMethod);
            File.WriteAllText(_path, sb.ToString(), Encoding.UTF8);
        }
    }
}
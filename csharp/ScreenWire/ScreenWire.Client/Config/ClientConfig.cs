using System;
using System.IO;
using System.Text;

namespace ScreenWire.Client.Config;

public class ClientConfig
{
    private readonly string _path;

    public string ServerAddress { get; set; } = "127.0.0.1";
    public int Port { get; set; } = 9090;
    public string Password { get; set; } = "";
    public int FrameRate { get; set; } = 20;
    public int JpegQuality { get; set; } = 50;
    public bool ScaleToFit { get; set; } = true;

    public ClientConfig()
        : this(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "client.ini"))
    { }

    public ClientConfig(string path)
    {
        _path = path;
    }

    public void Load()
    {
        if (!File.Exists(_path)) return;

        foreach (var line in File.ReadAllLines(_path, Encoding.UTF8))
        {
            var parts = line.Split('=');
            if (parts.Length != 2) continue;

            var key = parts[0].Trim().ToLowerInvariant();
            var value = parts[1].Trim();

            switch (key)
            {
                case "serveraddress":
                    ServerAddress = value;
                    break;
                case "port":
                    if (int.TryParse(value, out int port) && port > 0)
                        Port = port;
                    break;
                case "password":
                    Password = value;
                    break;
                case "framerate":
                    if (int.TryParse(value, out int fr))
                        FrameRate = Math.Clamp(fr, 1, 60);
                    break;
                case "jpegquality":
                    if (int.TryParse(value, out int q))
                        JpegQuality = Math.Clamp(q, 1, 100);
                    break;
                case "scaletofit":
                    ScaleToFit = value.ToLowerInvariant() == "true";
                    break;
            }
        }
    }

    public void Save()
    {
        var sb = new StringBuilder();
        sb.AppendLine($"ServerAddress={ServerAddress}");
        sb.AppendLine($"Port={Port}");
        sb.AppendLine($"Password={Password}");
        sb.AppendLine($"FrameRate={FrameRate}");
        sb.AppendLine($"JpegQuality={JpegQuality}");
        sb.AppendLine($"ScaleToFit={ScaleToFit}");
        File.WriteAllText(_path, sb.ToString(), Encoding.UTF8);
    }
}
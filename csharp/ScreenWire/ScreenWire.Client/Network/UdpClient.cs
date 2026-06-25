using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using ScreenWire.Client.Protocol;

namespace ScreenWire.Client.Network;

public class UdpClient : IDisposable
{
    private Socket? _cmd;
    private TcpClient? _tcp;
    private NetworkStream? _videoStream;
    private IPEndPoint? _server;
    private volatile bool _running;
    private ushort _msgId;
    private readonly ConcurrentQueue<ReceivedCmd> _queue = new();
    private readonly SynchronizationContext? _sync = SynchronizationContext.Current;
    private CancellationTokenSource? _cts;

    private const bool ENABLE_LOGGING = false;
    private static readonly string LogPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "debug.log");

    public event EventHandler<byte[]>? ScreenshotReceived;
    public event EventHandler<(int Width, int Height)>? ScreenInfoReceived;
    public event EventHandler<byte[]>? DisplayInfoReceived;
    public event EventHandler<string>? ClipboardTextReceived;
    public event EventHandler<string>? ConnectionError;
    public event EventHandler<string>? StatusChanged;
    public event EventHandler<bool>? ConnectedChanged;

    private volatile bool _connected;
    public bool Connected
    {
        get => _connected;
        private set
        {
            if (_connected != value)
            {
                _connected = value;
                PostToUI(() => ConnectedChanged?.Invoke(this, value));
            }
        }
    }

    public async Task<bool> ConnectAsync(string ip, int port, string password)
    {
        try
        {
            Log("Connecting to " + ip + ":" + port);
            RaiseStatus("Подключение...");
            _cts = new CancellationTokenSource();
            _server = new IPEndPoint(IPAddress.Parse(ip), port);
            _cmd = BindSocket(0);

            _running = true;
            _ = Task.Run(() => CmdLoop(_cts.Token));

            RaiseStatus("Авторизация...");
            Send(UdpProtocol.MsgAuthRequest, null);

            var salt = await WaitForAsync(UdpProtocol.MsgAuthRequest, 5000);
            if (salt == null) { Log("No salt received"); Error("Нет ответа от сервера"); Disconnect(); return false; }
            Log("Salt received: " + salt.Length + " bytes");

            var hash = ComputeHash(password, salt);
            Send(UdpProtocol.MsgAuthResponse, Encoding.UTF8.GetBytes(hash));

            var res = await WaitForAsync(UdpProtocol.MsgAuthResult, 5000);
            if (res == null || res.Length < 1 || res[0] != UdpProtocol.AuthOk)
            {
                Log("Auth failed: " + (res != null && res.Length > 0 ? res[0].ToString() : "no response"));
                Error("Неверный пароль"); Disconnect(); return false;
            }

            Log("Auth OK, waiting for screen info...");
            var info = await WaitForAsync(UdpProtocol.MsgScreenInfo, 5000);
            if (info != null && info.Length >= 8)
            {
                int w = BitConverter.ToInt32(info, 0);
                int h = BitConverter.ToInt32(info, 4);
                Log("Screen info: " + w + "x" + h);
                PostToUI(() => ScreenInfoReceived?.Invoke(this, (w, h)));
            }

            // Ждём информацию о мониторах
            var displayInfo = await WaitForAsync(UdpProtocol.MsgDisplayInfo, 5000);
            if (displayInfo != null && displayInfo.Length > 0)
            {
                Log("Display info received: " + displayInfo[0] + " monitors");
                PostToUI(() => DisplayInfoReceived?.Invoke(this, displayInfo));
            }

            Log("Connecting TCP for video...");
            _tcp = new TcpClient();
            _tcp.NoDelay = true;
            _tcp.ReceiveTimeout = 5000;
            _tcp.SendTimeout = 5000;
            await _tcp.ConnectAsync(IPAddress.Parse(ip), port + 1);
            _videoStream = _tcp.GetStream();
            Log("TCP video connected on port " + (port + 1));

            _ = Task.Run(() => VideoLoop(_cts.Token));

            Connected = true;
            Log("Connected successfully");
            RaiseStatus("Подключено");
            return true;
        }
        catch (Exception ex) { Log("Connect exception: " + ex); Error(ex.Message); Disconnect(); return false; }
    }

    public void SendFpsRequest(int fps) => Send(UdpProtocol.MsgFpsRequest, [(byte)Math.Clamp(fps, 1, 60)]);
    public void SendQuality(int q) => Send(UdpProtocol.MsgQualityRequest, [(byte)Math.Clamp(q, 1, 100)]);
    public void SendReductionRatio(float r) => Send(UdpProtocol.MsgReductionRatio, [(byte)Math.Clamp(r, 10, 50)]);
    public void SendDisplaySelect(int index) => Send(UdpProtocol.MsgDisplaySelect, [(byte)index]);

    public void SendMouseEvent(byte flags, short x, short y, short wheel)
    {
        byte[] p = new byte[7];
        p[0] = flags;
        BitConverter.GetBytes(x).CopyTo(p, 1);
        BitConverter.GetBytes(y).CopyTo(p, 3);
        BitConverter.GetBytes(wheel).CopyTo(p, 5);
        SendFast(UdpProtocol.MsgMouseEvent, p);
    }

    public void SendKeyboardEvent(byte flags, byte vk)
        => SendFast(UdpProtocol.MsgKeyboardEvent, [flags, vk]);

    public void SendClipboardText(string t)
        => Send(UdpProtocol.MsgClipboardText, Encoding.UTF8.GetBytes(t ?? ""));

    public async Task<bool> SendUpdateAsync(string zipFilePath, Action<string>? progressCallback = null)
    {
        if (!Connected || _cmd == null || _server == null)
        { progressCallback?.Invoke("Нет подключения к серверу"); return false; }
        if (!File.Exists(zipFilePath))
        { progressCallback?.Invoke("Файл обновления не найден: " + zipFilePath); return false; }

        try
        {
            progressCallback?.Invoke("Запрос обновления сервера...");
            Send(UdpProtocol.MsgUpdateRequest, null);

            var portData = await WaitForAsync(UdpProtocol.MsgUpdatePort, 10000);
            if (portData == null || portData.Length < 2)
            { progressCallback?.Invoke("Сервер не ответил на запрос обновления"); return false; }

            ushort updatePort = BitConverter.ToUInt16(portData, 0);
            progressCallback?.Invoke($"Сервер готов, порт TCP: {updatePort}");

            using var tcp = new TcpClient();
            await tcp.ConnectAsync(_server.Address, updatePort);
            tcp.SendTimeout = 30000;
            using var ns = tcp.GetStream();
            using var fs = File.OpenRead(zipFilePath);

            long fileSize = fs.Length, sent = 0;
            byte[] buffer = new byte[8192];
            DateTime lastProgress = DateTime.Now;
            progressCallback?.Invoke($"Отправка обновления ({FormatSize(fileSize)})...");

            int bytesRead;
            while ((bytesRead = await fs.ReadAsync(buffer, 0, buffer.Length)) > 0)
            {
                await ns.WriteAsync(buffer, 0, bytesRead);
                sent += bytesRead;
                if ((DateTime.Now - lastProgress).TotalMilliseconds > 500 && progressCallback != null)
                {
                    int percent = (int)(sent * 100 / fileSize);
                    progressCallback($"Отправлено: {percent}% ({FormatSize(sent)} / {FormatSize(fileSize)})");
                    lastProgress = DateTime.Now;
                }
            }
            await ns.FlushAsync();
            progressCallback?.Invoke("Обновление отправлено. Сервер перезапускается...");
            return true;
        }
        catch (Exception ex) { progressCallback?.Invoke("Ошибка при отправке обновления: " + ex.Message); return false; }
    }

    public void Disconnect()
    {
        Log("Disconnecting...");
        Connected = false;
        _running = false;

        try { SendFast(UdpProtocol.MsgDisconnect, null); } catch { }

        _cts?.Cancel(); _cts?.Dispose(); _cts = null;
        try { _cmd?.Close(); } catch { }
        try { _videoStream?.Close(); } catch { }
        try { _tcp?.Close(); } catch { }
        _cmd = null; _videoStream = null; _tcp = null;
        while (_queue.TryDequeue(out _)) { }
        RaiseStatus("Отключено");
        Log("Disconnected");
    }

    public void Dispose() { Disconnect(); GC.SuppressFinalize(this); }

    private void Send(byte type, byte[]? payload)
    {
        if (_cmd == null || _server == null) return;
        try { _cmd.SendTo(UdpProtocol.CreateCommandPacket(_msgId++, type, payload), _server); } catch { }
    }

    private void SendFast(byte type, byte[]? payload)
    {
        if (_cmd == null || _server == null) return;
        try
        {
            int plen = payload?.Length ?? 0;
            byte[] packet = new byte[UdpProtocol.CmdHeaderSize + plen];
            Buffer.BlockCopy(UdpProtocol.Magic, 0, packet, 0, 4);
            packet[4] = 0; packet[5] = 0; packet[6] = type;
            packet[7] = (byte)(plen >> 8); packet[8] = (byte)(plen & 0xFF);
            if (plen > 0 && payload != null) Buffer.BlockCopy(payload, 0, packet, UdpProtocol.CmdHeaderSize, plen);
            _cmd.SendTo(packet, _server);
        }
        catch { }
    }

    private async Task<byte[]?> WaitForAsync(byte expectedType, int timeoutMs)
    {
        using var cts = new CancellationTokenSource(timeoutMs);
        try
        {
            while (!cts.Token.IsCancellationRequested)
            {
                var snapshot = _queue.ToArray();
                foreach (var cmd in snapshot)
                {
                    if (cmd.Type == expectedType)
                    {
                        var newQueue = new ConcurrentQueue<ReceivedCmd>(snapshot.Where(c => c != cmd));
                        while (_queue.TryDequeue(out _)) { }
                        foreach (var c in newQueue) _queue.Enqueue(c);
                        return cmd.Data;
                    }
                }
                await Task.Delay(10, cts.Token);
            }
        }
        catch (OperationCanceledException) { }
        return null;
    }

    private async Task CmdLoop(CancellationToken ct)
    {
        var buf = new byte[65536];
        var ep = new IPEndPoint(IPAddress.Any, 0);
        EndPoint remoteEp = ep;
        while (!ct.IsCancellationRequested && _running)
        {
            try
            {
                if (_cmd!.Available > 0)
                {
                    var result = await _cmd.ReceiveFromAsync(buf, SocketFlags.None, remoteEp);
                    byte[] p = new byte[result.ReceivedBytes];
                    Buffer.BlockCopy(buf, 0, p, 0, result.ReceivedBytes);
                    if (UdpProtocol.ParseCommandHeader(p, out _, out byte type, out ushort plen))
                    {
                        byte[] data = new byte[plen];
                        if (plen > 0) Buffer.BlockCopy(p, UdpProtocol.CmdHeaderSize, data, 0, plen);
                        _queue.Enqueue(new ReceivedCmd { Type = type, Data = data });
                    }
                }
                else await Task.Delay(1, ct);
            }
            catch (SocketException) { if (_running && !ct.IsCancellationRequested) await Task.Delay(10, ct); }
            catch (OperationCanceledException) { break; }
            catch { }
        }
    }

    private async Task VideoLoop(CancellationToken ct)
    {
        var lenBuf = new byte[4];
        while (!ct.IsCancellationRequested && _running && _videoStream != null)
        {
            try
            {
                int read = await ReadExactAsync(_videoStream, lenBuf, 0, 4, ct);
                if (read < 4) break;

                int packetLen = (lenBuf[0] << 24) | (lenBuf[1] << 16) | (lenBuf[2] << 8) | lenBuf[3];
                if (packetLen <= 0 || packetLen > 10 * 1024 * 1024) break;

                byte[] jpeg = new byte[packetLen];
                read = await ReadExactAsync(_videoStream, jpeg, 0, packetLen, ct);
                if (read < packetLen) break;

                PostToUI(() => ScreenshotReceived?.Invoke(this, jpeg));
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                Log("VideoLoop error: " + ex.Message);
                if (_running && !ct.IsCancellationRequested)
                {
                    PostToUI(() => ConnectionError?.Invoke(this, "Видео-соединение разорвано"));
                    Disconnect();
                }
                break;
            }
        }
    }

    private static async Task<int> ReadExactAsync(NetworkStream stream, byte[] buffer, int offset, int count, CancellationToken ct)
    {
        int totalRead = 0;
        while (totalRead < count)
        {
            int read = await stream.ReadAsync(buffer, offset + totalRead, count - totalRead, ct);
            if (read == 0) return totalRead;
            totalRead += read;
        }
        return totalRead;
    }

    private static Socket BindSocket(int port)
    {
        var s = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp);
        s.Bind(new IPEndPoint(IPAddress.Any, port));
        s.Blocking = false;
        s.ReceiveBufferSize = 1048576;
        s.SendBufferSize = 1048576;
        return s;
    }

    private static string ComputeHash(string password, byte[] salt)
    {
        using var sha = SHA256.Create();
        byte[] hash = sha.ComputeHash(Encoding.UTF8.GetBytes(password ?? ""));
        byte[] combined = new byte[hash.Length + salt.Length];
        Buffer.BlockCopy(hash, 0, combined, 0, hash.Length);
        Buffer.BlockCopy(salt, 0, combined, hash.Length, salt.Length);
        byte[] finalHash = sha.ComputeHash(combined);
        var sb = new StringBuilder(64);
        foreach (var b in finalHash) sb.AppendFormat("{0:x2}", b);
        return sb.ToString();
    }

    private static string FormatSize(long bytes)
    {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024.0).ToString("F1") + " KB";
        return (bytes / (1024.0 * 1024.0)).ToString("F1") + " MB";
    }

    private void PostToUI(Action action)
    {
        if (_sync != null) _sync.Post(_ => action(), null);
        else action();
    }

    private void RaiseStatus(string s) => PostToUI(() => StatusChanged?.Invoke(this, s));
    private void Error(string s) => PostToUI(() => ConnectionError?.Invoke(this, s));

    private static void Log(string msg)
    {
        if (!ENABLE_LOGGING) return;
        try
        {
            File.AppendAllText(LogPath,
                DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + " [Cli] " + msg + Environment.NewLine,
                Encoding.UTF8);
        }
        catch { }
    }

    private class ReceivedCmd { public byte Type { get; init; } public byte[] Data { get; init; } = []; }
}
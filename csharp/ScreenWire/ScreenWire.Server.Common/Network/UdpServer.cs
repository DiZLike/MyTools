using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using ScreenWire.Server.Auth;
using ScreenWire.Server.Capture;
using ScreenWire.Server.Config;
using ScreenWire.Server.Input;
using ScreenWire.Server.Protocol;
using ScreenWire.Server.Update;

namespace ScreenWire.Server.Network
{
    public class UdpServer
    {
        private readonly ServerConfig _config;
        private Socket _cmdSocket;
        private TcpListener _tcpListener;
        private IScreenCaptor _captor;
        private InputSimulator _input = new InputSimulator();
        private volatile bool _running;
        private Dictionary<string, UdpClientSession> _clients = new Dictionary<string, UdpClientSession>();
        private Dictionary<string, TcpClient> _tcpClients = new Dictionary<string, TcpClient>();
        private object _lock = new object();
        private uint _frameId;
        private byte _prevFlags;
        private string _currentInputClientKey;

        private UpdateManager _updateManager;
        private ParameterizedThreadStart _frameThreadCallback;

        private int _displayOffsetX = 0;
        private int _displayOffsetY = 0;

        private const bool ENABLE_LOGGING = false;
        private static readonly string LogPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "debug.log");

        public event EventHandler<StatusChangedEventArgs> StatusChanged;

        public UdpServer(ServerConfig config)
        {
            _config = config;
            _captor = ScreenCaptorFactory.Create(config.CaptureMethod, -1);
            _frameThreadCallback = FrameThreadCallback;
        }

        public void Start()
        {
            _running = true;
            _cmdSocket = BindSocket(_config.Port);
            _tcpListener = new TcpListener(IPAddress.Any, _config.Port + 1);
            _tcpListener.Start();
            Log("Server started: UDP " + _config.Port + ", TCP " + (_config.Port + 1));
            RaiseStatus("Запущен (UDP " + _config.Port + "/TCP " + (_config.Port + 1) + ")");
            new Thread(CommandLoop) { IsBackground = true }.Start();
            new Thread(TcpAcceptLoop) { IsBackground = true }.Start();
            new Thread(CleanupLoop) { IsBackground = true }.Start();
        }

        public void Stop()
        {
            _running = false;
            StopUpdate();
            CloseSocket(ref _cmdSocket);
            try { _tcpListener?.Stop(); } catch { }
            lock (_lock)
            {
                foreach (var tcp in _tcpClients.Values)
                    try { tcp.Close(); } catch { }
                _tcpClients.Clear();
                foreach (var c in _clients.Values) c.Dispose();
                _clients.Clear();
            }
            _captor?.Dispose();
            Log("Server stopped");
            RaiseStatus("Остановлен");
        }

        private static Socket BindSocket(int port)
        {
            var s = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp);
            s.Bind(new IPEndPoint(IPAddress.Any, port));
            s.ReceiveBufferSize = 1048576;
            s.SendBufferSize = 1048576;
            s.ReceiveTimeout = 1000;
            return s;
        }

        private static void CloseSocket(ref Socket s)
        {
            try { if (s != null) s.Close(); } catch { }
            s = null;
        }

        private void TcpAcceptLoop()
        {
            while (_running)
            {
                try
                {
                    var tcpClient = _tcpListener.AcceptTcpClient();
                    tcpClient.NoDelay = true;
                    tcpClient.ReceiveTimeout = 5000;
                    tcpClient.SendTimeout = 5000;
                    string ip = ((IPEndPoint)tcpClient.Client.RemoteEndPoint).Address.ToString();
                    lock (_lock)
                    {
                        if (_tcpClients.ContainsKey(ip))
                            try { _tcpClients[ip].Close(); } catch { }
                        _tcpClients[ip] = tcpClient;
                    }
                    Log("TCP client connected: " + ip);
                }
                catch (SocketException) { if (_running) Thread.Sleep(100); }
                catch { }
            }
        }

        private void CommandLoop()
        {
            byte[] buf = new byte[65536];
            EndPoint ep = new IPEndPoint(IPAddress.Any, 0);
            while (_running)
            {
                try
                {
                    if (_cmdSocket != null && _cmdSocket.Available > 0)
                    {
                        int len = _cmdSocket.ReceiveFrom(buf, ref ep);
                        byte[] pkt = new byte[len];
                        Buffer.BlockCopy(buf, 0, pkt, 0, len);
                        ProcessPacket(pkt, (IPEndPoint)ep);
                    }
                    else Thread.Sleep(1);
                }
                catch (SocketException) { if (_running) Thread.Sleep(10); }
                catch { }
            }
        }

        private void ProcessPacket(byte[] pkt, IPEndPoint clientEp)
        {
            if (!UdpProtocol.ParseCommandHeader(pkt, out ushort msgId, out byte type, out ushort plen))
                return;

            string key = clientEp.Address + ":" + clientEp.Port;

            if (type == UdpProtocol.MsgAck)
            {
                lock (_lock) { if (_clients.TryGetValue(key, out var s)) s.OnAckReceived(msgId); }
                return;
            }

            if (type == UdpProtocol.MsgDisconnect)
            {
                ForceDisconnect(key);
                return;
            }

            if (type != UdpProtocol.MsgMouseEvent && type != UdpProtocol.MsgKeyboardEvent)
            {
                try { if (_cmdSocket != null) _cmdSocket.SendTo(UdpProtocol.CreateAckPacket(msgId), clientEp); }
                catch { }
            }

            byte[] payload = new byte[plen];
            if (plen > 0) Buffer.BlockCopy(pkt, UdpProtocol.CmdHeaderSize, payload, 0, plen);

            switch (type)
            {
                case UdpProtocol.MsgAuthRequest: AuthRequest(clientEp, key); break;
                case UdpProtocol.MsgAuthResponse: AuthResponse(clientEp, key, payload); break;
                case UdpProtocol.MsgMouseEvent: MouseEvent(key, payload); break;
                case UdpProtocol.MsgKeyboardEvent: KeyEvent(key, payload); break;
                case UdpProtocol.MsgQualityRequest: Quality(key, payload); break;
                case UdpProtocol.MsgReductionRatio: ReductionRatio(key, payload); break;
                case UdpProtocol.MsgClipboardText: ClipboardSet(key, payload); break;
                case UdpProtocol.MsgPing: Ping(key); break;
                case UdpProtocol.MsgUpdateRequest: HandleUpdateRequest(key); break;
                case UdpProtocol.MsgFpsRequest: FpsRequest(key, payload); break;
                case UdpProtocol.MsgDisplaySelect:
                    if (payload.Length > 0) ChangeDisplay(payload[0]);
                    break;
            }
        }

        private void ChangeDisplay(int displayIndex)
        {
            lock (_lock)
            {
                _captor?.Dispose();
                _captor = ScreenCaptorFactory.Create(_config.CaptureMethod, displayIndex);
            }

            var bounds = BaseScreenCaptor.GetDisplayBounds(displayIndex);
            _displayOffsetX = bounds.X;
            _displayOffsetY = bounds.Y;

            byte[] info = new byte[8];
            BitConverter.GetBytes(bounds.Width).CopyTo(info, 0);
            BitConverter.GetBytes(bounds.Height).CopyTo(info, 4);

            lock (_lock)
            {
                foreach (var kv in _clients)
                {
                    if (kv.Value.Authenticated)
                        kv.Value.SendWithRetry(_cmdSocket, UdpProtocol.MsgScreenInfo, info);
                }
            }

            Log("Display changed to " + (displayIndex < 0 ? "all" : displayIndex.ToString()) +
                ": " + bounds.Width + "x" + bounds.Height + " at (" + _displayOffsetX + "," + _displayOffsetY + ")");
        }

        private void ForceDisconnect(string key)
        {
            lock (_lock)
            {
                if (_clients.TryGetValue(key, out var s))
                {
                    s.Dispose();
                    _clients.Remove(key);

                    string ip = key.Split(':')[0];
                    if (_tcpClients.TryGetValue(ip, out var tcp))
                    {
                        try { tcp.Close(); } catch { }
                        _tcpClients.Remove(ip);
                    }

                    if (_currentInputClientKey == key)
                    {
                        _currentInputClientKey = null;
                        if ((_prevFlags & UdpProtocol.MouseLeftDown) != 0) _input.MouseEvent(InputSimulator.MOUSEEVENTF_LEFTUP, 0, 0, 0);
                        if ((_prevFlags & UdpProtocol.MouseRightDown) != 0) _input.MouseEvent(InputSimulator.MOUSEEVENTF_RIGHTUP, 0, 0, 0);
                        if ((_prevFlags & UdpProtocol.MouseMiddleDown) != 0) _input.MouseEvent(InputSimulator.MOUSEEVENTF_MIDDLEUP, 0, 0, 0);
                        _prevFlags = 0;
                    }

                    Log("Client force-disconnected: " + key);
                }
            }
        }

        private UdpClientSession GetOrCreateSession(IPEndPoint ep, string key)
        {
            lock (_lock)
            {
                if (!_clients.TryGetValue(key, out var s))
                {
                    s = new UdpClientSession(ep);
                    _clients[key] = s;
                    Log("New session: " + key);
                }
                s.LastSeen = Environment.TickCount;
                return s;
            }
        }

        private void AuthRequest(IPEndPoint ep, string key)
        {
            var s = GetOrCreateSession(ep, key);
            s.Salt = Authenticator.GenerateSalt();
            s.SendWithRetry(_cmdSocket, UdpProtocol.MsgAuthRequest, s.Salt);
        }

        private void AuthResponse(IPEndPoint ep, string key, byte[] payload)
        {
            UdpClientSession s;
            lock (_lock) { if (!_clients.TryGetValue(key, out s)) return; }

            string clientHash = System.Text.Encoding.UTF8.GetString(payload).Trim();
            if (string.IsNullOrEmpty(_config.PasswordHash))
            {
                s.SendWithRetry(_cmdSocket, UdpProtocol.MsgAuthResult, new[] { UdpProtocol.AuthBadPassword });
                return;
            }

            string computed = Authenticator.ComputeHash(
                Convert.FromBase64String(_config.PasswordHash), s.Salt);
            byte result = clientHash == computed ? UdpProtocol.AuthOk : UdpProtocol.AuthBadPassword;

            if (result == UdpProtocol.AuthOk)
            {
                s.Authenticated = true;
                s.StartFrameThread(_frameThreadCallback);
                SendScreenInfo(s);
                SendDisplayInfo(s);
                Log("Client authenticated: " + key);
                RaiseStatus("Клиент: " + ep.Address);
            }
            else
            {
                Log("Auth failed for: " + key);
            }

            s.SendWithRetry(_cmdSocket, UdpProtocol.MsgAuthResult, new[] { result });
        }

        private void SendScreenInfo(UdpClientSession s)
        {
            var bounds = BaseScreenCaptor.GetDisplayBounds(-1);
            byte[] info = new byte[8];
            BitConverter.GetBytes(bounds.Width).CopyTo(info, 0);
            BitConverter.GetBytes(bounds.Height).CopyTo(info, 4);
            s.SendWithRetry(_cmdSocket, UdpProtocol.MsgScreenInfo, info);
            Log("Sent screen info: " + bounds.Width + "x" + bounds.Height);
        }

        private void SendDisplayInfo(UdpClientSession s)
        {
            var screens = BaseScreenCaptor.GetSortedScreens();
            int count = screens.Count;
            byte[] data = new byte[1 + count * 8];
            data[0] = (byte)count;
            for (int i = 0; i < count; i++)
            {
                var b = screens[i].Bounds;
                BitConverter.GetBytes((ushort)b.X).CopyTo(data, 1 + i * 8);
                BitConverter.GetBytes((ushort)b.Y).CopyTo(data, 1 + i * 8 + 2);
                BitConverter.GetBytes((ushort)b.Width).CopyTo(data, 1 + i * 8 + 4);
                BitConverter.GetBytes((ushort)b.Height).CopyTo(data, 1 + i * 8 + 6);
            }
            s.SendWithRetry(_cmdSocket, UdpProtocol.MsgDisplayInfo, data);
            Log("Sent display info: " + count + " monitors");
        }

        // ---------- Frame thread callback ----------

        private void FrameThreadCallback(object state)
        {
            var s = (UdpClientSession)state;

            while (s._frameRunning && _running)
            {
                if (!s.Authenticated)
                {
                    Thread.Sleep(100);
                    continue;
                }

                s.LastSeen = Environment.TickCount;

                var sw = System.Diagnostics.Stopwatch.StartNew();

                try
                {
                    TcpClient tcp;
                    lock (_lock)
                    {
                        string ip = s.Endpoint.Address.ToString();
                        if (!_tcpClients.TryGetValue(ip, out tcp)) break;
                    }

                    byte[] jpeg = _captor.CaptureScreen(s.Quality, s.ReductionRatio);
                    if (jpeg != null && jpeg.Length > 0)
                    {
                        byte[] frame = UdpProtocol.WrapTcpFrame(jpeg);
                        NetworkStream ns = tcp.GetStream();
                        ns.Write(frame, 0, frame.Length);
                    }
                }
                catch
                {
                    lock (_lock)
                    {
                        string ip = s.Endpoint.Address.ToString();
                        if (_tcpClients.TryGetValue(ip, out var tcp))
                        {
                            try { tcp.Close(); } catch { }
                            _tcpClients.Remove(ip);
                        }
                    }
                    break;
                }

                sw.Stop();
                int frameTime = (int)sw.ElapsedMilliseconds;
                int targetInterval = 1000 / Math.Max(1, s.TargetFps);
                int sleepTime = targetInterval - frameTime;

                if (sleepTime > 0)
                    Thread.Sleep(sleepTime);
                else
                    Thread.Sleep(1);
            }
        }

        // ---------- Остальные обработчики ----------

        private void FpsRequest(string key, byte[] data)
        {
            lock (_lock)
                if (_clients.TryGetValue(key, out var s) && s.Authenticated && data.Length > 0)
                {
                    s.TargetFps = Math.Max(1, Math.Min(60, (int)data[0]));
                    s.LastSeen = Environment.TickCount;
                    s.StartFrameThread(_frameThreadCallback);
                }
        }

        private void MouseEvent(string key, byte[] data)
        {
            UdpClientSession s;
            lock (_lock)
            {
                if (!_clients.TryGetValue(key, out s) || !s.Authenticated) return;
                if (_currentInputClientKey != null && _currentInputClientKey != key) return;
                _currentInputClientKey = key;
                s.LastSeen = Environment.TickCount;
            }
            if (data.Length < 7) return;

            byte flags = data[0];
            short x = (short)(BitConverter.ToInt16(data, 1) + _displayOffsetX);
            short y = (short)(BitConverter.ToInt16(data, 3) + _displayOffsetY);
            short wheel = BitConverter.ToInt16(data, 5);

            // Применяем коэффициент уменьшения
            float ratio = s.ReductionRatio;
            if (ratio > 1.0f)
            {
                x = (short)(x * ratio);
                y = (short)(y * ratio);
            }

            // Добавляем смещение дисплея
            x = (short)(x + _displayOffsetX);
            y = (short)(y + _displayOffsetY);

            if ((flags & UdpProtocol.MouseMove) != 0) _input.MoveMouse(x, y);
            HandleMouseButton(flags, UdpProtocol.MouseLeftDown, InputSimulator.MOUSEEVENTF_LEFTDOWN, InputSimulator.MOUSEEVENTF_LEFTUP);
            HandleMouseButton(flags, UdpProtocol.MouseRightDown, InputSimulator.MOUSEEVENTF_RIGHTDOWN, InputSimulator.MOUSEEVENTF_RIGHTUP);
            HandleMouseButton(flags, UdpProtocol.MouseMiddleDown, InputSimulator.MOUSEEVENTF_MIDDLEDOWN, InputSimulator.MOUSEEVENTF_MIDDLEUP);
            if ((flags & UdpProtocol.MouseWheel) != 0) _input.MouseEvent(InputSimulator.MOUSEEVENTF_WHEEL, 0, 0, (uint)wheel);
            _prevFlags = flags;
        }

        private void HandleMouseButton(byte flags, byte mask, uint downFlag, uint upFlag)
        {
            bool cur = (flags & mask) != 0;
            bool prev = (_prevFlags & mask) != 0;
            if (cur && !prev) _input.MouseEvent(downFlag, 0, 0, 0);
            else if (!cur && prev) _input.MouseEvent(upFlag, 0, 0, 0);
        }

        private void KeyEvent(string key, byte[] data)
        {
            UdpClientSession s;
            lock (_lock)
            {
                if (!_clients.TryGetValue(key, out s) || !s.Authenticated) return;
                if (_currentInputClientKey != null && _currentInputClientKey != key) return;
                _currentInputClientKey = key;
                s.LastSeen = Environment.TickCount;
            }
            if (data.Length < 2) return;
            _input.SendKey(data[1], (data[0] & UdpProtocol.KeyDown) != 0);
        }

        private void Quality(string key, byte[] data)
        {
            lock (_lock)
                if (_clients.TryGetValue(key, out var s) && s.Authenticated && data.Length > 0)
                {
                    s.LastSeen = Environment.TickCount;
                    s.Quality = Math.Max(1, Math.Min(100, (int)data[0]));
                }
        }
        private void ReductionRatio(string key, byte[] data)
        {
            lock ( _lock)
            {
                if (_clients.TryGetValue(key, out var s) && s.Authenticated && data.Length > 0)
                {
                    s.LastSeen = Environment.TickCount;
                    int r = Math.Max(10, Math.Min(50, (int)data[0]));
                    s.ReductionRatio = r / 10f;
                }
            }
        }

        private void ClipboardSet(string key, byte[] data)
        {
            lock (_lock)
                if (_clients.TryGetValue(key, out var s) && s.Authenticated)
                {
                    s.LastSeen = Environment.TickCount;
                    try { System.Windows.Forms.Clipboard.SetText(System.Text.Encoding.UTF8.GetString(data)); } catch { }
                }
        }

        private void Ping(string key)
        {
            lock (_lock) { if (_clients.TryGetValue(key, out var s)) s.LastSeen = Environment.TickCount; }
        }

        // ---------- Update ----------

        private void HandleUpdateRequest(string key)
        {
            UdpClientSession s;
            lock (_lock) { if (!_clients.TryGetValue(key, out s) || !s.Authenticated) return; s.LastSeen = Environment.TickCount; }
            StopUpdate();
            _updateManager = new UpdateManager();
            _updateManager.StatusChanged += OnUpdateStatusChanged;
            int port = _updateManager.StartListener();
            if (port > 0)
                s.SendWithRetry(_cmdSocket, UdpProtocol.MsgUpdatePort, BitConverter.GetBytes((ushort)port));
            else
            {
                s.SendWithRetry(_cmdSocket, UdpProtocol.MsgUpdateStatus, new byte[] { UdpProtocol.UpdateStatusError, UdpProtocol.UpdateErrorExtract });
                StopUpdate();
            }
        }

        private void OnUpdateStatusChanged(object sender, UpdateStatusEventArgs e)
        {
            if (!string.IsNullOrEmpty(e.Message)) { Log("Update: " + e.Message); RaiseStatus("Update: " + e.Message); }
            byte[] data = new byte[] { e.Status, e.ErrorCode };
            lock (_lock)
                foreach (var kv in _clients)
                    if (kv.Value.Authenticated)
                        try { kv.Value.SendWithRetry(_cmdSocket, UdpProtocol.MsgUpdateStatus, data); } catch { }
        }

        private void StopUpdate()
        {
            if (_updateManager != null)
            {
                try { _updateManager.StatusChanged -= OnUpdateStatusChanged; _updateManager.Stop(); _updateManager.Dispose(); }
                catch { }
                _updateManager = null;
            }
        }

        // ---------- Cleanup ----------

        private void CleanupLoop()
        {
            while (_running)
            {
                Thread.Sleep(1000);
                int now = Environment.TickCount;
                lock (_lock)
                {
                    var dead = new List<string>();
                    foreach (var kv in _clients)
                        if (unchecked(now - kv.Value.LastSeen) > 10000) dead.Add(kv.Key);

                    foreach (var key in dead)
                    {
                        if (_currentInputClientKey == key)
                        {
                            _currentInputClientKey = null;
                            if ((_prevFlags & UdpProtocol.MouseLeftDown) != 0) _input.MouseEvent(InputSimulator.MOUSEEVENTF_LEFTUP, 0, 0, 0);
                            if ((_prevFlags & UdpProtocol.MouseRightDown) != 0) _input.MouseEvent(InputSimulator.MOUSEEVENTF_RIGHTUP, 0, 0, 0);
                            if ((_prevFlags & UdpProtocol.MouseMiddleDown) != 0) _input.MouseEvent(InputSimulator.MOUSEEVENTF_MIDDLEUP, 0, 0, 0);
                            _prevFlags = 0;
                        }
                        _clients[key].Dispose();
                        _clients.Remove(key);

                        string ip = key.Split(':')[0];
                        if (_tcpClients.TryGetValue(ip, out var tcp))
                        {
                            try { tcp.Close(); } catch { }
                            _tcpClients.Remove(ip);
                        }

                        Log("Client disconnected: " + key);
                        RaiseStatus("Клиент отключен: " + key);
                    }
                }
            }
        }

        private void RaiseStatus(string s)
        {
            var h = StatusChanged;
            if (h != null) h(this, new StatusChangedEventArgs(s));
        }

        private static void Log(string msg)
        {
            if (!ENABLE_LOGGING) return;
            try
            {
                File.AppendAllText(LogPath,
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + " [Srv] " + msg + Environment.NewLine,
                    System.Text.Encoding.UTF8);
            }
            catch { }
        }
    }

    public class StatusChangedEventArgs : EventArgs
    {
        public string Status { get; }
        public StatusChangedEventArgs(string status) { Status = status; }
    }
}
using FuzzCast.Core.Configuration;
using FuzzCast.Core.Native;
using FuzzCast.Core.Protocol;
using FuzzCast.Core.Protocol.Models;
using System.Net;
using System.Net.Sockets;
using Un4seen.Bass;

namespace FuzzCast.Player;

public class PlayerEngine
{
    private readonly AppConfig _config;
    private readonly Guid _clientId;
    private UdpClient? _udp;
    private IPEndPoint? _serverEndpoint;

    private JitterBuffer _jitterBuffer;
    private readonly object _stateLock = new();
    private readonly SemaphoreSlim _udpLock = new(1, 1);

    private volatile bool _running;

    private string _title = "—";
    private string _artist = "—";
    private string _album = "—";
    private double _duration;
    private uint _trackPosition;
    private byte _serverStatus = ServerInfoPacket.StatusNoSource;
    private uint _serverUptime;
    private int _listenersCount;
    private int _reconnects;

    private int _lastFrameMs;
    private int _lastPacketSize;
    private string _lastBandwidth = "—";
    private int _plcCount;
    private int _fecCount;
    private int _silenceCount;
    private double _simLossPercent;
    private int _jitterMs;
    private bool _plcEnabled = true;
    private bool _fecEnabled = true;

    private int _receivedPackets;
    private int _lostPackets;
    private DateTime _lastQualityCheck = DateTime.UtcNow;
    private int _signalStrength = 5;

    private bool _isPrimaryStream = true;
    private bool _autoSwitchEnabled = true;
    private DateTime _lastSwitchTime = DateTime.MinValue;
    private const int SwitchCooldownMs = 3000;
    private uint _expectedSequence;

    private DateTime _lastPacketReceived = DateTime.MinValue;
    private OpusDecoder? _opusDecoder;
    private int _outputStream;
    private int _currentDecoderChannels;

    private readonly Queue<string> _lastEvents = new();
    private const int MaxEvents = 5;

    public PlayerEngine(AppConfig config)
    {
        _config = config;
        _clientId = Guid.NewGuid();
        _jitterBuffer = new JitterBuffer();
        _currentDecoderChannels = _config.Opus.Channels;
    }

    public void SetSimulatedLoss(double percent)
    {
        _simLossPercent = Math.Clamp(percent, 0, 100);
        _jitterBuffer.SetSimulation(_simLossPercent, _jitterMs, burstProb: 0.3);
    }

    private void UpdateSimulation()
    {
        _jitterBuffer.SetSimulation(_simLossPercent, _jitterMs, burstProb: 0.3);
    }

    private void RecreateDecoder(int channels)
    {
        _opusDecoder?.Dispose();
        _opusDecoder = new OpusDecoder(_config.Opus.SampleRate, channels);
        _currentDecoderChannels = channels;
        Console.WriteLine($"[DECODER] Recreated: {_config.Opus.SampleRate}Hz, {channels}ch");
    }

    private void RecreateBassStream(int channels)
    {
        int oldStream = _outputStream;

        if (oldStream != 0)
        {
            Thread.Sleep(50);
            Bass.BASS_StreamFree(oldStream);
        }

        _outputStream = Bass.BASS_StreamCreatePush(
            _config.Opus.SampleRate,
            channels,
            BASSFlag.BASS_DEFAULT,
            IntPtr.Zero);

        if (_outputStream == 0)
        {
            Console.WriteLine($"[ERROR] Cannot create BASS stream: {Bass.BASS_ErrorGetCode()}");
            return;
        }

        Bass.BASS_ChannelPlay(_outputStream, false);
        Console.WriteLine($"[BASS] Stream recreated: {_config.Opus.SampleRate}Hz, {channels}ch");
    }

    public async Task RunAsync(CancellationToken ct)
    {
        if (!InitBass())
        {
            Console.WriteLine("[FATAL] Failed to initialize BASS");
            return;
        }

        _running = true;
        _lastPacketReceived = DateTime.MinValue;
        _lastQualityCheck = DateTime.UtcNow;

        var playbackThread = new Thread(PlaybackLoop) { IsBackground = true };
        playbackThread.Start();

        var uiThread = new Thread(UiLoop) { IsBackground = true };
        uiThread.Start();

        var qualityThread = new Thread(QualityCheckLoop) { IsBackground = true };
        qualityThread.Start();

        var inputThread = new Thread(InputLoop) { IsBackground = true };
        inputThread.Start(ct);

        try
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    await ConnectAndListenAsync(ct);
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[ERROR] Connection error: {ex.Message}");
                }

                if (!ct.IsCancellationRequested)
                {
                    Console.WriteLine("[RECONNECT] Connection lost, reconnecting in 1s...");
                    _reconnects++;
                    _serverStatus = ServerInfoPacket.StatusNoSource;
                    ResetPlaybackState();
                    await Task.Delay(1000, ct);
                }
            }
        }
        finally
        {
            _running = false;
            playbackThread.Join(2000);
            uiThread.Join(2000);
            qualityThread.Join(1000);
            inputThread.Join(1000);
            Bass.BASS_StreamFree(_outputStream);
            Bass.BASS_Free();
            await DisposeUdpClientAsync();
        }
    }

    private async Task DisposeUdpClientAsync()
    {
        await _udpLock.WaitAsync();
        try
        {
            _udp?.Close();
            _udp?.Dispose();
            _udp = null;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[WARN] Error disposing UDP client: {ex.Message}");
        }
        finally
        {
            _udpLock.Release();
        }
    }

    private void ResetPlaybackState()
    {
        lock (_stateLock)
        {
            _title = "—";
            _artist = "—";
            _album = "—";
            _duration = 0;
            _trackPosition = 0;
            _lastFrameMs = 0;
            _lastPacketSize = 0;
            _lastBandwidth = "—";
            _plcCount = 0;
            _fecCount = 0;
            _silenceCount = 0;
            _receivedPackets = 0;
            _lostPackets = 0;
            _signalStrength = 5;
        }

        lock (_lastEvents) { _lastEvents.Clear(); }
        _jitterBuffer.Clear();
        Console.WriteLine("[STATE] Playback state reset for reconnection");
    }

    private int GetCurrentPort()
    {
        return _isPrimaryStream ? _config.Player.ServerPort : _config.Player.ServerPortFallback;
    }

    private async Task SwitchStream(bool toPrimary)
    {
        if ((DateTime.UtcNow - _lastSwitchTime).TotalMilliseconds < SwitchCooldownMs)
            return;

        if (_isPrimaryStream == toPrimary)
            return;

        _isPrimaryStream = toPrimary;
        _lastSwitchTime = DateTime.UtcNow;

        int newPort = GetCurrentPort();
        int channels = toPrimary ? _config.Opus.Channels : _config.Opus.FallbackChannels;
        string streamName = toPrimary ? "primary" : "fallback";

        AddEvent($"SWITCH {streamName}");

        RecreateDecoder(channels);
        RecreateBassStream(channels);
        _jitterBuffer.Clear();

        await _udpLock.WaitAsync();
        try
        {
            _udp?.Close();
            _udp = new UdpClient();
            _serverEndpoint = new IPEndPoint(IPAddress.Parse(_config.Player.ServerAddress), newPort);

            var subscribe = new SubscribePacket(_clientId);
            await _udp.SendAsync(PacketWriter.WriteSubscribe(subscribe), _serverEndpoint);

            Console.WriteLine($"[STREAM] Switched to {streamName} stream on port {newPort} ({channels}ch)");
        }
        finally
        {
            _udpLock.Release();
        }
    }

    private async Task ConnectAndListenAsync(CancellationToken ct)
    {
        int port = GetCurrentPort();

        await _udpLock.WaitAsync();
        try
        {
            _udp?.Close();
            _udp?.Dispose();

            _udp = new UdpClient();
            _serverEndpoint = new IPEndPoint(IPAddress.Parse(_config.Player.ServerAddress), port);

            var subscribe = new SubscribePacket(_clientId);
            await _udp.SendAsync(PacketWriter.WriteSubscribe(subscribe), _serverEndpoint, ct);
            Console.WriteLine($"[CONNECT] Subscribed to port {port}. GUID: {_clientId.ToString("N")[..8]}...");
        }
        finally
        {
            _udpLock.Release();
        }

        _lastPacketReceived = DateTime.UtcNow;

        using var keepAliveCts = new CancellationTokenSource();
        var keepAliveTask = KeepAliveLoop(keepAliveCts.Token);

        try
        {
            while (!ct.IsCancellationRequested)
            {
                using var receiveCts = new CancellationTokenSource(TimeSpan.FromSeconds(1));
                using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct, receiveCts.Token);

                try
                {
                    UdpReceiveResult result;

                    await _udpLock.WaitAsync();
                    try
                    {
                        if (_udp == null) break;
                        result = await _udp.ReceiveAsync(linked.Token);
                    }
                    finally
                    {
                        _udpLock.Release();
                    }

                    HandlePacket(result.Buffer);
                    _lastPacketReceived = DateTime.UtcNow;
                    _receivedPackets++;
                }
                catch (OperationCanceledException) when (!ct.IsCancellationRequested) { }

                var silence = (DateTime.UtcNow - _lastPacketReceived).TotalMilliseconds;
                if (silence > _config.Player.KeepAliveIntervalMs * 3)
                {
                    Console.WriteLine($"[TIMEOUT] No data from server for {silence:F0}ms");
                    break;
                }
            }
        }
        finally
        {
            keepAliveCts.Cancel();
            try { await keepAliveTask; } catch { }
        }
    }

    private void HandlePacket(byte[] data)
    {
        if (data.Length < 1) return;
        byte type = PacketReader.GetPacketType(data);

        switch (type)
        {
            case PacketTypes.Audio:
                HandleAudio(data);
                break;
            case PacketTypes.ServerInfo:
                HandleServerInfo(data);
                break;
        }
    }

    private void HandleAudio(byte[] data)
    {
        var packet = PacketReader.ReadAudioFromServer(data);

        if (packet.Metadata != null && !packet.Metadata.IsEmpty)
        {
            lock (_stateLock)
            {
                _title = packet.Metadata.Title;
                _artist = packet.Metadata.Artist;
                _album = packet.Metadata.Album;
                _duration = packet.Metadata.Duration;
                _trackPosition = 0;
            }
        }

        if (packet.OpusFrame.Length > 0)
        {
            _jitterBuffer.Add(packet.Sequence, packet.OpusFrame);
            _expectedSequence = packet.Sequence + 1;
        }
    }

    private void HandleServerInfo(byte[] data)
    {
        var info = PacketReader.ReadServerInfo(data);

        lock (_stateLock)
        {
            _serverStatus = info.Status;
            _serverUptime = info.Uptime;
            _listenersCount = info.ClientsCount;
            _trackPosition = info.TrackPosition;
        }
    }

    private async Task KeepAliveLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await Task.Delay(_config.Player.KeepAliveIntervalMs, ct);

            await _udpLock.WaitAsync();
            try
            {
                if (_udp != null && _serverEndpoint != null)
                {
                    var keepAlive = new KeepAlivePacket(_clientId);
                    await _udp.SendAsync(PacketWriter.WriteKeepAlive(keepAlive), _serverEndpoint, ct);
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { }
            catch (Exception) { }
            finally
            {
                _udpLock.Release();
            }
        }
    }

    private void QualityCheckLoop()
    {
        while (_running)
        {
            Thread.Sleep(_config.Player.QualityCheckIntervalMs);
            CheckQuality();
        }
    }

    private void CheckQuality()
    {
        int totalPackets, lostPackets;

        lock (_stateLock)
        {
            totalPackets = _receivedPackets + _lostPackets;
            lostPackets = _lostPackets;
        }

        if (totalPackets == 0)
        {
            UpdateSignalStrength(0);
            return;
        }

        double lossPercent = (double)lostPackets / totalPackets * 100;

        int newStrength = lossPercent switch
        {
            <= 1 => 5,
            <= 3 => 4,
            <= 7 => 3,
            <= 15 => 2,
            <= 30 => 1,
            _ => 0
        };
        UpdateSignalStrength(newStrength);

        if (_autoSwitchEnabled)
        {
            if (_isPrimaryStream && lossPercent > _config.Player.ToleranceSwitchToFallback)
            {
                _ = SwitchStream(toPrimary: false);
                lock (_stateLock) { _receivedPackets = 0; _lostPackets = 0; }
            }
            else if (!_isPrimaryStream && lossPercent < _config.Player.ToleranceSwitchToPrimary)
            {
                _ = SwitchStream(toPrimary: true);
                lock (_stateLock) { _receivedPackets = 0; _lostPackets = 0; }
            }
        }

        lock (_stateLock) { _receivedPackets = 0; _lostPackets = 0; }
    }

    private void UpdateSignalStrength(int strength)
    {
        lock (_stateLock) { _signalStrength = Math.Clamp(strength, 0, 5); }
    }

    private void AddEvent(string msg)
    {
        lock (_lastEvents)
        {
            _lastEvents.Enqueue($"{DateTime.UtcNow:HH:mm:ss} {msg}");
            while (_lastEvents.Count > MaxEvents)
                _lastEvents.Dequeue();
        }
    }

    private void InputLoop(object? ctObj)
    {
        var ct = (CancellationToken)ctObj!;

        while (!ct.IsCancellationRequested)
        {
            if (Console.KeyAvailable)
            {
                var key = Console.ReadKey(true);

                switch (key.Key)
                {
                    case ConsoleKey.Oem4:
                        _simLossPercent = Math.Max(0, _simLossPercent - 5);
                        UpdateSimulation();
                        break;
                    case ConsoleKey.Oem6:
                        _simLossPercent = Math.Min(100, _simLossPercent + 5);
                        UpdateSimulation();
                        break;
                    case ConsoleKey.L:
                        _simLossPercent = _simLossPercent > 0 || _jitterMs > 0 ? 0 : 10;
                        _jitterMs = 0;
                        UpdateSimulation();
                        break;
                    case ConsoleKey.P:
                        _plcEnabled = !_plcEnabled;
                        break;
                    case ConsoleKey.F:
                        _fecEnabled = !_fecEnabled;
                        break;
                    case ConsoleKey.J:
                        _jitterMs = Math.Min(500, _jitterMs + 20);
                        UpdateSimulation();
                        break;
                    case ConsoleKey.K:
                        _jitterMs = Math.Max(0, _jitterMs - 20);
                        UpdateSimulation();
                        break;
                    case ConsoleKey.S:
                        _ = SwitchStream(!_isPrimaryStream);
                        lock (_stateLock) { _receivedPackets = 0; _lostPackets = 0; }
                        break;
                    case ConsoleKey.A:
                        _autoSwitchEnabled = !_autoSwitchEnabled;
                        AddEvent(_autoSwitchEnabled ? "AUTO ON" : "AUTO OFF");
                        break;
                    case ConsoleKey.Q:
                        Environment.Exit(0);
                        break;
                }
            }
            Thread.Sleep(50);
        }
    }

    private void PlaybackLoop()
    {
        int maxFrameSamples = _config.Opus.SampleRate * 120 / 1000;
        int maxChannels = Math.Max(_config.Opus.Channels, _config.Opus.FallbackChannels);
        int maxTotalSamples = maxFrameSamples * maxChannels;

        short[] pcmBuffer = new short[maxTotalSamples];
        byte[] byteBuffer = new byte[maxTotalSamples * sizeof(short)];

        while (_running)
        {
            var jitterResult = _jitterBuffer.GetNext();

            if (jitterResult.Type == JitterBuffer.ResultType.Empty)
            {
                Thread.Sleep(1);
                continue;
            }

            if (jitterResult.Type == JitterBuffer.ResultType.Missing)
            {
                lock (_stateLock) { _lostPackets++; }
            }

            if (_outputStream != 0 && _opusDecoder != null)
            {
                try
                {
                    if (jitterResult.Type == JitterBuffer.ResultType.Missing)
                    {
                        bool fecApplied = false;

                        if (_fecEnabled)
                        {
                            var nextFrame = _jitterBuffer.PeekNextAvailable();
                            if (nextFrame != null)
                            {
                                var fecResult = _opusDecoder.Decode(nextFrame, pcmBuffer, fec: true);
                                if (fecResult != null)
                                {
                                    _fecCount++;
                                    fecApplied = true;
                                    AddEvent($"FEC {fecResult.Value.bandwidth}");
                                    lock (_stateLock)
                                    {
                                        _lastFrameMs = fecResult.Value.frameMs;
                                        _lastPacketSize = fecResult.Value.packetBytes;
                                        _lastBandwidth = "FEC";
                                    }
                                    WriteToBass(fecResult.Value.decodedSamples, _currentDecoderChannels, pcmBuffer, byteBuffer);
                                }
                            }
                        }

                        if (!fecApplied)
                            HandleMissingFrame(pcmBuffer, byteBuffer);
                    }
                    else if (jitterResult.Data != null)
                    {
                        var result = _opusDecoder.Decode(jitterResult.Data, pcmBuffer, false);

                        if (result != null)
                        {
                            _jitterBuffer.SetLastFrame(jitterResult.Data);
                            lock (_stateLock)
                            {
                                _lastFrameMs = result.Value.frameMs;
                                _lastPacketSize = result.Value.packetBytes;
                                _lastBandwidth = result.Value.bandwidth;
                            }
                            WriteToBass(result.Value.decodedSamples, _currentDecoderChannels, pcmBuffer, byteBuffer);
                        }
                    }
                }
                catch (Exception ex)
                {
                    if (_running) Console.WriteLine($"[DECODE] Error: {ex.Message}");
                }
            }
            else
            {
                Thread.Sleep(1);
            }
        }
    }

    private void HandleMissingFrame(short[] pcmBuffer, byte[] byteBuffer)
    {
        if (_plcEnabled)
        {
            var lastFrame = _jitterBuffer.GetLastFrame();
            if (lastFrame != null && _opusDecoder != null)
            {
                var plcResult = _opusDecoder.Decode(null, pcmBuffer, fec: false);
                if (plcResult != null)
                {
                    _plcCount++;
                    AddEvent("PLC");
                    lock (_stateLock)
                    {
                        _lastFrameMs = plcResult.Value.frameMs;
                        _lastPacketSize = 0;
                        _lastBandwidth = "PLC";
                    }
                    WriteToBass(plcResult.Value.decodedSamples, _currentDecoderChannels, pcmBuffer, byteBuffer);
                    return;
                }
            }
        }

        WriteSilence(pcmBuffer, byteBuffer);
    }

    private void WriteSilence(short[] pcmBuffer, byte[] byteBuffer)
    {
        int channels = _currentDecoderChannels;
        int frameSamples = _config.Opus.SampleRate * _config.Opus.FrameSize / 1000;
        int samples = frameSamples * channels;

        Array.Clear(pcmBuffer, 0, samples);
        int byteCount = samples * sizeof(short);
        Array.Clear(byteBuffer, 0, byteCount);

        _silenceCount++;
        AddEvent("SILENCE");
        lock (_stateLock)
        {
            _lastFrameMs = _config.Opus.FrameSize;
            _lastPacketSize = 0;
            _lastBandwidth = "SILENCE";
        }

        WriteToBass(frameSamples, channels, pcmBuffer, byteBuffer);
    }

    private void WriteToBass(int decodedSamples, int channels, short[] pcmBuffer, byte[] byteBuffer)
    {
        int samplesToWrite = decodedSamples * channels;
        int byteCount = samplesToWrite * sizeof(short);
        Buffer.BlockCopy(pcmBuffer, 0, byteBuffer, 0, byteCount);

        while (_running)
        {
            int queued = Bass.BASS_StreamPutData(_outputStream, IntPtr.Zero, 0);
            if (queued < byteCount * 20)
                break;
            Thread.Sleep(1);
        }

        if (_running)
        {
            Bass.BASS_StreamPutData(_outputStream, byteBuffer, byteCount);
        }
    }

    private void UiLoop()
    {
        while (_running)
        {
            DrawUi();
            Thread.Sleep(250);
        }
    }

    private void DrawUi()
    {
        string statusText, statusIcon;
        int listeners, reconnects;
        string title, artist, album, trackPosStr, uptimeStr;
        double duration;
        string codecInfo;
        int plcCount, fecCount, silenceCount;
        double simLoss;
        int jitterMs;
        bool plcEnabled, fecEnabled, isPrimary, autoSwitch;
        int signalStrength;
        List<string> events;

        lock (_stateLock)
        {
            statusIcon = _serverStatus switch
            {
                ServerInfoPacket.StatusLive => "🟢",
                ServerInfoPacket.StatusShuttingDown => "🔴",
                _ => "🟡"
            };
            statusText = _serverStatus switch
            {
                ServerInfoPacket.StatusLive => "Live",
                ServerInfoPacket.StatusShuttingDown => "Shutdown",
                _ => "No Source"
            };
            listeners = _listenersCount;
            reconnects = _reconnects;
            title = _title;
            artist = _artist;
            album = _album;
            duration = _duration;
            plcCount = _plcCount;
            fecCount = _fecCount;
            silenceCount = _silenceCount;
            simLoss = _simLossPercent;
            jitterMs = _jitterMs;
            plcEnabled = _plcEnabled;
            fecEnabled = _fecEnabled;
            isPrimary = _isPrimaryStream;
            autoSwitch = _autoSwitchEnabled;
            signalStrength = _signalStrength;

            var pos = TimeSpan.FromSeconds(_trackPosition);
            trackPosStr = $"{(int)pos.TotalMinutes:D2}:{pos.Seconds:D2}";
            var dur = TimeSpan.FromSeconds(duration);
            string durStr = duration > 0 ? $" / {(int)dur.TotalMinutes:D2}:{dur.Seconds:D2}" : "";
            trackPosStr += durStr;

            var up = TimeSpan.FromSeconds(_serverUptime);
            uptimeStr = up.TotalHours >= 1
                ? $"{(int)up.TotalHours}ч {up.Minutes:D2}м {up.Seconds:D2}с"
                : $"{up.Minutes}м {up.Seconds:D2}с";

            codecInfo = _lastPacketSize > 0
                ? $"{_lastFrameMs}ms {_lastPacketSize}B {_lastBandwidth}"
                : $"{_lastFrameMs}ms {_lastBandwidth}";
        }

        lock (_lastEvents) { events = _lastEvents.ToList(); }

        string simStr = simLoss > 0 || jitterMs > 0 ? $"L:{simLoss:F0}% J:{jitterMs}ms" : "SIM: OFF";
        string plcStr = plcEnabled ? "P:ON" : "P:OFF";
        string fecStr = fecEnabled ? "F:ON" : "F:OFF";
        string streamStr = isPrimary ? "PRI" : "FALL";
        string autoStr = autoSwitch ? "AUTO" : "MAN";
        string antenna = GetAntenna(signalStrength);

        Console.SetCursorPosition(0, 0);
        Console.WriteLine("┌──────────────────────────────────────────────────┐");
        Console.WriteLine($"│ {statusIcon} {statusText,-8} │ Слушателей: {listeners,-5} Reconnects: {reconnects,-3} │");
        Console.WriteLine($"│ Сервер: {uptimeStr,-33} │");
        Console.WriteLine("├──────────────────────────────────────────────────┤");
        Console.WriteLine($"│ {Truncate(artist, 48)} │");
        Console.WriteLine($"│ {Truncate(title, 48)} │");
        Console.WriteLine($"│ {Truncate(album, 48)} │");
        Console.WriteLine($"│ {trackPosStr,-48} │");
        Console.WriteLine($"│ {antenna} {streamStr} {autoStr} │ Opus: {codecInfo,-18} │");
        Console.WriteLine($"│ {plcStr} {fecStr} FEC:{fecCount,-4} SIL:{silenceCount,-4} {simStr,-17} │");
        Console.WriteLine("├──────────────────────────────────────────────────┤");
        for (int i = 0; i < MaxEvents; i++)
        {
            string evt = i < events.Count ? Truncate(events[i], 48) : new string(' ', 48);
            Console.WriteLine($"│ {evt} │");
        }
        Console.WriteLine("├──────────────────────────────────────────────────┤");
        Console.WriteLine("│ [Q] [P]PLC [F]FEC [S]Stream [A]Auto [[]/[]]Loss  │");
        Console.WriteLine("│ [J/K]Jitter [L]Off                               │");
        Console.WriteLine("└──────────────────────────────────────────────────┘");
    }

    private static string GetAntenna(int strength)
    {
        string[] bars = { "·", "▁", "▂", "▃", "▄", "▅" };
        string antenna = "♫";
        for (int i = 1; i <= 5; i++)
            antenna += i <= strength ? bars[strength] : "·";
        return antenna;
    }

    private bool InitBass()
    {
        if (!Bass.BASS_Init(-1, _config.Opus.SampleRate, BASSInit.BASS_DEVICE_DEFAULT, IntPtr.Zero))
        {
            Console.WriteLine($"BASS_Init error: {Bass.BASS_ErrorGetCode()}");
            return false;
        }

        Console.WriteLine($"[Opus] Version: {OpusNative.opus_get_version_string()}");

        _opusDecoder = new OpusDecoder(_config.Opus.SampleRate, _config.Opus.Channels);
        _currentDecoderChannels = _config.Opus.Channels;
        Console.WriteLine($"Native Opus decoder: {_config.Opus.SampleRate}Hz, {_config.Opus.Channels}ch");

        _outputStream = Bass.BASS_StreamCreatePush(_config.Opus.SampleRate, _config.Opus.Channels, BASSFlag.BASS_DEFAULT, IntPtr.Zero);

        if (_outputStream == 0)
        {
            Console.WriteLine($"[ERROR] Cannot create output stream: {Bass.BASS_ErrorGetCode()}");
            return false;
        }

        Bass.BASS_ChannelPlay(_outputStream, false);
        Console.WriteLine("BASS output started");
        return true;
    }

    private static string Truncate(string str, int maxLen)
    {
        if (string.IsNullOrEmpty(str)) return new string(' ', maxLen);
        return str.Length > maxLen ? str[..(maxLen - 1)] + "…" : str.PadRight(maxLen);
    }
}
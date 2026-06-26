using System.Net;
using System.Net.Sockets;
using Concentus.Structs;
using FrostWire.Core.Configuration;
using FrostWire.Core.Protocol;
using FrostWire.Core.Protocol.Models;
using Un4seen.Bass;

namespace FrostWire.Player;

public class PlayerEngine
{
    private readonly AppConfig _config;
    private readonly Guid _clientId;
    private UdpClient? _udp;
    private IPEndPoint? _serverEndpoint;

    private JitterBuffer _jitterBuffer;
    private readonly object _stateLock = new();

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

    private DateTime _lastPacketReceived = DateTime.MinValue;

    private OpusDecoder _opusDecoder = null!;
    private int _outputStream;

    public PlayerEngine(AppConfig config)
    {
        _config = config;
        _clientId = Guid.NewGuid();
        _jitterBuffer = new JitterBuffer();
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

        var playbackThread = new Thread(PlaybackLoop)
        {
            IsBackground = true
        };
        playbackThread.Start();

        var uiThread = new Thread(UiLoop)
        {
            IsBackground = true
        };
        uiThread.Start();

        try
        {
            while (!ct.IsCancellationRequested)
            {
                await ConnectAndListenAsync(ct);

                if (!ct.IsCancellationRequested)
                {
                    Console.WriteLine("[RECONNECT] Connection lost, reconnecting in 1s...");
                    _reconnects++;
                    _serverStatus = ServerInfoPacket.StatusNoSource;

                    // ДОБАВЛЕНО: сброс состояния при реконнекте
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
            Bass.BASS_StreamFree(_outputStream);
            Bass.BASS_Free();
            _udp?.Close();
        }
    }

    // НОВЫЙ МЕТОД: сброс состояния воспроизведения
    private void ResetPlaybackState()
    {
        lock (_stateLock)
        {
            _title = "—";
            _artist = "—";
            _album = "—";
            _duration = 0;
            _trackPosition = 0;
        }

        // Очищаем jitter buffer при реконнекте
        _jitterBuffer.Clear();

        Console.WriteLine("[STATE] Playback state reset for reconnection");
    }

    private async Task ConnectAndListenAsync(CancellationToken ct)
    {
        _udp = new UdpClient();
        _serverEndpoint = new IPEndPoint(IPAddress.Parse(_config.Player.ServerAddress), _config.Player.ServerPort);

        var subscribe = new SubscribePacket(_clientId);
        await _udp.SendAsync(PacketWriter.WriteSubscribe(subscribe), _serverEndpoint, ct);
        Console.WriteLine($"[CONNECT] Subscribed. GUID: {_clientId.ToString("N")[..8]}...");

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
                    var result = await _udp.ReceiveAsync(linked.Token);
                    HandlePacket(result.Buffer);
                    _lastPacketReceived = DateTime.UtcNow;
                }
                catch (OperationCanceledException) when (!ct.IsCancellationRequested)
                {
                }

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
            _udp.Close();
            // УБРАНО: _jitterBuffer.Clear(); — теперь очищаем в ResetPlaybackState()
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

            if (_udp != null && _serverEndpoint != null)
            {
                var keepAlive = new KeepAlivePacket(_clientId);
                await _udp.SendAsync(PacketWriter.WriteKeepAlive(keepAlive), _serverEndpoint, ct);
            }
        }
    }

    // ─── Воспроизведение ──────────────────────────────────────

    private void PlaybackLoop()
    {
        short[] pcmBuffer = new short[5760 * 2];
        byte[] byteBuffer = new byte[5760 * 2 * 2];

        while (_running)
        {
            var opusFrame = _jitterBuffer.GetNext();

            if (opusFrame != null && _outputStream != 0)
            {
                try
                {
                    int frameSamples = _opusDecoder.Decode(
                        opusFrame, 0, opusFrame.Length,
                        pcmBuffer, 0, pcmBuffer.Length / 2,
                        false);

                    if (frameSamples > 0)
                    {
                        Buffer.BlockCopy(pcmBuffer, 0, byteBuffer, 0, frameSamples * 2 * 2);

                        // Ждём пока в буфере BASS не освободится место
                        while (_running)
                        {
                            int queued = Bass.BASS_StreamPutData(_outputStream, IntPtr.Zero, 0);
                            if (queued < frameSamples * 2 * 2 * 20) // меньше 20 фреймов
                                break;
                            Thread.Sleep(1);
                        }

                        Bass.BASS_StreamPutData(_outputStream, byteBuffer, frameSamples * 2 * 2);
                    }
                }
                catch { }
            }

            Thread.Sleep(1);
        }
    }

    // ─── UI ───────────────────────────────────────────────────

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
        string title, artist, album, trackPosStr;
        string uptimeStr;
        double duration;

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

            var pos = TimeSpan.FromSeconds(_trackPosition);
            trackPosStr = $"{(int)pos.TotalMinutes:D2}:{pos.Seconds:D2}";

            var dur = TimeSpan.FromSeconds(duration);
            string durStr = duration > 0 ? $" / {(int)dur.TotalMinutes:D2}:{dur.Seconds:D2}" : "";

            var up = TimeSpan.FromSeconds(_serverUptime);
            uptimeStr = up.TotalHours >= 1
                ? $"{(int)up.TotalHours}ч {up.Minutes:D2}м {up.Seconds:D2}с"
                : $"{up.Minutes}м {up.Seconds:D2}с";

            trackPosStr += durStr;
        }

        Console.SetCursorPosition(0, 0);
        Console.WriteLine("┌──────────────────────────────────────────────────┐");
        Console.WriteLine($"│ {statusIcon} {statusText,-8} │ Слушателей: {listeners,-5} Reconnects: {reconnects,-3} │");
        Console.WriteLine($"│ Сервер: {uptimeStr,-33} │");
        Console.WriteLine("├──────────────────────────────────────────────────┤");
        Console.WriteLine($"│ {Truncate(artist, 48)} │");
        Console.WriteLine($"│ {Truncate(title, 48)} │");
        Console.WriteLine($"│ {Truncate(album, 48)} │");
        Console.WriteLine($"│ {trackPosStr,-48} │");
        Console.WriteLine("├──────────────────────────────────────────────────┤");
        Console.WriteLine("│ [Q] Выход                                        │");
        Console.WriteLine("└──────────────────────────────────────────────────┘");
    }

    // ─── BASS ────────────────────────────────────────────────

    private bool InitBass()
    {
        if (!Bass.BASS_Init(-1, _config.Opus.SampleRate, BASSInit.BASS_DEVICE_DEFAULT, IntPtr.Zero))
        {
            Console.WriteLine($"BASS_Init error: {Bass.BASS_ErrorGetCode()}");
            return false;
        }

        _opusDecoder = new OpusDecoder(_config.Opus.SampleRate, _config.Opus.Channels);
        Console.WriteLine($"Concentus Opus decoder: {_config.Opus.SampleRate}Hz, {_config.Opus.Channels}ch");

        _outputStream = Bass.BASS_StreamCreatePush(
            _config.Opus.SampleRate,
            _config.Opus.Channels,
            BASSFlag.BASS_DEFAULT,
            IntPtr.Zero);

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
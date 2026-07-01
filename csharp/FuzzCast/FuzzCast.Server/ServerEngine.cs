using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using FuzzCast.Core.Configuration;
using FuzzCast.Core.Native;
using FuzzCast.Core.Protocol;
using FuzzCast.Core.Protocol.Models;
using FuzzCast.Core.Security;

namespace FuzzCast.Server;

public class ServerEngine
{
    private readonly AppConfig _config;
    private readonly UdpClient _udpPrimary;
    private readonly UdpClient _udpFallback;
    private readonly ClientRegistry _clients;
    private readonly byte[] _expectedPasswordHash;

    private IPEndPoint? _sourceEndpoint;
    private TrackMetadata? _lastMetadata;
    private DateTime _lastAudioTime = DateTime.MinValue;
    private DateTime _serverStartTime = DateTime.UtcNow;
    private DateTime _currentTrackStart = DateTime.MinValue;
    private double _currentTrackDuration;

    private byte _status = ServerInfoPacket.StatusNoSource;

    private readonly SemaphoreSlim _broadcastSemaphore = new(1, 1);

    // Перекодирование fallback в отдельном потоке
    private OpusDecoder? _transcodeDecoder;
    private OpusEncoder? _transcodeEncoder;
    private short[]? _pcmBuffer;
    private byte[]? _fallbackBuf;
    private readonly ConcurrentQueue<(byte[] opusFrame, uint sequence, long timestamp)> _transcodeQueue = new();
    private readonly SemaphoreSlim _transcodeSignal = new(0);

    public ServerEngine(AppConfig config)
    {
        _config = config;
        _udpPrimary = new UdpClient(config.Server.ListenPort);
        _udpFallback = new UdpClient(config.Server.ListenPortFallback);

        try
        {
            _udpPrimary.Client.IOControl((IOControlCode)(-1744830452), new byte[] { 0 }, null);
            _udpFallback.Client.IOControl((IOControlCode)(-1744830452), new byte[] { 0 }, null);
        }
        catch { }

        _clients = new ClientRegistry();
        _expectedPasswordHash = PasswordHasher.ComputeHash(config.Server.Password);

        InitTranscoder();
    }

    private void InitTranscoder()
    {
        _transcodeDecoder = new OpusDecoder(_config.Opus.SampleRate, _config.Opus.Channels);

        bool fecEnabled = _config.Opus.FallbackPacketLossPercent > 0;

        _transcodeEncoder = new OpusEncoder(
            _config.Opus.SampleRate,
            _config.Opus.FallbackChannels,
            OpusApplication.Audio,
            _config.Opus.FrameSize)
        {
            Bitrate = _config.Opus.FallbackBitrate,
            Complexity = _config.Opus.Complexity,
            Vbr = true,
            InbandFec = fecEnabled,
            PacketLossPercent = _config.Opus.FallbackPacketLossPercent,
            Dtx = false,
            SignalType = OpusSignal.Music,
            MaxBandwidth = OpusBandwidth.Fullband
        };

        int maxSamples = _config.Opus.SampleRate * 120 / 1000 * _config.Opus.Channels;
        _pcmBuffer = new short[maxSamples];
        _fallbackBuf = new byte[65536];

        Console.WriteLine($"[FALLBACK] Transcoder ready: {_config.Opus.FallbackBitrate / 1000}kbps mono" +
                         (fecEnabled ? $", FEC {_config.Opus.FallbackPacketLossPercent}%" : ""));
    }

    public async Task RunAsync(CancellationToken ct)
    {
        Console.WriteLine($"Listening on UDP ports {_config.Server.ListenPort} (primary) and {_config.Server.ListenPortFallback} (fallback)");

        using var timerCts = CancellationTokenSource.CreateLinkedTokenSource(ct);

        _ = Task.Run(() => SourceStatusLoop(timerCts.Token), ct);
        _ = Task.Run(() => PlayerTimeoutLoop(timerCts.Token), ct);
        _ = Task.Run(() => ServerInfoLoop(timerCts.Token), ct);
        _ = Task.Run(() => TranscodeLoop(ct), ct);

        var primaryTask = ReceiveLoop(_udpPrimary, ct);
        var fallbackTask = ReceiveLoop(_udpFallback, ct);

        try
        {
            await Task.WhenAll(primaryTask, fallbackTask);
        }
        catch (OperationCanceledException) { }
        finally
        {
            timerCts.Cancel();
            _udpPrimary.Close();
            _udpFallback.Close();
            _transcodeDecoder?.Dispose();
            _transcodeEncoder?.Dispose();
        }
    }

    private async Task ReceiveLoop(UdpClient udp, CancellationToken ct)
    {
        try
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var result = await udp.ReceiveAsync(ct);
                    _ = Task.Run(() => HandlePacket(result.Buffer, result.RemoteEndPoint, udp), ct);
                }
                catch (SocketException ex)
                {
                    Console.WriteLine($"[WARN] Receive error on port {((IPEndPoint)udp.Client.LocalEndPoint).Port}: {ex.Message}");
                }
            }
        }
        catch (OperationCanceledException) { }
    }

    private void HandlePacket(byte[] data, IPEndPoint remote, UdpClient sourceUdp)
    {
        if (data.Length < 1) return;

        byte type = PacketReader.GetPacketType(data);

        try
        {
            switch (type)
            {
                case PacketTypes.Audio:
                    HandleAudio(data, remote);
                    break;
                case PacketTypes.Subscribe:
                    HandleSubscribe(data, remote, sourceUdp);
                    break;
                case PacketTypes.KeepAlive:
                    HandleKeepAlive(data, remote);
                    break;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[ERROR] Processing packet type 0x{type:X2} from {remote}: {ex.Message}");
        }
    }

    private void HandleAudio(byte[] data, IPEndPoint remote)
    {
        var packet = PacketReader.ReadAudioFromSource(data);

        if (packet.PasswordMD5 == null || !packet.PasswordMD5.SequenceEqual(_expectedPasswordHash))
        {
            Console.WriteLine($"[WARN] Invalid password from {remote}");
            return;
        }

        if (_sourceEndpoint == null || !_sourceEndpoint.Equals(remote))
        {
            Console.WriteLine($"[INFO] Source connected: {remote}");
            _sourceEndpoint = remote;
        }
        _lastAudioTime = DateTime.UtcNow;

        if (packet.Metadata != null && !packet.Metadata.IsEmpty)
        {
            _lastMetadata = packet.Metadata;
            _currentTrackStart = DateTime.UtcNow;
            _currentTrackDuration = packet.Metadata.Duration;
            Console.WriteLine($"[TRACK] {packet.Metadata.Artist} - {packet.Metadata.Title} [{packet.Metadata.Duration:F0}s]");
        }

        if (_status != ServerInfoPacket.StatusLive)
        {
            _status = ServerInfoPacket.StatusLive;
            Console.WriteLine("[STATUS] Live");
        }

        var playerPacket = new AudioPacket
        {
            Sequence = packet.Sequence,
            Timestamp = packet.Timestamp,
            Metadata = packet.Metadata,
            OpusFrame = packet.OpusFrame
        };

        // Ретранслируем primary
        var primaryData = PacketWriter.WriteAudioToPlayer(playerPacket);
        _ = BroadcastToPlayersAsync(primaryData, _udpPrimary);

        // Кладём в очередь для перекодирования
        _transcodeQueue.Enqueue((packet.OpusFrame, packet.Sequence, packet.Timestamp));
        _transcodeSignal.Release();
    }

    private async Task TranscodeLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                await _transcodeSignal.WaitAsync(ct);
            }
            catch (OperationCanceledException)
            {
                break;
            }

            while (_transcodeQueue.TryDequeue(out var item))
            {
                if (_transcodeDecoder == null || _transcodeEncoder == null || _pcmBuffer == null || _fallbackBuf == null)
                    continue;

                var decodeResult = _transcodeDecoder.Decode(item.opusFrame, _pcmBuffer, fec: false);
                if (decodeResult == null)
                    continue;

                // Даунмикс стерео → моно
                int frameSamples = decodeResult.Value.decodedSamples; // семплов на канал
                short[] monoPcm = DownmixStereoToMono(_pcmBuffer, frameSamples, _config.Opus.Channels);

                int fallbackLen = _transcodeEncoder.Encode(monoPcm, _fallbackBuf);
                if (fallbackLen <= 0)
                    continue;

                var fallbackPacket = new AudioPacket
                {
                    Sequence = item.sequence,
                    Timestamp = item.timestamp,
                    Metadata = null,
                    OpusFrame = _fallbackBuf.Take(fallbackLen).ToArray()
                };

                var fallbackData = PacketWriter.WriteAudioToPlayer(fallbackPacket);
                _ = BroadcastToPlayersAsync(fallbackData, _udpFallback);
            }
        }
    }

    private short[] DownmixStereoToMono(short[] stereo, int samplesPerChannel, int channels)
    {
        if (channels == 1)
            return stereo;

        short[] mono = new short[samplesPerChannel];
        for (int i = 0; i < samplesPerChannel; i++)
        {
            int left = stereo[i * 2];
            int right = stereo[i * 2 + 1];
            mono[i] = (short)((left + right) / 2);
        }
        return mono;
    }

    private void HandleSubscribe(byte[] data, IPEndPoint remote, UdpClient sourceUdp)
    {
        var packet = PacketReader.ReadSubscribe(data);
        var clientId = packet.GetClientId();
        int subscribePort = ((IPEndPoint)sourceUdp.Client.LocalEndPoint).Port;

        bool isNew = _clients.AddOrUpdate(clientId, remote, subscribePort);
        string action = isNew ? "connected" : "reconnected";
        Console.WriteLine($"[PLAYER] {action}: {clientId.ToString("N")[..8]}... from {remote} (port {subscribePort})");

        var serverInfo = BuildServerInfo();
        _ = SendToAsync(PacketWriter.WriteServerInfo(serverInfo), remote, _udpPrimary);

        if (_lastMetadata != null && !_lastMetadata.IsEmpty)
        {
            var metaPacket = new AudioPacket
            {
                Sequence = 0,
                Timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                Metadata = _lastMetadata,
                OpusFrame = Array.Empty<byte>()
            };
            _ = SendToAsync(PacketWriter.WriteAudioToPlayer(metaPacket), remote, _udpPrimary);
        }
    }

    private void HandleKeepAlive(byte[] data, IPEndPoint remote)
    {
        var packet = PacketReader.ReadKeepAlive(data);
        var clientId = packet.GetClientId();
        _clients.Refresh(clientId);
    }

    private async Task SourceStatusLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await Task.Delay(_config.Server.SourceStatusIntervalMs, ct);

            var status = new SourceStatusPacket
            {
                Timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                ClientsCount = _clients.Count
            };
            var statusData = PacketWriter.WriteSourceStatus(status);

            if (_sourceEndpoint != null)
                await SendToAsync(statusData, _sourceEndpoint, _udpPrimary);

            if (_status == ServerInfoPacket.StatusLive &&
                (DateTime.UtcNow - _lastAudioTime).TotalMilliseconds > _config.Server.SourceTimeoutMs)
            {
                _status = ServerInfoPacket.StatusNoSource;
                _sourceEndpoint = null;
                Console.WriteLine("[STATUS] NoSource — source timeout");
            }
        }
    }

    private async Task PlayerTimeoutLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await Task.Delay(5000, ct);
            int removed = _clients.RemoveTimedOut(_config.Server.PlayerTimeoutMs);
            if (removed > 0)
                Console.WriteLine($"[PLAYER] Removed {removed} timed out, total: {_clients.Count}");
        }
    }

    private async Task ServerInfoLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await Task.Delay(_config.Server.ServerInfoIntervalMs, ct);
            if (_clients.Count > 0)
            {
                var info = BuildServerInfo();
                var infoData = PacketWriter.WriteServerInfo(info);
                var clients = _clients.GetAllEndpoints().ToList();
                foreach (var client in clients)
                    _ = SendToAsync(infoData, client, _udpPrimary);
            }
        }
    }

    private ServerInfoPacket BuildServerInfo()
    {
        uint trackPosition = 0;
        if (_status == ServerInfoPacket.StatusLive && _currentTrackDuration > 0)
        {
            trackPosition = (uint)(DateTime.UtcNow - _currentTrackStart).TotalSeconds;
            if (trackPosition > _currentTrackDuration)
                trackPosition = (uint)_currentTrackDuration;
        }

        return new ServerInfoPacket
        {
            Timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            Uptime = (uint)(DateTime.UtcNow - _serverStartTime).TotalSeconds,
            Status = _status,
            ClientsCount = _clients.Count,
            TrackPosition = trackPosition
        };
    }

    private async Task BroadcastToPlayersAsync(byte[] data, UdpClient sourceUdp)
    {
        int port = ((IPEndPoint)sourceUdp.Client.LocalEndPoint).Port;

        await _broadcastSemaphore.WaitAsync();
        try
        {
            var clients = _clients.GetByPort(port).ToList();
            var tasks = new List<Task>(clients.Count);
            foreach (var (endpoint, _) in clients)
                tasks.Add(SendToClientSafeAsync(data, endpoint, sourceUdp));
            await Task.WhenAll(tasks);
        }
        finally
        {
            _broadcastSemaphore.Release();
        }
    }

    private async Task SendToClientSafeAsync(byte[] data, IPEndPoint client, UdpClient sourceUdp)
    {
        try
        {
            await sourceUdp.SendAsync(data, data.Length, client);
        }
        catch (SocketException)
        {
            var clientId = _clients.GetClientIdByEndpoint(client);
            if (clientId != null)
            {
                _clients.Remove(clientId.Value);
                Console.WriteLine($"[PLAYER] Removed dead client: {clientId.Value.ToString("N")[..8]}...");
            }
        }
    }

    private async Task SendToAsync(byte[] data, IPEndPoint target, UdpClient sourceUdp)
    {
        try
        {
            await sourceUdp.SendAsync(data, data.Length, target);
        }
        catch (SocketException) { }
    }
}
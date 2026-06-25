using System.Net;
using System.Net.Sockets;
using FrostWire.Core.Configuration;
using FrostWire.Core.Protocol;
using FrostWire.Core.Protocol.Models;

namespace FrostWire.Server;

public class ServerEngine
{
    private readonly AppConfig _config;
    private readonly UdpClient _udp;
    private readonly ClientRegistry _clients;
    private readonly byte[] _expectedPasswordMD5;

    private IPEndPoint? _sourceEndpoint;
    private TrackMetadata? _lastMetadata;
    private DateTime _lastAudioTime = DateTime.MinValue;
    private DateTime _serverStartTime = DateTime.UtcNow;
    private DateTime _currentTrackStart = DateTime.MinValue;
    private double _currentTrackDuration;

    private byte _status = ServerInfoPacket.StatusNoSource;

    public ServerEngine(AppConfig config)
    {
        _config = config;
        _udp = new UdpClient(config.Server.ListenPort);
        _clients = new ClientRegistry();
        _expectedPasswordMD5 = StringToMD5Bytes(config.Server.PasswordMD5);
    }

    public async Task RunAsync(CancellationToken ct)
    {
        Console.WriteLine($"Listening on UDP port {_config.Server.ListenPort}");
        Console.WriteLine($"Expected password MD5: {_config.Server.PasswordMD5}");

        using var timerCts = CancellationTokenSource.CreateLinkedTokenSource(ct);

        _ = Task.Run(() => SourceStatusLoop(timerCts.Token), ct);
        _ = Task.Run(() => PlayerTimeoutLoop(timerCts.Token), ct);
        _ = Task.Run(() => ServerInfoLoop(timerCts.Token), ct);

        try
        {
            while (!ct.IsCancellationRequested)
            {
                var result = await _udp.ReceiveAsync(ct);
                _ = Task.Run(() => HandlePacket(result.Buffer, result.RemoteEndPoint), ct);
            }
        }
        catch (OperationCanceledException) { }
        finally
        {
            timerCts.Cancel();
            _udp.Close();
        }
    }

    private void HandlePacket(byte[] data, IPEndPoint remote)
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
                    HandleSubscribe(data, remote);
                    break;
                case PacketTypes.KeepAlive:
                    HandleKeepAlive(data, remote);
                    break;
                default:
                    // неизвестный тип — игнорируем
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

        // Проверка пароля
        if (packet.PasswordMD5 == null || !packet.PasswordMD5.SequenceEqual(_expectedPasswordMD5))
        {
            Console.WriteLine($"[WARN] Invalid password from {remote}");
            return;
        }

        // Новый source или подтверждение существующего
        if (_sourceEndpoint == null || !_sourceEndpoint.Equals(remote))
        {
            Console.WriteLine($"[INFO] Source connected: {remote}");
            _sourceEndpoint = remote;
        }

        _lastAudioTime = DateTime.UtcNow;

        // Обновляем метаданные если есть
        if (packet.Metadata != null && !packet.Metadata.IsEmpty)
        {
            _lastMetadata = packet.Metadata;
            _currentTrackStart = DateTime.UtcNow;
            _currentTrackDuration = packet.Metadata.Duration;
            Console.WriteLine($"[TRACK] {packet.Metadata.Artist} - {packet.Metadata.Title} [{packet.Metadata.Duration:F0}s]");
        }

        // Статус Live
        if (_status != ServerInfoPacket.StatusLive)
        {
            _status = ServerInfoPacket.StatusLive;
            Console.WriteLine("[STATUS] Live");
        }

        // Ретрансляция плеерам (вырезаем MD5)
        var playerPacket = new AudioPacket
        {
            Sequence = packet.Sequence,
            Timestamp = packet.Timestamp,
            Metadata = packet.Metadata,
            OpusFrame = packet.OpusFrame
        };

        BroadcastToPlayers(PacketWriter.WriteAudioToPlayer(playerPacket));
    }

    private void HandleSubscribe(byte[] data, IPEndPoint remote)
    {
        var packet = PacketReader.ReadSubscribe(data);
        var clientId = packet.GetClientId();

        bool isNew = _clients.AddOrUpdate(clientId, remote);
        string action = isNew ? "connected" : "reconnected";
        Console.WriteLine($"[PLAYER] {action}: {clientId.ToString("N")[..8]}... from {remote}");

        // Отправляем SERVER_INFO
        var serverInfo = BuildServerInfo();
        SendTo(PacketWriter.WriteServerInfo(serverInfo), remote);

        // Отправляем последние метаданные (если есть) с пустым OpusFrame
        if (_lastMetadata != null && !_lastMetadata.IsEmpty)
        {
            var metaPacket = new AudioPacket
            {
                Sequence = 0,
                Timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                Metadata = _lastMetadata,
                OpusFrame = Array.Empty<byte>()
            };
            SendTo(PacketWriter.WriteAudioToPlayer(metaPacket), remote);
        }
    }

    private void HandleKeepAlive(byte[] data, IPEndPoint remote)
    {
        var packet = PacketReader.ReadKeepAlive(data);
        var clientId = packet.GetClientId();

        _clients.Refresh(clientId);
    }

    // ─── Фоновые циклы ─────────────────────────────────────────

    private async Task SourceStatusLoop(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await Task.Delay(_config.Server.SourceStatusIntervalMs, ct);

            if (_sourceEndpoint != null)
            {
                var status = new SourceStatusPacket
                {
                    Timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                    ClientsCount = _clients.Count
                };
                SendTo(PacketWriter.WriteSourceStatus(status), _sourceEndpoint);
            }

            // Проверка таймаута source
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
                BroadcastToPlayers(PacketWriter.WriteServerInfo(info));
            }
        }
    }

    // ─── Helpers ───────────────────────────────────────────────

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

    private void BroadcastToPlayers(byte[] data)
    {
        foreach (var client in _clients.GetAllEndpoints())
        {
            SendTo(data, client);
        }
    }

    private void SendTo(byte[] data, IPEndPoint target)
    {
        try
        {
            _udp.Send(data, data.Length, target);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[ERROR] Send to {target}: {ex.Message}");
        }
    }

    private static byte[] StringToMD5Bytes(string hex)
    {
        byte[] bytes = new byte[16];
        for (int i = 0; i < 16; i++)
            bytes[i] = Convert.ToByte(hex.Substring(i * 2, 2), 16);
        return bytes;
    }
}
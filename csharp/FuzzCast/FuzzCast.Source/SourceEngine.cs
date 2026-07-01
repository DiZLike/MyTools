using FuzzCast.Core.Configuration;
using FuzzCast.Core.Native;
using FuzzCast.Core.Protocol;
using FuzzCast.Core.Protocol.Models;
using FuzzCast.Core.Security;
using FuzzCast.Source.Audio;
using FuzzCast.Source.Playlist;
using System.Net;
using System.Net.Sockets;
using Un4seen.Bass;
using Un4seen.Bass.AddOn.Fx;

namespace FuzzCast.Source;

public class SourceEngine : IDisposable
{
    private readonly AppConfig _config;
    private readonly UdpClient _udp;
    private readonly byte[] _passwordHash;
    private readonly PlaylistManager _playlist;
    private readonly IPEndPoint _serverEndpoint;
    private readonly ReplayGainProcessor _replayGain;
    private readonly CompressorProcessor _compressor;

    private uint _sequence;
    private DateTime _lastStatusReceived = DateTime.MinValue;

    private OpusEncoder? _opusEncoder;
    private bool _metadataSent;
    private TrackMetadata? _currentMetadata;
    private bool _disposed;

    private CancellationTokenSource? _playbackCts;
    private Task? _currentPlaybackTask;

    public SourceEngine(AppConfig config)
    {
        _config = config;
        _udp = new UdpClient(0);
        _passwordHash = PasswordHasher.ComputeHash(config.Source.Password);
        _playlist = new PlaylistManager(config.Source.PlaylistPath, config.Source.Shuffle);
        _replayGain = new ReplayGainProcessor();
        _compressor = new CompressorProcessor();

        IPAddress serverIp = ResolveAddress(config.Source.ServerAddress);
        _serverEndpoint = new IPEndPoint(serverIp, config.Source.ServerPort);

        Console.WriteLine($"[DEBUG] Source local endpoint: {_udp.Client.LocalEndPoint}");
        Console.WriteLine($"[DEBUG] Server endpoint: {_serverEndpoint}");
    }

    private static IPAddress ResolveAddress(string address)
    {
        if (IPAddress.TryParse(address, out var ip))
        {
            Console.WriteLine($"[DEBUG] Using IP address directly: {ip}");
            return ip;
        }

        try
        {
            Console.WriteLine($"[DEBUG] Resolving hostname: {address}");
            var hostEntry = Dns.GetHostEntry(address);

            var ipv4 = hostEntry.AddressList
                .FirstOrDefault(a => a.AddressFamily == AddressFamily.InterNetwork);

            if (ipv4 != null)
            {
                Console.WriteLine($"[DEBUG] Resolved to: {ipv4}");
                return ipv4;
            }

            var firstIp = hostEntry.AddressList.First();
            Console.WriteLine($"[DEBUG] Resolved to: {firstIp}");
            return firstIp;
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException($"Failed to resolve address: {address}", ex);
        }
    }

    public async Task RunAsync(CancellationToken ct)
    {
        if (!InitBass())
        {
            Console.WriteLine("[FATAL] Failed to initialize BASS");
            return;
        }

        Console.WriteLine("BASS initialized");

        using var statusCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        var statusTask = Task.Run(() => StatusListenerLoop(statusCts.Token), ct);

        try
        {
            while (!ct.IsCancellationRequested)
            {
                var track = _playlist.GetNext();
                if (track == null)
                {
                    Console.WriteLine("[WARN] Playlist empty, waiting...");
                    await Task.Delay(5000, ct);
                    _playlist.Reset();
                    continue;
                }

                using (_playbackCts = CancellationTokenSource.CreateLinkedTokenSource(ct))
                {
                    try
                    {
                        _currentPlaybackTask = PlayTrackAsync(track, _playbackCts.Token);
                        await _currentPlaybackTask;
                    }
                    catch (OperationCanceledException)
                    {
                        Console.WriteLine("[INFO] Playback cancelled");
                        break;
                    }
                }
            }
        }
        finally
        {
            statusCts.Cancel();
            try { await statusTask; } catch (OperationCanceledException) { }

            if (_currentPlaybackTask != null)
            {
                try
                {
                    _playbackCts?.Cancel();
                    await Task.WhenAny(_currentPlaybackTask, Task.Delay(2000));
                }
                catch { }
            }
        }
    }

    private Task PlayTrackAsync(string filePath, CancellationToken ct)
    {
        return Task.Run(() => PlayTrack(filePath, ct), ct);
    }

    private void PlayTrack(string filePath, CancellationToken ct)
    {
        Console.WriteLine($"Loading: {Path.GetFileName(filePath)}");

        _currentMetadata = MetadataExtractor.Extract(filePath);

        // Извлекаем ReplayGain из комментария
        ReplayGainInfo? rgInfo = null;
        try
        {
            using var tagFile = TagLib.File.Create(filePath);
            rgInfo = _replayGain.ExtractFromComment(tagFile.Tag.Comment);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[WARN] Failed to read ReplayGain tags: {ex.Message}");
        }

        var rgLog = rgInfo != null
            ? $" | RG: {rgInfo.TrackGainDb:F2} dB" + (rgInfo.RmsDb.HasValue ? $", RMS: {rgInfo.RmsDb:F2} dB" : "")
            : "";

        Console.WriteLine(
            $"[NOW PLAYING] {_currentMetadata.Artist} - {_currentMetadata.Title} " +
            $"[{_currentMetadata.Duration:F0}s]{rgLog}");

        int stream = Bass.BASS_StreamCreateFile(filePath, 0, 0,
            BASSFlag.BASS_STREAM_DECODE | BASSFlag.BASS_SAMPLE_FLOAT);

        if (stream == 0)
        {
            Console.WriteLine($"[ERROR] Cannot open file: {filePath} — {Bass.BASS_ErrorGetCode()}");
            return;
        }

        float appliedGainDb = 0f;

        // ReplayGain
        if (_config.Compressor.ReplayGainEnabled && rgInfo != null)
        {
            float gainLinear = (float)Math.Pow(10, rgInfo.TrackGainDb / 20.0);
            _replayGain.ApplyToStream(stream, gainLinear);
            appliedGainDb = rgInfo.TrackGainDb;
        }

        // Компрессор
        if (_config.Compressor.CompressorEnabled && rgInfo?.RmsDb.HasValue == true)
        {
            float rmsAfterRG = rgInfo.RmsDb.Value + appliedGainDb;
            float threshold = rmsAfterRG + (float)_config.Compressor.HeadroomDb;

            threshold = Math.Min(threshold, 0f);

            _compressor.ApplyToStream(stream, threshold, _config.Compressor);
        }

        try
        {
            _metadataSent = false;

            int frameDurationMs = _config.Opus.FrameSize;
            int sampleRate = _config.Opus.SampleRate;
            int channels = _config.Opus.Channels;
            int frameSamplesPerChannel = sampleRate * frameDurationMs / 1000;
            int totalFrameSamples = frameSamplesPerChannel * channels;
            int frameSizeBytes = totalFrameSamples * 4;

            float[] pcmFloat = new float[totalFrameSamples];
            short[] pcmShort = new short[totalFrameSamples];
            byte[] opusBuf = new byte[65536];

            long totalSamples = Bass.BASS_ChannelGetLength(stream);
            double totalSeconds = Bass.BASS_ChannelBytes2Seconds(stream, totalSamples);
            Console.WriteLine($"Duration: {totalSeconds:F1}s");

            var nextFrameTime = DateTime.UtcNow;

            while (!ct.IsCancellationRequested)
            {
                long pos = Bass.BASS_ChannelGetPosition(stream);
                double currentSec = Bass.BASS_ChannelBytes2Seconds(stream, pos);

                if (currentSec >= totalSeconds)
                    break;

                int read = Bass.BASS_ChannelGetData(stream, pcmFloat, frameSizeBytes);
                if (read <= 0)
                    break;

                int samplesRead = read / 4;

                for (int i = 0; i < samplesRead; i++)
                {
                    float s = pcmFloat[i];
                    if (s > 1f) s = 1f;
                    if (s < -1f) s = -1f;
                    pcmShort[i] = (short)(s * 32767f);
                }

                for (int i = samplesRead; i < pcmShort.Length; i++)
                    pcmShort[i] = 0;

                if (_opusEncoder != null)
                {
                    int encoded = _opusEncoder.Encode(pcmShort, opusBuf);

                    if (encoded > 0)
                    {
                        byte[] frame = new byte[encoded];
                        Array.Copy(opusBuf, frame, encoded);
                        SendAudioPacket(frame);
                    }
                }

                nextFrameTime = nextFrameTime.AddMilliseconds(frameDurationMs);
                var delay = (int)(nextFrameTime - DateTime.UtcNow).TotalMilliseconds;

                if (delay > 0)
                {
                    try { Task.Delay(delay, ct).Wait(ct); }
                    catch (OperationCanceledException) { break; }
                }
                else if (delay < -frameDurationMs * 2)
                {
                    nextFrameTime = DateTime.UtcNow;
                }
            }
        }
        finally
        {
            Bass.BASS_StreamFree(stream);
            Console.WriteLine($"Track finished: {_currentMetadata?.Title ?? "unknown"}");
        }
    }

    private void SendAudioPacket(byte[] opusFrame)
    {
        var packet = new AudioPacket
        {
            PasswordMD5 = _passwordHash,
            Sequence = _sequence++,
            Timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            Metadata = _metadataSent ? null : _currentMetadata,
            OpusFrame = opusFrame
        };

        _metadataSent = true;

        byte[] data = PacketWriter.WriteAudioFromSource(packet);

        try
        {
            _udp.Send(data, data.Length, _serverEndpoint);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[ERROR] Send failed: {ex.Message}");
        }
    }

    private async Task StatusListenerLoop(CancellationToken ct)
    {
        try
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var result = await _udp.ReceiveAsync(ct);

                    if (result.Buffer.Length > 0 &&
                        PacketReader.GetPacketType(result.Buffer) == PacketTypes.SourceStatus)
                    {
                        var status = PacketReader.ReadSourceStatus(result.Buffer);
                        _lastStatusReceived = DateTime.UtcNow;
                        Console.WriteLine($"[STATUS] Server OK | Listeners: {status.ClientsCount}");
                    }
                }
                catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
                catch (SocketException) { await Task.Delay(1000, ct); }

                var since = (DateTime.UtcNow - _lastStatusReceived).TotalSeconds;
                if (_lastStatusReceived != DateTime.MinValue && since > 30)
                    Console.WriteLine($"[WARN] No status from server for {since:F0}s");
            }
        }
        catch (OperationCanceledException) { }
    }

    private bool InitBass()
    {
        BassNet.Registration("email@example.com", "key");

        if (!Bass.BASS_Init(-1, _config.Opus.SampleRate, BASSInit.BASS_DEVICE_DEFAULT, IntPtr.Zero))
        {
            Console.WriteLine($"BASS_Init error: {Bass.BASS_ErrorGetCode()}");
            return false;
        }
        int fx_ver = BassFx.BASS_FX_GetVersion();
        Console.WriteLine($"[Opus] Version: {OpusNative.opus_get_version_string()}");

        _opusEncoder = new OpusEncoder(
            _config.Opus.SampleRate,
            _config.Opus.Channels,
            OpusApplication.Audio,
            _config.Opus.FrameSize)
        {
            Bitrate = _config.Opus.Bitrate,
            Complexity = _config.Opus.Complexity,
            Vbr = true,
            InbandFec = _config.Opus.PacketLossPercent > 0,
            PacketLossPercent = _config.Opus.PacketLossPercent,
            Dtx = false,
            SignalType = OpusSignal.Music,
            MaxBandwidth = OpusBandwidth.Fullband
        };

        Console.WriteLine(
            $"Opus encoder: {_config.Opus.Bitrate / 1000}kbps, " +
            $"{_config.Opus.Channels}ch, {_config.Opus.FrameSize}ms");

        return true;
    }

    public void Dispose()
    {
        if (!_disposed)
        {
            _disposed = true;
            _playbackCts?.Cancel();
            _playbackCts?.Dispose();
            _opusEncoder?.Dispose();
            _udp?.Dispose();
            Bass.BASS_Free();
        }
    }
}
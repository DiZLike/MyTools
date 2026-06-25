using FrostWire.Core.Configuration;
using FrostWire.Core.Protocol;
using FrostWire.Core.Protocol.Models;
using System.Net;
using System.Net.Sockets;
using Un4seen.Bass;
using Un4seen.Bass.AddOn.Enc;
using Un4seen.Bass.AddOn.EncOpus;
using Un4seen.Bass.AddOn.Opus;

namespace FrostWire.Source;

public class SourceEngine
{
    private readonly AppConfig _config;
    private readonly UdpClient _udp;
    private readonly byte[] _passwordMD5;
    private readonly PlaylistManager _playlist;
    private readonly IPEndPoint _serverEndpoint;

    private uint _sequence;
    private DateTime _lastStatusReceived = DateTime.MinValue;

    public SourceEngine(AppConfig config)
    {
        _config = config;
        _udp = new UdpClient();
        _passwordMD5 = StringToMD5Bytes(config.Source.PasswordMD5);
        _playlist = new PlaylistManager(config.Source.PlaylistPath, config.Source.Shuffle);
        _serverEndpoint = new IPEndPoint(IPAddress.Parse(config.Source.ServerAddress), config.Source.ServerPort);
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
        _ = Task.Run(() => StatusListenerLoop(statusCts.Token), ct);

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

                await PlayTrackAsync(track, ct);
            }
        }
        finally
        {
            statusCts.Cancel();
            Bass.BASS_Free();
            _udp.Close();
        }
    }

    private Task PlayTrackAsync(string filePath, CancellationToken ct)
    {
        var tcs = new TaskCompletionSource();
        var thread = new Thread(() =>
        {
            try
            {
                PlayTrack(filePath, ct);
                tcs.SetResult();
            }
            catch (Exception ex)
            {
                tcs.SetException(ex);
            }
        });
        thread.Start();
        return tcs.Task;
    }

    private byte[] _pendingData = Array.Empty<byte>();
    private bool _metadataSent;
    private TrackMetadata? _currentMetadata;

    private void PlayTrack(string filePath, CancellationToken ct)
    {
        Console.WriteLine($"Loading: {Path.GetFileName(filePath)}");

        _currentMetadata = MetadataExtractor.Extract(filePath);
        Console.WriteLine($"[NOW PLAYING] {_currentMetadata.Artist} - {_currentMetadata.Title} [{_currentMetadata.Duration:F0}s]");

        int stream = Bass.BASS_StreamCreateFile(filePath, 0, 0, BASSFlag.BASS_STREAM_DECODE | BASSFlag.BASS_SAMPLE_FLOAT);
        if (stream == 0)
        {
            Console.WriteLine($"[ERROR] Cannot open file: {filePath} — {Bass.BASS_ErrorGetCode()}");
            return;
        }

        _metadataSent = false;
        _pendingData = Array.Empty<byte>();

        string options = $"--bitrate {_config.Opus.Bitrate / 1000} " +
                         $"--comp {_config.Opus.Complexity} " +
                         $"--framesize {_config.Opus.FrameSize} " +
                         $"--sample-rate {_config.Opus.SampleRate} " +
                         $"--channels {_config.Opus.Channels}";

        var encodeProc = new ENCODEPROC((int handle, int channel, IntPtr buffer, int length, IntPtr user) =>
        {
            if (length <= 0) return;

            byte[] data = new byte[length];
            System.Runtime.InteropServices.Marshal.Copy(buffer, data, 0, length);
            _pendingData = ConcatArrays(_pendingData, data);
        });

        int encoderHandle = BassEnc_Opus.BASS_Encode_OPUS_Start(
            stream,
            options,
            BASSEncode.BASS_ENCODE_AUTOFREE,
            encodeProc,
            IntPtr.Zero);

        if (encoderHandle == 0)
        {
            Console.WriteLine($"[ERROR] Cannot start Opus encoder: {Bass.BASS_ErrorGetCode()}");
            Bass.BASS_StreamFree(stream);
            return;
        }

        Console.WriteLine($"Opus encoder started: {_config.Opus.SampleRate}Hz, {_config.Opus.Channels}ch, {_config.Opus.Bitrate / 1000}kbps");

        try
        {
            while (!ct.IsCancellationRequested)
            {
                // Process encoding
                BassEnc.BASS_Encode_Write(encoderHandle, IntPtr.Zero, 0);

                // Send accumulated data
                if (_pendingData.Length > 0)
                {
                    SendAudioPacket(_pendingData);
                    _pendingData = Array.Empty<byte>();
                }

                // Check if stream still active
                var active = Bass.BASS_ChannelIsActive(stream);
                if (active != BASSActive.BASS_ACTIVE_PLAYING &&
                    active != BASSActive.BASS_ACTIVE_STALLED &&
                    _pendingData.Length == 0)
                    break;

                Thread.Sleep(1);
            }
        }
        finally
        {
            BassEnc.BASS_Encode_Stop(encoderHandle);
        }

        Console.WriteLine($"Track finished: {_currentMetadata.Title}");
    }

    private void SendAudioPacket(byte[] opusFrame)
    {
        var packet = new AudioPacket
        {
            PasswordMD5 = _passwordMD5,
            Sequence = _sequence++,
            Timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            Metadata = _metadataSent ? null : _currentMetadata,
            OpusFrame = opusFrame
        };

        _metadataSent = true;

        byte[] data = PacketWriter.WriteAudioFromSource(packet);
        _udp.Send(data, data.Length, _serverEndpoint);
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

                    if (result.Buffer.Length > 0 && PacketReader.GetPacketType(result.Buffer) == PacketTypes.SourceStatus)
                    {
                        var status = PacketReader.ReadSourceStatus(result.Buffer);
                        _lastStatusReceived = DateTime.UtcNow;
                        Console.WriteLine($"[STATUS] Server OK | Listeners: {status.ClientsCount}");
                    }
                }
                catch (OperationCanceledException) when (ct.IsCancellationRequested)
                {
                    break;
                }
                catch (SocketException)
                {
                    await Task.Delay(1000, ct);
                }

                var since = (DateTime.UtcNow - _lastStatusReceived).TotalSeconds;
                if (_lastStatusReceived != DateTime.MinValue && since > 30)
                {
                    Console.WriteLine($"[WARN] No status from server for {since:F0}s");
                }
            }
        }
        catch (OperationCanceledException) { }
    }

    private bool InitBass()
    {
        if (!Bass.BASS_Init(-1, _config.Opus.SampleRate, BASSInit.BASS_DEVICE_DEFAULT, IntPtr.Zero))
        {
            Console.WriteLine($"BASS_Init error: {Bass.BASS_ErrorGetCode()}");
            return false;
        }

        int opusPlugin = Bass.BASS_PluginLoad("bassopus.dll");
        if (opusPlugin == 0)
            opusPlugin = Bass.BASS_PluginLoad("libbassopus.so");

        if (opusPlugin == 0)
        {
            Console.WriteLine($"[ERROR] Cannot load Opus plugin: {Bass.BASS_ErrorGetCode()}");
            return false;
        }

        Console.WriteLine("Opus plugin loaded");
        return true;
    }

    private static byte[] ConcatArrays(byte[] a, byte[] b)
    {
        byte[] result = new byte[a.Length + b.Length];
        Buffer.BlockCopy(a, 0, result, 0, a.Length);
        Buffer.BlockCopy(b, 0, result, a.Length, b.Length);
        return result;
    }

    private static byte[] StringToMD5Bytes(string hex)
    {
        byte[] bytes = new byte[16];
        for (int i = 0; i < 16; i++)
            bytes[i] = Convert.ToByte(hex.Substring(i * 2, 2), 16);
        return bytes;
    }
}
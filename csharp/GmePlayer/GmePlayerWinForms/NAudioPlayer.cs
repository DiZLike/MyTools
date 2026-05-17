using System;
using NAudio.Wave;
using gmesharp;

namespace GmePlayerWinForms
{
    public class NAudioPlayer : IDisposable
    {
        private readonly GmePlayer _gmePlayer;
        private WaveOut? _outputDevice; // Обычный WaveOut, не Event!
        private BufferedWaveProvider? _bufferedProvider;
        private System.Threading.Timer? _fillTimer;
        private volatile bool _playing;
        private bool _disposed;
        private int _currentTrack;
        private float _volume = 1.0f;
        private readonly object _lock = new object();
        private short[] _readBuffer;

        public event Action<int>? TrackChanged;
        public event Action<bool>? PlaybackChanged;
        public event Action? TrackEnded;

        public bool IsPlaying => _playing;
        public int CurrentTrack => _currentTrack;
        public int TrackCount => _gmePlayer.TrackCount;
        public int SampleRate => _gmePlayer.SampleRate;

        public float Volume
        {
            get => _volume;
            set
            {
                _volume = Math.Clamp(value, 0f, 1f);
                if (_outputDevice != null)
                    _outputDevice.Volume = _volume;
            }
        }

        public NAudioPlayer(GmePlayer player)
        {
            _gmePlayer = player ?? throw new ArgumentNullException(nameof(player));
            // 10мс буфер как в SDL2 (стерео = * 2)
            _readBuffer = new short[SampleRate / 100 * 2];
        }

        public void PlayTrack(int track)
        {
            lock (_lock)
            {
                if (_gmePlayer.TrackCount == 0) return;

                StopInternal();

                _currentTrack = ((track % _gmePlayer.TrackCount) + _gmePlayer.TrackCount) % _gmePlayer.TrackCount;

                _gmePlayer.StartTrack(_currentTrack);

                var info = _gmePlayer.GetTrackInfo(_currentTrack);
                if (info != null)
                {
                    int len = info.Length;
                    if (len <= 0) len = info.IntroLength + info.LoopLength * 2;
                    if (len <= 0) len = (int)(2.5 * 60 * 1000);
                    _gmePlayer.SetFade(len, 8000);
                }

                TrackChanged?.Invoke(_currentTrack);

                // Создаём буферизированный провайдер
                var format = new WaveFormat(SampleRate, 16, 2);
                _bufferedProvider = new BufferedWaveProvider(format)
                {
                    BufferDuration = TimeSpan.FromMilliseconds(500),
                    DiscardOnBufferOverflow = false
                };

                // Используем ОБЫЧНЫЙ WaveOut (не WaveOutEvent!)
                _outputDevice = new WaveOut();
                _outputDevice.Volume = _volume;
                _outputDevice.PlaybackStopped += OnPlaybackStopped;
                _outputDevice.Init(_bufferedProvider);
                _outputDevice.Play();

                _playing = true;
                PlaybackChanged?.Invoke(true);

                // Запускаем таймер заполнения буфера с повышенной частотой
                _fillTimer = new System.Threading.Timer(
                    FillBuffer, null, 0, 10); // Каждые 10мс вместо 20мс
            }
        }

        private void FillBuffer(object? state)
        {
            if (_disposed || _bufferedProvider == null || !_playing)
                return;

            try
            {
                lock (_lock)
                {
                    if (_gmePlayer.TrackEnded)
                    {
                        if (_bufferedProvider.BufferedDuration.TotalMilliseconds < 50)
                        {
                            StopInternal();
                            Task.Run(() => TrackEnded?.Invoke());
                        }
                        return;
                    }

                    // Проверяем сколько места в буфере
                    int bufferedBytes = _bufferedProvider.BufferLength - _bufferedProvider.BufferedBytes;

                    // ИСПРАВЛЕНИЕ: заполняем весь доступный буфер, если он не полный
                    if (bufferedBytes >= _readBuffer.Length * sizeof(short))
                    {
                        // ВСЕ short'ы из буфера (включая оба канала стерео)
                        int samplesToRead = _readBuffer.Length;

                        unsafe
                        {
                            fixed (short* ptr = _readBuffer)
                            {
                                bool ok = _gmePlayer.PlayDirect(ptr, samplesToRead);
                                if (ok)
                                {
                                    byte[] bytes = new byte[_readBuffer.Length * sizeof(short)];
                                    Buffer.BlockCopy(_readBuffer, 0, bytes, 0, bytes.Length);
                                    _bufferedProvider.AddSamples(bytes, 0, bytes.Length);
                                }
                            }
                        }
                    }
                }
            }
            catch
            {
                // Игнорируем ошибки заполнения
            }
        }

        private void OnPlaybackStopped(object? sender, StoppedEventArgs e)
        {
            if (!_disposed)
            {
                _playing = false;
                PlaybackChanged?.Invoke(false);
            }
        }

        public void Pause()
        {
            lock (_lock)
            {
                if (_playing && _outputDevice != null)
                {
                    _outputDevice.Pause();
                    _fillTimer?.Change(Timeout.Infinite, Timeout.Infinite);
                    _playing = false;
                    PlaybackChanged?.Invoke(false);
                }
            }
        }

        public void Resume()
        {
            lock (_lock)
            {
                if (!_playing && _outputDevice != null && !_disposed)
                {
                    _outputDevice.Play();
                    _fillTimer?.Change(0, 10);
                    _playing = true;
                    PlaybackChanged?.Invoke(true);
                }
            }
        }

        public void Next()
        {
            PlayTrack(_currentTrack + 1);
        }

        public void Prev()
        {
            PlayTrack(_currentTrack - 1);
        }

        public void Stop()
        {
            lock (_lock)
            {
                StopInternal();
                if (!_disposed)
                {
                    _playing = false;
                    PlaybackChanged?.Invoke(false);
                }
            }
        }

        private void StopInternal()
        {
            _fillTimer?.Dispose();
            _fillTimer = null;

            if (_outputDevice != null)
            {
                try { _outputDevice.Stop(); } catch { }
                try { _outputDevice.Dispose(); } catch { }
                _outputDevice = null;
            }

            _bufferedProvider = null;
        }

        public GmeTrackInfo? GetTrackInfo(int index)
        {
            try { return _gmePlayer.GetTrackInfo(index); }
            catch { return null; }
        }

        public string GetVoiceName(int index)
        {
            try { return _gmePlayer.GetVoiceName(index) ?? ""; }
            catch { return ""; }
        }

        public void MuteVoice(int index, bool mute)
        {
            try { _gmePlayer.MuteVoice(index, mute); } catch { }
        }

        public void MuteVoices(int mask)
        {
            try { _gmePlayer.MuteVoices(mask); } catch { }
        }

        public void SetTempo(double tempo)
        {
            try { _gmePlayer.SetTempo(tempo); } catch { }
        }

        public void SetStereoDepth(double depth)
        {
            try { _gmePlayer.SetStereoDepth(depth); } catch { }
        }

        public void SetAccuracy(bool enabled)
        {
            try { _gmePlayer.SetAccuracy(enabled); } catch { }
        }

        public void SetEchoDisabled(bool disabled)
        {
            try { _gmePlayer.SetEchoDisabled(disabled); } catch { }
        }

        public int PositionMs
        {
            get
            {
                try { return _gmePlayer.PositionMs; }
                catch { return 0; }
            }
        }

        public int VoiceCount
        {
            get
            {
                try { return _gmePlayer.VoiceCount; }
                catch { return 0; }
            }
        }

        public string EmulatorType
        {
            get
            {
                try { return _gmePlayer.EmulatorType ?? "Unknown"; }
                catch { return "Unknown"; }
            }
        }

        public string Warning
        {
            get
            {
                try { return _gmePlayer.Warning ?? ""; }
                catch { return ""; }
            }
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                _disposed = true;
                lock (_lock)
                {
                    StopInternal();
                }
                _gmePlayer.Dispose();
            }
        }
    }
}

using System;
using System.Threading;
using System.Threading.Tasks;

namespace gmesharp
{
    public enum PlayerState
    {
        Stopped,
        Playing,
        Paused
    }
    public class TrackChangedEventArgs : EventArgs
    {
        public int TrackIndex { get; }
        public GmeTrackInfo TrackInfo { get; }

        public TrackChangedEventArgs(int index, GmeTrackInfo info)
        {
            TrackIndex = index;
            TrackInfo = info;
        }
    }
    public class GmeAudioPlayer : IDisposable
    {
        private readonly GmePlayer _player;
        private readonly int _bufferSizeMs;
        private readonly object _lock = new object();

        private PlayerState _state = PlayerState.Stopped;
        private int _currentTrack = -1;
        private bool _loopTrack;
        private bool _autoAdvance = true;
        private CancellationTokenSource _playbackCts;
        private Task _playbackTask;

        public event EventHandler<TrackChangedEventArgs> TrackChanged;
        public event EventHandler<PlayerState> StateChanged;
        public event EventHandler<string> PlaybackError;
        public event EventHandler TrackEnded;
        public PlayerState State
        {
            get => _state;
            private set
            {
                if (_state != value)
                {
                    _state = value;
                    StateChanged?.Invoke(this, value);
                }
            }
        }

        public int CurrentTrack
        {
            get => _currentTrack;
            private set
            {
                if (_currentTrack != value)
                {
                    _currentTrack = value;
                    var info = GetTrackInfo(value);
                    TrackChanged?.Invoke(this, new TrackChangedEventArgs(value, info));
                }
            }
        }

        public int TrackCount => _player.TrackCount;
        public int SampleRate => _player.SampleRate;
        public int PositionMs => _player.PositionMs;
        public bool TrackEndedFlag => _player.TrackEnded;
        public int VoiceCount => _player.VoiceCount;
        public string EmulatorType => _player.EmulatorType;
        public string Warning => _player.Warning;
        public bool AutoAdvance
        {
            get => _autoAdvance;
            set => _autoAdvance = value;
        }
        public bool LoopTrack
        {
            get => _loopTrack;
            set => _loopTrack = value;
        }
        public float Volume { get; set; } = 1.0f;

        public GmeAudioPlayer(string filePath, int sampleRate = 44100, int bufferSizeMs = 100)
        {
            _player = new GmePlayer(filePath, sampleRate);
            _bufferSizeMs = bufferSizeMs;
        }
        public void Play(int trackIndex = 0)
        {
            lock (_lock)
            {
                StopInternal();

                if (trackIndex < 0 || trackIndex >= TrackCount)
                    throw new ArgumentOutOfRangeException(nameof(trackIndex),
                        $"Track index must be between 0 and {TrackCount - 1}");

                CurrentTrack = trackIndex;
                _player.StartTrack(trackIndex);
                State = PlayerState.Playing;

                _playbackCts = new CancellationTokenSource();
                _playbackTask = Task.Run(() => PlaybackLoop(_playbackCts.Token));
            }
        }
        public void Pause()
        {
            lock (_lock)
            {
                if (State == PlayerState.Playing)
                    State = PlayerState.Paused;
            }
        }
        public void Resume()
        {
            lock (_lock)
            {
                if (State == PlayerState.Paused)
                    State = PlayerState.Playing;
            }
        }
        public void Stop()
        {
            lock (_lock)
            {
                StopInternal();
                State = PlayerState.Stopped;
            }
        }

        private void StopInternal()
        {
            _playbackCts?.Cancel();
            _playbackTask?.Wait(1000);
            _playbackCts?.Dispose();
            _playbackCts = null;
            _playbackTask = null;
        }
        public void NextTrack()
        {
            lock (_lock)
            {
                if (TrackCount == 0) return;

                int nextTrack = (_currentTrack + 1) % TrackCount;
                if (nextTrack == 0 && !_loopTrack && !_autoAdvance)
                {
                    Stop();
                    return;
                }

                bool wasPlaying = State == PlayerState.Playing;
                StopInternal();

                CurrentTrack = nextTrack;
                _player.StartTrack(nextTrack);
                State = wasPlaying ? PlayerState.Playing : PlayerState.Paused;

                if (wasPlaying)
                {
                    _playbackCts = new CancellationTokenSource();
                    _playbackTask = Task.Run(() => PlaybackLoop(_playbackCts.Token));
                }
            }
        }
        public void PreviousTrack()
        {
            lock (_lock)
            {
                if (TrackCount == 0) return;

                int prevTrack = _currentTrack <= 0 ? TrackCount - 1 : _currentTrack - 1;

                bool wasPlaying = State == PlayerState.Playing;
                StopInternal();

                CurrentTrack = prevTrack;
                _player.StartTrack(prevTrack);
                State = wasPlaying ? PlayerState.Playing : PlayerState.Paused;

                if (wasPlaying)
                {
                    _playbackCts = new CancellationTokenSource();
                    _playbackTask = Task.Run(() => PlaybackLoop(_playbackCts.Token));
                }
            }
        }
        public GmeTrackInfo GetTrackInfo(int index)
        {
            return _player.GetTrackInfo(index);
        }
        public string GetVoiceName(int index)
        {
            return _player.GetVoiceName(index);
        }
        public void MuteVoice(int index, bool mute)
        {
            _player.MuteVoice(index, mute);
        }
        public void MuteVoices(int mask)
        {
            _player.MuteVoices(mask);
        }
        public void SetTempo(double tempo)
        {
            _player.SetTempo(tempo);
        }
        public void SetStereoDepth(double depth)
        {
            _player.SetStereoDepth(depth);
        }
        public void SetAccuracy(bool enabled)
        {
            _player.SetAccuracy(enabled);
        }
        public void SetEchoDisabled(bool disabled)
        {
            _player.SetEchoDisabled(disabled);
        }
        public int GenerateAudio(short[] buffer, int offset, int sampleCount)
        {
            if (State != PlayerState.Playing)
            {
                Array.Clear(buffer, offset, sampleCount * 2);
                return 0;
            }

            unsafe
            {
                fixed (short* ptr = &buffer[offset])
                {
                    bool ok = _player.PlayDirect(ptr, sampleCount);
                    if (!ok)
                    {
                        Array.Clear(buffer, offset, sampleCount * 2);
                        return -1;
                    }
                }
            }

            if (Volume < 1.0f)
            {
                for (int i = 0; i < sampleCount * 2; i++)
                {
                    buffer[offset + i] = (short)(buffer[offset + i] * Volume);
                }
            }

            return sampleCount;
        }
        public int GetBufferSizeInSamples()
        {
            return SampleRate * _bufferSizeMs / 1000;
        }

        private void PlaybackLoop(CancellationToken token)
        {
            try
            {
                while (!token.IsCancellationRequested)
                {
                    if (State == PlayerState.Paused)
                    {
                        Thread.Sleep(10);
                        continue;
                    }

                    // Ждём окончания трека или паузы
                    if (_player.TrackEnded)
                    {
                        TrackEnded?.Invoke(this, EventArgs.Empty);

                        if (_loopTrack)
                        {
                            _player.StartTrack(_currentTrack);
                            continue;
                        }

                        if (_autoAdvance && _currentTrack < TrackCount - 1)
                        {
                            CurrentTrack++;
                            _player.StartTrack(_currentTrack);
                            continue;
                        }

                        Stop();
                        return;
                    }

                    Thread.Sleep(10);
                }
            }
            catch (Exception ex)
            {
                PlaybackError?.Invoke(this, ex.Message);
            }
        }
        public void Dispose()
        {
            Stop();
            _player?.Dispose();
            _playbackCts?.Dispose();
        }
    }
}
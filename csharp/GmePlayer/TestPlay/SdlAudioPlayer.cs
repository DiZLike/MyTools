using System;
using System.Runtime.InteropServices;
using SDL2;

namespace TestPlay
{
    public class SdlAudioPlayer : IDisposable
    {
        private readonly gmesharp.GmePlayer _gmePlayer;
        private readonly short[] _buf;
        private GCHandle _bufHandle;
        private volatile bool _playing;
        private bool _disposed;
        private bool _audioOpen;
        private const int FillRate = 80;
        private readonly int _bufSamples;

        public event Action<int> TrackChanged;
        public event Action<bool> PlaybackChanged;
        public event Action<short[], int> ScopeData;

        public bool IsPlaying => _playing;
        public int CurrentTrack { get; private set; }
        public int SampleRate => _gmePlayer.SampleRate;

        public SdlAudioPlayer(gmesharp.GmePlayer player)
        {
            _gmePlayer = player;
            int minSize = player.SampleRate * 2 / FillRate;
            _bufSamples = 512;
            while (_bufSamples < minSize) _bufSamples *= 2;
            _buf = new short[_bufSamples * 2];
            _bufHandle = GCHandle.Alloc(_buf, GCHandleType.Pinned);

            // Открываем аудио один раз при создании
            OpenAudio();
        }

        private unsafe void OpenAudio()
        {
            SDL.SDL_AudioSpec desired = new SDL.SDL_AudioSpec
            {
                freq = SampleRate,
                format = SDL.AUDIO_S16SYS,
                channels = 2,
                samples = (ushort)_bufSamples,
                callback = Callback,
                userdata = IntPtr.Zero
            };

            if (SDL.SDL_OpenAudio(ref desired, IntPtr.Zero) < 0)
                throw new Exception($"SDL error: {SDL.SDL_GetError()}");

            _audioOpen = true;
        }

        public void PlayTrack(int track)
        {
            // Как в оригинале: останавливаем звук, НО НЕ закрываем устройство
            if (_playing)
            {
                SDL.SDL_PauseAudio(1);
                SDL.SDL_LockAudio();
                SDL.SDL_UnlockAudio();
                _playing = false;
            }

            CurrentTrack = (track + _gmePlayer.TrackCount) % _gmePlayer.TrackCount;

            // Запускаем трек пока звук остановлен
            _gmePlayer.StartTrack(CurrentTrack);

            var info = _gmePlayer.GetTrackInfo(CurrentTrack);
            if (info != null)
            {
                int len = info.Length;
                if (len <= 0) len = info.IntroLength + info.LoopLength * 2;
                if (len <= 0) len = (int)(2.5 * 60 * 1000);
                _gmePlayer.SetFade(len, 8000);
            }

            TrackChanged?.Invoke(CurrentTrack);

            // Очищаем буфер перед стартом
            Array.Clear(_buf, 0, _buf.Length);

            // Запускаем звук (как в оригинале)
            _playing = true;
            PlaybackChanged?.Invoke(true);
            SDL.SDL_PauseAudio(0);
        }

        private unsafe void Callback(IntPtr userdata, IntPtr stream, int len)
        {
            if (!_playing || _gmePlayer == null || _gmePlayer.TrackEnded)
            {
                var p = (byte*)stream.ToPointer();
                for (int i = 0; i < len; i++) p[i] = 0;
                return;
            }

            int shortCount = len / sizeof(short);

            fixed (short* bufPtr = _buf)
            {
                bool ok = _gmePlayer.PlayDirect(bufPtr, shortCount);
                if (!ok)
                {
                    var p = (byte*)stream.ToPointer();
                    for (int i = 0; i < len; i++) p[i] = 0;
                    return;
                }
            }

            Marshal.Copy(_buf, 0, stream, shortCount);
            ScopeData?.Invoke(_buf, shortCount);
        }

        public void Pause()
        {
            if (_playing)
            {
                SDL.SDL_PauseAudio(1);
                SDL.SDL_LockAudio();
                SDL.SDL_UnlockAudio();
                _playing = false;
                PlaybackChanged?.Invoke(false);
            }
        }

        public void Resume()
        {
            if (!_playing && _audioOpen)
            {
                Array.Clear(_buf, 0, _buf.Length);
                _playing = true;
                PlaybackChanged?.Invoke(true);
                SDL.SDL_PauseAudio(0);
            }
        }

        public void Next() => PlayTrack(CurrentTrack + 1);
        public void Prev() => PlayTrack(CurrentTrack - 1);

        public void Stop()
        {
            if (_playing)
            {
                SDL.SDL_PauseAudio(1);
                SDL.SDL_LockAudio();
                SDL.SDL_UnlockAudio();
                _playing = false;
            }
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                _disposed = true;
                if (_playing)
                {
                    SDL.SDL_PauseAudio(1);
                    SDL.SDL_LockAudio();
                    SDL.SDL_UnlockAudio();
                }
                if (_audioOpen)
                {
                    SDL.SDL_CloseAudio();
                    _audioOpen = false;
                }
                if (_bufHandle.IsAllocated) _bufHandle.Free();
            }
        }
    }
}
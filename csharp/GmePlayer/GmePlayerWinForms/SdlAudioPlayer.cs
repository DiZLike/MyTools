using System;
using System.Runtime.InteropServices;
using SDL2;
using gmesharp;

namespace GmePlayerWinForms
{
    public class SdlAudioPlayer : IDisposable
    {
        private readonly GmePlayer _gmePlayer;
        private readonly short[] _buf;
        private GCHandle _bufHandle;
        private volatile bool _playing;
        private bool _disposed;
        private bool _audioOpen;
        private const int FillRate = 80;
        private readonly int _bufSamples;
        private int _currentTrack;

        // Важно: сохраняем делегат как поле класса
        private SDL.SDL_AudioCallback _callbackDelegate;

        public event Action<int>? TrackChanged;
        public event Action<bool>? PlaybackChanged;
        public event Action<short[], int>? ScopeData;
        public event Action? TrackEnded;

        public bool IsPlaying => _playing;
        public int CurrentTrack => _currentTrack;
        public int TrackCount => _gmePlayer.TrackCount;
        public int SampleRate => _gmePlayer.SampleRate;

        public SdlAudioPlayer(GmePlayer player)
        {
            _gmePlayer = player ?? throw new ArgumentNullException(nameof(player));

            int minSize = player.SampleRate * 2 / FillRate;
            _bufSamples = 512;
            while (_bufSamples < minSize) _bufSamples *= 2;
            _buf = new short[_bufSamples * 2];
            _bufHandle = GCHandle.Alloc(_buf, GCHandleType.Pinned);

            // Сохраняем делегат как поле класса
            _callbackDelegate = AudioCallback;

            OpenAudio();
        }

        private void OpenAudio()
        {
            SDL.SDL_AudioSpec desired = new SDL.SDL_AudioSpec
            {
                freq = SampleRate,
                format = SDL.AUDIO_S16SYS,
                channels = 2,
                samples = (ushort)_bufSamples,
                callback = _callbackDelegate,
                userdata = IntPtr.Zero
            };

            if (SDL.SDL_OpenAudio(ref desired, IntPtr.Zero) < 0)
                throw new Exception($"SDL error: {SDL.SDL_GetError()}");

            _audioOpen = true;
        }

        private void AudioCallback(IntPtr userdata, IntPtr stream, int len)
        {
            try
            {
                if (!_playing || _gmePlayer == null || _disposed)
                {
                    FillSilence(stream, len);
                    return;
                }

                // Проверяем окончание трека ВНЕ блока fixed
                if (_gmePlayer.TrackEnded)
                {
                    FillSilence(stream, len);

                    // Асинхронно уведомляем об окончании
                    ThreadPool.QueueUserWorkItem(_ => TrackEnded?.Invoke());
                    return;
                }

                int shortCount = len / sizeof(short);

                // Ограничиваем количество сэмплов размером буфера
                if (shortCount > _buf.Length)
                    shortCount = _buf.Length;

                // Генерируем аудио в буфер
                bool ok = false;
                unsafe
                {
                    fixed (short* bufPtr = _buf)
                    {
                        try
                        {
                            ok = _gmePlayer.PlayDirect(bufPtr, shortCount);
                        }
                        catch
                        {
                            ok = false;
                        }
                    }
                }

                if (!ok)
                {
                    FillSilence(stream, len);
                    return;
                }

                // Копируем данные в выходной поток
                Marshal.Copy(_buf, 0, stream, shortCount);

                // Вызываем событие скопа если нужно
                if (ScopeData != null)
                {
                    ThreadPool.QueueUserWorkItem(_ => ScopeData?.Invoke(_buf, shortCount));
                }
            }
            catch
            {
                // В случае любой ошибки - тишина
                FillSilence(stream, len);
            }
        }

        private void FillSilence(IntPtr stream, int len)
        {
            try
            {
                unsafe
                {
                    byte* p = (byte*)stream.ToPointer();
                    for (int i = 0; i < len; i++)
                        p[i] = 0;
                }
            }
            catch
            {
                // Альтернативный способ очистки без unsafe
                byte[] silence = new byte[len];
                Marshal.Copy(silence, 0, stream, len);
            }
        }

        public void PlayTrack(int track)
        {
            if (_gmePlayer.TrackCount == 0) return;

            // Останавливаем текущее воспроизведение
            if (_playing)
            {
                SDL.SDL_PauseAudio(1);
                _playing = false;
                // Небольшая задержка чтобы колбэк завершился
                Thread.Sleep(50);
            }

            _currentTrack = ((track % _gmePlayer.TrackCount) + _gmePlayer.TrackCount) % _gmePlayer.TrackCount;

            // Запускаем трек пока звук остановлен
            try
            {
                _gmePlayer.StartTrack(_currentTrack);
            }
            catch
            {
                return;
            }

            // Настраиваем затухание
            var info = _gmePlayer.GetTrackInfo(_currentTrack);
            if (info != null)
            {
                int len = info.Length;
                if (len <= 0) len = info.IntroLength + info.LoopLength * 2;
                if (len <= 0) len = (int)(2.5 * 60 * 1000);
                try
                {
                    _gmePlayer.SetFade(len, 8000);
                }
                catch
                {
                    // Игнорируем ошибки fade
                }
            }

            TrackChanged?.Invoke(_currentTrack);

            // Очищаем буфер перед стартом
            Array.Clear(_buf, 0, _buf.Length);

            // Запускаем звук
            _playing = true;
            PlaybackChanged?.Invoke(true);
            SDL.SDL_PauseAudio(0);
        }

        public void Pause()
        {
            if (_playing)
            {
                SDL.SDL_PauseAudio(1);
                _playing = false;
                PlaybackChanged?.Invoke(false);
                // Небольшая задержка для завершения колбэка
                Thread.Sleep(10);
            }
        }

        public void Resume()
        {
            if (!_playing && _audioOpen && !_disposed)
            {
                Array.Clear(_buf, 0, _buf.Length);
                _playing = true;
                PlaybackChanged?.Invoke(true);
                SDL.SDL_PauseAudio(0);
            }
        }

        public void Next() => PlayTrack(_currentTrack + 1);
        public void Prev() => PlayTrack(_currentTrack - 1);

        public void Stop()
        {
            if (_playing)
            {
                SDL.SDL_PauseAudio(1);
                _playing = false;
                Thread.Sleep(10);
            }
        }

        public GmeTrackInfo? GetTrackInfo(int index)
        {
            try
            {
                return _gmePlayer.GetTrackInfo(index);
            }
            catch
            {
                return null;
            }
        }

        public string GetVoiceName(int index)
        {
            try
            {
                return _gmePlayer.GetVoiceName(index) ?? "";
            }
            catch
            {
                return "";
            }
        }

        public void MuteVoice(int index, bool mute)
        {
            try
            {
                _gmePlayer.MuteVoice(index, mute);
            }
            catch { }
        }

        public void MuteVoices(int mask)
        {
            try
            {
                _gmePlayer.MuteVoices(mask);
            }
            catch { }
        }

        public void SetTempo(double tempo)
        {
            try
            {
                _gmePlayer.SetTempo(tempo);
            }
            catch { }
        }

        public void SetStereoDepth(double depth)
        {
            try
            {
                _gmePlayer.SetStereoDepth(depth);
            }
            catch { }
        }

        public void SetAccuracy(bool enabled)
        {
            try
            {
                _gmePlayer.SetAccuracy(enabled);
            }
            catch { }
        }

        public void SetEchoDisabled(bool disabled)
        {
            try
            {
                _gmePlayer.SetEchoDisabled(disabled);
            }
            catch { }
        }

        public int PositionMs
        {
            get
            {
                try
                {
                    return _gmePlayer.PositionMs;
                }
                catch
                {
                    return 0;
                }
            }
        }

        public int VoiceCount
        {
            get
            {
                try
                {
                    return _gmePlayer.VoiceCount;
                }
                catch
                {
                    return 0;
                }
            }
        }

        public string EmulatorType
        {
            get
            {
                try
                {
                    return _gmePlayer.EmulatorType ?? "Unknown";
                }
                catch
                {
                    return "Unknown";
                }
            }
        }

        public string Warning
        {
            get
            {
                try
                {
                    return _gmePlayer.Warning ?? "";
                }
                catch
                {
                    return "";
                }
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
                    _playing = false;
                    Thread.Sleep(50); // Ждём завершения колбэка
                }

                if (_audioOpen)
                {
                    SDL.SDL_CloseAudio();
                    _audioOpen = false;
                }

                if (_bufHandle.IsAllocated)
                    _bufHandle.Free();

                _gmePlayer.Dispose();

                // Очищаем делегат
                _callbackDelegate = null;
            }
        }
    }
}
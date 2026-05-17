using System;
using System.Runtime.InteropServices;
using Un4seen.Bass;
using gmesharp;

namespace GmePlayerWinForms
{
    public class GmeBassStream : IDisposable
    {
        private readonly GmeAudioPlayer _player;
        private int _streamHandle;
        private STREAMPROC _streamCallback;
        private GCHandle _gcHandle; // Защита от сборщика мусора
        private float _volume = 1.0f;
        private bool _disposed;
        private readonly object _lockObject = new object();

        public int StreamHandle => _streamHandle;
        public GmeAudioPlayer Player => _player;

        public float Volume
        {
            get => _volume;
            set
            {
                _volume = Math.Clamp(value, 0f, 1f);
                if (_streamHandle != 0)
                {
                    Bass.BASS_ChannelSetAttribute(_streamHandle,
                        BASSAttribute.BASS_ATTRIB_VOL, _volume);
                }
            }
        }

        public GmeBassStream(GmeAudioPlayer player)
        {
            _player = player ?? throw new ArgumentNullException(nameof(player));

            // Инициализируем Bass только если еще не инициализирован
            if (Bass.BASS_GetDevice() == -1)
            {
                if (!Bass.BASS_Init(-1, _player.SampleRate,
                    BASSInit.BASS_DEVICE_DEFAULT, IntPtr.Zero))
                {
                    throw new InvalidOperationException(
                        $"BASS_Init failed: {Bass.BASS_ErrorGetCode()}");
                }
            }

            // Фиксируем объект в памяти чтобы GC не сбросил делегат
            _gcHandle = GCHandle.Alloc(this, GCHandleType.Normal);
        }

        private unsafe int StreamCallback(int handle, IntPtr buffer, int length, IntPtr user)
        {
            try
            {
                if (_player == null || _disposed)
                {
                    // Заполняем тишиной
                    ClearBuffer(buffer, length);
                    return (int)BASSStreamProc.BASS_STREAMPROC_END;
                }

                // Проверяем состояние плеера БЕЗ блокировки
                if (_player.State != PlayerState.Playing)
                {
                    ClearBuffer(buffer, length);
                    return length; // Возвращаем тишину но не останавливаем поток
                }

                // Вычисляем количество сэмплов (стерео 16-бит)
                int sampleCount = length / 4;

                // Используем фиксированный буфер для избежания аллокаций
                short[] tempBuffer = new short[sampleCount * 2];
                int generated = 0;

                // Вызываем генерацию аудио
                generated = _player.GenerateAudio(tempBuffer, 0, sampleCount);

                if (generated <= 0)
                {
                    ClearBuffer(buffer, length);

                    // Если трек закончился - сигнализируем об окончании
                    if (_player.TrackEndedFlag)
                    {
                        return (int)BASSStreamProc.BASS_STREAMPROC_END;
                    }
                    return length;
                }

                // Копируем данные в unmanaged буфер с применением громкости
                short* destPtr = (short*)buffer;
                for (int i = 0; i < generated * 2; i++)
                {
                    destPtr[i] = _volume < 1.0f
                        ? (short)(tempBuffer[i] * _volume)
                        : tempBuffer[i];
                }

                return length;
            }
            catch (Exception)
            {
                // В случае любой ошибки - тишина и продолжение
                ClearBuffer(buffer, length);
                return length;
            }
        }

        private void ClearBuffer(IntPtr buffer, int length)
        {
            // Быстрая очистка буфера
            unsafe
            {
                byte* ptr = (byte*)buffer;
                for (int i = 0; i < length; i++)
                    ptr[i] = 0;
            }
        }

        public void CreateStream()
        {
            lock (_lockObject)
            {
                if (_streamHandle != 0)
                {
                    Bass.BASS_StreamFree(_streamHandle);
                    _streamHandle = 0;
                }

                // Создаем делегат и сохраняем его
                _streamCallback = new STREAMPROC(StreamCallback);

                _streamHandle = Bass.BASS_StreamCreate(
                    _player.SampleRate,
                    2, // стерео
                    BASSFlag.BASS_DEFAULT,
                    _streamCallback,
                    IntPtr.Zero
                );

                if (_streamHandle == 0)
                {
                    throw new InvalidOperationException(
                        $"BASS_StreamCreate failed: {Bass.BASS_ErrorGetCode()}");
                }

                Volume = _volume;
            }
        }

        public void Play(bool restart = false)
        {
            lock (_lockObject)
            {
                if (_streamHandle == 0)
                    CreateStream();

                if (!Bass.BASS_ChannelPlay(_streamHandle, restart))
                {
                    var error = Bass.BASS_ErrorGetCode();
                    // Если ошибка - пробуем пересоздать поток
                    if (error != BASSError.BASS_OK)
                    {
                        CreateStream();
                        Bass.BASS_ChannelPlay(_streamHandle, false);
                    }
                }
            }
        }

        public void Pause()
        {
            lock (_lockObject)
            {
                if (_streamHandle != 0)
                    Bass.BASS_ChannelPause(_streamHandle);
            }
        }

        public void Resume()
        {
            lock (_lockObject)
            {
                if (_streamHandle != 0)
                    Bass.BASS_ChannelPlay(_streamHandle, false);
            }
        }

        public void Stop()
        {
            lock (_lockObject)
            {
                if (_streamHandle != 0)
                {
                    Bass.BASS_ChannelStop(_streamHandle);
                    Bass.BASS_StreamFree(_streamHandle);
                    _streamHandle = 0;
                }
            }
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                lock (_lockObject)
                {
                    Stop();
                    _streamCallback = null;
                    _disposed = true;
                }

                if (_gcHandle.IsAllocated)
                    _gcHandle.Free();
            }
            GC.SuppressFinalize(this);
        }
    }
}
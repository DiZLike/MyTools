using System;
using System.Runtime.InteropServices;
using Un4seen.Bass;
using BrickwallCompressor.Core;

namespace BrickwallCompressor.Audio
{
    public class AudioEngine : IDisposable
    {
        private int _streamHandle;
        private DSPPROC _dspCallback;
        private CompressorPipeline _pipeline;
        private bool _initialized;

        public CompressorPipeline Pipeline => _pipeline;
        public bool IsPlaying { get; private set; }

        public AudioEngine()
        {
            _pipeline = new CompressorPipeline();
        }

        public bool Initialize(IntPtr windowHandle)
        {
            if (_initialized) return true;

            // BassNet.Registration — обязательный вызов перед Init
            BassNet.Registration("ваш_email@example.com", "ваш_ключ_2.4");

            if (!Bass.BASS_Init(-1, 44100, BASSInit.BASS_DEVICE_DEFAULT, windowHandle))
                throw new Exception("Не удалось инициализировать BASS: " + Bass.BASS_ErrorGetCode());

            Bass.BASS_SetConfig(BASSConfig.BASS_CONFIG_UPDATEPERIOD, 50);
            _initialized = true;
            return true;
        }

        public void LoadFile(string filePath)
        {
            Stop();

            _streamHandle = Bass.BASS_StreamCreateFile(filePath, 0, 0,
                BASSFlag.BASS_STREAM_DECODE | BASSFlag.BASS_SAMPLE_FLOAT);

            if (_streamHandle == 0)
                throw new Exception("Не удалось загрузить файл: " + Bass.BASS_ErrorGetCode());

            // Получаем частоту дискретизации файла
            var info = Bass.BASS_ChannelGetInfo(_streamHandle);
            _pipeline.SetSampleRate(info.freq);

            // Создаём новый поток с DSP (не decode)
            int newStream = Bass.BASS_StreamCreateFile(filePath, 0, 0,
                BASSFlag.BASS_SAMPLE_FLOAT | BASSFlag.BASS_STREAM_AUTOFREE);

            if (newStream == 0)
                throw new Exception("Ошибка создания выходного потока: " + Bass.BASS_ErrorGetCode());

            // Освобождаем decode-поток
            Bass.BASS_StreamFree(_streamHandle);
            _streamHandle = newStream;

            // Вешаем DSP
            _dspCallback = new DSPPROC(DspCallback);
            Bass.BASS_ChannelSetDSP(_streamHandle, _dspCallback, IntPtr.Zero, 0);

            Play();
        }

        private unsafe void DspCallback(int handle, int channel, IntPtr buffer, int length, IntPtr user)
        {
            float* data = (float*)buffer;
            int sampleCount = length / sizeof(float);

            for (int i = 0; i < sampleCount; i++)
            {
                data[i] = _pipeline.Process(data[i]);
            }
        }

        public void Play()
        {
            if (_streamHandle != 0)
            {
                Bass.BASS_ChannelPlay(_streamHandle, false);
                IsPlaying = true;
            }
        }

        public void Pause()
        {
            if (_streamHandle != 0)
            {
                Bass.BASS_ChannelPause(_streamHandle);
                IsPlaying = false;
            }
        }

        public void Stop()
        {
            if (_streamHandle != 0)
            {
                Bass.BASS_ChannelStop(_streamHandle);
                Bass.BASS_StreamFree(_streamHandle);
                _streamHandle = 0;
                IsPlaying = false;
                _pipeline.Reset();
            }
        }

        public double GetPosition()
        {
            if (_streamHandle == 0) return 0;
            long pos = Bass.BASS_ChannelGetPosition(_streamHandle);
            return Bass.BASS_ChannelBytes2Seconds(_streamHandle, pos);
        }

        public double GetLength()
        {
            if (_streamHandle == 0) return 0;
            long len = Bass.BASS_ChannelGetLength(_streamHandle);
            return Bass.BASS_ChannelBytes2Seconds(_streamHandle, len);
        }

        public void Dispose()
        {
            Stop();
            Bass.BASS_Free();
        }
    }
}
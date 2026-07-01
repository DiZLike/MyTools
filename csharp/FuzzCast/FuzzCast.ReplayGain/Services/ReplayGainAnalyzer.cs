using FuzzCast.ReplayGain.Models;
using Un4seen.Bass;

namespace FuzzCast.ReplayGain.Services;

public class ReplayGainAnalyzer
{
    private readonly double _referenceLevel;
    private readonly double _preAmp;

    public ReplayGainAnalyzer(double referenceLevel, double preAmp)
    {
        _referenceLevel = referenceLevel;
        _preAmp = preAmp;
    }

    public ReplayGainResult Analyze(string filePath)
    {
        // Создаём декодер на исходной частоте
        int stream = Bass.BASS_StreamCreateFile(filePath, 0, 0,
            BASSFlag.BASS_STREAM_DECODE | BASSFlag.BASS_SAMPLE_FLOAT);

        if (stream == 0)
        {
            return ReplayGainResult.Fail($"Не удалось открыть файл: {Bass.BASS_ErrorGetCode()}");
        }

        try
        {
            BASS_CHANNELINFO info = Bass.BASS_ChannelGetInfo(stream);
            int channels = info.chans;
            int sampleRate = info.freq;

            // Если частота не 48 kHz — ресемплим
            int processStream = stream;

            if (sampleRate != 48000)
            {
                processStream = Bass.BASS_StreamCreate(48000, channels,
                    BASSFlag.BASS_STREAM_DECODE | BASSFlag.BASS_SAMPLE_FLOAT,
                    BASSStreamProc.STREAMPROC_PUSH);

                Bass.BASS_ChannelSetPosition(stream, 0);

                byte[] resampleBuffer = new byte[65536];
                while (true)
                {
                    int len = Bass.BASS_ChannelGetData(stream, resampleBuffer, resampleBuffer.Length);
                    if (len <= 0) break;
                    Bass.BASS_StreamPutData(processStream, resampleBuffer, len);
                }
                Bass.BASS_StreamPutData(processStream, IntPtr.Zero, (int)BASSStreamProc.BASS_STREAMPROC_END);
                Bass.BASS_ChannelSetPosition(processStream, 0);
            }

            try
            {
                var kFilter = new KWeightingFilter();

                const int BUFFER_FRAMES = 16384;
                int bufferSize = BUFFER_FRAMES * channels;
                float[] buffer = new float[bufferSize];

                double sumSqL = 0.0;
                double sumSqR = 0.0;
                double sumSqLFiltered = 0.0;
                double sumSqRFiltered = 0.0;
                long processedFrames = 0;

                // Проход 1: считаем RMS с фильтром (для Gain) и без фильтра (для тегов)
                while (true)
                {
                    int bytesRead = Bass.BASS_ChannelGetData(processStream, buffer, bufferSize * sizeof(float));
                    if (bytesRead <= 0) break;

                    int samplesRead = bytesRead / sizeof(float);
                    int framesRead = samplesRead / channels;

                    for (int i = 0; i < framesRead; i++)
                    {
                        int idx = i * channels;
                        float sampleL = buffer[idx];
                        float sampleR = channels > 1 ? buffer[idx + 1] : sampleL;

                        // RMS без фильтра (для компрессора)
                        sumSqL += sampleL * sampleL;
                        sumSqR += sampleR * sampleR;

                        // RMS с фильтром (для ReplayGain)
                        double filteredL = kFilter.ProcessLeft(sampleL);
                        double filteredR = kFilter.ProcessRight(sampleR);

                        sumSqLFiltered += filteredL * filteredL;
                        sumSqRFiltered += filteredR * filteredR;
                    }

                    processedFrames += framesRead;
                }

                if (processedFrames == 0)
                    return ReplayGainResult.Fail("Не удалось прочитать сэмплы");

                // Вычисляем Gain по фильтрованному RMS
                double rmsFiltered = Math.Sqrt((sumSqLFiltered + sumSqRFiltered) / (processedFrames * 2.0));

                if (rmsFiltered < 1e-10)
                    return ReplayGainResult.Fail("Сигнал слишком тихий");

                double refRms = Math.Pow(10.0, _referenceLevel / 20.0);
                double gain = 10.0 * Math.Log10((refRms * refRms) / (rmsFiltered * rmsFiltered)) + _preAmp;

                // Проход 2: считаем пики по оригинальному сигналу
                Bass.BASS_ChannelSetPosition(stream, 0);
                double peakL = 0.0;
                double peakR = 0.0;
                const int PEAK_BUFFER = 4096;
                float[] peakBuffer = new float[PEAK_BUFFER * channels];

                while (true)
                {
                    int bytesRead = Bass.BASS_ChannelGetData(stream, peakBuffer,
                        PEAK_BUFFER * channels * sizeof(float));
                    if (bytesRead <= 0) break;

                    int samplesRead = bytesRead / sizeof(float);
                    int framesRead = samplesRead / channels;

                    for (int i = 0; i < framesRead; i++)
                    {
                        int idx = i * channels;
                        double absL = Math.Abs(peakBuffer[idx]);
                        double absR = Math.Abs(channels > 1 ? peakBuffer[idx + 1] : peakBuffer[idx]);

                        if (absL > peakL) peakL = absL;
                        if (absR > peakR) peakR = absR;
                    }
                }

                double peak = Math.Max(peakL, peakR);

                return new ReplayGainResult
                {
                    Success = true,
                    RmsLeft = Math.Sqrt(sumSqL / processedFrames),
                    RmsRight = Math.Sqrt(sumSqR / processedFrames),
                    PeakLeft = peakL,
                    PeakRight = peakR,
                    TrackGain = Math.Round(gain, 2),
                    TrackPeak = Math.Round(peak, 6)
                };
            }
            finally
            {
                if (processStream != stream)
                    Bass.BASS_StreamFree(processStream);
            }
        }
        finally
        {
            Bass.BASS_StreamFree(stream);
        }
    }
}
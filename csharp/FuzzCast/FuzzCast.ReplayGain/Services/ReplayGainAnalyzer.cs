using FuzzCast.ReplayGain.Models;
using Un4seen.Bass;

namespace FuzzCast.ReplayGain.Services;

public class ReplayGainAnalyzer
{
    private readonly double _referenceLevel;
    private readonly double _preAmp;

    // Частоты кроссоверов для трёхполосного анализа
    private const double CrossoverLowFreq = 200.0;
    private const double CrossoverHighFreq = 2000.0;
    private const int AnalysisSampleRate = 48000;

    public ReplayGainAnalyzer(double referenceLevel, double preAmp)
    {
        _referenceLevel = referenceLevel;
        _preAmp = preAmp;
    }

    public ReplayGainResult Analyze(string filePath)
    {
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

            int processStream = stream;

            if (sampleRate != AnalysisSampleRate)
            {
                processStream = Bass.BASS_StreamCreate(AnalysisSampleRate, channels,
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

                // Фильтры для трёхполосного анализа
                var lowpass = new DoubleLinkwitzRileyFilter(AnalysisSampleRate, CrossoverLowFreq, FilterType.LowPass);
                var bandpassLow = new DoubleLinkwitzRileyFilter(AnalysisSampleRate, CrossoverLowFreq, FilterType.HighPass);
                var bandpassHigh = new DoubleLinkwitzRileyFilter(AnalysisSampleRate, CrossoverHighFreq, FilterType.LowPass);
                var highpass = new DoubleLinkwitzRileyFilter(AnalysisSampleRate, CrossoverHighFreq, FilterType.HighPass);

                const int BUFFER_FRAMES = 16384;
                int bufferSize = BUFFER_FRAMES * channels;
                float[] buffer = new float[bufferSize];

                // Аккумуляторы для общего RMS
                double sumSqL = 0.0;
                double sumSqR = 0.0;
                double sumSqLFiltered = 0.0;
                double sumSqRFiltered = 0.0;

                // Аккумуляторы для RMS по полосам
                double sumSqLow = 0.0;
                double sumSqMid = 0.0;
                double sumSqHigh = 0.0;

                long processedFrames = 0;

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

                        // Общий RMS без фильтра
                        sumSqL += sampleL * sampleL;
                        sumSqR += sampleR * sampleR;

                        // Общий RMS с K-weighting (для Gain)
                        double filteredL = kFilter.ProcessLeft(sampleL);
                        double filteredR = kFilter.ProcessRight(sampleR);
                        sumSqLFiltered += filteredL * filteredL;
                        sumSqRFiltered += filteredR * filteredR;

                        // Трёхполосный RMS (без K-weighting, как в компрессоре)
                        // Сигнал преобразуем в double для фильтров
                        double dSampleL = sampleL;
                        double dSampleR = sampleR;

                        // Разделяем на полосы (лево + право -> среднее)
                        double lowL = lowpass.Process(dSampleL);
                        double lowR = lowpass.Process(dSampleR);
                        sumSqLow += (lowL * lowL + lowR * lowR) / 2.0;

                        double bandL = bandpassHigh.Process(bandpassLow.Process(dSampleL));
                        double bandR = bandpassHigh.Process(bandpassLow.Process(dSampleR));
                        sumSqMid += (bandL * bandL + bandR * bandR) / 2.0;

                        double highL = highpass.Process(dSampleL);
                        double highR = highpass.Process(dSampleR);
                        sumSqHigh += (highL * highL + highR * highR) / 2.0;
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

                // Вычисляем RMS по полосам (среднее между каналами, делим на количество фреймов)
                double rmsLow = Math.Sqrt(sumSqLow / processedFrames);
                double rmsMid = Math.Sqrt(sumSqMid / processedFrames);
                double rmsHigh = Math.Sqrt(sumSqHigh / processedFrames);

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
                    TrackPeak = Math.Round(peak, 6),
                    RmsLow = rmsLow,
                    RmsMid = rmsMid,
                    RmsHigh = rmsHigh
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
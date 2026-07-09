using FuzzCast.Core.Configuration;
using FuzzCast.Fx.Trinity.Compressors;
using FuzzCast.Fx.Trinity.Pipeline;

namespace FuzzCast.Source.Audio;

public class CompressorProcessor
{
    private CompressorPipeline? _pipeline;
    private int _sampleRate;
    private bool _initialized;

    public void Initialize(int sampleRate, CompressorPipelineConfig config)
    {
        _sampleRate = sampleRate;
        _pipeline = new CompressorPipeline(sampleRate);

        // Применяем лимитер
        _pipeline.ThreeBand.Limiter.Ceiling = config.Limiter.Ceiling;
        _pipeline.ThreeBand.Limiter.LookaheadMs = config.Limiter.LookaheadMs;
        _pipeline.ThreeBand.Limiter.AttackMs = config.Limiter.AttackMs;
        _pipeline.ThreeBand.Limiter.ReleaseMs = config.Limiter.ReleaseMs;

        _initialized = true;

        Console.WriteLine(
            $"[CompressorPipeline] Initialized | " +
            $"Limiter ceiling: {config.Limiter.Ceiling:F1}dB");
    }

    /// <summary>
    /// Обновление порогов и настроек без пересоздания фильтров.
    /// Вызывается для каждого трека с адаптивными параметрами.
    /// </summary>
    public void UpdateSettings(
        float lowThreshold, float lowRatio, float lowKnee, float lowMakeup,
        float midThreshold, float midRatio, float midKnee, float midMakeup,
        float highThreshold, float highRatio, float highKnee, float highMakeup)
    {
        if (_pipeline == null)
            throw new InvalidOperationException("CompressorProcessor not initialized");

        _pipeline.ThreeBand.LowCompressor.UpdateSettings(lowThreshold, lowRatio, lowKnee, lowMakeup);
        _pipeline.ThreeBand.MidCompressor.UpdateSettings(midThreshold, midRatio, midKnee, midMakeup);
        _pipeline.ThreeBand.HighCompressor.UpdateSettings(highThreshold, highRatio, highKnee, highMakeup);

        Console.WriteLine(
            $"[CompressorPipeline] Adaptive: " +
            $"Low={lowThreshold:F1}dB {lowRatio:F0}:1 | " +
            $"Mid={midThreshold:F1}dB {midRatio:F0}:1 | " +
            $"High={highThreshold:F1}dB {highRatio:F0}:1 | " +
            $"Makeup: L={lowMakeup:F1} M={midMakeup:F1} H={highMakeup:F1} dB");
    }

    /// <summary>
    /// Установка attack/release для всех трёх компрессоров
    /// </summary>
    public void SetAttackRelease(float attackMs, float releaseMs)
    {
        if (_pipeline == null)
            throw new InvalidOperationException("CompressorProcessor not initialized");

        _pipeline.ThreeBand.LowCompressor.AttackMs = attackMs;
        _pipeline.ThreeBand.LowCompressor.ReleaseMs = releaseMs;
        _pipeline.ThreeBand.MidCompressor.AttackMs = attackMs;
        _pipeline.ThreeBand.MidCompressor.ReleaseMs = releaseMs;
        _pipeline.ThreeBand.HighCompressor.AttackMs = attackMs;
        _pipeline.ThreeBand.HighCompressor.ReleaseMs = releaseMs;
    }

    public void ProcessStereo(float left, float right, out float outLeft, out float outRight)
    {
        _pipeline!.ProcessStereo(left, right, out outLeft, out outRight);
    }

    public void Reset()
    {
        _pipeline?.Reset();
    }
}
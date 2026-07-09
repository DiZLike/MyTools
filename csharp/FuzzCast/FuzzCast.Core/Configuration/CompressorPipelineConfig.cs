namespace FuzzCast.Core.Configuration
{
    public class PresetConfig
    {
        public float Ratio { get; set; } = 3f;
        public float KneeWidth { get; set; } = 3f;
        public float HeadroomDb { get; set; } = -4f;
        public float MakeupGain { get; set; } = 5f;
        public float AttackMs { get; set; } = 10f;
        public float ReleaseMs { get; set; } = 80f;
    }

    public class LimiterConfig
    {
        public float Ceiling { get; set; } = -0.3f;
        public float LookaheadMs { get; set; } = 1.0f;
        public float AttackMs { get; set; } = 0.5f;
        public float ReleaseMs { get; set; } = 30f;
    }

    public class CompressorPipelineConfig
    {
        public bool Enabled { get; set; } = true;
        public bool ReplayGainEnabled { get; set; } = true;
        public string Preset { get; set; } = "Medium";
        public Dictionary<string, PresetConfig> Presets { get; set; } = new()
        {
            ["Soft"] = new PresetConfig
            {
                Ratio = 2f,
                KneeWidth = 6f,
                HeadroomDb = -6f,
                MakeupGain = 3f,
                AttackMs = 20f,
                ReleaseMs = 120f
            },
            ["Medium"] = new PresetConfig
            {
                Ratio = 3f,
                KneeWidth = 3f,
                HeadroomDb = -4f,
                MakeupGain = 5f,
                AttackMs = 10f,
                ReleaseMs = 80f
            },
            ["Hard"] = new PresetConfig
            {
                Ratio = 5f,
                KneeWidth = 0f,
                HeadroomDb = -2f,
                MakeupGain = 8f,
                AttackMs = 5f,
                ReleaseMs = 50f
            }
        };
        public LimiterConfig Limiter { get; set; } = new();
    }
}
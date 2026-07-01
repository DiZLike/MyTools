namespace FuzzCast.Fx
{
    public static class AudioMath
    {
        public static float DbToLinear(float db)
        {
            if (db <= -150f) return 0f;
            return MathF.Pow(10f, db / 20f);
        }

        public static float LinearToDb(float linear)
        {
            if (linear < 1e-10f) return -150f;
            return 20f * MathF.Log10(linear);
        }
    }
}
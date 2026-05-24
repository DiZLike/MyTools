using System;

namespace AudioFill.Audio.Restore
{
    public class RestoreProgress
    {
        public int Percent { get; set; }
        public string Step { get; set; } = "";
        public TimeSpan Elapsed { get; set; }
        public TimeSpan Remaining { get; set; }
    }
}
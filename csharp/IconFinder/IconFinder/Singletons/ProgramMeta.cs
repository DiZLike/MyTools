using System;
using System.Collections.Generic;
using System.Text;

namespace IconFinder.Singletons
{
    public static class ProgramMeta
    {
        public static string ProgramName { get; set; } = "Icon Finder";
        public static string Version { get; set; } = "1.0";
        public static string Title { get; } = $"{ProgramName} {Version}";
    }
}

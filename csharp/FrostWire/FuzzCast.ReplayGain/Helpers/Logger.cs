namespace FuzzCast.ReplayGain.Helpers;

public static class Logger
{
    public static void Info(string message) => Console.WriteLine($"[INFO] {message}");
    public static void Ok(string message) => Console.WriteLine($"[OK] {message}");
    public static void Warn(string message) => Console.WriteLine($"[WARN] {message}");
    public static void Error(string message) => Console.WriteLine($"[ERROR] {message}");
}
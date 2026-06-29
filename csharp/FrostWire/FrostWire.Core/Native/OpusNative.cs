using System.Runtime.InteropServices;

namespace FuzzCast.Core.Native;

public static class OpusNative
{
    private const string WinX64 = "runtimes/native/libopus-x64.dll";
    private const string LinuxX64 = "runtimes/native/libopus-x64.so";
    private const string LinuxArm64 = "runtimes/native/libopus-aarch64.so";

    static OpusNative()
    {
        string libPath = GetLibraryPath();
        if (NativeLibrary.TryLoad(libPath, out _))
        {
            Console.WriteLine($"[Opus] Loaded: {libPath}");
        }
        else
        {
            Console.WriteLine($"[Opus] Failed to load: {libPath}");
        }
    }

    private static string GetLibraryPath()
    {
        if (OperatingSystem.IsWindows())
            return WinX64;

        if (OperatingSystem.IsLinux())
        {
            Architecture arch = RuntimeInformation.ProcessArchitecture;
            return arch == Architecture.Arm64 ? LinuxArm64 : LinuxX64;
        }

        throw new PlatformNotSupportedException("Unsupported OS/Architecture");
    }

    #region Encoder

    [DllImport(WinX64, EntryPoint = "opus_encoder_create", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr encoder_create_win(int sampleRate, int channels, int application, out int error);

    [DllImport(LinuxX64, EntryPoint = "opus_encoder_create", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr encoder_create_linux_x64(int sampleRate, int channels, int application, out int error);

    [DllImport(LinuxArm64, EntryPoint = "opus_encoder_create", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr encoder_create_linux_arm64(int sampleRate, int channels, int application, out int error);

    public static IntPtr opus_encoder_create(int sampleRate, int channels, int application, out int error)
    {
        if (OperatingSystem.IsWindows())
            return encoder_create_win(sampleRate, channels, application, out error);
        if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            return encoder_create_linux_arm64(sampleRate, channels, application, out error);
        return encoder_create_linux_x64(sampleRate, channels, application, out error);
    }

    [DllImport(WinX64, EntryPoint = "opus_encode", CallingConvention = CallingConvention.Cdecl)]
    private static extern int encode_win(IntPtr st, short[] pcm, int frameSize, byte[] data, int maxDataBytes);

    [DllImport(LinuxX64, EntryPoint = "opus_encode", CallingConvention = CallingConvention.Cdecl)]
    private static extern int encode_linux_x64(IntPtr st, short[] pcm, int frameSize, byte[] data, int maxDataBytes);

    [DllImport(LinuxArm64, EntryPoint = "opus_encode", CallingConvention = CallingConvention.Cdecl)]
    private static extern int encode_linux_arm64(IntPtr st, short[] pcm, int frameSize, byte[] data, int maxDataBytes);

    public static int opus_encode(IntPtr st, short[] pcm, int frameSize, byte[] data, int maxDataBytes)
    {
        if (OperatingSystem.IsWindows())
            return encode_win(st, pcm, frameSize, data, maxDataBytes);
        if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            return encode_linux_arm64(st, pcm, frameSize, data, maxDataBytes);
        return encode_linux_x64(st, pcm, frameSize, data, maxDataBytes);
    }

    [DllImport(WinX64, EntryPoint = "opus_encoder_ctl", CallingConvention = CallingConvention.Cdecl)]
    private static extern int encoder_ctl_win(IntPtr st, int request, int value);

    [DllImport(LinuxX64, EntryPoint = "opus_encoder_ctl", CallingConvention = CallingConvention.Cdecl)]
    private static extern int encoder_ctl_linux_x64(IntPtr st, int request, int value);

    [DllImport(LinuxArm64, EntryPoint = "opus_encoder_ctl", CallingConvention = CallingConvention.Cdecl)]
    private static extern int encoder_ctl_linux_arm64(IntPtr st, int request, int value);

    public static int opus_encoder_ctl(IntPtr st, int request, int value)
    {
        if (OperatingSystem.IsWindows())
            return encoder_ctl_win(st, request, value);
        if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            return encoder_ctl_linux_arm64(st, request, value);
        return encoder_ctl_linux_x64(st, request, value);
    }

    [DllImport(WinX64, EntryPoint = "opus_encoder_destroy", CallingConvention = CallingConvention.Cdecl)]
    private static extern void encoder_destroy_win(IntPtr st);

    [DllImport(LinuxX64, EntryPoint = "opus_encoder_destroy", CallingConvention = CallingConvention.Cdecl)]
    private static extern void encoder_destroy_linux_x64(IntPtr st);

    [DllImport(LinuxArm64, EntryPoint = "opus_encoder_destroy", CallingConvention = CallingConvention.Cdecl)]
    private static extern void encoder_destroy_linux_arm64(IntPtr st);

    public static void opus_encoder_destroy(IntPtr st)
    {
        if (OperatingSystem.IsWindows())
            encoder_destroy_win(st);
        else if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            encoder_destroy_linux_arm64(st);
        else
            encoder_destroy_linux_x64(st);
    }

    #endregion

    #region Decoder

    [DllImport(WinX64, EntryPoint = "opus_decoder_create", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr decoder_create_win(int sampleRate, int channels, out int error);

    [DllImport(LinuxX64, EntryPoint = "opus_decoder_create", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr decoder_create_linux_x64(int sampleRate, int channels, out int error);

    [DllImport(LinuxArm64, EntryPoint = "opus_decoder_create", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr decoder_create_linux_arm64(int sampleRate, int channels, out int error);

    public static IntPtr opus_decoder_create(int sampleRate, int channels, out int error)
    {
        if (OperatingSystem.IsWindows())
            return decoder_create_win(sampleRate, channels, out error);
        if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            return decoder_create_linux_arm64(sampleRate, channels, out error);
        return decoder_create_linux_x64(sampleRate, channels, out error);
    }

    [DllImport(WinX64, EntryPoint = "opus_decode", CallingConvention = CallingConvention.Cdecl)]
    private static extern int decode_win(IntPtr st, byte[] data, int len, short[] pcm, int frameSize, int decodeFec);

    [DllImport(LinuxX64, EntryPoint = "opus_decode", CallingConvention = CallingConvention.Cdecl)]
    private static extern int decode_linux_x64(IntPtr st, byte[] data, int len, short[] pcm, int frameSize, int decodeFec);

    [DllImport(LinuxArm64, EntryPoint = "opus_decode", CallingConvention = CallingConvention.Cdecl)]
    private static extern int decode_linux_arm64(IntPtr st, byte[] data, int len, short[] pcm, int frameSize, int decodeFec);

    public static int opus_decode(IntPtr st, byte[] data, int len, short[] pcm, int frameSize, int decodeFec)
    {
        if (OperatingSystem.IsWindows())
            return decode_win(st, data, len, pcm, frameSize, decodeFec);
        if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            return decode_linux_arm64(st, data, len, pcm, frameSize, decodeFec);
        return decode_linux_x64(st, data, len, pcm, frameSize, decodeFec);
    }

    [DllImport(WinX64, EntryPoint = "opus_decoder_destroy", CallingConvention = CallingConvention.Cdecl)]
    private static extern void decoder_destroy_win(IntPtr st);

    [DllImport(LinuxX64, EntryPoint = "opus_decoder_destroy", CallingConvention = CallingConvention.Cdecl)]
    private static extern void decoder_destroy_linux_x64(IntPtr st);

    [DllImport(LinuxArm64, EntryPoint = "opus_decoder_destroy", CallingConvention = CallingConvention.Cdecl)]
    private static extern void decoder_destroy_linux_arm64(IntPtr st);

    public static void opus_decoder_destroy(IntPtr st)
    {
        if (OperatingSystem.IsWindows())
            decoder_destroy_win(st);
        else if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            decoder_destroy_linux_arm64(st);
        else
            decoder_destroy_linux_x64(st);
    }

    #endregion

    #region Utility

    [DllImport(WinX64, EntryPoint = "opus_packet_get_nb_samples", CallingConvention = CallingConvention.Cdecl)]
    private static extern int packet_get_nb_samples_win(byte[] packet, int len, int sampleRate);

    [DllImport(LinuxX64, EntryPoint = "opus_packet_get_nb_samples", CallingConvention = CallingConvention.Cdecl)]
    private static extern int packet_get_nb_samples_linux_x64(byte[] packet, int len, int sampleRate);

    [DllImport(LinuxArm64, EntryPoint = "opus_packet_get_nb_samples", CallingConvention = CallingConvention.Cdecl)]
    private static extern int packet_get_nb_samples_linux_arm64(byte[] packet, int len, int sampleRate);

    public static int opus_packet_get_nb_samples(byte[] packet, int len, int sampleRate)
    {
        if (OperatingSystem.IsWindows())
            return packet_get_nb_samples_win(packet, len, sampleRate);
        if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            return packet_get_nb_samples_linux_arm64(packet, len, sampleRate);
        return packet_get_nb_samples_linux_x64(packet, len, sampleRate);
    }

    [DllImport(WinX64, EntryPoint = "opus_packet_get_bandwidth", CallingConvention = CallingConvention.Cdecl)]
    private static extern int packet_get_bandwidth_win(byte[] packet, int len);

    [DllImport(LinuxX64, EntryPoint = "opus_packet_get_bandwidth", CallingConvention = CallingConvention.Cdecl)]
    private static extern int packet_get_bandwidth_linux_x64(byte[] packet, int len);

    [DllImport(LinuxArm64, EntryPoint = "opus_packet_get_bandwidth", CallingConvention = CallingConvention.Cdecl)]
    private static extern int packet_get_bandwidth_linux_arm64(byte[] packet, int len);

    public static int opus_packet_get_bandwidth(byte[] packet, int len)
    {
        if (OperatingSystem.IsWindows())
            return packet_get_bandwidth_win(packet, len);
        if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            return packet_get_bandwidth_linux_arm64(packet, len);
        return packet_get_bandwidth_linux_x64(packet, len);
    }

    [DllImport(WinX64, EntryPoint = "opus_packet_get_samples_per_frame", CallingConvention = CallingConvention.Cdecl)]
    private static extern int packet_get_samples_per_frame_win(byte[] packet, int sampleRate);

    [DllImport(LinuxX64, EntryPoint = "opus_packet_get_samples_per_frame", CallingConvention = CallingConvention.Cdecl)]
    private static extern int packet_get_samples_per_frame_linux_x64(byte[] packet, int sampleRate);

    [DllImport(LinuxArm64, EntryPoint = "opus_packet_get_samples_per_frame", CallingConvention = CallingConvention.Cdecl)]
    private static extern int packet_get_samples_per_frame_linux_arm64(byte[] packet, int sampleRate);

    public static int opus_packet_get_samples_per_frame(byte[] packet, int sampleRate)
    {
        if (OperatingSystem.IsWindows())
            return packet_get_samples_per_frame_win(packet, sampleRate);
        if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            return packet_get_samples_per_frame_linux_arm64(packet, sampleRate);
        return packet_get_samples_per_frame_linux_x64(packet, sampleRate);
    }

    #endregion

    #region Version

    [DllImport(WinX64, EntryPoint = "opus_get_version_string", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr version_win();

    [DllImport(LinuxX64, EntryPoint = "opus_get_version_string", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr version_linux_x64();

    [DllImport(LinuxArm64, EntryPoint = "opus_get_version_string", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr version_linux_arm64();

    public static string opus_get_version_string()
    {
        IntPtr ptr;
        if (OperatingSystem.IsWindows())
            ptr = version_win();
        else if (OperatingSystem.IsLinux() && RuntimeInformation.ProcessArchitecture == Architecture.Arm64)
            ptr = version_linux_arm64();
        else
            ptr = version_linux_x64();

        return Marshal.PtrToStringAnsi(ptr) ?? "unknown";
    }

    #endregion
}
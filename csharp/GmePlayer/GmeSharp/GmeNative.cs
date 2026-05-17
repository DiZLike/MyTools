using System;
using System.Runtime.InteropServices;

namespace gmesharp
{
    internal static class NativeMethods
    {
        public const string DllName = "libgme";

        [StructLayout(LayoutKind.Sequential)]
        public struct gme_equalizer_t
        {
            public double treble, bass;
            public double d2, d3, d4, d5, d6, d7, d8, d9;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct gme_info_t
        {
            /* times in milliseconds; -1 if unknown */
            public int length;         /* total length, if file specifies it */
            public int intro_length;   /* length of song up to looping section */
            public int loop_length;    /* length of looping section */

            /* Length if available, otherwise intro_length+loop_length*2 if available,
               otherwise a default of 150000 (2.5 minutes). */
            public int play_length;

            /* fade length in milliseconds; -1 if unknown */
            public int fade_length;

            /* reserved */
            public int i5, i6, i7, i8, i9, i10, i11, i12, i13, i14, i15;

            /* empty string ("") if not available */
            public IntPtr system;
            public IntPtr game;
            public IntPtr song;
            public IntPtr author;
            public IntPtr copyright;
            public IntPtr comment;
            public IntPtr dumper;

            /* reserved */
            public IntPtr s7, s8, s9, s10, s11, s12, s13, s14, s15;
        }

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_open_file(
            [MarshalAs(UnmanagedType.LPUTF8Str)] string path, out IntPtr emu, int sampleRate);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_open_data(IntPtr data, long size, out IntPtr emu, int sampleRate);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int gme_track_count(IntPtr emu);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_start_track(IntPtr emu, int index);

        /// <summary>
        /// gme_play - count = количество mono-сэмплов
        /// </summary>
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_play(IntPtr emu, int count, IntPtr output);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_delete(IntPtr emu);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_set_fade(IntPtr emu, int startMsec);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_set_fade_msecs(IntPtr emu, int startMsec, int lengthMsecs);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int gme_track_ended(IntPtr emu);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int gme_tell(IntPtr emu);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_seek(IntPtr emu, int msec);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_warning(IntPtr emu);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_track_info(IntPtr emu, out IntPtr info, int track);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_free_info(IntPtr info);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_set_stereo_depth(IntPtr emu, double depth);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_ignore_silence(IntPtr emu, int ignore);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_set_tempo(IntPtr emu, double tempo);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int gme_voice_count(IntPtr emu);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_voice_name(IntPtr emu, int i);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_mute_voice(IntPtr emu, int index, int mute);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_mute_voices(IntPtr emu, int mutingMask);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_disable_echo(IntPtr emu, int disable);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_set_equalizer(IntPtr emu, ref gme_equalizer_t eq);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void gme_enable_accuracy(IntPtr emu, int enabled);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_type(IntPtr emu);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_type_system(IntPtr type);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_load_m3u(IntPtr emu,
            [MarshalAs(UnmanagedType.LPUTF8Str)] string path);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_identify_extension(
            [MarshalAs(UnmanagedType.LPUTF8Str)] string pathOrExtension);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern IntPtr gme_type_list();
    }
}
using System;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace gmesharp
{
    public sealed class GmeEmuHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        public GmeEmuHandle() : base(true) { }
        public GmeEmuHandle(IntPtr h, bool owns) : base(owns) { SetHandle(h); }
        protected override bool ReleaseHandle()
        {
            NativeMethods.gme_delete(handle);
            return true;
        }
    }
    public struct GmeEqualizer
    {
        public double Treble, Bass;
        public double D2, D3, D4, D5, D6, D7, D8, D9;
    }

    public class GmeTrackInfo
    {
        public int Length, IntroLength, LoopLength, PlayLength, FadeLength;
        public string System, Game, Song, Author, Copyright, Comment, Dumper;

        public override string ToString()
        {
            return $"Track: {Song} - {Author} (Game: {Game}, System: {System})";
        }
    }

    public class GmeException : Exception
    {
        public GmeException(string msg) : base(msg) { }
    }

    public class GmePlayer : IDisposable
    {
        private GmeEmuHandle _emuHandle;
        private volatile bool _disposed;

        public int SampleRate { get; }

        public GmePlayer(string filePath, int sampleRate = 44100)
        {
            IntPtr err = NativeMethods.gme_open_file(filePath, out IntPtr emu, sampleRate);
            if (err != IntPtr.Zero)
                throw new GmeException(PtrToStringUtf8(err) ?? "Failed to open");
            if (emu == IntPtr.Zero)
                throw new GmeException("Null emu");

            _emuHandle = new GmeEmuHandle(emu, true);
            SampleRate = sampleRate;
            TryM3u(filePath);
        }

        private void TryM3u(string path)
        {
            try
            {
                string m3u = System.IO.Path.ChangeExtension(path, ".m3u");
                if (System.IO.File.Exists(m3u))
                    NativeMethods.gme_load_m3u(_emuHandle.DangerousGetHandle(), m3u);
            }
            catch { }
        }

        private static string PtrToStringUtf8(IntPtr p)
        {
            if (p == IntPtr.Zero) return null;
            return Marshal.PtrToStringUTF8(p);
        }
        public int TrackCount => NativeMethods.gme_track_count(GetHandle());
        public bool TrackEnded => NativeMethods.gme_track_ended(GetHandle()) != 0;
        public int PositionMs => NativeMethods.gme_tell(GetHandle());
        public int VoiceCount => NativeMethods.gme_voice_count(GetHandle());

        public string EmulatorType
        {
            get
            {
                IntPtr typePtr = NativeMethods.gme_type(GetHandle());
                if (typePtr == IntPtr.Zero) return null;

                IntPtr strPtr = NativeMethods.gme_type_system(typePtr);
                return PtrToStringUtf8(strPtr);
            }
        }

        public string Warning => PtrToStringUtf8(NativeMethods.gme_warning(GetHandle()));

        private IntPtr GetHandle()
        {
            if (_disposed || _emuHandle == null || _emuHandle.IsClosed || _emuHandle.IsInvalid)
                throw new ObjectDisposedException("GmePlayer");
            return _emuHandle.DangerousGetHandle();
        }

        public void StartTrack(int index)
        {
            IntPtr err = NativeMethods.gme_start_track(GetHandle(), index);
            if (err != IntPtr.Zero)
                throw new GmeException(PtrToStringUtf8(err) ?? "Start error");
        }
        public unsafe bool PlayDirect(short* buffer, int count)
        {
            if (_disposed || _emuHandle == null || _emuHandle.IsClosed || _emuHandle.IsInvalid)
                return false;

            IntPtr emuHandle = _emuHandle.DangerousGetHandle();
            IntPtr err = NativeMethods.gme_play(emuHandle, count, (IntPtr)buffer);
            return err == IntPtr.Zero;
        }
        public string PlayIntoNativeBuffer(IntPtr nativeBuffer, int count)
        {
            if (_disposed || _emuHandle == null || _emuHandle.IsClosed || _emuHandle.IsInvalid)
                return "disposed";

            IntPtr emuHandle = _emuHandle.DangerousGetHandle();
            IntPtr error = NativeMethods.gme_play(emuHandle, count, nativeBuffer);
            return error != IntPtr.Zero ? PtrToStringUtf8(error) : null;
        }
        public GmeTrackInfo GetTrackInfo(int index)
        {
            IntPtr err = NativeMethods.gme_track_info(GetHandle(), out IntPtr infoPtr, index);
            if (err != IntPtr.Zero)
                throw new GmeException(PtrToStringUtf8(err) ?? "Info error");
            if (infoPtr == IntPtr.Zero)
                return null;

            try
            {
                var n = Marshal.PtrToStructure<NativeMethods.gme_info_t>(infoPtr);
                return new GmeTrackInfo
                {
                    Length = n.length,
                    IntroLength = n.intro_length,
                    LoopLength = n.loop_length,
                    PlayLength = n.play_length,
                    FadeLength = n.fade_length,
                    System = PtrToStringUtf8(n.system),
                    Game = PtrToStringUtf8(n.game),
                    Song = PtrToStringUtf8(n.song),
                    Author = PtrToStringUtf8(n.author),
                    Copyright = PtrToStringUtf8(n.copyright),
                    Comment = PtrToStringUtf8(n.comment),
                    Dumper = PtrToStringUtf8(n.dumper)
                };
            }
            finally
            {
                NativeMethods.gme_free_info(infoPtr);
            }
        }

        public void Seek(int msec)
        {
            NativeMethods.gme_seek(GetHandle(), Math.Max(0, msec));
        }

        public void SetFade(int start, int len = 8000)
        {
            if (start < 0)
                NativeMethods.gme_set_fade(GetHandle(), -1);
            else
                NativeMethods.gme_set_fade_msecs(GetHandle(), start, len);
        }

        public void SetTempo(double t) => NativeMethods.gme_set_tempo(GetHandle(), t);

        public void SetStereoDepth(double d) => NativeMethods.gme_set_stereo_depth(GetHandle(), d);

        public void SetAccuracy(bool a) => NativeMethods.gme_enable_accuracy(GetHandle(), a ? 1 : 0);

        public void SetEchoDisabled(bool d) => NativeMethods.gme_disable_echo(GetHandle(), d ? 1 : 0);

        public void SetIgnoreSilence(bool s) => NativeMethods.gme_ignore_silence(GetHandle(), s ? 1 : 0);

        public string GetVoiceName(int i) => PtrToStringUtf8(NativeMethods.gme_voice_name(GetHandle(), i));

        public void MuteVoice(int i, bool mute) => NativeMethods.gme_mute_voice(GetHandle(), i, mute ? 1 : 0);

        public void MuteVoices(int mask) => NativeMethods.gme_mute_voices(GetHandle(), mask);
        // В класс GmePlayer добавьте метод:
        public int ReadSamples(short[] buffer, int offset, int count)
        {
            if (_disposed || _emuHandle == null || _emuHandle.IsClosed || _emuHandle.IsInvalid)
                return -1;

            try
            {
                unsafe
                {
                    fixed (short* ptr = &buffer[offset])
                    {
                        IntPtr err = NativeMethods.gme_play(
                            _emuHandle.DangerousGetHandle(),
                            count / 2, // gme_play принимает количество mono сэмплов
                            (IntPtr)ptr);

                        if (err != IntPtr.Zero)
                            return -1;
                    }
                }

                return count;
            }
            catch
            {
                return -1;
            }
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                _disposed = true;
                _emuHandle?.Dispose();
                _emuHandle = null;
            }
            GC.SuppressFinalize(this);
        }
    }
}
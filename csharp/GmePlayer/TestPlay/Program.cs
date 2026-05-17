using System;
using System.Threading;
using gmesharp;

namespace TestPlay
{
    class Program
    {
        private static GmePlayer _player;
        private static SdlAudioPlayer _audio;
        private static bool _running = true;
        private static bool _fadeout = true;
        private static bool _accurate;
        private static int _voiceMask;
        private static double _stereoDepth;
        private static double _tempo = 1.0;

        static void Main(string[] args)
        {
            Console.WriteLine("=== GME Player (SDL) ===");
            Console.WriteLine();

            string file = FindFile();
            if (file == null)
            {
                Console.WriteLine("Error: test/alien3.nsf not found!");
                Console.WriteLine("Press any key to exit...");
                Console.ReadKey();
                return;
            }

            try
            {
                Console.WriteLine($"Loading: {file}");
                using (_player = new GmePlayer(file, 44100))
                using (_audio = new SdlAudioPlayer(_player))
                {
                    Console.WriteLine($"Type: {_player.EmulatorType}");
                    Console.WriteLine($"Tracks: {_player.TrackCount}");
                    Console.WriteLine($"Warning: {_player.Warning ?? "none"}");
                    Console.WriteLine();

                    _audio.TrackChanged += OnTrackChanged;
                    _audio.PlaybackChanged += OnPlaybackChanged;

                    // Показываем первые 10 треков
                    for (int i = 0; i < _player.TrackCount && i < 10; i++)
                    {
                        var info = _player.GetTrackInfo(i);
                        if (info != null)
                            Console.WriteLine($"Track {i}: {info}");
                    }
                    Console.WriteLine();

                    // Запускаем первый трек
                    _audio.PlayTrack(0);

                    Console.WriteLine();
                    Console.WriteLine("Controls:");
                    Console.WriteLine("  N/P    - Next/Previous track");
                    Console.WriteLine("  Space  - Pause/Resume");
                    Console.WriteLine("  Left/Right - Seek -/+ 5s");
                    Console.WriteLine("  F      - Toggle fadeout");
                    Console.WriteLine("  A      - Toggle accuracy");
                    Console.WriteLine("  E      - Stereo depth (0/0.2/0.4)");
                    Console.WriteLine("  T      - Set tempo");
                    Console.WriteLine("  I      - Track info");
                    Console.WriteLine("  1-5    - Toggle voices");
                    Console.WriteLine("  0      - Reset tempo & voices");
                    Console.WriteLine("  Q/Esc  - Quit");
                    Console.WriteLine();

                    // Основной цикл
                    while (_running)
                    {
                        // Автопереход на следующий трек
                        if (_audio.IsPlaying && _player.TrackEnded)
                        {
                            Console.WriteLine("\n--- Track ended ---");
                            if (_audio.CurrentTrack < _player.TrackCount - 1)
                                _audio.Next();
                            else
                                _audio.Pause();
                        }

                        if (Console.KeyAvailable)
                        {
                            var key = Console.ReadKey(true);
                            HandleKey(key);
                        }

                        Thread.Sleep(50);
                    }
                }
            }
            catch (GmeException ex)
            {
                Console.WriteLine($"GME Error: {ex.Message}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error: {ex.Message}");
            }

            Console.WriteLine();
            Console.WriteLine("Goodbye!");
        }

        private static void OnTrackChanged(int track)
        {
            var info = _player?.GetTrackInfo(track);
            if (info != null)
            {
                Console.WriteLine($"\n--- Track {track} ---");
                Console.WriteLine($"Song: {info.Song}");
                Console.WriteLine($"Author: {info.Author}");
                Console.WriteLine($"Game: {info.Game}");
                Console.WriteLine($"System: {info.System}");

                if (info.Length > 0)
                {
                    int min = info.Length / 1000 / 60;
                    int sec = info.Length / 1000 % 60;
                    Console.WriteLine($"Length: {min}:{sec:D2}");
                }
            }
        }

        private static void OnPlaybackChanged(bool isPlaying)
        {
            Console.WriteLine($"\n{(isPlaying ? "▶ Playing" : "⏸ Paused")}");
        }

        private static string FindFile()
        {
            string[] paths = {
                "test/alien3.nsf",
                "../test/alien3.nsf",
                "../../test/alien3.nsf",
                "../../../test/alien3.nsf",
                "alien3.nsf"
            };

            foreach (var path in paths)
            {
                if (System.IO.File.Exists(path))
                    return System.IO.Path.GetFullPath(path);
            }

            return null;
        }

        private static void HandleKey(ConsoleKeyInfo key)
        {
            try
            {
                switch (key.Key)
                {
                    case ConsoleKey.N:
                        _audio?.Next();
                        break;

                    case ConsoleKey.P:
                        _audio?.Prev();
                        break;

                    case ConsoleKey.Spacebar:
                        if (_audio?.IsPlaying == true)
                            _audio.Pause();
                        else
                            _audio?.Resume();
                        break;

                    case ConsoleKey.LeftArrow:
                        if (_player != null)
                        {
                            int pos = Math.Max(0, _player.PositionMs - 5000);
                            _player.Seek(pos);
                            Console.WriteLine($"\n◄ Seek: {pos / 1000}s");
                        }
                        break;

                    case ConsoleKey.RightArrow:
                        if (_player != null)
                        {
                            int pos = _player.PositionMs + 5000;
                            _player.Seek(pos);
                            Console.WriteLine($"\n► Seek: {pos / 1000}s");
                        }
                        break;

                    case ConsoleKey.F:
                        _fadeout = !_fadeout;
                        Console.WriteLine($"\nFadeout: {(_fadeout ? "ON" : "OFF")}");
                        if (_fadeout)
                            _player?.SetFade(_player.PositionMs, 8000);
                        else
                            _player?.SetFade(-1);
                        break;

                    case ConsoleKey.A:
                        _accurate = !_accurate;
                        Console.WriteLine($"\nAccuracy: {(_accurate ? "ON" : "OFF")}");
                        if (_player != null)
                            _player.SetAccuracy(_accurate);
                        break;

                    case ConsoleKey.E:
                        _stereoDepth += 0.2;
                        if (_stereoDepth > 0.5)
                            _stereoDepth = 0;
                        if (_player != null)
                            _player.SetStereoDepth(_stereoDepth);
                        Console.WriteLine($"\nStereo depth: {_stereoDepth:F1}");
                        break;

                    case ConsoleKey.T:
                        Console.Write("\nTempo (0.1-2.0): ");
                        if (double.TryParse(Console.ReadLine(), out _tempo))
                        {
                            _tempo = Math.Clamp(_tempo, 0.1, 2.0);
                            if (_player != null)
                                _player.SetTempo(_tempo);
                            Console.WriteLine($"Tempo: {_tempo:F1}x");
                        }
                        break;

                    case ConsoleKey.I:
                        ShowTrackInfo();
                        break;

                    case ConsoleKey.D0:
                        _tempo = 1.0;
                        _voiceMask = 0;
                        if (_player != null)
                        {
                            _player.SetTempo(_tempo);
                            _player.MuteVoices(0);
                        }
                        Console.WriteLine("\nReset tempo & voices");
                        break;

                    case ConsoleKey.D1:
                    case ConsoleKey.D2:
                    case ConsoleKey.D3:
                    case ConsoleKey.D4:
                    case ConsoleKey.D5:
                    case ConsoleKey.D6:
                    case ConsoleKey.D7:
                    case ConsoleKey.D8:
                    case ConsoleKey.D9:
                        int voice = (int)key.Key - (int)ConsoleKey.D1;
                        if (_player != null && voice < _player.VoiceCount)
                        {
                            _voiceMask ^= (1 << voice);
                            _player.MuteVoices(_voiceMask);
                            Console.WriteLine($"\nVoice {voice}: {((_voiceMask & (1 << voice)) != 0 ? "MUTED" : "ON")}");
                        }
                        break;

                    case ConsoleKey.Q:
                    case ConsoleKey.Escape:
                        _running = false;
                        _audio?.Stop();
                        break;
                }
            }
            catch (GmeException ex)
            {
                Console.WriteLine($"\nError: {ex.Message}");
            }
        }

        private static void ShowTrackInfo()
        {
            if (_player == null || _audio == null) return;

            int track = _audio.CurrentTrack;
            var info = _player.GetTrackInfo(track);
            if (info != null)
            {
                Console.WriteLine("\n=== Track Info ===");
                Console.WriteLine($"Track: {track}");
                Console.WriteLine($"Song: {info.Song}");
                Console.WriteLine($"Author: {info.Author}");
                Console.WriteLine($"Game: {info.Game}");
                Console.WriteLine($"System: {info.System}");
                Console.WriteLine($"Copyright: {info.Copyright}");
                Console.WriteLine($"Comment: {info.Comment}");
                Console.WriteLine($"Dumper: {info.Dumper}");
                Console.WriteLine($"Length: {info.Length}ms");
                Console.WriteLine($"Intro: {info.IntroLength}ms");
                Console.WriteLine($"Loop: {info.LoopLength}ms");
                Console.WriteLine($"Play: {info.PlayLength}ms");
                Console.WriteLine($"Voices: {_player.VoiceCount}");

                for (int i = 0; i < _player.VoiceCount && i < 8; i++)
                {
                    Console.WriteLine($"  Voice {i}: {_player.GetVoiceName(i)}");
                }
                Console.WriteLine();
            }
        }
    }
}
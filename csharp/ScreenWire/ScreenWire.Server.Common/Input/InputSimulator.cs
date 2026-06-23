using System;
using System.Runtime.InteropServices;
using System.Threading;

namespace ScreenWire.Server.Input
{
    public class InputSimulator : IDisposable
    {
        // Константы для хуков
        private const int WH_JOURNALPLAYBACK = 1;
        private const int WH_JOURNALRECORD = 0;

        private const uint WM_KEYDOWN = 0x0100;
        private const uint WM_KEYUP = 0x0101;
        private const uint WM_SYSKEYDOWN = 0x0104;
        private const uint WM_SYSKEYUP = 0x0105;
        private const uint WM_MOUSEMOVE = 0x0200;
        private const uint WM_LBUTTONDOWN = 0x0201;
        private const uint WM_LBUTTONUP = 0x0202;
        private const uint WM_RBUTTONDOWN = 0x0204;
        private const uint WM_RBUTTONUP = 0x0205;
        private const uint WM_MBUTTONDOWN = 0x0207;
        private const uint WM_MBUTTONUP = 0x0208;
        private const uint WM_MOUSEWHEEL = 0x020A;

        // Константы для SendInput (используем как fallback)
        public const uint MOUSEEVENTF_MOVE = 0x0001;
        public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
        public const uint MOUSEEVENTF_LEFTUP = 0x0004;
        public const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
        public const uint MOUSEEVENTF_RIGHTUP = 0x0010;
        public const uint MOUSEEVENTF_MIDDLEDOWN = 0x0020;
        public const uint MOUSEEVENTF_MIDDLEUP = 0x0040;
        public const uint MOUSEEVENTF_WHEEL = 0x0800;
        public const uint MOUSEEVENTF_ABSOLUTE = 0x8000;

        // WinAPI функции
        [DllImport("user32.dll", SetLastError = true)]
        private static extern IntPtr SetWindowsHookEx(int idHook, HookProc lpfn, IntPtr hMod, uint dwThreadId);

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool UnhookWindowsHookEx(IntPtr hhk);

        [DllImport("user32.dll")]
        private static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);

        [DllImport("kernel32.dll")]
        private static extern IntPtr GetModuleHandle(string lpModuleName);

        [DllImport("user32.dll")]
        private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

        [DllImport("user32.dll")]
        private static extern bool SetCursorPos(int x, int y);

        [DllImport("user32.dll")]
        private static extern short GetAsyncKeyState(int vKey);

        [DllImport("user32.dll")]
        private static extern uint MapVirtualKey(uint uCode, uint uMapType);

        // Делегат для хука
        private delegate IntPtr HookProc(int nCode, IntPtr wParam, IntPtr lParam);

        // Структуры для SendInput (fallback)
        [StructLayout(LayoutKind.Sequential)]
        private struct INPUT
        {
            public uint type;
            public INPUTUNION u;
        }

        [StructLayout(LayoutKind.Explicit)]
        private struct INPUTUNION
        {
            [FieldOffset(0)] public MOUSEINPUT mi;
            [FieldOffset(0)] public KEYBDINPUT ki;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct MOUSEINPUT
        {
            public int dx;
            public int dy;
            public uint mouseData;
            public uint dwFlags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct KEYBDINPUT
        {
            public ushort wVk;
            public ushort wScan;
            public uint dwFlags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        // Структура для журнала событий
        [StructLayout(LayoutKind.Sequential)]
        private struct EVENTMSG
        {
            public uint message;
            public uint paramL;
            public uint paramH;
            public uint time;
            public IntPtr hwnd;
        }

        // Очередь событий для воспроизведения
        private readonly System.Collections.Generic.Queue<EVENTMSG> _eventQueue =
            new System.Collections.Generic.Queue<EVENTMSG>();
        private readonly object _queueLock = new object();
        private HookProc _hookProc;
        private IntPtr _hookHandle = IntPtr.Zero;
        private volatile bool _isPlaying = false;
        private volatile bool _disposed = false;

        // Статический экземпляр для обратного вызова
        private static InputSimulator _instance;

        public InputSimulator()
        {
            _instance = this;
            _hookProc = new HookProc(JournalPlaybackProc);
        }

        /// <summary>
        /// Запускает хук для воспроизведения событий ввода
        /// </summary>
        public void StartHook()
        {
            if (_hookHandle != IntPtr.Zero)
                return;

            uint threadId = 0; // 0 = глобальный хук для текущего потока
            _hookHandle = SetWindowsHookEx(WH_JOURNALPLAYBACK, _hookProc,
                GetModuleHandle(null), threadId);
        }

        /// <summary>
        /// Останавливает хук
        /// </summary>
        public void StopHook()
        {
            if (_hookHandle != IntPtr.Zero)
            {
                UnhookWindowsHookEx(_hookHandle);
                _hookHandle = IntPtr.Zero;
            }
        }

        private IntPtr JournalPlaybackProc(int nCode, IntPtr wParam, IntPtr lParam)
        {
            if (nCode < 0)
                return CallNextHookEx(_hookHandle, nCode, wParam, lParam);

            EVENTMSG evt;
            lock (_queueLock)
            {
                if (_eventQueue.Count > 0)
                {
                    evt = _eventQueue.Dequeue();
                    // Копируем структуру в lParam
                    Marshal.StructureToPtr(evt, lParam, false);
                    _isPlaying = true;
                    return (IntPtr)0; // Обработано
                }
            }

            _isPlaying = false;
            return (IntPtr)0;
        }

        private void QueueEvent(uint message, uint paramL, uint paramH)
        {
            var evt = new EVENTMSG
            {
                message = message,
                paramL = paramL,
                paramH = paramH,
                time = (uint)Environment.TickCount,
                hwnd = IntPtr.Zero
            };

            lock (_queueLock)
            {
                _eventQueue.Enqueue(evt);
            }

            StartHook();

            // Ждём пока событие будет обработано
            int timeout = 100;
            while (_isPlaying && timeout > 0)
            {
                Thread.Sleep(1);
                timeout--;
            }
        }

        public void MoveMouse(short x, short y)
        {
            // Пробуем через SetCursorPos
            if (SetCursorPos(x, y))
                return;

            // Fallback: через журнал событий
            uint lParam = (uint)((y << 16) | (x & 0xFFFF));
            QueueEvent(WM_MOUSEMOVE, lParam, 0);
        }

        public void MouseEvent(uint flags, int dx, int dy, uint data)
        {
            // Пробуем через SendInput
            if (TrySendInput(flags, dx, dy, data))
                return;

            // Fallback: через журнал событий
            if (flags == MOUSEEVENTF_LEFTDOWN)
                QueueEvent(WM_LBUTTONDOWN, 0, 0);
            else if (flags == MOUSEEVENTF_LEFTUP)
                QueueEvent(WM_LBUTTONUP, 0, 0);
            else if (flags == MOUSEEVENTF_RIGHTDOWN)
                QueueEvent(WM_RBUTTONDOWN, 0, 0);
            else if (flags == MOUSEEVENTF_RIGHTUP)
                QueueEvent(WM_RBUTTONUP, 0, 0);
            else if (flags == MOUSEEVENTF_MIDDLEDOWN)
                QueueEvent(WM_MBUTTONDOWN, 0, 0);
            else if (flags == MOUSEEVENTF_MIDDLEUP)
                QueueEvent(WM_MBUTTONUP, 0, 0);
            else if (flags == MOUSEEVENTF_WHEEL)
                QueueEvent(WM_MOUSEWHEEL, data << 16, 0);
        }

        private bool TrySendInput(uint flags, int dx, int dy, uint data)
        {
            try
            {
                var input = new INPUT[1];
                input[0].type = 0; // INPUT_MOUSE
                input[0].u.mi.dx = dx;
                input[0].u.mi.dy = dy;
                input[0].u.mi.mouseData = data;
                input[0].u.mi.dwFlags = flags;
                input[0].u.mi.time = 0;
                input[0].u.mi.dwExtraInfo = IntPtr.Zero;

                uint result = SendInput(1, input, Marshal.SizeOf(typeof(INPUT)));
                return result == 1;
            }
            catch
            {
                return false;
            }
        }

        public void SendKey(byte vk, bool down)
        {
            // Пробуем через SendInput
            if (TrySendKey(vk, down))
                return;

            // Fallback: через журнал событий
            uint message = down ? WM_KEYDOWN : WM_KEYUP;
            uint scanCode = MapVirtualKey(vk, 0);
            uint lParam = (scanCode << 16) | (down ? 0u : 0xC0000001u);
            QueueEvent(message, vk, lParam);
        }

        private bool TrySendKey(byte vk, bool down)
        {
            try
            {
                var input = new INPUT[1];
                input[0].type = 1; // INPUT_KEYBOARD
                input[0].u.ki.wVk = vk;
                input[0].u.ki.wScan = 0;
                input[0].u.ki.dwFlags = down ? 0u : 0x0002; // KEYEVENTF_KEYUP
                input[0].u.ki.time = 0;
                input[0].u.ki.dwExtraInfo = IntPtr.Zero;

                uint result = SendInput(1, input, Marshal.SizeOf(typeof(INPUT)));
                return result == 1;
            }
            catch
            {
                return false;
            }
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            StopHook();
        }
    }
}
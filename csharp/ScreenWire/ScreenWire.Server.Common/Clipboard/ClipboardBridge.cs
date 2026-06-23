using System;
using System.Threading;

namespace ScreenWire.Server.Clipboard
{
    public class ClipboardBridge : IDisposable
    {
        private string _last = "";
        // FIX: volatile для корректной работы в многопоточной среде
        private volatile bool _suppress;
        private volatile bool _running = true;

        public event EventHandler<TextChangedEventArgs> TextChanged;

        public ClipboardBridge()
        {
            _last = GetText();
            var t = new Thread(Monitor) { IsBackground = true };
            t.SetApartmentState(ApartmentState.STA);
            t.Start();
        }

        public void SetText(string text)
        {
            if (text == null) return;
            _suppress = true;
            try
            {
                System.Windows.Forms.Clipboard.SetText(text);
                _last = text;
            }
            catch { }
            finally { _suppress = false; }
        }

        private void Monitor()
        {
            while (_running)
            {
                Thread.Sleep(300);
                if (_suppress) continue;

                string cur = null;
                var t = new Thread(() => cur = GetText());
                t.SetApartmentState(ApartmentState.STA);
                t.Start();
                if (!t.Join(500))
                {
                    #if NET35
                        t.Abort(); // На XP единственный способ прервать зависший clipboard
                    #else
                                        // На .NET 6+ Abort() не поддерживается, просто пропускаем
                    #endif
                    continue;
                }

                if (cur != null && cur != _last)
                {
                    _last = cur;
                    TextChanged?.Invoke(this, new TextChangedEventArgs(cur));
                }
            }
        }

        private static string GetText()
        {
            try
            {
                // FIX: На XP ContainsText() может врать, пробуем сразу GetText()
                return System.Windows.Forms.Clipboard.GetText();
            }
            catch { return ""; }
        }

        public void Dispose()
        {
            _running = false;
            // FIX: Даём время потоку завершиться
            Thread.Sleep(100);
        }
    }

    public class TextChangedEventArgs : EventArgs
    {
        public string Text { get; }
        public TextChangedEventArgs(string s) => Text = s;
    }
}
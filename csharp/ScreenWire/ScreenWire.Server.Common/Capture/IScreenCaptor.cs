using System;

namespace ScreenWire.Server.Capture
{
    public interface IScreenCaptor : IDisposable
    {
        byte[] CaptureScreen(int quality, float reductionRatio);
    }
}
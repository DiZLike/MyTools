namespace ScreenWire.Server.Capture
{
    public static class ScreenCaptorFactory
    {
        public static IScreenCaptor Create(string method, int displayIndex)
        {
            switch ((method ?? "").ToLowerInvariant())
            {
                case "dda":
                    return new DxgiScreenCaptor(displayIndex);
                case "gdi":
                default:
                    return new GdiScreenCaptor(displayIndex);
            }
        }
    }
}
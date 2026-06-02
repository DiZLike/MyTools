namespace FileProxy.Shared;

public static class Protocol
{
    public const int DefaultPort = 5454;
    public const int BufferSize = 8192;
    public const int ChannelBufferCount = 32; // 32 * 8 КБ = 256 КБ буфер канала
    public const int AcceptTimeoutSeconds = 30;
    public const int IdleTimeoutSeconds = 60;

    // Команды клиент → сервер
    public const string LoginCommand = "LOGIN";
    public const string RegisterUserCommand = "REGUSER"; // одноразово, если нужна регистрация новых пользователей
    public const string SendCommand = "SEND";
    public const string AcceptResponse = "ACCEPT";
    public const string DeclineResponse = "DECLINE";
    public const string ListCommand = "LIST";
    public const string ExitCommand = "EXIT";

    // Ответы сервер → клиент
    public const string OkResponse = "OK";
    public const string ErrorPrefix = "ERROR:";
    public const string RequestPrefix = "REQUEST:";
    public const string OfflineResponse = "OFFLINE";
    public const string ReadyResponse = "READY";
    public const string SizePrefix = "SIZE:";
    public const string DoneResponse = "DONE";
    public const string OnlineListPrefix = "ONLINE:";

    public static string FormatSize(long bytes)
    {
        return bytes switch
        {
            >= 1_073_741_824 => $"{bytes / 1_073_741_824.0:F1} ГБ",
            >= 1_048_576 => $"{bytes / 1_048_576.0:F1} МБ",
            >= 1024 => $"{bytes / 1024.0:F1} КБ",
            _ => $"{bytes} Б"
        };
    }
}
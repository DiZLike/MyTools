using System.Net.Sockets;
using System.Text;

namespace FileProxy.Client;

class Program
{
    const int DefaultPort = 5454;
    const int BufferSize = 8192;

    static string _serverHost = "127.0.0.1";
    static int _serverPort = DefaultPort;
    static TcpClient? _client;
    static NetworkStream? _stream;
    static StreamReader? _reader;
    static StreamWriter? _writer;
    static readonly string _downloadDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads", "FileProxy");

    static async Task Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        Console.InputEncoding = Encoding.UTF8;

        string username = "";
        string password = "";

        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--server" when i + 1 < args.Length:
                    var parts = args[++i].Split(':');
                    _serverHost = parts[0];
                    if (parts.Length > 1) _serverPort = int.Parse(parts[1]);
                    break;
                case "--user" when i + 1 < args.Length:
                    username = args[++i];
                    break;
                case "--pass" when i + 1 < args.Length:
                    password = args[++i];
                    break;
            }
        }

        if (string.IsNullOrEmpty(username))
        {
            Console.Write("Логин: ");
            username = Console.ReadLine()?.Trim() ?? "";
        }
        if (string.IsNullOrEmpty(password))
        {
            Console.Write("Пароль: ");
            password = ReadPassword();
            Console.WriteLine();
        }

        // Подключение
        try
        {
            _client = new TcpClient();
            await _client.ConnectAsync(_serverHost, _serverPort);
            _stream = _client.GetStream();
            _reader = new StreamReader(_stream, Encoding.UTF8);
            _writer = new StreamWriter(_stream, Encoding.UTF8) { AutoFlush = true };

            var prompt = await _reader.ReadLineAsync();
            if (prompt != "LOGIN")
            {
                Console.WriteLine($"Ошибка: {prompt}");
                return;
            }

            await _writer.WriteLineAsync($"{username}:{password}");
            var resp = await _reader.ReadLineAsync();
            if (resp != "OK")
            {
                Console.WriteLine(resp);
                return;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Ошибка подключения: {ex.Message}");
            return;
        }

        Console.WriteLine($"Подключены как '{username}'.");
        Console.WriteLine($"Файлы сохраняются в: {_downloadDir}");
        Console.WriteLine("Команды: send <кому> <файл>, list, exit\n");

        // Основной цикл
        while (true)
        {
            // Сначала проверяем, нет ли входящего REQUEST
            if (_client.Available > 0)
            {
                var incoming = await _reader!.ReadLineAsync();
                if (incoming == null) break;

                if (incoming.StartsWith("REQUEST:"))
                {
                    await HandleRequest(incoming);
                }
                else if (incoming.StartsWith("ONLINE:"))
                {
                    Console.WriteLine($"\nВ сети: {incoming[7..]}");
                }
                else if (incoming.StartsWith("ERROR:"))
                {
                    Console.WriteLine($"\nОшибка: {incoming[6..]}");
                }
            }

            Console.Write("> ");
            var input = Console.ReadLine()?.Trim();
            if (string.IsNullOrEmpty(input)) continue;

            var spaceIdx = input.IndexOf(' ');
            var cmd = spaceIdx > 0 ? input[..spaceIdx].ToLower() : input.ToLower();
            var arg = spaceIdx > 0 ? input[(spaceIdx + 1)..] : "";

            switch (cmd)
            {
                case "send":
                    var sendArgs = arg.Split(' ', 2);
                    if (sendArgs.Length < 2)
                    {
                        Console.WriteLine("Формат: send <кому> <путь к файлу>");
                        break;
                    }
                    await SendFile(sendArgs[0], sendArgs[1]);
                    break;

                case "list":
                    await _writer!.WriteLineAsync("LIST");
                    break;

                case "exit":
                    await _writer!.WriteLineAsync("EXIT");
                    return;

                default:
                    Console.WriteLine("Команды: send <кому> <файл>, list, exit");
                    break;
            }
        }
    }

    static async Task HandleRequest(string line)
    {
        // REQUEST:отправитель:имя_файла:размер
        var parts = line[8..].Split(':', 3);
        if (parts.Length != 3 || !long.TryParse(parts[2], out var fileSize))
            return;

        Console.WriteLine($"\n📩 Запрос от {parts[0]}: {parts[1]} ({FormatSize(fileSize)})");
        Console.Write("Принять? [д/н]: ");
        var answer = Console.ReadLine()?.Trim().ToLower();
        var accept = answer == "д" || answer == "y" || answer == "да" || answer == "yes";

        await _writer!.WriteLineAsync(accept ? "ACCEPT" : "DECLINE");

        if (!accept)
        {
            Console.Write("> ");
            return;
        }

        // Ждём READY:SIZE:N
        var ready = await _reader!.ReadLineAsync();
        if (ready == null || !ready.StartsWith("READY:SIZE:"))
        {
            Console.WriteLine($"Ошибка протокола: {ready}");
            Console.Write("> ");
            return;
        }

        await ReceiveFile(parts[1], fileSize);
        Console.Write("> ");
    }

    static async Task SendFile(string toUser, string filePath)
    {
        if (!File.Exists(filePath))
        {
            Console.WriteLine($"Файл не найден: {filePath}");
            return;
        }

        var info = new FileInfo(filePath);
        var fileName = info.Name;
        var fileSize = info.Length;

        Console.WriteLine($"Отправка '{fileName}' ({FormatSize(fileSize)}) → {toUser}");
        await _writer!.WriteLineAsync($"SEND:{toUser}:{fileName}:{fileSize}");

        // Ждём ответа: DECLINE или READY:SIZE:N или ERROR:
        var response = await _reader!.ReadLineAsync();
        if (response == null)
        {
            Console.WriteLine("Соединение потеряно");
            return;
        }

        if (response == "DECLINE" || response.StartsWith("ERROR:"))
        {
            Console.WriteLine($"❌ {response}");
            return;
        }

        if (!response.StartsWith("READY:SIZE:"))
        {
            Console.WriteLine($"❌ Неожиданный ответ: {response}");
            return;
        }

        Console.WriteLine($"{toUser} принял запрос. Передача...");

        using var progress = new ConsoleProgressBar("Отправка", fileSize);
        var buffer = new byte[BufferSize];
        long sent = 0;

        await using var fs = File.OpenRead(filePath);
        int read;
        while ((read = await fs.ReadAsync(buffer)) > 0)
        {
            await _stream!.WriteAsync(buffer.AsMemory(0, read));
            sent += read;
            progress.Update(read);
        }
        progress.Complete();

        // Ждём DONE
        var done = await _reader.ReadLineAsync();
        if (done == "DONE")
            Console.WriteLine("✅ Передача завершена!");
    }

    static async Task ReceiveFile(string fileName, long fileSize)
    {
        Directory.CreateDirectory(_downloadDir);
        var savePath = Path.Combine(_downloadDir, fileName);
        int counter = 1;
        var name = Path.GetFileNameWithoutExtension(fileName);
        var ext = Path.GetExtension(fileName);
        while (File.Exists(savePath))
        {
            savePath = Path.Combine(_downloadDir, $"{name} ({counter}){ext}");
            counter++;
        }

        using var progress = new ConsoleProgressBar("Получение", fileSize);
        var buffer = new byte[BufferSize];
        long received = 0;

        await using var fs = File.Create(savePath);

        while (received < fileSize)
        {
            var toRead = (int)Math.Min(buffer.Length, fileSize - received);
            var read = await _stream!.ReadAsync(buffer.AsMemory(0, toRead));
            if (read == 0) break;

            await fs.WriteAsync(buffer.AsMemory(0, read));
            received += read;
            progress.Update(read);
        }
        progress.Complete();
        Console.WriteLine($"✅ Файл сохранён: {savePath}");
    }

    static string ReadPassword()
    {
        var pwd = "";
        while (true)
        {
            var key = Console.ReadKey(true);
            if (key.Key == ConsoleKey.Enter) break;
            if (key.Key == ConsoleKey.Backspace && pwd.Length > 0)
            {
                pwd = pwd[..^1];
                Console.Write("\b \b");
            }
            else if (!char.IsControl(key.KeyChar))
            {
                pwd += key.KeyChar;
                Console.Write("*");
            }
        }
        return pwd;
    }

    static string FormatSize(long bytes)
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
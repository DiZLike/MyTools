using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;

namespace FileProxy.Server;

class Program
{
    const int DefaultPort = 5454;
    const int BufferSize = 8192;
    const int AcceptTimeoutSec = 30;

    static readonly ConcurrentDictionary<string, UserConnection> _users = new(StringComparer.OrdinalIgnoreCase);
    static readonly Dictionary<string, string> _credentials = new(StringComparer.OrdinalIgnoreCase);

    class UserConnection
    {
        public string Name { get; init; } = "";
        public TcpClient Client { get; init; } = null!;
        public NetworkStream Stream { get; init; } = null!;
        public StreamWriter Writer { get; init; } = null!;
        public bool Busy { get; set; }
        public TaskCompletionSource<bool>? AcceptTcs { get; set; }
    }

    static async Task Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;

        _credentials["анна"] = Hash("123");
        _credentials["борис"] = Hash("123");
        _credentials["diz"] = Hash("123");
        _credentials["qwe"] = Hash("123");

        var port = args.Length > 0 && int.TryParse(args[0], out var p) ? p : DefaultPort;
        var listener = new TcpListener(IPAddress.Any, port);
        listener.Start();
        Console.WriteLine($"[Сервер] Запущен на порту {port}");

        while (true)
        {
            var client = await listener.AcceptTcpClientAsync();
            Console.WriteLine($"[Сервер] Подключение от {client.Client.RemoteEndPoint}");
            _ = HandleClient(client);
        }
    }

    static async Task HandleClient(TcpClient client)
    {
        var stream = client.GetStream();
        var reader = new StreamReader(stream, Encoding.UTF8);
        var writer = new StreamWriter(stream, Encoding.UTF8) { AutoFlush = true };
        UserConnection? user = null;

        try
        {
            // АВТОРИЗАЦИЯ
            await writer.WriteLineAsync("LOGIN");
            var loginLine = await reader.ReadLineAsync();
            if (string.IsNullOrEmpty(loginLine)) return;

            var parts = loginLine.Split(':', 2);
            if (parts.Length != 2)
            {
                await writer.WriteLineAsync("ERROR:Формат: логин:пароль");
                return;
            }

            var username = parts[0];
            var password = parts[1];

            if (!_credentials.TryGetValue(username, out var hash) || hash != Hash(password))
            {
                await writer.WriteLineAsync("ERROR:Неверный логин или пароль");
                return;
            }

            if (_users.ContainsKey(username))
            {
                await writer.WriteLineAsync("ERROR:Пользователь уже в сети");
                return;
            }

            user = new UserConnection
            {
                Name = username,
                Client = client,
                Stream = stream,
                Writer = writer
            };
            _users[username] = user;
            await writer.WriteLineAsync("OK");
            Console.WriteLine($"[Сервер] {username} авторизован");

            // ОСНОВНОЙ ЦИКЛ
            while (true)
            {
                var command = await reader.ReadLineAsync();
                if (command == null) break;

                Console.WriteLine($"[Сервер] ← {username}: {command}");

                if (command == "EXIT") break;
                if (command == "LIST")
                {
                    var online = string.Join(",", _users.Keys.OrderBy(k => k));
                    await writer.WriteLineAsync($"ONLINE:{online}");
                    continue;
                }
                if (command == "ACCEPT")
                {
                    user.AcceptTcs?.TrySetResult(true);
                    user.AcceptTcs = null;
                    continue;
                }
                if (command == "DECLINE")
                {
                    user.AcceptTcs?.TrySetResult(false);
                    user.AcceptTcs = null;
                    continue;
                }
                if (command.StartsWith("SEND:"))
                {
                    var sendParts = command.Split(':', 4);
                    if (sendParts.Length < 4 || !long.TryParse(sendParts[3], out var fileSize))
                    {
                        await writer.WriteLineAsync("ERROR:Формат: SEND:кому:имя_файла:размер");
                        continue;
                    }
                    await ProcessSend(user, sendParts[1], sendParts[2], fileSize, reader, writer);
                    continue;
                }
                await writer.WriteLineAsync("ERROR:Неизвестная команда");
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[Сервер] Ошибка: {ex.Message}");
        }
        finally
        {
            if (user != null)
            {
                _users.TryRemove(user.Name, out _);
                Console.WriteLine($"[Сервер] {user.Name} отключился");
            }
            try { client.Close(); } catch { }
        }
    }

    static async Task ProcessSend(UserConnection sender, string toUser, string fileName, long fileSize,
        StreamReader reader, StreamWriter writer)
    {
        if (!_users.TryGetValue(toUser, out var receiver) || receiver.Busy)
        {
            await writer.WriteLineAsync($"ERROR:{toUser} не в сети или занят");
            return;
        }

        sender.Busy = true;
        receiver.Busy = true;

        var tcs = new TaskCompletionSource<bool>();
        receiver.AcceptTcs = tcs;

        try
        {
            // Отправляем запрос получателю
            await receiver.Writer.WriteLineAsync($"REQUEST:{sender.Name}:{fileName}:{fileSize}");
            Console.WriteLine($"[Сервер] Запрос отправлен {toUser}, ждём ответа...");

            // Ждём ACCEPT/DECLINE от получателя
            var timeout = Task.Delay(TimeSpan.FromSeconds(AcceptTimeoutSec));
            var completed = await Task.WhenAny(tcs.Task, timeout);

            if (completed == timeout)
            {
                receiver.AcceptTcs = null;
                await writer.WriteLineAsync("DECLINE");
                Console.WriteLine($"[Сервер] Таймаут ожидания ответа от {toUser}");
                return;
            }

            if (!tcs.Task.Result)
            {
                await writer.WriteLineAsync("DECLINE");
                Console.WriteLine($"[Сервер] {toUser} отклонил запрос");
                return;
            }

            Console.WriteLine($"[Сервер] {toUser} принял запрос");

            // Отправляем READY обеим сторонам
            await writer.WriteLineAsync($"READY:SIZE:{fileSize}");
            await receiver.Writer.WriteLineAsync($"READY:SIZE:{fileSize}");

            Console.WriteLine($"[Сервер] Начинаем передачу: {sender.Name} → {toUser}, {fileName}, {FormatSize(fileSize)}");

            // Ретрансляция байтов
            var buffer = new byte[BufferSize];
            long total = 0;

            while (total < fileSize)
            {
                var toRead = (int)Math.Min(buffer.Length, fileSize - total);
                var read = await sender.Stream.ReadAsync(buffer.AsMemory(0, toRead));
                if (read == 0) break;

                await receiver.Stream.WriteAsync(buffer.AsMemory(0, read));
                total += read;
            }

            Console.WriteLine($"[Сервер] Передано: {FormatSize(total)}");

            await writer.WriteLineAsync("DONE");
            await receiver.Writer.WriteLineAsync("DONE");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[Сервер] Ошибка передачи: {ex.Message}");
            try { await writer.WriteLineAsync("ERROR:Ошибка передачи"); } catch { }
            try { await receiver.Writer.WriteLineAsync("ERROR:Ошибка передачи"); } catch { }
        }
        finally
        {
            sender.Busy = false;
            receiver.Busy = false;
            receiver.AcceptTcs = null;
        }
    }

    static string Hash(string password)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(password + "salt"));
        return Convert.ToHexString(bytes);
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
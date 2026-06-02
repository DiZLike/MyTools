using System.Net.Sockets;

var host = "127.0.0.1";
var port = 4545;
var client_name = "diz";

Console.WriteLine("Подключаюсь...");
var client = new TcpClient(host, port);
Console.WriteLine("Подключился!");
using var stream  = client.GetStream();
using var reader = new StreamReader(stream);
using var writer = new StreamWriter(stream) { AutoFlush = true };



writer.WriteLine($"CLIENT_NAME:{client_name}");
var resp = reader.ReadLine();
Console.WriteLine(resp);
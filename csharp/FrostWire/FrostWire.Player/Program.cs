using FrostWire.Core.Configuration;
using FrostWire.Player;

var configPath = args.Length > 0 ? args[0] : "appsettings.json";
var config = ConfigLoader.Load(configPath);

Console.WriteLine("FrostWire Player");
Console.WriteLine($"Server: {config.Player.ServerAddress}:{config.Player.ServerPort}");

using var cts = new CancellationTokenSource();
var engine = new PlayerEngine(config);

Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    cts.Cancel();
};

try
{
    await engine.RunAsync(cts.Token);
}
catch (OperationCanceledException) { }

Console.WriteLine("Player stopped.");
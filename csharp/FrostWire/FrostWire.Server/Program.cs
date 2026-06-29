using FuzzCast.Core.Configuration;
using FuzzCast.Server;

var configPath = args.Length > 0 ? args[0] : "appsettings.json";
var config = ConfigLoader.Load(configPath);

Console.WriteLine($"FuzzCast Server starting on port {config.Server.ListenPort}...");

using var cts = new CancellationTokenSource();
var engine = new ServerEngine(config);

Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    Console.WriteLine("Shutting down...");
    cts.Cancel();
};

try
{
    await engine.RunAsync(cts.Token);
}
catch (OperationCanceledException)
{
    // нормальное завершение
}

Console.WriteLine("Server stopped.");
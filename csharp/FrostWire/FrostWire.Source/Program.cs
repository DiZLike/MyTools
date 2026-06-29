using FuzzCast.Core.Configuration;
using FuzzCast.Core.Native;
using FuzzCast.Source;

var configPath = args.Length > 0 ? args[0] : "appsettings.json";
var config = ConfigLoader.Load(configPath);

Console.WriteLine($"FuzzCast Source starting...");
Console.WriteLine($"Server: {config.Source.ServerAddress}:{config.Source.ServerPort}");
Console.WriteLine($"Playlist: {config.Source.PlaylistPath}");
Console.WriteLine($"[Opus] Version: {OpusNative.opus_get_version_string()}");

using var cts = new CancellationTokenSource();
var engine = new SourceEngine(config);

Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    Console.WriteLine("Stopping...");
    cts.Cancel();
};

try
{
    await engine.RunAsync(cts.Token);
}
catch (OperationCanceledException) { }

Console.WriteLine("Source stopped.");
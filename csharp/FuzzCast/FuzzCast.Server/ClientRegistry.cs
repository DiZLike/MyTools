using System.Collections.Concurrent;
using System.Net;

namespace FuzzCast.Server;

public class ClientRegistry
{
    private readonly ConcurrentDictionary<Guid, ClientEntry> _clients = new();

    public int Count => _clients.Count;

    public bool AddOrUpdate(Guid clientId, IPEndPoint endpoint, int subscribePort)
    {
        bool isNew = !_clients.ContainsKey(clientId);

        _clients.AddOrUpdate(clientId,
            _ => new ClientEntry { Endpoint = endpoint, LastSeen = DateTime.UtcNow, SubscribePort = subscribePort },
            (_, entry) =>
            {
                entry.Endpoint = endpoint;
                entry.LastSeen = DateTime.UtcNow;
                entry.SubscribePort = subscribePort;
                return entry;
            });

        return isNew;
    }

    public void Refresh(Guid clientId)
    {
        if (_clients.TryGetValue(clientId, out var entry))
            entry.LastSeen = DateTime.UtcNow;
    }

    public int RemoveTimedOut(int timeoutMs)
    {
        var cutoff = DateTime.UtcNow.AddMilliseconds(-timeoutMs);
        int removed = 0;

        foreach (var kvp in _clients)
        {
            if (kvp.Value.LastSeen < cutoff)
            {
                if (_clients.TryRemove(kvp.Key, out _))
                    removed++;
            }
        }

        return removed;
    }

    public void Remove(Guid clientId)
    {
        _clients.TryRemove(clientId, out _);
    }

    public IEnumerable<(IPEndPoint Endpoint, int SubscribePort)> GetByPort(int port)
    {
        return _clients.Values
            .Where(e => e.SubscribePort == port)
            .Select(e => (e.Endpoint, e.SubscribePort));
    }

    public IEnumerable<IPEndPoint> GetAllEndpoints()
    {
        return _clients.Values.Select(e => e.Endpoint);
    }

    public Guid? GetClientIdByEndpoint(IPEndPoint endpoint)
    {
        foreach (var kvp in _clients)
        {
            if (kvp.Value.Endpoint.Equals(endpoint))
                return kvp.Key;
        }
        return null;
    }

    private class ClientEntry
    {
        public IPEndPoint Endpoint { get; set; } = new(IPAddress.Any, 0);
        public DateTime LastSeen { get; set; }
        public int SubscribePort { get; set; }
    }
}
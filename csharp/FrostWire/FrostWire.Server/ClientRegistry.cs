using System.Collections.Concurrent;
using System.Net;

namespace FrostWire.Server;

public class ClientRegistry
{
    private readonly ConcurrentDictionary<Guid, ClientEntry> _clients = new();

    public int Count => _clients.Count;

    public bool AddOrUpdate(Guid clientId, IPEndPoint endpoint)
    {
        bool isNew = !_clients.ContainsKey(clientId);

        _clients.AddOrUpdate(clientId,
            _ => new ClientEntry { Endpoint = endpoint, LastSeen = DateTime.UtcNow },
            (_, entry) =>
            {
                entry.Endpoint = endpoint;
                entry.LastSeen = DateTime.UtcNow;
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

    public IEnumerable<IPEndPoint> GetAllEndpoints()
    {
        return _clients.Values.Select(e => e.Endpoint);
    }

    private class ClientEntry
    {
        public IPEndPoint Endpoint { get; set; } = new(IPAddress.Any, 0);
        public DateTime LastSeen { get; set; }
    }
}
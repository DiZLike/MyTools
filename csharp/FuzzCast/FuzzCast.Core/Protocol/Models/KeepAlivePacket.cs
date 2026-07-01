namespace FuzzCast.Core.Protocol.Models;

public class KeepAlivePacket
{
    public byte[] ClientId { get; set; } = Array.Empty<byte>();

    public KeepAlivePacket()
    {
    }

    public KeepAlivePacket(Guid clientId)
    {
        ClientId = clientId.ToByteArray();
    }

    public Guid GetClientId() => new Guid(ClientId);
}
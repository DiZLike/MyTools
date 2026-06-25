namespace FrostWire.Core.Protocol.Models;

public class SubscribePacket
{
    public byte[] ClientId { get; set; } = Array.Empty<byte>();

    public SubscribePacket()
    {
    }

    public SubscribePacket(Guid clientId)
    {
        ClientId = clientId.ToByteArray();
    }

    public Guid GetClientId() => new Guid(ClientId);
}
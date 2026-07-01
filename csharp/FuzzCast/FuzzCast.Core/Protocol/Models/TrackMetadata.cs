namespace FuzzCast.Core.Protocol.Models;

public class TrackMetadata
{
    public string Title { get; set; } = string.Empty;
    public string Artist { get; set; } = string.Empty;
    public string Album { get; set; } = string.Empty;
    public double Duration { get; set; }

    public bool IsEmpty => string.IsNullOrEmpty(Title) && string.IsNullOrEmpty(Artist);

    public byte[] Serialize()
    {
        var json = System.Text.Json.JsonSerializer.Serialize(this);
        return System.Text.Encoding.UTF8.GetBytes(json);
    }

    public static TrackMetadata Deserialize(byte[] data)
    {
        var json = System.Text.Encoding.UTF8.GetString(data);
        return System.Text.Json.JsonSerializer.Deserialize<TrackMetadata>(json) ?? new TrackMetadata();
    }
}
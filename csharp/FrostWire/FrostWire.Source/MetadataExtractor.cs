using FrostWire.Core.Protocol.Models;
using Un4seen.Bass;
using Un4seen.Bass.AddOn.Tags;

namespace FrostWire.Source;

public static class MetadataExtractor
{
    public static TrackMetadata Extract(string filePath)
    {
        var metadata = new TrackMetadata
        {
            Title = Path.GetFileNameWithoutExtension(filePath),
            Artist = "Unknown",
            Album = "",
            Duration = 0
        };

        try
        {
            int stream = Bass.BASS_StreamCreateFile(filePath, 0, 0, BASSFlag.BASS_STREAM_DECODE);
            if (stream != 0)
            {
                // Длительность
                long length = Bass.BASS_ChannelGetLength(stream);
                double seconds = Bass.BASS_ChannelBytes2Seconds(stream, length);
                metadata.Duration = Math.Round(seconds, 1);

                // ID3v2 теги через TAG_INFO
                var tagInfo = new TAG_INFO();
                tagInfo = BassTags.BASS_TAG_GetFromFile(stream, tagInfo) ? tagInfo : null;

                if (tagInfo != null)
                {
                    if (!string.IsNullOrEmpty(tagInfo.title))
                        metadata.Title = tagInfo.title;
                    if (!string.IsNullOrEmpty(tagInfo.artist))
                        metadata.Artist = tagInfo.artist;
                    if (!string.IsNullOrEmpty(tagInfo.album))
                        metadata.Album = tagInfo.album;
                }

                Bass.BASS_StreamFree(stream);
            }
        }
        catch
        {
            // fallback to filename
        }

        return metadata;
    }
}
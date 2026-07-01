using FuzzCast.Core.Protocol.Models;
using Un4seen.Bass;
using TagLib;

namespace FuzzCast.Source.Audio;

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
                long length = Bass.BASS_ChannelGetLength(stream);
                double seconds = Bass.BASS_ChannelBytes2Seconds(stream, length);
                metadata.Duration = Math.Round(seconds, 1);
                Bass.BASS_StreamFree(stream);
            }

            using var tagFile = TagLib.File.Create(filePath);
            var tag = tagFile.Tag;

            if (!string.IsNullOrEmpty(tag.Title))
                metadata.Title = tag.Title;
            if (!string.IsNullOrEmpty(tag.FirstPerformer))
                metadata.Artist = tag.FirstPerformer;
            if (!string.IsNullOrEmpty(tag.Album))
                metadata.Album = tag.Album;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[WARN] Metadata extraction failed for {Path.GetFileName(filePath)}: {ex.Message}");
        }

        return metadata;
    }
}
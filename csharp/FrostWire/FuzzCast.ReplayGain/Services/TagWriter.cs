using System.Globalization;
using FuzzCast.ReplayGain.Models;
using FuzzCast.ReplayGain.Helpers;
using TagLib;

namespace FuzzCast.ReplayGain.Services;

public class TagWriter
{
    private readonly string _commentFormat;

    public TagWriter(string commentFormat)
    {
        _commentFormat = commentFormat;
    }

    public bool Write(string filePath, ReplayGainResult result)
    {
        try
        {
            using var file = TagLib.File.Create(filePath);

            string rgComment = _commentFormat
                .Replace("{gain:0.00}", result.TrackGain.ToString("0.00", CultureInfo.InvariantCulture))
                .Replace("{peak:0.000000}", result.TrackPeak.ToString("0.000000", CultureInfo.InvariantCulture));

            // Получаем все типы тегов, присутствующие в файле
            TagTypes tagTypes = file.TagTypes;

            // Если тегов нет — создаём дефолтный для формата
            if (tagTypes == TagTypes.None)
            {
                tagTypes = GetDefaultTagType(filePath);
                if (tagTypes != TagTypes.None)
                {
                    file.GetTag(tagTypes, true); // Принудительно создаём
                }
            }

            // Проходим по каждому типу тегов и записываем RG
            foreach (TagTypes tagType in Enum.GetValues<TagTypes>())
            {
                if (tagType == TagTypes.None || !tagTypes.HasFlag(tagType))
                    continue;

                try
                {
                    var tag = file.GetTag(tagType);
                    if (tag != null)
                    {
                        string? oldComment = tag.Comment;

                        if (string.IsNullOrEmpty(oldComment) || !oldComment.Contains("REPLAYGAIN_TRACK_GAIN"))
                        {
                            tag.Comment = string.IsNullOrEmpty(oldComment)
                                ? rgComment
                                : oldComment + "\n" + rgComment;
                        }
                        else
                        {
                            var lines = oldComment.Split('\n')
                                .Where(l => !l.StartsWith("REPLAYGAIN_TRACK_GAIN") && !l.StartsWith("REPLAYGAIN_TRACK_PEAK"))
                                .ToList();

                            lines.Add(rgComment);
                            tag.Comment = string.Join("\n", lines);
                        }
                    }
                }
                catch
                {
                    // Пропускаем типы тегов, которые не поддерживаются в этом формате
                }
            }

            file.Save();
            return true;
        }
        catch (UnauthorizedAccessException)
        {
            Logger.Warn($"{Path.GetFileName(filePath)} -> Нет прав на запись тегов");
            return false;
        }
        catch (Exception ex)
        {
            Logger.Error($"{Path.GetFileName(filePath)} -> Ошибка записи тегов: {ex.Message}");
            return false;
        }
    }

    private static TagTypes GetDefaultTagType(string filePath)
    {
        string ext = Path.GetExtension(filePath).ToLowerInvariant();

        return ext switch
        {
            ".mp3" => TagTypes.Id3v2,
            ".flac" => TagTypes.Xiph,
            ".ogg" => TagTypes.Xiph,
            ".opus" => TagTypes.Xiph,
            ".wav" => TagTypes.RiffInfo,
            ".wma" => TagTypes.Asf,
            ".m4a" => TagTypes.Apple,
            ".aac" => TagTypes.Apple,
            ".ape" => TagTypes.Ape,
            ".wv" => TagTypes.Ape,
            _ => TagTypes.None
        };
    }
}
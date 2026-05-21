using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json.Serialization;

namespace IconFinder.Models
{
    public class UsingInfo
    {
        [JsonPropertyName("runCount")]
        public int RunCount { get; set; } = 0;
        [JsonPropertyName("drugCount")]
        public int DrugCount { get; set; } = 0;
        [JsonPropertyName("svgSaveCount")]
        public int SvgSaveCount { get; set; } = 0;
        [JsonPropertyName("pngSaveCount")]
        public int PngSaveCount { get; set; } = 0;
        [JsonPropertyName("icoSaveCount")]
        public int IcoSaveCount { get; set; } = 0;
        [JsonPropertyName("webpSaveCount")]
        public int WebpSaveCount { get; set; } = 0;
        [JsonIgnore]
        public int TotalSaveCount { get => DrugCount + SvgSaveCount + PngSaveCount + IcoSaveCount + WebpSaveCount; }

        public void AddRun() => RunCount++;
        public void AddDrug() => DrugCount++;
        public void AddSvg() => SvgSaveCount++;
        public void AddPng() => PngSaveCount++;
        public void AddIco() => IcoSaveCount++;
        public void AddWebp() => WebpSaveCount++;
    }
}

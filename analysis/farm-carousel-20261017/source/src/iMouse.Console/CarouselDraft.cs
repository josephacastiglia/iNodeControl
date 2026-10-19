using System.IO;
using System.Text.Json;

namespace IMouse2;

internal sealed class CarouselValidation
{
    public string[] Errors { get; set; } = [];
    public string[] Warnings { get; set; } = [];
}

internal sealed class CarouselSlide
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Preview { get; set; } = "";
    public string Sha256 { get; set; } = "";
    public int Width { get; set; }
    public int Height { get; set; }
}

internal sealed class CarouselDraft
{
    public string Id { get; set; } = "";
    public string Title { get; set; } = "";
    public string Caption { get; set; } = "";
    public int Revision { get; set; }
    public string[] SlideIds { get; set; } = [];
    public CarouselSlide[] Slides { get; set; } = [];
    public CarouselValidation Validation { get; set; } = new();
    public bool SavedInInstagram { get; set; }
    public static CarouselDraft Read(JsonElement root) => root.GetProperty("draft").Deserialize<CarouselDraft>(new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
        ?? throw new InvalidOperationException("Draft response was empty.");
}

internal sealed record CarouselEdits(string DraftId, int Revision, string Title, string Caption, string[] SlideIds, bool Unsaved, string Mode);

/// <summary>Keep in-progress edits in this console's own data folder, including after a crash.</summary>
internal sealed class CarouselRecovery(string folder)
{
    private string FilePath => Path.Combine(folder, "farm-carousel-edits.json");
    internal CarouselEdits? Load()
    {
        if (!File.Exists(FilePath)) return null;
        byte[] bytes = File.ReadAllBytes(FilePath);
        try
        {
            var edits = JsonSerializer.Deserialize<CarouselEdits>(bytes);
            if (edits is not null && (!Guid.TryParse(edits.DraftId, out _) || edits.Revision < 1 ||
                    edits.Mode is not ("live" or "simulate") || edits.Title is null || edits.Caption is null || edits.SlideIds is null))
                throw new JsonException("Invalid saved editing session.");
            return edits;
        }
        catch (JsonException ex)
        {
            string archive = Path.Combine(folder, "farm-carousel-damaged-" + Guid.NewGuid().ToString("N") + ".json");
            SettingsPersistence.WriteAtomic(archive, bytes);
            throw new InvalidOperationException("Saved edits could not be read. The original bytes are preserved in " + archive, ex);
        }
    }
    internal void Save(CarouselEdits edits) => SettingsPersistence.WriteAtomic(FilePath, JsonSerializer.SerializeToUtf8Bytes(edits));
    internal string Archive(CarouselEdits edits)
    {
        string path = Path.Combine(folder, "farm-carousel-edits-" + Guid.NewGuid().ToString("N") + ".json");
        SettingsPersistence.WriteAtomic(path, JsonSerializer.SerializeToUtf8Bytes(edits));
        return path;
    }
}

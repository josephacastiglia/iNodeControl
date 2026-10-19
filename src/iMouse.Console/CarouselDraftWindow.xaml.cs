using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media.Imaging;
using Microsoft.Win32;

namespace IMouse2;

public partial class CarouselDraftWindow : Window
{
    private readonly FarmApiClient _api;
    private readonly CarouselRecovery _recovery;
    private readonly string _mode;
    private readonly string _dataFolder;
    private readonly string? _initialDraftId;
    private readonly ObservableCollection<CarouselSlide> _slides = [];
    private CarouselDraft? _draft;
    private bool _loading, _busy, _dirty;
    private sealed record LibraryDraft(string Id, string Title)
    {
        public override string ToString() => Title;
    }

    internal CarouselDraftWindow(FarmApiClient api, string dataFolder, string mode, string? initialDraftId = null)
    {
        _api = api;
        _recovery = new CarouselRecovery(dataFolder);
        _mode = mode;
        _dataFolder = dataFolder;
        _initialDraftId = initialDraftId is null ? null : Guid.Parse(initialDraftId).ToString();
        InitializeComponent();
        SlidesList.ItemsSource = _slides;
        Loaded += async (_, _) => await RunAsync(InitializeAsync);
        Closing += (_, e) =>
        {
            if (_busy) { e.Cancel = true; StatusText.Text = "Wait for the current draft operation to finish before closing."; }
            else if (_dirty)
            {
                try { PersistEdits(); }
                catch (Exception ex) { e.Cancel = true; StatusText.Text = "Edits could not be kept: " + ex.Message; }
            }
        };
    }

    private async Task RunAsync(Func<Task> action, bool phoneWorkflow = false)
    {
        if (_busy) return;
        _busy = true;
        LibraryControls.IsEnabled = EditorControls.IsEnabled = false;
        try { await action(); }
        catch (Exception ex) { StatusText.Text = ex.Message + (phoneWorkflow
            ? " Reopen Check phone draft to retrieve any saved request. No check is replayed."
            : " No phone action was sent."); }
        finally
        {
            _busy = false;
            LibraryControls.IsEnabled = true;
            EditorControls.IsEnabled = _draft is not null;
        }
    }

    private async Task RefreshLibraryAsync()
    {
        var result = await _api.SendAsync("/api/farm/drafts");
        var rows = result.GetProperty("drafts").EnumerateArray().Select(d => new LibraryDraft(d.GetProperty("id").GetString()!, d.GetProperty("title").GetString()!)).ToArray();
        DraftList.ItemsSource = rows;
        DraftList.SelectedItem = rows.FirstOrDefault(d => d.Id == _draft?.Id) ?? rows.FirstOrDefault();
    }

    private async Task InitializeAsync()
    {
        await RefreshLibraryAsync();
        var edits = _recovery.Load();
        if (_initialDraftId is not null && (edits is null || edits.DraftId != _initialDraftId || edits.Mode != _mode))
        {
            // Read the requested draft before replacing any recovery pointer.
            var requested = CarouselDraft.Read(await _api.SendAsync("/api/farm/drafts/" + _initialDraftId));
            if (requested.Id != _initialDraftId) throw new InvalidOperationException("The backend returned a different draft. Previous edits were kept.");
            string? backup = edits?.Unsaved == true ? _recovery.Archive(edits) : null;
            Apply(requested); PersistEdits();
            StatusText.Text = "Opened this preparation's saved local draft. Nothing was sent to a phone."
                + (backup is null ? "" : " Other unsaved edits preserved in " + backup);
            return;
        }
        if (edits is null) { StatusText.Text = "Open a saved draft or create one. Drafts stay on this PC."; return; }
        if (edits.Mode != _mode)
        {
            string backup = _recovery.Archive(edits);
            StatusText.Text = "Previous mode's editing session kept in " + backup;
            return;
        }
        CarouselDraft draft;
        try { draft = CarouselDraft.Read(await _api.SendAsync("/api/farm/drafts/" + Uri.EscapeDataString(edits.DraftId))); }
        catch
        {
            if (edits.Unsaved) _recovery.Archive(edits);
            throw;
        }
        if (edits.Unsaved && (edits.Revision != draft.Revision || edits.SlideIds.Any(id => !draft.Slides.Any(s => s.Id == id))))
        {
            string backup = _recovery.Archive(edits);
            Apply(draft);
            PersistEdits();
            StatusText.Text = "Opened the newer saved revision. Conflicting local edits preserved in " + backup;
            return;
        }
        Apply(draft);
        if (edits.Unsaved)
        {
            _loading = true;
            try
            {
                TitleBox.Text = edits.Title;
                CaptionBox.Text = edits.Caption;
                _slides.Clear();
                foreach (string id in edits.SlideIds) _slides.Add(draft.Slides.First(s => s.Id == id));
            }
            finally { _loading = false; }
            _dirty = true;
            UpdateCounts();
            StatusText.Text = "Restored your unsaved edits. Save draft to commit them.";
        }
        else StatusText.Text = "Reopened your last saved local draft.";
    }

    private void Apply(CarouselDraft draft)
    {
        _loading = true;
        try
        {
            _draft = draft;
            TitleBox.Text = draft.Title;
            CaptionBox.Text = draft.Caption;
            _slides.Clear();
            foreach (var slide in draft.Slides) _slides.Add(slide);
            SlidesList.SelectedIndex = _slides.Count > 0 ? 0 : -1;
            ValidationText.Text = string.Join("\n\n", draft.Validation.Errors.Concat(draft.Validation.Warnings));
            _dirty = false;
            UpdateCounts();
        }
        finally { _loading = false; }
    }

    private void UpdateCounts()
    {
        if (CaptionCount is not null) CaptionCount.Text = $"{CaptionBox.Text.EnumerateRunes().Count()} / 2200 · {_slides.Count} / 10 slides";
    }

    private void PersistEdits()
    {
        if (_draft is null) return;
        _recovery.Save(new CarouselEdits(_draft.Id, _draft.Revision, TitleBox.Text, CaptionBox.Text,
            _slides.Select(s => s.Id).ToArray(), _dirty, _mode));
    }

    private void Changed()
    {
        if (_loading || _draft is null) return;
        _dirty = true;
        UpdateCounts();
        try { PersistEdits(); StatusText.Text = "Unsaved changes kept locally for recovery. Choose Save draft when ready."; }
        catch (Exception ex) { StatusText.Text = "Could not preserve these edits: " + ex.Message; }
    }

    private void Edit_Changed(object sender, TextChangedEventArgs e) => Changed();

    private async Task SaveAsync()
    {
        if (_draft is null) throw new InvalidOperationException("Open or create a draft first.");
        if (!_dirty) return;
        PersistEdits();
        var result = await _api.SendAsync($"/api/farm/drafts/{_draft.Id}/save", new
        {
            revision = _draft.Revision, title = TitleBox.Text, caption = CaptionBox.Text,
            slide_ids = _slides.Select(s => s.Id).ToArray()
        });
        Apply(CarouselDraft.Read(result));
        PersistEdits();
        StatusText.Text = $"Saved on this PC · revision {_draft.Revision} · Instagram save not verified.";
        await RefreshLibraryAsync();
    }

    private async Task CreateAsync(bool generated)
    {
        await SaveBeforeLeavingAsync();
        var result = await _api.SendAsync("/api/farm/drafts", new { id = Guid.NewGuid().ToString(), from_generated = generated });
        Apply(CarouselDraft.Read(result));
        PersistEdits();
        await RefreshLibraryAsync();
        StatusText.Text = generated ? "Generated images copied into an independent draft. Review the caption and slide order." : "Empty local draft created. Add JPEG or PNG images.";
    }

    private Task SaveBeforeLeavingAsync() => _dirty ? SaveAsync() : Task.CompletedTask;
    private async void PhoneDraft_Click(object sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        await SaveBeforeLeavingAsync();
        if (_draft is null) return;
        new FarmDraftRunWindow(_api, _dataFolder, _draft.Id, _draft.Revision, _draft.Title) { Owner = this }.ShowDialog();
    }, phoneWorkflow: true);

    private async void Rehearsal_Click(object sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        if (_draft is null) throw new InvalidOperationException("Open a local draft first.");
        await SaveBeforeLeavingAsync();
        new FarmDraftRehearsalWindow(_api, _draft.Id, _draft.Revision, _draft.Title) { Owner = this }.ShowDialog();
    });
    private async void Verification_Click(object sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        if (_draft is null) throw new InvalidOperationException("Open a local draft first.");
        await SaveBeforeLeavingAsync();
        new FarmDraftVerificationWindow(_api, _draft.Id, _draft.Revision, _draft.Title) { Owner = this }.ShowDialog();
    });
    private async void New_Click(object sender, RoutedEventArgs e) => await RunAsync(() => CreateAsync(false));
    private async void Generated_Click(object sender, RoutedEventArgs e) => await RunAsync(() => CreateAsync(true));
    private async void Save_Click(object sender, RoutedEventArgs e) => await RunAsync(SaveAsync);

    private async void Open_Click(object sender, RoutedEventArgs e)
    {
        if (DraftList.SelectedItem is not LibraryDraft selected) return;
        await RunAsync(async () =>
        {
            await SaveBeforeLeavingAsync();
            Apply(CarouselDraft.Read(await _api.SendAsync("/api/farm/drafts/" + selected.Id)));
            PersistEdits();
            StatusText.Text = "Local draft opened. Nothing sent to Instagram.";
        });
    }

    private async void Reload_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _draft is null) return;
        await RunAsync(async () =>
        {
            string? backup = null;
            if (_dirty)
            {
                PersistEdits();
                backup = _recovery.Archive(_recovery.Load()!);
            }
            Apply(CarouselDraft.Read(await _api.SendAsync("/api/farm/drafts/" + _draft.Id)));
            PersistEdits();
            StatusText.Text = backup is null ? "Reloaded saved draft." : "Reloaded saved draft. Previous edits preserved in " + backup;
        });
    }

    private async void Add_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _draft is null) return;
        var picker = new OpenFileDialog { Filter = "Images (*.jpg;*.jpeg;*.png)|*.jpg;*.jpeg;*.png", Multiselect = true };
        if (picker.ShowDialog(this) != true) return;
        await RunAsync(async () =>
        {
            await SaveAsync();
            if (_slides.Count + picker.FileNames.Length > 10) throw new InvalidOperationException("Choose at most 10 images in total.");
            int added = 0;
            try
            {
                foreach (string file in picker.FileNames)
                {
                    var info = new FileInfo(file);
                    if (info.Length > 8 * 1024 * 1024) throw new InvalidOperationException(info.Name + " exceeds 8 MiB.");
                    var bytes = await File.ReadAllBytesAsync(file);
                    var result = await _api.SendAsync($"/api/farm/drafts/{_draft!.Id}/import", new { revision = _draft.Revision, name = info.Name, content = Convert.ToBase64String(bytes) });
                    Apply(CarouselDraft.Read(result));
                    PersistEdits();
                    added++;
                }
            }
            catch (Exception ex) { throw new InvalidOperationException($"{added} image(s) saved; import stopped. Reopen the draft if the last response was lost. {ex.Message}"); }
            StatusText.Text = $"{added} images imported and saved. Check the fitted previews.";
        });
    }

    private void Move(int direction)
    {
        int current = SlidesList.SelectedIndex, next = current + direction;
        if (_busy || current < 0 || next < 0 || next >= _slides.Count) return;
        _slides.Move(current, next);
        SlidesList.SelectedIndex = next;
        Changed();
        UpdatePreview();
    }
    private void Earlier_Click(object sender, RoutedEventArgs e) => Move(-1);
    private void Later_Click(object sender, RoutedEventArgs e) => Move(1);
    private void Remove_Click(object sender, RoutedEventArgs e)
    {
        if (!_busy && SlidesList.SelectedItem is CarouselSlide slide) { _slides.Remove(slide); Changed(); UpdatePreview(); }
    }
    private void Slide_Changed(object sender, SelectionChangedEventArgs e) => UpdatePreview();
    private void UpdatePreview()
    {
        if (SlidePreview is null || SlideNumber is null) return;
        SlidePreview.Source = null;
        SlideNumber.Text = "Select a slide";
        if (SlidesList.SelectedItem is not CarouselSlide slide) return;
        try
        {
            using var stream = new MemoryStream(Convert.FromBase64String(slide.Preview));
            var image = new BitmapImage();
            image.BeginInit(); image.CacheOption = BitmapCacheOption.OnLoad; image.StreamSource = stream; image.EndInit(); image.Freeze();
            SlidePreview.Source = image;
            SlideNumber.Text = $"Slide {SlidesList.SelectedIndex + 1} of {_slides.Count}";
        }
        catch (Exception ex) { StatusText.Text = "Preview unavailable: " + ex.Message; }
    }

    private async void Export_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _draft is null) return;
        var picker = new SaveFileDialog { Filter = "Draft review package (*.zip)|*.zip", FileName = "instagram-carousel.zip" };
        if (picker.ShowDialog(this) != true) return;
        await RunAsync(async () =>
        {
            await SaveAsync();
            var result = await _api.SendAsync($"/api/farm/drafts/{_draft!.Id}/export", new { revision = _draft.Revision });
            SettingsPersistence.WriteAtomic(picker.FileName, Convert.FromBase64String(result.GetProperty("content").GetString()!));
            StatusText.Text = "Exported ordered slides, caption, review page and checksums. Not uploaded or saved in Instagram.";
        });
    }

    private async void Transfer_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _draft is null) return;
        CarouselDraft? saved = null;
        await RunAsync(async () => { await SaveAsync(); saved = _draft; });
        if (saved is not null)
            new CarouselTransferWindow(_api, saved) { Owner = this }.ShowDialog();
    }
}

using System.Globalization;
using System.Net.Http.Headers;

namespace IMouse2;

/// <summary>Receiver delivery age, not phone capture time. Missing or malformed headers
/// are unknown. Request duration is included conservatively in the age estimate.</summary>
public sealed record ScreenshotMetadata(string Session, long Sequence, double AgeMs, string Delivery)
{
    public static ScreenshotMetadata? Parse(HttpResponseHeaders headers, double requestMs)
    {
        string? One(string key) => headers.TryGetValues(key, out var values) && values.Count() == 1 ? values.First() : null;
        string? session = One("X-iMouse-Frame-Session"), state = One("X-iMouse-Frame-Delivery");
        if (!Guid.TryParseExact(session, "N", out _)
            || !long.TryParse(One("X-iMouse-Frame-Sequence"), NumberStyles.None, CultureInfo.InvariantCulture, out long seq) || seq < 1
            || !double.TryParse(One("X-iMouse-Frame-Age-Ms"), NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out double age)
            || !double.IsFinite(age) || age < 0 || !double.IsFinite(requestMs) || requestMs < 0
            || state is not ("flowing" or "quiet")) return null;
        age += requestMs;
        return double.IsFinite(age) ? new(session!, seq, age, state) : null;
    }
}

public sealed record PreviewStamp(int Epoch, long Revision, ScreenshotMetadata? Metadata, long ObservedAt);
public sealed record PreviewStatus(string State, double? AgeMs, bool FetchFailed)
{
    public string Text => FetchFailed ? "Preview not updating — image may be old"
        : State switch {
            "waiting" => "Waiting for preview",
            "unknown" => "Preview age unavailable",
            "quiet" => $"Preview may be old (about {AgeMs / 1000:0.#} s) — screen may be still",
            _ => "Preview recently received"
        };
}

/// <summary>Thread-safe freshness of the bitmap actually presented. Content revisions
/// allow identical pixels to refresh delivery without redrawing. A fetched frame that
/// was skipped or replaced must not refresh a different displayed image.</summary>
public sealed class PreviewFreshness
{
    private readonly object _gate = new();
    private readonly TimeProvider _clock;
    private int _epoch;
    private long _revision, _lastRequest;
    private PreviewStamp? _latest, _shown, _lastEvidence;
    private string? _source;
    private bool _fetchFailed;
    public PreviewFreshness(TimeProvider? clock = null) => _clock = clock ?? TimeProvider.System;
    public void Reset(int epoch)
    {
        lock (_gate) { _epoch = epoch; _revision = 0; _lastRequest = 0; _latest = _shown = _lastEvidence = null; _source = null; _fetchFailed = false; }
    }
    public PreviewStamp? Observe(int epoch, bool samePixels, ScreenshotMetadata? metadata, string source = "pump", long requestSerial = 0)
    {
        lock (_gate)
        {
            if (epoch != _epoch || (requestSerial > 0 && requestSerial < _lastRequest)) return null;
            _lastRequest = Math.Max(_lastRequest, requestSerial);
            long now = _clock.GetTimestamp();
            // A repeated delivery identity cannot become younger just because it was polled again.
            if (_lastEvidence is { Metadata: { } old } previous && metadata is { } next && old.Session == next.Session)
            {
                if (next.Sequence < old.Sequence) metadata = null; // inconsistent stream, not fresh evidence
                else if (next.Sequence == old.Sequence)
                    metadata = next with { AgeMs = Math.Max(next.AgeMs, Age(previous, now)!.Value) };
            }
            if (!samePixels || _latest is null || _source != source) _revision++;
            _source = source;
            _latest = new(epoch, _revision, metadata, now);
            if (metadata is not null) _lastEvidence = _latest;
            if (_shown?.Revision == _revision) _shown = _latest;
            _fetchFailed = false;
            return _latest;
        }
    }
    public bool IsCurrent(PreviewStamp stamp) { lock (_gate) return stamp.Epoch == _epoch && (_shown is null || stamp.Revision >= _shown.Revision); }
    public void Presented(PreviewStamp stamp)
    {
        lock (_gate)
        {
            if (stamp.Epoch != _epoch || (_shown is not null && stamp.Revision < _shown.Revision)) return;
            _shown = _latest?.Revision == stamp.Revision ? _latest : stamp;
        }
    }
    public void Failed(int epoch, long requestSerial = 0)
    {
        lock (_gate)
        {
            if (epoch != _epoch || (requestSerial > 0 && requestSerial < _lastRequest)) return;
            _lastRequest = Math.Max(_lastRequest, requestSerial);
            _fetchFailed = true;
        }
    }
    private double? Age(PreviewStamp stamp, long now) => stamp.Metadata is { } m
        ? m.AgeMs + Math.Max(0, _clock.GetElapsedTime(stamp.ObservedAt, now).TotalMilliseconds) : null;
    public PreviewStatus Status
    {
        get
        {
            lock (_gate)
            {
                if (_shown is null) return new("waiting", null, _fetchFailed);
                double? age = Age(_shown, _clock.GetTimestamp());
                return new(age is null ? "unknown" : age >= 2000 || _shown.Metadata?.Delivery == "quiet" ? "quiet" : "recent",
                    age, _fetchFailed);
            }
        }
    }
}

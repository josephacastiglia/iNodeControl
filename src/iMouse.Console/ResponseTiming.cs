namespace IMouse2;

public sealed record TimedAction(long Id, int Epoch, string Targets, string Origin, string Operation);
public sealed record ResponseTimingEvent(long Index, long Timestamp, string Kind, int Epoch,
    string Targets, long? ActionId = null, string? Origin = null, string? Operation = null,
    string? Outcome = null, string? FrameSession = null, long? FrameSequence = null,
    long? ContentRevision = null, int? Width = null, int? Height = null);
public sealed record ResponseTimingSnapshot(int SchemaVersion, string RecordingId, DateTimeOffset StartedUtc,
    long TimestampFrequency, long CapturedAt, int Capacity, long DroppedEvents,
    string Scope, ResponseTimingEvent[] Events);

/// <summary>Opt-in, bounded in-memory observations from one monotonic clock.
/// Bitmap application is not a physical display scan or proof that the requested
/// result is correct. No I/O, image pixels, key payloads or lease tokens are collected.</summary>
public sealed class ResponseTiming
{
    private readonly object _gate = new();
    private readonly TimeProvider _clock;
    private readonly List<ResponseTimingEvent> _events = [];
    private readonly int _capacity;
    private readonly string _recordingId = Guid.NewGuid().ToString("N");
    private readonly DateTimeOffset _startedUtc;
    private long _index, _action, _dropped;

    public ResponseTiming(TimeProvider? clock = null, int capacity = 4096)
    {
        if (capacity < 1 || capacity > 65536) throw new ArgumentOutOfRangeException(nameof(capacity));
        _clock = clock ?? TimeProvider.System;
        if (_clock.TimestampFrequency <= 0) throw new ArgumentException("Clock frequency must be positive.", nameof(clock));
        _capacity = capacity;
        _startedUtc = _clock.GetUtcNow();
    }

    public static ResponseTiming? FromSetting(string? setting) => setting == "1" ? new() : null;

    // Called only under _gate. Stop retaining at the limit; never silently replace
    // the beginning of a trial with later frames. The export declares every omission.
    private void Add(ResponseTimingEvent item)
    {
        if (_events.Count < _capacity) _events.Add(item);
        else _dropped++;
    }

    public TimedAction Begin(int epoch, string targets, string origin, string operation)
    {
        lock (_gate)
        {
            var action = new TimedAction(++_action, epoch, targets, origin, operation);
            Add(new(++_index, _clock.GetTimestamp(), "action_requested", epoch, targets,
                action.Id, origin, operation));
            return action;
        }
    }

    public void CommandStarted(TimedAction action) => ActionEvent(action, "command_started", null);
    public void End(TimedAction action, string outcome) => ActionEvent(action, "action_finished", outcome);
    private void ActionEvent(TimedAction action, string kind, string? outcome)
    {
        lock (_gate) Add(new(++_index, _clock.GetTimestamp(), kind, action.Epoch, action.Targets,
            action.Id, action.Origin, action.Operation, outcome));
    }

    public void Reset(int epoch)
    {
        lock (_gate) Add(new(++_index, _clock.GetTimestamp(), "preview_reset", epoch, ""));
    }

    public void BitmapApplied(int epoch, string phone, PreviewStamp? stamp, int width, int height, string source)
    {
        lock (_gate) Add(new(++_index, _clock.GetTimestamp(), "bitmap_applied", epoch, phone,
            Origin: source, FrameSession: stamp?.Metadata?.Session, FrameSequence: stamp?.Metadata?.Sequence,
            ContentRevision: stamp?.Revision, Width: width, Height: height));
    }

    public ResponseTimingSnapshot Snapshot()
    {
        lock (_gate) return new(1, _recordingId, _startedUtc, _clock.TimestampFrequency,
            _clock.GetTimestamp(), _capacity, _dropped,
            "Console handler entry, queued command start/completion, and selected-preview bitmap application. " +
            "Not physical click time, compositor scan-out, or correctness evidence. Frames are not attributed " +
            "to an action automatically. Missing events invalidate timing conclusions. Wall, drag and Send text paths are not traced.",
            _events.ToArray());
    }

    public static string Operation(string function, object? key) => function switch
    {
        "/mouse/click" => "tap", "/mouse/reset" => "pointer_reset", "/mouse/swipe" => "swipe",
        "/key/sendkey" => key is "Home" or "AppSwitch" or "ControlBar" ? (string)key : "key",
        _ => "other"
    };
}

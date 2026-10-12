namespace IMouse2;

/// <summary>Rate of bitmap presentations, not source frames or physical display scans.
/// A still image may need no presentations; zero does not by itself mean a freeze.</summary>
public sealed class RateMeter
{
    private readonly Queue<long> _stamps = new();
    private readonly TimeProvider _clock;
    public RateMeter(TimeProvider? clock = null) => _clock = clock ?? TimeProvider.System;
    private void Trim(long now)
    {
        while (_stamps.Count > 0 && _clock.GetElapsedTime(_stamps.Peek(), now).TotalSeconds > 2)
            _stamps.Dequeue();
    }
    public void Mark()
    {
        long now = _clock.GetTimestamp();
        _stamps.Enqueue(now);
        Trim(now);
    }
    public double Fps
    {
        get
        {
            long now = _clock.GetTimestamp();
            Trim(now); // A stalled stream has no Mark call to expire the window.
            if (_stamps.Count < 2) return 0;
            double span = _clock.GetElapsedTime(_stamps.Peek(), now).TotalSeconds;
            return span <= 0 ? 0 : (_stamps.Count - 1) / span;
        }
    }
    public void Reset() => _stamps.Clear();
}

/// <summary>Last 240 completed presentation intervals. Includes long pauses.
/// These are UI bitmap-copy intervals, not proof of compositor or phone freshness.
/// Accessed on the UI thread. A pending gap is exposed separately from completed ones.</summary>
public sealed class JitterMeter
{
    private readonly double[] _gaps = new double[240];
    private readonly TimeProvider _clock;
    private int _count, _next;
    private long? _last;
    public JitterMeter(TimeProvider? clock = null) => _clock = clock ?? TimeProvider.System;
    public void Mark()
    {
        long now = _clock.GetTimestamp();
        if (_last is { } last)
        {
            double ms = _clock.GetElapsedTime(last, now).TotalMilliseconds;
            if (ms > 0)
            {
                _gaps[_next] = ms;
                _next = (_next + 1) % _gaps.Length;
                if (_count < _gaps.Length) _count++;
            }
        }
        _last = now;
    }
    public double? SinceLastMs => _last is { } last
        ? _clock.GetElapsedTime(last, _clock.GetTimestamp()).TotalMilliseconds : null;

    /// <summary>Completed gaps: median, 95th percentile, maximum and count over 45 ms.</summary>
    public (double P50, double P95, double Max, int Long) Summary()
    {
        if (_count == 0) return (0, 0, 0, 0);
        var window = new double[_count];
        Array.Copy(_gaps, window, _count);
        Array.Sort(window);
        int over = 0;
        foreach (var g in window) if (g > 45) over++;
        return (window[_count / 2], window[Math.Min(_count - 1, (int)(_count * 0.95))], window[^1], over);
    }
    public void Reset() { _count = 0; _next = 0; _last = null; }
}

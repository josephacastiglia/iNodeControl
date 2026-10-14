namespace IMouse2.Kernel;

public sealed record HidReplySnapshot(string State, long Connection, long Reports, long MovementSignals,
    long StatusReports, long IdentifierReports, long UnknownReports, long InvalidReports,
    string? LastFamily, long? LastReportAgeMs, string? ErrorType,
    string Meaning = "Diagnostic observations only; not command acknowledgement or iOS success");

/// <summary>Constant-sized telemetry. No raw payload, identifier, command token or text is retained.</summary>
public sealed class HidReplyTelemetry
{
    private readonly object _gate = new();
    private readonly Func<long> _clock;
    private string _state = "not-opened";
    private long _connection, _reports, _movement, _status, _identifiers, _unknown, _invalid;
    private long? _lastAt;
    private string? _lastFamily, _error;
    public HidReplyTelemetry() : this(() => Environment.TickCount64) { }
    internal HidReplyTelemetry(Func<long> clock) => _clock = clock;
    internal void Started()
    {
        lock (_gate)
        {
            _connection++; _reports = _movement = _status = _identifiers = _unknown = _invalid = 0;
            _state = "awaiting-report"; _lastAt = null; _lastFamily = _error = null;
        }
    }
    internal void Observe(ReadOnlySpan<byte> bytes)
    {
        lock (_gate)
        {
            try
            {
                var report = HidInputReport.Parse(bytes);
                _reports++; _lastAt = _clock(); _lastFamily = report.Family.ToString("X2");
                _state = "receiving";
                switch (report.Kind)
                {
                    case "vendor-movement-signal": _movement++; break;
                    case "vendor-status": _status++; break;
                    case "vendor-identifier": _identifiers++; break;
                    default: _unknown++; break;
                }
            }
            catch (InvalidDataException) { _invalid++; }
        }
    }
    internal void Failed(string state, Exception ex) { lock (_gate) { _state = state; _error = ex.GetType().Name; } }
    internal void Stopped() { lock (_gate) { if (_error is null) _state = "stopped"; } }
    public HidReplySnapshot Snapshot()
    {
        lock (_gate) return new(_state, _connection, _reports, _movement, _status, _identifiers, _unknown,
            _invalid, _lastFamily, _lastAt is { } at ? Math.Max(0, _clock() - at) : null, _error);
    }
}

/// <summary>Optional observation only. Never gates writes, retries a command or changes phone state.</summary>
internal sealed class HidReplyMonitor : IDisposable
{
    private readonly Stream _stream;
    private readonly HidReplyTelemetry _telemetry;
    private readonly CancellationTokenSource _cancel = new();
    private readonly Task _pump;
    private readonly object _stopGate = new();
    private Task? _stop;

    internal HidReplyMonitor(Stream stream, HidReplyTelemetry telemetry, Action<byte[]>? evidence = null)
    {
        _stream = stream; _telemetry = telemetry;
        _telemetry.Started();
        _pump = PumpAsync(evidence);
    }
    internal Task Completion => _pump;
    private async Task PumpAsync(Action<byte[]>? evidence)
    {
        var buffer = new byte[HidInputReport.WindowsReportLength];
        try
        {
            while (true)
            {
                _cancel.Token.ThrowIfCancellationRequested();
                int count = await _stream.ReadAsync(buffer, _cancel.Token).ConfigureAwait(false);
                if (count == 0) throw new EndOfStreamException("HID input stream ended.");
                _telemetry.Observe(buffer.AsSpan(0, count));
                evidence?.Invoke(buffer.AsSpan(0, count).ToArray());
            }
        }
        catch (OperationCanceledException) when (_cancel.IsCancellationRequested) { }
        catch (ObjectDisposedException) when (_cancel.IsCancellationRequested) { }
        catch (IOException) when (_cancel.IsCancellationRequested) { }
        catch (Exception ex) { _telemetry.Failed("faulted", ex); }
    }
    internal Task StopAsync()
    {
        lock (_stopGate) return _stop ??= StopCoreAsync();
    }
    private async Task StopCoreAsync()
    {
        try
        {
            await _cancel.CancelAsync().ConfigureAwait(false);
            _stream.Dispose();
            await _pump.WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
            _telemetry.Stopped();
        }
        catch (TimeoutException ex)
        {
            _telemetry.Failed("stop-unconfirmed", ex);
            throw new IOException("HID input reader shutdown was not confirmed.", ex);
        }
        catch (Exception ex)
        {
            _telemetry.Failed("stop-unconfirmed", ex);
            throw;
        }
        finally { _cancel.Dispose(); }
    }
    public void Dispose() => StopAsync().GetAwaiter().GetResult();
}

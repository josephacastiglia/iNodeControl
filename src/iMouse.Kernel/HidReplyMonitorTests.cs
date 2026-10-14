using System.Collections.Concurrent;
using System.Text.Json;
using System.Threading.Channels;

namespace IMouse2.Kernel;

internal static class HidReplyMonitorTests
{
    internal static async Task RunAsync(Action<bool, string> check)
    {
        byte[] Report(byte family) { var b = new byte[17]; b[1] = family; return b; }
        long now = 100;
        var telemetry = new HidReplyTelemetry(() => now);
        check(telemetry.Snapshot() is { State: "not-opened", Reports: 0, Connection: 0, LastReportAgeMs: null },
            "Reply diagnostics do not report an unopened reader as receiving");
        var stream = new ScriptedStream();
        var monitor = new HidReplyMonitor(stream, telemetry);
        await stream.WaitForReads(1);
        check(telemetry.Snapshot() is { State: "awaiting-report", Reports: 0, Connection: 1 },
            "Silent HID input remains unknown rather than confirming a command");
        stream.Queue(new byte[8]);
        stream.Queue(Report(0xA1));
        stream.Queue(Report(0xAF));
        var identifier = Report(0xA5); identifier[2] = 0xde; identifier[3] = 0xad;
        stream.Queue(identifier);
        stream.Queue(Report(0xEE));
        await stream.WaitForReads(6);
        now = 137;
        var snapshot = telemetry.Snapshot();
        check(snapshot is { Reports: 4, InvalidReports: 1, MovementSignals: 1, StatusReports: 1,
            IdentifierReports: 1, UnknownReports: 1, LastFamily: "EE", LastReportAgeMs: 37 },
            "Reply counters distinguish malformed, movement, status, identifier and unknown packets");
        string json = JsonSerializer.Serialize(snapshot);
        check(!json.Contains("DEAD") && !json.Contains("Payload") && !json.Contains("IdentifierHex")
            && snapshot.Meaning.Contains("not command acknowledgement"),
            "Public reply diagnostics omit raw device identifiers and cannot claim iOS success");
        Task stop = monitor.StopAsync();
        await stop;
        check(ReferenceEquals(stop, monitor.StopAsync()) && stream.DisposeCount == 1 && monitor.Completion.IsCompleted,
            "Concurrent/repeated reader shutdown shares one joined cleanup");
        check(telemetry.Snapshot() is { State: "stopped", Reports: 4 },
            "Closed reader preserves bounded observations for diagnostics");

        var disconnected = new ScriptedStream();
        var faultStats = new HidReplyTelemetry();
        var faultReader = new HidReplyMonitor(disconnected, faultStats);
        disconnected.End();
        await faultReader.Completion.WaitAsync(TimeSpan.FromSeconds(1));
        await faultReader.StopAsync();
        check(faultStats.Snapshot() is { State: "faulted", ErrorType: "EndOfStreamException", Reports: 0 },
            "Input EOF is retained as a read failure without inventing a successful reply");

        var ignoresCancel = new ScriptedStream { IgnoreCancellation = true };
        var cancellationStats = new HidReplyTelemetry();
        var cancellationReader = new HidReplyMonitor(ignoresCancel, cancellationStats);
        await ignoresCancel.WaitForReads(1);
        await cancellationReader.StopAsync();
        check(ignoresCancel.DisposeCount == 1 && cancellationReader.Completion.IsCompleted
            && cancellationStats.Snapshot().State == "stopped", "Closing the owned stream drains a read that ignores cancellation");

        var stuck = new ScriptedStream { IgnoreCancellation = true, IgnoreDispose = true };
        var stuckStats = new HidReplyTelemetry();
        var stuckReader = new HidReplyMonitor(stuck, stuckStats);
        await stuck.WaitForReads(1);
        bool refused = false;
        try { await stuckReader.StopAsync(); }
        catch (IOException) { refused = true; }
        check(refused && stuckStats.Snapshot().State == "stop-unconfirmed",
            "An unjoined reader reports incomplete cleanup instead of hanging or claiming success");
        stuck.End();
        await stuckReader.Completion.WaitAsync(TimeSpan.FromSeconds(1));

        telemetry.Started();
        check(telemetry.Snapshot() is { Connection: 2, Reports: 0, LastReportAgeMs: null, ErrorType: null },
            "A new reader lifetime cannot inherit an earlier reply as fresh evidence");
        for (int i = 0; i < 10000; i++) telemetry.Observe(Report(0xA1));
        check(telemetry.Snapshot().Reports == 10000 && JsonSerializer.Serialize(telemetry.Snapshot()).Length < 700,
            "High report counts retain only a fixed-size summary");

        var input = new ScriptedStream();
        using var output = new MemoryStream();
        var writeStats = new HidReplyTelemetry();
        var reading = new HidReplyMonitor(input, writeStats);
        using (var connection = new HidConnection(output, reading))
        {
            await connection.SendAsync([0xA1,0,1,0,0,0,0,0], CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(1));
            check(output.ToArray().SequenceEqual(new byte[] { 0,0xA1,0,1,0,0,0,0,0 }) && writeStats.Snapshot().Reports == 0,
                "A missing reply cannot gate or change the existing output report");
            input.End();
            await reading.Completion.WaitAsync(TimeSpan.FromSeconds(1));
            await connection.SendAsync([0xA2,0,0,0,0,0,0,0], CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(1));
            check(output.Length == 18 && writeStats.Snapshot().ErrorType == "EndOfStreamException",
                "Reply EOF does not replay or prevent a key-release write");
        }
        check(input.DisposeCount == 1, "Transport disposal closes its independent input reader once");
    }

    private sealed class ScriptedStream : Stream
    {
        private readonly Channel<byte[]> _queue = Channel.CreateUnbounded<byte[]>();
        private readonly ConcurrentDictionary<int, TaskCompletionSource> _waits = new();
        private int _reads;
        internal int DisposeCount;
        internal bool IgnoreCancellation, IgnoreDispose;
        internal void Queue(byte[] bytes) => _queue.Writer.TryWrite(bytes);
        internal void End() => _queue.Writer.TryComplete();
        internal Task WaitForReads(int count)
        {
            var wait = _waits.GetOrAdd(count, _ => new(TaskCreationOptions.RunContinuationsAsynchronously));
            if (Volatile.Read(ref _reads) >= count) wait.TrySetResult();
            return wait.Task.WaitAsync(TimeSpan.FromSeconds(1));
        }
        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
        {
            int n = Interlocked.Increment(ref _reads);
            foreach (var pair in _waits) if (pair.Key <= n) pair.Value.TrySetResult();
            if (!await _queue.Reader.WaitToReadAsync(IgnoreCancellation ? CancellationToken.None : ct)) return 0;
            if (!_queue.Reader.TryRead(out var bytes)) throw new IOException("Test queue race");
            bytes.AsMemory().CopyTo(buffer); return bytes.Length;
        }
        protected override void Dispose(bool disposing)
        {
            Interlocked.Increment(ref DisposeCount);
            if (!IgnoreDispose) End();
            base.Dispose(disposing);
        }
        public override bool CanRead => true;
        public override bool CanWrite => false;
        public override bool CanSeek => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() => throw new NotSupportedException();
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException("Reader must never write");
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
    }
}

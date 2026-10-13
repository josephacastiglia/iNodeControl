using System.Text.Json;

namespace IMouse2;

internal static class ResponseTimingTests
{
    internal static void Register(Action<string, Action> test)
    {
        test("Response timing is disabled unless explicitly set to 1", () => {
            Check(new string?[] { null, "", "0", "true", " 1" }.All(s => ResponseTiming.FromSetting(s) is null));
            Check(ResponseTiming.FromSetting("1") is not null);
        });
        test("Handler, queue, bitmap and completion share one monotonic clock", () => {
            var clock = new TimingClock(); var trace = new ResponseTiming(clock);
            var action = trace.Begin(2, "TEST:A", "button_handler", "Home");
            clock.Advance(25); trace.CommandStarted(action);
            clock.Advance(100); trace.BitmapApplied(2, "TEST:A", Stamp(), 500, 1080, "pump");
            clock.Advance(200); trace.End(action, "command_completed");
            var s = trace.Snapshot();
            Check(s.TimestampFrequency == 1000 && s.Events.Select(e => e.Timestamp).SequenceEqual(new long[] {0,25,125,325}));
            Check(s.Events[2].ActionId is null && s.Events[3].ActionId == action.Id);
        });
        test("Wall-clock changes cannot alter recorded elapsed timestamps", () => {
            var clock = new TimingClock(); var trace = new ResponseTiming(clock);
            var first = trace.Begin(1, "TEST:A", "internal", "tap");
            clock.Utc = clock.Utc.AddHours(-3); clock.Advance(50); trace.End(first, "failed");
            var s = trace.Snapshot(); Check(s.Events[1].Timestamp - s.Events[0].Timestamp == 50 && s.StartedUtc != clock.Utc);
        });
        test("Selection reset retains the original action scope", () => {
            var trace = new ResponseTiming(); var action = trace.Begin(1, "TEST:A", "internal", "tap");
            trace.Reset(2); trace.BitmapApplied(2, "TEST:B", Stamp() with { Epoch = 2 }, 500, 1080, "pump");
            trace.End(action, "cancelled");
            var events = trace.Snapshot().Events;
            Check(events[2].Targets == "TEST:B" && events[2].ActionId is null);
            Check(events[3].Epoch == 1 && events[3].Targets == "TEST:A" && events[3].Outcome == "cancelled");
        });
        test("Legacy frames have unknown delivery identity", () => {
            var trace = new ResponseTiming(); trace.BitmapApplied(0, "TEST:A", null, 5, 10, "manual");
            var e = trace.Snapshot().Events.Single();
            Check(e.FrameSession is null && e.FrameSequence is null && e.ContentRevision is null);
        });
        test("Frame delivery identity is retained separately from content revision", () => {
            var trace = new ResponseTiming(); var stamp = Stamp();
            trace.BitmapApplied(1, "TEST:A", stamp, 500, 1080, "pump");
            var e = trace.Snapshot().Events.Single();
            Check(e.FrameSession == stamp.Metadata!.Session && e.FrameSequence == 42 && e.ContentRevision == 7);
        });
        test("Capacity exhaustion retains original events and declares every omission", () => {
            var trace = new ResponseTiming(capacity: 2); var action = trace.Begin(0, "TEST:A", "internal", "tap");
            trace.CommandStarted(action); trace.End(action, "failed"); trace.Reset(1);
            var s = trace.Snapshot(); Check(s.Events.Length == 2 && s.DroppedEvents == 2 && s.Events[0].Index == 1);
        });
        test("Exported arrays cannot mutate retained evidence", () => {
            var trace = new ResponseTiming(); trace.Reset(1);
            var s = trace.Snapshot(); s.Events[0] = s.Events[0] with { Kind = "changed" };
            Check(trace.Snapshot().Events[0].Kind == "preview_reset");
        });
        test("Concurrent callbacks retain ordered unique event and action IDs", () => {
            var trace = new ResponseTiming(capacity: 1000);
            Parallel.For(0, 100, i => { var a = trace.Begin(0, "TEST:A", "internal", "tap"); trace.CommandStarted(a); trace.End(a, "failed"); });
            var e = trace.Snapshot().Events;
            Check(e.Length == 300 && e.Select(x => x.Index).SequenceEqual(Enumerable.Range(1, 300).Select(x => (long)x)));
            Check(e.Where(x => x.Kind == "action_requested").Select(x => x.ActionId).Distinct().Count() == 100);
            Check(e.Zip(e.Skip(1)).All(pair => pair.First.Timestamp <= pair.Second.Timestamp));
        });
        test("Operation labels never contain key payloads", () => {
            Check(ResponseTiming.Operation("/key/sendkey", "private typed content") == "key");
            Check(ResponseTiming.Operation("/key/sendkey", "Home") == "Home");
            Check(ResponseTiming.Operation("private unknown endpoint", null) == "other");
        });
        test("Invalid event capacities are rejected", () => {
            foreach (int size in new[] { 0, -1, 65537 }) {
                try { _ = new ResponseTiming(capacity: size); throw new Exception("accepted invalid capacity"); }
                catch (ArgumentOutOfRangeException) { }
            }
        });
        test("Snapshots include recording identity, limits and measurement caveats", () => {
            var trace = new ResponseTiming(); var s = trace.Snapshot();
            Check(Guid.TryParseExact(s.RecordingId, "N", out _) && s.Capacity == 4096 && s.DroppedEvents == 0);
            Check(s.Scope.Contains("Not physical click") && s.Scope.Contains("correctness"));
            Check(JsonSerializer.Serialize(s).Contains("TimestampFrequency"));
        });
    }
    private static void Check(bool pass) { if (!pass) throw new Exception("Response timing assertion failed"); }
    private static PreviewStamp Stamp() => new(1, 7, new("0123456789abcdef0123456789abcdef", 42, 0, "flowing"), 0);
    private sealed class TimingClock : TimeProvider
    {
        private long _ticks;
        public DateTimeOffset Utc = new(2026, 10, 13, 0, 0, 0, TimeSpan.Zero);
        public override long TimestampFrequency => 1000;
        public override long GetTimestamp() => _ticks;
        public override DateTimeOffset GetUtcNow() => Utc;
        public void Advance(long ms) => _ticks += ms;
    }
}

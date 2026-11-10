
namespace IMouse2;

// Moved on 9 Nov 2026 from the stand-alone project tools/frame_tests, which is deleted: the checks now run
// in this executable's --self-test. Each named case is one self-test check; it passes when none of
// its assertions throws. A fake clock only.
internal static class FrameMetricsTests
{
    internal static async Task RunAsync(Func<string, Func<Task>, Task> record)
    {
        var tests = new (string, Func<Task>)[] {
            ("idle presentation rate expires without another frame", () => {
                var c = new Clock(); var r = new RateMeter(c); r.Mark(); c.Advance(20); r.Mark();
                Check(r.Fps == 50); c.Advance(2100); Check(r.Fps == 0); return Task.CompletedTask;
            }),
            ("rate decays while waiting instead of retaining old burst rate", () => {
                var c = new Clock(); var r = new RateMeter(c); r.Mark(); c.Advance(20); r.Mark();
                c.Advance(980); Check(r.Fps == 1); return Task.CompletedTask;
            }),
            ("rate uses monotonic time and reset clears history", () => {
                var c = new Clock(); var r = new RateMeter(c); r.Mark(); c.Advance(20); r.Mark();
                c.Wall = DateTimeOffset.UtcNow.AddYears(-10); Check(r.Fps == 50);
                r.Reset(); Check(r.Fps == 0); return Task.CompletedTask;
            }),
            ("simultaneous timestamps do not divide by zero", () => {
                var c = new Clock(); var r = new RateMeter(c); r.Mark(); r.Mark();
                Check(r.Fps == 0); return Task.CompletedTask;
            }),
            ("presentation gaps retain a six-second pause", () => {
                var c = new Clock(); var j = new JitterMeter(c); j.Mark();
                c.Advance(6000); j.Mark(); Check(j.Summary().Max == 6000 && j.Summary().Long == 1);
                return Task.CompletedTask;
            }),
            ("pending gap is visible before another presentation", () => {
                var c = new Clock(); var j = new JitterMeter(c); Check(j.SinceLastMs is null);
                j.Mark(); c.Advance(7000); Check(j.SinceLastMs == 7000 && j.Summary().Max == 0);
                j.Reset(); Check(j.SinceLastMs is null); return Task.CompletedTask;
            }),
            ("completed gap ring remains bounded and evicts old samples", () => {
                var c = new Clock(); var j = new JitterMeter(c); j.Mark(); c.Advance(6000); j.Mark();
                for (int i = 0; i < 240; i++) { c.Advance(10); j.Mark(); }
                Check(j.Summary() == (10, 10, 10, 0)); return Task.CompletedTask;
            })
        };
        foreach (var (name, test) in tests) await record(name, test);
    }

    private static void Check(bool yes) { if (!yes) throw new Exception("Assertion failed"); }
    private sealed class Clock : TimeProvider
    {
        private long _ms;
        public DateTimeOffset Wall = DateTimeOffset.UtcNow;
        public override long TimestampFrequency => 1000;
        public override long GetTimestamp() => Interlocked.Read(ref _ms);
        public override DateTimeOffset GetUtcNow() => Wall;
        public void Advance(long ms) => Interlocked.Add(ref _ms, ms);
    }
}

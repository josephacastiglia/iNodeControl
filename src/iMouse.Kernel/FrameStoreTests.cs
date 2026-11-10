using System.Buffers.Binary;
using System.Threading.Channels;

namespace IMouse2.Kernel;

// Moved on 9 Nov 2026 from the stand-alone project tools/frame_tests, which is deleted: the checks now run
// in this executable's --self-test. Each named case is one self-test check; it passes when none of
// its assertions throws. Synthetic streams and a fake clock; no pipe, listener or receiver.
internal static class FrameStoreTests
{
    internal static async Task RunAsync(Func<string, Func<Task>, Task> record)
    {
        var tests = new (string, Func<Task>)[] {
            ("no frame starts with unknown age, not a fresh zero", () => {
                using var f = new FrameStore("unused", "fake", new Clock());
                Check(f.Delivery is { Available: false, Connected: false, Sequence: 0, AgeMs: null, Status: "waiting" });
                return Task.CompletedTask;
            }),
            ("waiting connection does not invent a frame", async () => {
                await using var r = new Rig(); await r.Wait(d => d.Connected);
                Check(r.Store.Delivery is { Available: false, AgeMs: null, Status: "waiting" });
            }),
            ("valid frame publishes dimensions sequence and zero age", async () => {
                await using var r = new Rig(); await r.Send(Bmp());
                Check(r.Store.Delivery is { Available: true, Width: 2, Height: 2, Sequence: 1, AgeMs: 0, Status: "flowing" });
            }),
            ("unchanged new frames advance delivery and reset age", async () => {
                await using var r = new Rig(); await r.Send(Bmp()); r.Clock.Advance(2500);
                Check(r.Store.Delivery.Status == "quiet"); await r.Send(Bmp());
                Check(r.Store.Delivery is { Sequence: 2, AgeMs: 0, Status: "flowing" });
            }),
            ("polling cached picture does not refresh age or increment sequence", async () => {
                await using var r = new Rig(); await r.Send(Bmp()); r.Clock.Advance(2000);
                for (int i = 0; i < 10; i++) Check(r.Store.State.Live && r.Store.Delivery.Sequence == 1);
                Check(r.Store.Delivery is { AgeMs: 2000, Status: "quiet", Available: true });
            }),
            ("receiver stop marker clears cached availability but retains evidence", async () => {
                await using var r = new Rig(); await r.Send(Bmp()); r.Clock.Advance(50);
                r.Pipe.Put(new byte[4]); await r.Wait(d => d.Status == "stopped");
                Check(r.Store.Delivery is { Available: false, Connected: true, Width: 0, Sequence: 1, AgeMs: 50 });
                await r.Send(Bmp()); Check(r.Store.Delivery is { Available: true, Sequence: 2 });
            }),
            ("disconnect clears cached frame and records reason", async () => {
                await using var r = new Rig(); await r.Send(Bmp()); r.Pipe.End(); await r.Run;
                Check(r.Store.Delivery is { Available: false, Connected: false, Status: "disconnected", Sequence: 1 });
            }),
            ("malformed BMP is refused and previous picture cleared", async () => {
                await using var r = new Rig(); await r.Send(Bmp()); var bad = Bmp(); bad[0] = 0;
                r.Pipe.Put(Packet(bad)); await r.Run;
                Check(r.Store.Delivery is { Available: false, Status: "invalid_frame", Sequence: 1 });
            }),
            ("oversized length rejected before allocation or payload read", async () => {
                await using var r = new Rig(); var header = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(header, int.MaxValue);
                r.Pipe.Put(header); await r.Run;
                Check(r.Store.Delivery is { Available: false, Status: "invalid_frame", Sequence: 0 });
            }),
            ("truncated frame never counts as received", async () => {
                await using var r = new Rig(); r.Pipe.Put(Packet(Bmp())[..12]); r.Pipe.End(); await r.Run;
                Check(r.Store.Delivery is { Sequence: 0, AgeMs: null, Status: "disconnected" });
            }),
            ("fragmented stream assembles exactly one validated frame", async () => {
                await using var r = new Rig(); foreach (var b in Packet(Bmp())) r.Pipe.Put(new[]{b});
                await r.Wait(d => d.Sequence == 1); Check(r.Store.Delivery.Available);
            }),
            ("cancelled read leaves no available frame", async () => {
                await using var r = new Rig(); await r.Send(Bmp()); r.Cancel.Cancel(); await r.Run;
                Check(r.Store.Delivery is { Connected: false, Available: false, Status: "stopped" });
            }),
            ("reconnect retains identity and sequence but replaces failure", async () => {
                var clock = new Clock(); using var f = new FrameStore("unused", "fake", clock);
                string session = f.Delivery.Session;
                using var p1 = new Feed(); p1.Put(Packet(Bmp())); p1.End(); await f.ReadConnectionAsync(p1, CancellationToken.None);
                using var p2 = new Feed(); using var cancel = new CancellationTokenSource();
                var run = f.ReadConnectionAsync(p2, cancel.Token);
                try {
                    Check(f.Delivery is { Available: false, Status: "waiting" });
                    p2.Put(Packet(Bmp())); await Until(() => f.Frames == 2);
                    Check(f.Delivery.Session == session && f.Delivery.Status == "flowing");
                } finally { cancel.Cancel(); await run; }
            }),
            ("screenshot metadata is culture independent and identifies the stored frame", async () => {
                await using var r = new Rig(); await r.Send(Bmp()); r.Clock.Advance(1234);
                var original = System.Globalization.CultureInfo.CurrentCulture;
                try {
                    System.Globalization.CultureInfo.CurrentCulture = new("fr-FR");
                    var headers = new System.Net.WebHeaderCollection();
                    FrameStore.WriteMetadata(r.Store.Delivery, headers);
                    Check(headers["X-iMouse-Frame-Sequence"] == "1" && headers["X-iMouse-Frame-Age-Ms"] == "1234");
                    Check(headers["X-iMouse-Frame-Session"] == r.Store.Delivery.Session
                        && headers["X-iMouse-Frame-Delivery"] == "flowing");
                } finally { System.Globalization.CultureInfo.CurrentCulture = original; }
            }),
            ("read failure clears the image and provides recovery diagnostics", async () => {
                await using var r = new Rig(); await r.Send(Bmp()); r.Pipe.Fail(); await r.Run;
                Check(r.Store.Delivery is { Available: false, Connected: false, Status: "io_error" });
            }),
            ("disposed reader reports stopped without opening a pipe", async () => {
                using var f = new FrameStore("unused", "fake"); f.Dispose(); await f.RunAsync();
                Check(f.Delivery is { Status: "stopped", Available: false });
            }),
            ("duplicate reader run is rejected", async () => {
                using var f = new FrameStore("unused", "fake"); f.Dispose(); await f.RunAsync();
                bool rejected = false;
                try { await f.RunAsync(); } catch (InvalidOperationException) { rejected = true; }
                Check(rejected);
            }),
            ("a stalled screenshot client does not block frame delivery or status", async () => {
                await using var r = new Rig(); await r.Send(Bmp());
                var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                var transfer = r.Store.TransferFrameAsync("fake", async (_, _, ct) => { entered.SetResult(); await release.Task.WaitAsync(ct); }, CancellationToken.None);
                Task? progress = null;
                try {
                    await entered.Task.WaitAsync(TimeSpan.FromSeconds(1));
                    progress = Task.Run(async () => { await r.Send(Bmp()); Check(r.Store.Delivery.Sequence == 2); });
                    await progress.WaitAsync(TimeSpan.FromMilliseconds(500));
                } finally {
                    release.TrySetResult(); await transfer.WaitAsync(TimeSpan.FromSeconds(2));
                    if (progress is not null) await progress.WaitAsync(TimeSpan.FromSeconds(2));
                }
            }),
            ("in-flight screenshot keeps its exact bytes and matching metadata as producer buffers change", async () => {
                await using var r = new Rig(); var first = Bmp(); first[^1]=17; await r.Send(first);
                var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                FrameDelivery? captured=null; ReadOnlyMemory<byte> pending=default;
                var transfer=r.Store.TransferFrameAsync("fake", async (metadata, bytes, ct) => {
                    captured=metadata; pending=bytes; await release.Task.WaitAsync(ct);
                    Check(bytes.Span.SequenceEqual(first));
                }, CancellationToken.None);
                try {
                    for (int i=0;i<5;i++) { var next=Bmp(); next[^1]=(byte)(50+i); await r.Send(next); }
                    Check(captured is {Sequence:1, Width:2, Height:2, AgeMs:0} && pending.Span.SequenceEqual(first));
                    Check(r.Store.Delivery.Sequence==6);
                } finally { release.TrySetResult(); await transfer; }
            }),
            ("two stalled transfers bound copies and a third is refused without queueing or affecting peers", async () => {
                await using var r=new Rig(); await using var peer=new Rig(); await r.Send(Bmp()); await peer.Send(Bmp());
                var release=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                int entered=0;
                Task Send(FrameDelivery d, ReadOnlyMemory<byte> b, CancellationToken ct) { entered++; return release.Task.WaitAsync(ct); }
                var first=r.Store.TransferFrameAsync("fake",Send,CancellationToken.None);
                var second=r.Store.TransferFrameAsync("fake",Send,CancellationToken.None);
                try {
                    var third=await r.Store.TransferFrameAsync("fake",Send,CancellationToken.None);
                    Check(third==FrameWriteResult.Busy && entered==2);
                    await r.Send(Bmp()); await peer.Send(Bmp());
                    Check(r.Store.Frames==2 && peer.Store.Frames==2);
                    Check(await peer.Store.TransferFrameAsync("fake",(_,_,_)=>Task.CompletedTask,CancellationToken.None)==FrameWriteResult.Written);
                } finally { release.TrySetResult(); await Task.WhenAll(first,second); }
                Check(await r.Store.TransferFrameAsync("fake",(_,_,_)=>Task.CompletedTask,CancellationToken.None)==FrameWriteResult.Written);
            }),
            ("missing or stopped frames never invoke writers or consume transfer slots", async () => {
                await using var r=new Rig(); int called=0;
                Task Send(FrameDelivery d,ReadOnlyMemory<byte> b,CancellationToken ct) { called++;return Task.CompletedTask; }
                for(int i=0;i<3;i++) Check(await r.Store.TransferFrameAsync("fake",Send,CancellationToken.None)==FrameWriteResult.Unavailable);
                await r.Send(Bmp());
                Check(await r.Store.TransferFrameAsync("other-phone",Send,CancellationToken.None)==FrameWriteResult.Unavailable && called==0);
                r.Pipe.Put(new byte[4]);await r.Wait(d=>d.Status=="stopped");
                Check(await r.Store.TransferFrameAsync("fake",Send,CancellationToken.None)==FrameWriteResult.Unavailable && called==0);
                await r.Send(Bmp());
                Check(await r.Store.TransferFrameAsync("fake",Send,CancellationToken.None)==FrameWriteResult.Written && called==1);
            }),
            ("writer failure returns its slot and cannot stop receiver delivery", async () => {
                await using var r=new Rig();await r.Send(Bmp());
                for(int i=0;i<3;i++) {
                    bool failed=false;
                    try { await r.Store.TransferFrameAsync("fake",(_,_,_)=>Task.FromException(new IOException("broken client")),CancellationToken.None); }
                    catch(IOException) { failed=true; }
                    Check(failed);await r.Send(Bmp());
                }
                Check(await r.Store.TransferFrameAsync("fake",(_,_,_)=>Task.CompletedTask,CancellationToken.None)==FrameWriteResult.Written);
            }),
            ("caller cancellation interrupts its transfer and permits a later request", async () => {
                await using var r=new Rig();await r.Send(Bmp());using var caller=new CancellationTokenSource();
                var transfer=r.Store.TransferFrameAsync("fake",(_,_,ct)=>Task.Delay(Timeout.Infinite,ct),caller.Token);
                caller.Cancel();await MustCancel(transfer);
                Check(await r.Store.TransferFrameAsync("fake",(_,_,_)=>Task.CompletedTask,CancellationToken.None)==FrameWriteResult.Written);
                bool called=false;
                await MustCancel(r.Store.TransferFrameAsync("fake",(_,_,_)=>{called=true;return Task.CompletedTask;},caller.Token));
                Check(!called);
            }),
            ("store shutdown cancels pending screenshot transfers", async () => {
                await using var r=new Rig();await r.Send(Bmp());
                var transfer=r.Store.TransferFrameAsync("fake",(_,_,ct)=>Task.Delay(Timeout.Infinite,ct),CancellationToken.None);
                r.Store.Dispose();await MustCancel(transfer);
            }),
            ("a timed-out writer is cancelled and frees its slot", async () => {
                await using var r=new Rig();await r.Send(Bmp());
                var elapsed=System.Diagnostics.Stopwatch.StartNew();
                var transfer=r.Store.TransferFrameAsync("fake",(_,_,ct)=>Task.Delay(Timeout.Infinite,ct),CancellationToken.None);
                await MustCancel(transfer,TimeSpan.FromSeconds(8));
                Check(elapsed.Elapsed>=FrameStore.ScreenshotTimeout-TimeSpan.FromMilliseconds(100));
                Check(await r.Store.TransferFrameAsync("fake",(_,_,_)=>Task.CompletedTask,CancellationToken.None)==FrameWriteResult.Written);
            }),
            ("cancellation does not return a buffer while a writer is still using it", async () => {
                await using var r=new Rig();await r.Send(Bmp());using var caller=new CancellationTokenSource();
                var release=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                var first=r.Store.TransferFrameAsync("fake",(_,_,_)=>release.Task,caller.Token);
                var second=r.Store.TransferFrameAsync("fake",(_,_,_)=>release.Task,caller.Token);
                try {
                    caller.Cancel(); Check(!first.IsCompleted && !second.IsCompleted);
                    Check(await r.Store.TransferFrameAsync("fake",(_,_,_)=>Task.CompletedTask,CancellationToken.None)==FrameWriteResult.Busy);
                } finally { release.TrySetResult();await Task.WhenAll(first,second); }
                Check(await r.Store.TransferFrameAsync("fake",(_,_,_)=>Task.CompletedTask,CancellationToken.None)==FrameWriteResult.Written);
            }),
            ("independent stores have distinct identities and failure isolation", async () => {
                await using var a = new Rig(); await using var b = new Rig();
                await a.Send(Bmp()); await b.Send(Bmp()); a.Pipe.End(); await a.Run;
                Check(a.Store.Delivery.Session != b.Store.Delivery.Session);
                Check(b.Store.Delivery is { Connected: true, Available: true, Sequence: 1 });
            })
        };
        foreach (var (name, test) in tests) await record(name, test);
    }

    private static void Check(bool yes) { if (!yes) throw new Exception("Assertion failed"); }
    private static async Task MustCancel(Task task,TimeSpan? timeout=null)
    {
        bool cancelled=false;
        try { await task.WaitAsync(timeout??TimeSpan.FromSeconds(2)); }
        catch(OperationCanceledException) { cancelled=true; }
        Check(cancelled);
    }
    private static async Task Until(Func<bool> ready)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(2));
        while (!ready()) await Task.Delay(1, timeout.Token);
    }
    private static byte[] Bmp()
    {
        var b = new byte[70]; b[0] = (byte)'B'; b[1] = (byte)'M';
        BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(2), b.Length);
        BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(10), 54);
        BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(14), 40);
        BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(18), 2);
        BinaryPrimitives.WriteInt32LittleEndian(b.AsSpan(22), 2);
        BinaryPrimitives.WriteInt16LittleEndian(b.AsSpan(26), 1);
        BinaryPrimitives.WriteInt16LittleEndian(b.AsSpan(28), 24); return b;
    }
    private static byte[] Packet(byte[] bmp)
    {
        var packet = new byte[bmp.Length + 4]; BinaryPrimitives.WriteInt32LittleEndian(packet, bmp.Length);
        bmp.CopyTo(packet, 4); return packet;
    }
    private sealed class Clock : TimeProvider
    {
        private long _ms;
        public DateTimeOffset Wall = DateTimeOffset.UtcNow;
        public override long TimestampFrequency => 1000;
        public override long GetTimestamp() => Interlocked.Read(ref _ms);
        public override DateTimeOffset GetUtcNow() => Wall;
        public void Advance(long ms) => Interlocked.Add(ref _ms, ms);
    }
    private sealed class Rig : IAsyncDisposable
    {
        public readonly Clock Clock = new();
        public readonly Feed Pipe = new();
        public readonly CancellationTokenSource Cancel = new();
        public readonly FrameStore Store;
        public readonly Task Run;
        public Rig() { Store = new("unused", "fake", Clock); Run = Store.ReadConnectionAsync(Pipe, Cancel.Token); }
        public async Task Send(byte[] bmp)
        {
            long sequence = Store.Frames + 1;
            var packet = new byte[bmp.Length + 4]; BinaryPrimitives.WriteInt32LittleEndian(packet, bmp.Length); bmp.CopyTo(packet, 4);
            Pipe.Put(packet); await Wait(d => d.Sequence == sequence);
        }
        public async Task Wait(Func<FrameDelivery, bool> ready)
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(2));
            while (!ready(Store.Delivery)) await Task.Delay(1, timeout.Token);
        }
        public async ValueTask DisposeAsync() { Cancel.Cancel(); await Run; Store.Dispose(); Pipe.Dispose(); Cancel.Dispose(); }
    }
    private sealed class Feed : Stream
    {
        private readonly Channel<byte[]> _data = Channel.CreateUnbounded<byte[]>();
        private byte[] _current = []; private int _at;
        public void Put(byte[] bytes) => _data.Writer.TryWrite(bytes);
        public void End() => _data.Writer.TryComplete();
        public void Fail() => _data.Writer.TryComplete(new IOException("synthetic read failure"));
        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
        {
            while (_at == _current.Length)
            {
                if (!await _data.Reader.WaitToReadAsync(ct)) return 0;
                if (!_data.Reader.TryRead(out var next)) continue;
                _current = next; _at = 0;
            }
            int count = Math.Min(buffer.Length, _current.Length - _at);
            _current.AsMemory(_at, count).CopyTo(buffer); _at += count; return count;
        }
        public override bool CanRead => true; public override bool CanWrite => false; public override bool CanSeek => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() => throw new NotSupportedException();
        public override int Read(byte[] b, int o, int c) => throw new NotSupportedException();
        public override void Write(byte[] b, int o, int c) => throw new NotSupportedException();
        public override long Seek(long o, SeekOrigin s) => throw new NotSupportedException();
        public override void SetLength(long l) => throw new NotSupportedException();
    }
}

using System.Collections.Concurrent;
using System.Net;
using IMouse2;

var tests = new List<(string, Func<Task>)>();
void Test(string name, Action run) => tests.Add((name, () => { run(); return Task.CompletedTask; }));
void Async(string name, Func<Task> run) => tests.Add((name, run));
foreach (var (state, label, warning) in new[] {("recent","Recent",false),("quiet","May be old",true),("unknown","Age unknown",false),("waiting","Waiting",false)})
    Test("tile label for " + state, () => {
        var v = TileStatusView.From(new(state, 3000, false), true, false);
        Check(v.Label == label && v.Warning == warning);
    });
Test("offline and paused state override old image delivery", () => {
    var p = new PreviewStatus("recent", 0, false);
    Check(TileStatusView.From(p, false, false).Label == "Offline");
    Check(TileStatusView.From(p, true, true).Label == "Paused");
});
Test("failed screenshot has visible warning and full explanation", () => {
    var v = TileStatusView.From(new("recent", 0, true), true, false);
    Check(v.Label == "No updates" && v.Warning && v.Detail.Contains("not updating"));
});
Test("repeated reconciliation never starts a duplicate pump", () => {
    var streams = new TileStreams(); var first = streams.Reconcile(["A","B","A"],1,CancellationToken.None);
    Check(first.Count == 2 && streams.Reconcile(["B","A"],1,CancellationToken.None).Count == 0);
    Check(streams.RunningCount == 2); foreach (var s in first) streams.Complete(s);
});
Test("removing a tile cancels only that stream", () => {
    var streams = new TileStreams(); var first = streams.Reconcile(["A","B"],1,CancellationToken.None);
    streams.Reconcile(["B"],1,CancellationToken.None);
    Check(first.Single(s=>s.Id=="A").Token.IsCancellationRequested);
    Check(streams.IsCurrent(first.Single(s=>s.Id=="B")));
    foreach (var s in first) streams.Complete(s);
});
Test("late completion cannot remove a replacement with same phone ID", () => {
    var streams = new TileStreams(); var old = streams.Reconcile(["A"],1,CancellationToken.None).Single();
    streams.Reconcile([],1,CancellationToken.None);
    var next = streams.Reconcile(["A"],1,CancellationToken.None).Single();
    Check(!streams.IsCurrent(old) && streams.RunningCount == 2);
    streams.Complete(old); Check(streams.IsCurrent(next) && streams.RunningCount == 1);
    streams.Complete(next); Check(streams.RunningCount == 0);
});
Test("connection replacement cancels old session even with same IDs", () => {
    var streams = new TileStreams(); var old = streams.Reconcile(["A"],1,CancellationToken.None).Single();
    var next = streams.Reconcile(["A"],2,CancellationToken.None).Single();
    Check(old.Token.IsCancellationRequested && !streams.IsCurrent(old) && streams.IsCurrent(next));
    streams.Complete(old); streams.Complete(next);
});
Test("parent cancellation refuses new work and invalidates publication", () => {
    using var c = new CancellationTokenSource(); var streams = new TileStreams();
    var one = streams.Reconcile(["A"],1,c.Token).Single(); c.Cancel();
    Check(!streams.IsCurrent(one) && streams.Reconcile(["A","B"],1,c.Token).Count == 0);
    streams.Complete(one);
});
Test("stop invalidates every tile before retired work finishes", () => {
    var streams = new TileStreams(); var all = streams.Reconcile(["A","B"],1,CancellationToken.None);
    streams.Stop(); Check(all.All(s=>s.Token.IsCancellationRequested && !streams.IsCurrent(s)));
    Check(streams.Find("A") is null); foreach (var s in all) streams.Complete(s);
});
Test("19 streams keep age, failure and unchanged-delivery state separate", () => {
    var c = new Clock(); var streams = new TileStreams(c);
    var all = streams.Reconcile(Enumerable.Range(0,19).Select(i=>"P"+i),1,CancellationToken.None);
    foreach (var s in all) s.Freshness.Presented(s.Freshness.Observe(0,false,Meta(s.Id,1))!);
    c.Advance(3000);
    for (int i=1;i<19;i++) all[i].Freshness.Observe(0,true,Meta(all[i].Id,2));
    all[2].Freshness.Failed(0); all[3].Freshness.Observe(0,true,null);
    Check(all[0].Freshness.Status.State=="quiet");
    Check(all[1].Freshness.Status.State=="recent" && !all[1].Freshness.Status.FetchFailed);
    Check(all[2].Freshness.Status.FetchFailed && all[3].Freshness.Status.State=="unknown");
    Check(all.Skip(4).All(s=>s.Freshness.Status.State=="recent"));
    foreach(var s in all) streams.Complete(s);
});
Async("19 actual API screenshot requests obey shared three-slot limit", async () => {
    var release = Signal(); using var handler = new Rack(async (_,ct)=>await release.Task.WaitAsync(ct));
    using var api = new ApiClient("http://offline.invalid",handler); var scheduler = new TileFetchScheduler(3);
    var tasks = Enumerable.Range(0,19).Select(i=>scheduler.FetchAsync(ct=>api.ScreenshotIntoAsync("P"+i,false,new FrameBuffer(),ct),CancellationToken.None)).ToArray();
    try { await Until(()=>handler.Started==3); Check(handler.Active==3 && handler.Maximum==3); }
    finally { release.TrySetResult(); }
    var results=await Task.WhenAll(tasks); Check(results.All(r=>r.Success) && handler.Started==19 && handler.Maximum==3);
});
Async("one stalled phone leaves other 18 able to finish", async () => {
    var release=Signal(); using var handler=new Rack(async(id,ct)=>{if(id=="slow") await release.Task.WaitAsync(ct);});
    using var api=new ApiClient("http://offline.invalid",handler);var scheduler=new TileFetchScheduler(3);
    var slow=scheduler.FetchAsync(ct=>api.ScreenshotIntoAsync("slow",false,new FrameBuffer(),ct),CancellationToken.None);
    var others=Enumerable.Range(0,18).Select(i=>scheduler.FetchAsync(ct=>api.ScreenshotIntoAsync("P"+i,false,new FrameBuffer(),ct),CancellationToken.None)).ToArray();
    try { var results=await Task.WhenAll(others).WaitAsync(TimeSpan.FromSeconds(2)); Check(results.All(r=>r.Success)&&!slow.IsCompleted); }
    finally {release.TrySetResult();await slow;}
    Check(handler.Maximum<=3);
});
Async("unrequested timeout is failure, not stream cancellation, and recovers", async () => {
    int calls=0; using var handler=new Rack((_,_)=>Interlocked.Increment(ref calls)==1?Task.FromException(new TaskCanceledException("fake timeout")):Task.CompletedTask);
    using var api=new ApiClient("http://offline.invalid",handler); var scheduler=new TileFetchScheduler(1);
    var streams=new TileStreams();var s=streams.Reconcile(["A"],1,CancellationToken.None).Single();
    try {
        var first=await scheduler.FetchAsync(ct=>api.ScreenshotIntoAsync("A",false,new FrameBuffer(),ct),s.Token);
        Check(!first.Success&&!first.Cancelled&&streams.IsCurrent(s));
        var next=await scheduler.FetchAsync(ct=>api.ScreenshotIntoAsync("A",false,new FrameBuffer(),ct),s.Token);
        Check(next.Success && calls==2);
    } finally {streams.Complete(s);}
});
Async("queued cancellation never starts the transport or leaks a slot", async () => {
    var scheduler=new TileFetchScheduler(1); var started=Signal();var release=Signal();using var c=new CancellationTokenSource();int calls=0;
    var first=scheduler.FetchAsync(async ct=>{started.SetResult();await release.Task.WaitAsync(ct);},CancellationToken.None);
    await started.Task;var queued=scheduler.FetchAsync(_=>{calls++;return Task.CompletedTask;},c.Token);c.Cancel();
    try {var result=await queued;Check(result.Cancelled&&calls==0);}
    finally {release.SetResult();await first;}
    Check((await scheduler.FetchAsync(_=>Task.CompletedTask,CancellationToken.None)).Success);
});
Async("active cancellation releases its slot while peer keeps running", async () => {
    var scheduler=new TileFetchScheduler(2);var a=Signal();var b=Signal();using var c=new CancellationTokenSource();
    var cancelled=scheduler.FetchAsync(async ct=>{a.SetResult();await Task.Delay(Timeout.Infinite,ct);},c.Token);
    var peer=scheduler.FetchAsync(_=>b.Task,CancellationToken.None);await a.Task;c.Cancel();
    try {Check((await cancelled).Cancelled&&!peer.IsCompleted);Check((await scheduler.FetchAsync(_=>Task.CompletedTask,CancellationToken.None)).Success);}
    finally {b.SetResult();await peer;}
});
Async("failed fetch releases its slot before retry delay or display", async () => {
    var scheduler=new TileFetchScheduler(1);var bad=await scheduler.FetchAsync(_=>Task.FromException(new IOException("fake disconnect")),CancellationToken.None);
    Check(!bad.Success&&!bad.Cancelled);
    Check((await scheduler.FetchAsync(_=>Task.CompletedTask,CancellationToken.None)).Success);
});
Async("all occupied slots recover after request failures", async () => {
    var scheduler=new TileFetchScheduler(3);var release=Signal();int started=0;
    var failures=Enumerable.Range(0,3).Select(_=>scheduler.FetchAsync(async ct=>{Interlocked.Increment(ref started);await release.Task;throw new IOException("fake");},CancellationToken.None)).ToArray();
    await Until(()=>started==3);var next=scheduler.FetchAsync(_=>Task.CompletedTask,CancellationToken.None);
    Check(!next.IsCompleted);release.SetResult();Check((await Task.WhenAll(failures)).All(x=>!x.Success));Check((await next).Success);
});
Async("late response ignoring cancellation is refused after tile removal", async () => {
    var streams=new TileStreams();var s=streams.Reconcile(["A"],1,CancellationToken.None).Single();var release=Signal();
    var scheduler=new TileFetchScheduler(1);var result=scheduler.FetchAsync(_=>release.Task,s.Token);
    streams.Reconcile([],1,CancellationToken.None);release.SetResult();
    Check((await result).Cancelled&&!streams.IsCurrent(s));streams.Complete(s);
});
Test("invalid fetch concurrency is rejected", () => {
    bool rejected=false;try{new TileFetchScheduler(0);}catch(ArgumentOutOfRangeException){rejected=true;}Check(rejected);
});
int passed=0;
foreach(var(name,run)in tests){try{await run().WaitAsync(TimeSpan.FromSeconds(6));passed++;Console.WriteLine("PASS "+name);}catch(Exception ex){Console.WriteLine("FAIL "+name+": "+ex);}}
Console.WriteLine($"{passed}/{tests.Count} passed");return passed==tests.Count?0:1;
static void Check(bool yes){if(!yes)throw new Exception("Assertion failed");}
static TaskCompletionSource Signal()=>new(TaskCreationOptions.RunContinuationsAsynchronously);
static async Task Until(Func<bool> ready){using var c=new CancellationTokenSource(TimeSpan.FromSeconds(2));while(!ready())await Task.Delay(1,c.Token);}
static ScreenshotMetadata Meta(string id,long seq)=>new(id,seq,0,"flowing");
sealed class Clock:TimeProvider {private long _ms;public override long TimestampFrequency=>1000;public override long GetTimestamp()=>_ms;public void Advance(long ms)=>_ms+=ms;}
sealed class Rack(Func<string,CancellationToken,Task> action):HttpMessageHandler
{
    private int _started,_active,_maximum;
    public int Started=>Volatile.Read(ref _started);public int Active=>Volatile.Read(ref _active);public int Maximum=>Volatile.Read(ref _maximum);
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct)
    {
        if(request.Method!=HttpMethod.Get||request.RequestUri?.AbsolutePath!="/api/pic/screenshot")throw new Exception("Only mock screenshot GET allowed");
        string id=Uri.UnescapeDataString(request.RequestUri.Query.Split('&')[0].Split('=')[1]);
        Interlocked.Increment(ref _started);int active=Interlocked.Increment(ref _active);int old;
        do{old=Volatile.Read(ref _maximum);if(old>=active)break;}while(Interlocked.CompareExchange(ref _maximum,active,old)!=old);
        try{
            await action(id,ct);var b=new byte[70];b[0]=(byte)'B';b[1]=(byte)'M';
            return new(HttpStatusCode.OK){Content=new ByteArrayContent(b)};
        }finally{Interlocked.Decrement(ref _active);}
    }
}

using System.Globalization;
using System.Net;
using System.Text.Json;
using IMouse2;

var tests = new List<(string, Func<Task>)>();
void Test(string name, Action test) => tests.Add((name, () => { test(); return Task.CompletedTask; }));
void Async(string name, Func<Task> test) => tests.Add((name, test));
Test("no response is waiting, legacy response is unknown", () => {
    var t = new PreviewFreshness(new Clock()); Check(t.Status.State == "waiting");
    t.Presented(t.Observe(0, false, null)!); Check(t.Status.State == "unknown" && t.Status.AgeMs is null);
});
Test("known age becomes quiet even without another fetch", () => {
    var c = new Clock(); var t = new PreviewFreshness(c);
    t.Presented(t.Observe(0, false, Meta())!); Check(t.Status.State == "recent");
    c.Advance(2000); Check(t.Status.State == "quiet" && t.Status.AgeMs == 2000);
});
Test("unchanged pixels with advancing delivery stay recent", () => {
    var c = new Clock(); var t = new PreviewFreshness(c);
    t.Presented(t.Observe(0, false, Meta())!); c.Advance(5000);
    t.Observe(0, true, Meta(2)); Check(t.Status.State == "recent" && t.Status.AgeMs == 0);
});
Test("repeated identity never becomes younger when polled", () => {
    var c = new Clock(); var t = new PreviewFreshness(c);
    t.Presented(t.Observe(0, false, Meta())!); c.Advance(3000);
    t.Observe(0, true, Meta()); Check(t.Status.State == "quiet" && t.Status.AgeMs == 3000);
});
Test("malformed evidence does not erase monotonic age history", () => {
    var c = new Clock(); var t = new PreviewFreshness(c);
    t.Presented(t.Observe(0, false, Meta())!); c.Advance(3000);
    t.Observe(0, true, null); Check(t.Status.State == "unknown");
    t.Observe(0, true, Meta()); Check(t.Status.AgeMs == 3000);
});
Test("sequence regression is unknown until valid progress returns", () => {
    var t = new PreviewFreshness(new Clock()); t.Presented(t.Observe(0, false, Meta(9))!);
    t.Observe(0, true, Meta(8)); Check(t.Status.State == "unknown");
    t.Observe(0, true, Meta(10)); Check(t.Status.State == "recent");
});
Test("receiver session replacement permits sequence reset", () => {
    var t = new PreviewFreshness(new Clock()); t.Presented(t.Observe(0, false, Meta(9, 3000))!);
    t.Observe(0, true, Meta(1) with { Session = Guid.NewGuid().ToString("N") });
    Check(t.Status.State == "recent");
});
Test("fetched but unpresented changed pixels do not refresh old display", () => {
    var c = new Clock(); var t = new PreviewFreshness(c);
    t.Presented(t.Observe(0, false, Meta())!); c.Advance(3000);
    var pending = t.Observe(0, false, Meta(2))!;
    Check(t.Status.State == "quiet"); t.Presented(pending); Check(t.Status.State == "recent");
});
Test("duplicates received while pending refresh only matching content", () => {
    var c = new Clock(); var t = new PreviewFreshness(c);
    var pending = t.Observe(0, false, Meta())!; c.Advance(3000); t.Observe(0, true, Meta(2));
    t.Presented(pending); Check(t.Status.State == "recent");
});
Test("a replaced pending frame cannot borrow newer content freshness", () => {
    var c = new Clock(); var t = new PreviewFreshness(c);
    var old = t.Observe(0, false, Meta())!; c.Advance(3000); t.Observe(0, false, Meta(2));
    t.Presented(old); Check(t.Status.State == "quiet");
});
Test("old selected-phone responses, failures and presentations are ignored", () => {
    var t = new PreviewFreshness(new Clock()); var old = t.Observe(0, false, Meta())!;
    t.Reset(1); Check(!t.IsCurrent(old)); t.Presented(old); t.Failed(0);
    Check(t.Observe(0, false, Meta()) is null);
    Check(t.Status.State == "waiting" && !t.Status.FetchFailed);
});
Test("failed fetch warns until a successful response", () => {
    var t = new PreviewFreshness(new Clock()); t.Presented(t.Observe(0, false, Meta())!);
    t.Failed(0); Check(t.Status.FetchFailed && t.Status.Text.Contains("not updating"));
    t.Observe(0, true, Meta(2)); Check(!t.Status.FetchFailed);
});
Test("manual refresh and pump histories never share content revisions", () => {
    var t = new PreviewFreshness(new Clock()); t.Presented(t.Observe(0, false, Meta(1))!);
    var manual = t.Observe(0, false, Meta(2, 3000), "manual")!; t.Presented(manual);
    var pump = t.Observe(0, true, Meta(3))!; Check(pump.Revision != manual.Revision);
    Check(t.Status.State == "quiet");
});
Test("receiver quiet flag is not overridden by a small age", () => {
    var t = new PreviewFreshness(new Clock()); t.Presented(t.Observe(0, false, Meta() with { Delivery = "quiet" })!);
    Check(t.Status.State == "quiet");
});
Test("valid headers parse with invariant decimals and request duration", () => {
    using var r = Response(); r.Headers.Remove("X-iMouse-Frame-Age-Ms"); r.Headers.Add("X-iMouse-Frame-Age-Ms", "12.5");
    var old = CultureInfo.CurrentCulture;
    try { CultureInfo.CurrentCulture = new("fr-FR"); Check(ScreenshotMetadata.Parse(r.Headers, 5)?.AgeMs == 17.5); }
    finally { CultureInfo.CurrentCulture = old; }
});
Test("missing headers are unknown", () => {
    using var r = new HttpResponseMessage(); Check(ScreenshotMetadata.Parse(r.Headers, 0) is null);
});
foreach (var (key, value) in new[]{
    ("Sequence", "0"), ("Sequence", "-1"), ("Sequence", "1.5"), ("Sequence", "9223372036854775808"),
    ("Age-Ms", "NaN"), ("Age-Ms", "Infinity"), ("Age-Ms", "-1"), ("Age-Ms", "1,5"),
    ("Session", "not-a-session"), ("Delivery", "failed")})
    Test($"invalid {key}={value} stays unknown", () => {
        using var r = Response(); r.Headers.Remove("X-iMouse-Frame-" + key);
        r.Headers.TryAddWithoutValidation("X-iMouse-Frame-" + key, value);
        Check(ScreenshotMetadata.Parse(r.Headers, 0) is null);
    });
Test("duplicate header values cannot assert freshness", () => {
    using var r = Response(); r.Headers.TryAddWithoutValidation("X-iMouse-Frame-Sequence", "2");
    Check(ScreenshotMetadata.Parse(r.Headers, 0) is null);
});
Async("actual API buffer attaches metadata and clears it for legacy response", async () => {
    int n = 0; using var handler = new Fake(_ => ++n == 1 ? Response() : Response(false));
    using var api = new ApiClient("http://offline.invalid", handler); var b = new FrameBuffer();
    await api.ScreenshotIntoAsync("fake", false, b); Check(b.Metadata?.Sequence == 1 && b.Length == 70);
    await api.ScreenshotIntoAsync("fake", false, b); Check(b.Metadata is null && b.Length == 70);
});
Async("failed fetch clears old metadata before request and sends no input", async () => {
    int n = 0; using var handler = new Fake(_ => ++n == 1 ? Response() : new(HttpStatusCode.ServiceUnavailable));
    using var api = new ApiClient("http://offline.invalid", handler); var b = new FrameBuffer();
    await api.ScreenshotIntoAsync("fake", false, b); bool failed = false;
    try { await api.ScreenshotIntoAsync("fake", false, b); } catch (HttpRequestException) { failed = true; }
    Check(failed && b.Metadata is null && b.Length == 0);
});
Async("base64 fallback preserves metadata from same response", async () => {
    using var handler = new Fake(_ => {
        var r = Response(); r.Content = new StringContent(JsonSerializer.Serialize(new {status=200,data=new {code=0,image=Convert.ToBase64String(Bmp())}})); return r;
    });
    using var api = new ApiClient("http://offline.invalid", handler); var b = new FrameBuffer();
    await api.ScreenshotIntoAsync("fake", false, b); Check(b.Metadata?.Sequence == 1 && b.Length == 70);
});
Async("bad image response cannot retain previous metadata", async () => {
    int n = 0; using var handler = new Fake(_ => ++n == 1 ? Response() : new(HttpStatusCode.OK) {Content=new StringContent("bad image")});
    using var api = new ApiClient("http://offline.invalid", handler); var b = new FrameBuffer();
    await api.ScreenshotIntoAsync("fake", false, b); bool failed = false;
    try { await api.ScreenshotIntoAsync("fake", false, b); } catch (ApiException) { failed = true; }
    Check(failed && b.Metadata is null);
});
Test("out-of-order response cannot replace newer observed receiver session", () => {
    var t = new PreviewFreshness(new Clock());
    t.Presented(t.Observe(0, false, Meta(), requestSerial: 2)!);
    Check(t.Observe(0, false, Meta() with {Session=Guid.NewGuid().ToString("N")}, requestSerial: 1) is null);
    Check(t.Status.State == "recent");
});
Test("pending older content cannot overwrite a newer presented refresh", () => {
    var t = new PreviewFreshness(new Clock()); var old = t.Observe(0, false, Meta())!;
    t.Presented(t.Observe(0, false, Meta(2, 3000), "manual")!);
    Check(!t.IsCurrent(old)); t.Presented(old); Check(t.Status.State == "quiet");
});
Async("bad headers leave a usable legacy image with unknown age", async () => {
    using var handler = new Fake(_ => { var r = Response(); r.Headers.Remove("X-iMouse-Frame-Age-Ms"); r.Headers.Add("X-iMouse-Frame-Age-Ms", "NaN"); return r; });
    using var api = new ApiClient("http://offline.invalid", handler); var b = new FrameBuffer();
    await api.ScreenshotIntoAsync("fake", false, b); Check(b.Length == 70 && b.Metadata is null);
});
Async("cancelled fetch clears evidence and next screenshot can recover", async () => {
    int n = 0; using var handler = new Fake(_ => ++n == 2 ? throw new TaskCanceledException("mock timeout") : Response());
    using var api = new ApiClient("http://offline.invalid", handler); var b = new FrameBuffer();
    await api.ScreenshotIntoAsync("fake", false, b); bool failed = false;
    try { await api.ScreenshotIntoAsync("fake", false, b); } catch (OperationCanceledException) { failed = true; }
    Check(failed && b.Metadata is null && b.Length == 0);
    await api.ScreenshotIntoAsync("fake", false, b); Check(b.Metadata is not null && b.RequestSerial == 3);
});
Test("late failed request cannot mark newer successful preview failed", () => {
    var t = new PreviewFreshness(new Clock());
    t.Presented(t.Observe(0, false, Meta(), requestSerial: 2)!);
    t.Failed(0, 1); Check(!t.Status.FetchFailed);
    t.Failed(0, 3); Check(t.Status.FetchFailed);
    Check(t.Observe(0, true, Meta(), requestSerial: 2) is null);
    Check(t.Status.FetchFailed);
});
tests.AddRange(ScreenshotTransferTests.Cases());
int passed = 0;
foreach (var (name, run) in tests)
{
    // Transfer cases exercise the real eight-second HTTP deadline. Each owns
    // its cancellation/cleanup; this outer bound is only a failed-test guard.
    try { await run().WaitAsync(TimeSpan.FromSeconds(20)); passed++; Console.WriteLine("PASS " + name); }
    catch (Exception ex) { Console.WriteLine("FAIL " + name + ": " + ex); }
}
Console.WriteLine($"{passed}/{tests.Count} passed"); return passed == tests.Count ? 0 : 1;
static void Check(bool ok) { if (!ok) throw new Exception("Assertion failed"); }
static ScreenshotMetadata Meta(long seq = 1, double age = 0) => new("0123456789abcdef0123456789abcdef", seq, age, "flowing");
static byte[] Bmp() { var b = new byte[70]; b[0] = (byte)'B'; b[1] = (byte)'M'; return b; }
static HttpResponseMessage Response(bool headers = true)
{
    var r = new HttpResponseMessage(HttpStatusCode.OK) {Content=new ByteArrayContent(Bmp())};
    if (headers) {
        r.Headers.Add("X-iMouse-Frame-Session", Meta().Session); r.Headers.Add("X-iMouse-Frame-Sequence", "1");
        r.Headers.Add("X-iMouse-Frame-Age-Ms", "0"); r.Headers.Add("X-iMouse-Frame-Delivery", "flowing");
    }
    return r;
}
sealed class Clock : TimeProvider
{
    private long _ms; public override long TimestampFrequency => 1000;
    public override long GetTimestamp() => _ms; public void Advance(long ms) => _ms += ms;
}
sealed class Fake(Func<HttpRequestMessage, HttpResponseMessage> reply) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        if (request.Method != HttpMethod.Get || request.RequestUri?.AbsolutePath != "/api/pic/screenshot")
            throw new Exception("Only mock screenshot reads allowed");
        ct.ThrowIfCancellationRequested(); return Task.FromResult(reply(request));
    }
}

using System.IO;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Threading;

// Test driver for the preserved native assembly. Never calls Show, creates a
// window handle, moves a desktop cursor, or sends a kernel request directly.
internal static class Program
{
    const string CandidateHash = "effa8083c8c71a7f1522cfaf9765de315e6bca9c18891c2a1bd42822bf49570a";
    const BindingFlags Members = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
    static readonly JsonSerializerOptions Json = new() { WriteIndented = true };
    static readonly List<object> Checks = [];
    static readonly List<Window> Windows = [];
    static string Folder = "";
    static T Field<T>(object target, string name) => (T)target.GetType().GetField(name, Members)!.GetValue(target)!;
    static void Set(object target, string name, object value) => target.GetType().GetField(name, Members)!.SetValue(target, value);
    static async Task Call(object target, string name)
    {
        Func<Task> call = () => (Task)target.GetType().GetMethod(name, Members)!.Invoke(target, null)!;
        await (Task)target.GetType().GetMethod("RunAsync", Members)!.Invoke(target, [call])!;
        Field<DispatcherTimer>(target, "_poll").Stop();
    }
    static void Check(string name, bool pass)
    {
        Checks.Add(new { name, pass });
        Write("checks.json", Checks);
        if (!pass) throw new InvalidOperationException(name);
    }
    static void Write(string name, object value) => File.WriteAllText(Path.Combine(Folder, name), JsonSerializer.Serialize(value, Json));
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        var options = JsonDocument.Parse(File.ReadAllBytes(args[0])).RootElement.Clone();
        Folder = options.GetProperty("output").GetString()!;
        if (Directory.Exists(Folder)) throw new InvalidOperationException("Never reuse an attempt folder.");
        Directory.CreateDirectory(Folder);
        var application = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
        application.Dispatcher.BeginInvoke(async () =>
        {
            int result = 0;
            try { await Run(options); }
            catch (Exception error) { result = 1; Write("failure.json", new { error = error.ToString(), utc = DateTime.UtcNow }); }
            finally
            {
                // On failure request cancellation of this driver's own pending
                // operation before stopping the message loop. No new request.
                foreach (var window in Windows)
                {
                    if (result != 0 && Field<object?>(window, "_pending") is not null && !Field<bool>(window, "_terminal"))
                    {
                        try { await Call(window, "StopAsync"); } catch { }
                    }
                    Field<DispatcherTimer>(window, "_poll").Stop();
                    Set(window, "_terminal", true); window.Close();
                }
                application.Shutdown(result);
            }
        });
        return application.Run();
    }

    static async Task Run(JsonElement options)
    {
        string phase = options.GetProperty("phase").GetString()!, scenario = options.GetProperty("scenario").GetString()!;
        Check("Explicit bounded scenario", phase is "offline" or "live" && scenario is "response-loss" or "cancel-on-admission");
        bool stopAfterReset = phase == "live" || (options.TryGetProperty("exerciseOwnedReset", out var exercise) && exercise.GetBoolean());
        var address = new Uri(options.GetProperty("backend").GetString()!);
        Check("Only the configured loopback backend", address.Scheme == "http" && address.Host == "127.0.0.1" && address.AbsolutePath == "/" && (phase == "live" ? address.Port == 9915 : address.Port > 1024 && address.Port is not (9911 or 9913 or 9914 or 9915 or 9916)));
        string assemblyPath = options.GetProperty("assembly").GetString()!;
        Check("Preserved native assembly hash", Hash(File.ReadAllBytes(assemblyPath)) == CandidateHash);
        string draft = options.GetProperty("draftId").GetString()!, store = options.GetProperty("storeId").GetString()!;
        int revision = options.GetProperty("revision").GetInt32();
        Check("Request has saved draft and store identities", Guid.TryParse(draft, out _) && Guid.TryParse(store, out _) && revision > 0);
        using var handler = new RecordedHandler(address, scenario);
        using var http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(10) };
        var health = await Read(http, address + "health");
        Check("Backend identity and source match preparation", health.GetProperty("sourceHash").GetString() == options.GetProperty("backendSourceHash").GetString() && health.GetProperty("executionMode").GetString() == "live" && health.GetProperty("draftWorkflow").GetProperty("storeId").GetString() == store && health.GetProperty("draftWorkflow").GetProperty("enabled").GetBoolean());
        if (phase == "live")
            Check("Live request remains C24C test draft only", draft == "eeb59816-5805-4169-aa1c-d91fe1e2c14f" && revision == 5 && health.GetProperty("draftWorkflow").GetProperty("contentSha256").GetString() == "fa226761c643c72800a2fada366652ae4baa49177cea3e76e5280b71f673a058");
        var assembly = Assembly.LoadFrom(assemblyPath);
        var apiType = assembly.GetType("IMouse2.FarmApiClient", true)!;
        var windowType = assembly.GetType("IMouse2.FarmDraftRunWindow", true)!;
        object api = Activator.CreateInstance(apiType, Members, null, [http, address.ToString().TrimEnd('/')], null)!;
        var data = Path.Combine(Folder, "interface-data"); Directory.CreateDirectory(data);
        handler.Bookmark = Path.Combine(data, "farm-pending-draft-run.json");
        Window New()
        {
            var window = (Window)Activator.CreateInstance(windowType, Members, null, [api, data, draft, revision, "Prepared three-slide test draft"], null)!;
            Windows.Add(window); return window;
        }
        var original = New(); await Call(original, "InitializeAsync");
        Check("Native window starts read-only and permits explicit start", Field<Button>(original, "_start").IsEnabled && handler.Starts == 0);
        await Call(original, "StartAsync");
        Check("Bookmark persisted before the single submission", handler.BookmarkSeen && handler.Starts == 1 && handler.Id is not null);
        if (scenario == "response-loss")
        {
            Check("Lost response retains the request without another start", handler.Dropped && Field<object?>(original, "_pending") is not null && !Field<Button>(original, "_start").IsEnabled);
        }
        else
        {
            // For the live check wait only for the first confirmed pointer reset.
            // This proves cancellation releases an acquired lease, before any
            // draft edit/save. A changed sequence is stopped and left for review.
            if (stopAfterReset)
            {
                bool acquired = false, navigated = false;
                var stopLimit = DateTime.UtcNow.AddSeconds(20);
                while (!acquired && !navigated && DateTime.UtcNow < stopLimit)
                {
                    var current = (await Read(http, address + "api/farm/draft-runs/" + handler.Id)).GetProperty("run");
                    if (current.GetProperty("terminal").GetBoolean()) break;
                    if (current.GetProperty("workflow") is var workflow && workflow.ValueKind == JsonValueKind.Object)
                    {
                        navigated = workflow.GetProperty("actions").GetArrayLength() > 0;
                        acquired = workflow.GetProperty("commands").EnumerateArray().Any(c => c.GetProperty("purpose").GetString() == "initial_pointer_reset" && c.GetProperty("state").GetString() == "answered");
                    }
                    if (!acquired && !navigated) await Task.Delay(50);
                }
                await Call(original, "StopAsync");
                Check("Stop sent after ownership and before draft navigation", acquired && !navigated);
            }
            else
            {
                await Call(original, "StopAsync");
            }
            Check("Native Stop uses the scoped cancellation route", handler.Cancels == 1);
        }
        // Detach this test view without invoking the normal Close cancellation.
        // The replacement object reads its durable bookmark exactly as reopening
        // the product window does; the backend operation is never resubmitted.
        Set(original, "_terminal", true); original.Close();
        var recovered = New(); await Call(recovered, "InitializeAsync");
        Check("Recreated native view recovers without POST replay", handler.Starts == 1);
        var limit = DateTime.UtcNow.AddSeconds(145);
        while (!Field<bool>(recovered, "_terminal") && DateTime.UtcNow < limit)
        {
            await Task.Delay(1000); await Call(recovered, "RecoverAsync");
        }
        Check("Recovered request terminates within the bounded window", Field<bool>(recovered, "_terminal"));
        var response = await Read(http, address + "api/farm/draft-runs/" + handler.Id);
        var run = response.GetProperty("run"); Write("terminal.json", response);
        Check("Same request and store returned", run.GetProperty("id").GetString() == handler.Id && run.GetProperty("storeId").GetString() == store);
        Check("Cleanup confirmed with no automatic resume", run.GetProperty("cleanup").GetString() == "confirmed" && !run.GetProperty("automaticResume").GetBoolean());
        if (scenario == "response-loss")
        {
            Check("Native view recognizes verified saved draft", run.GetProperty("savedDraftVerified").GetBoolean() && Field<TextBlock>(recovered, "_status").Text.Contains("PHONE DRAFT VERIFIED") && Field<object?>(recovered, "_pending") is null);
            if (phase == "live")
            {
                var actions = run.GetProperty("workflow").GetProperty("actions").EnumerateArray().ToArray();
                Check("Exactly the validated nineteen actions", actions.Length == 19 && actions.All(a => a.GetProperty("state").GetString() == "answered"));
                await Call(recovered, "ViewAsync");
                Check("Native evidence preview loads retained phone frame", Field<Image>(recovered, "_preview").Source is not null);
            }
        }
        else
        {
            Check("Cancelled check stays review-only with its bookmark", run.GetProperty("jobStatus").GetString() == "cancelled" && !run.GetProperty("savedDraftVerified").GetBoolean() && Field<object?>(recovered, "_pending") is not null && !Field<Button>(recovered, "_start").IsEnabled);
            if (stopAfterReset) Check("Cancelled phone check sent no semantic navigation or Save", run.GetProperty("workflow").GetProperty("actions").GetArrayLength() == 0);
        }
        var before = run.GetRawText();
        await Call(recovered, "RecoverAsync");
        var after = (await Read(http, address + "api/farm/draft-runs/" + handler.Id)).GetProperty("run");
        Check("Repeated result retrieval never starts another workflow", before == after.GetRawText() && handler.Starts == 1);
        Check("No desktop window handle created", Windows.All(w => new WindowInteropHelper(w).Handle == IntPtr.Zero));
        Write("result.json", new { passed = true, phase, scenario, candidateHash = CandidateHash, requestId = handler.Id, storeId = store, startRequests = handler.Starts, cancellationRequests = handler.Cancels, desktopControl = false, windowHandles = 0, publishing = false, messaging = false, checks = Checks.Count, statusText = Field<TextBlock>(recovered, "_status").Text });
    }

    static async Task<JsonElement> Read(HttpClient http, string url)
    {
        using var response = await http.GetAsync(url); response.EnsureSuccessStatusCode();
        return JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement.Clone();
    }

    sealed class RecordedHandler(Uri backend, string scenario) : DelegatingHandler(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false })
    {
        internal string? Bookmark, Id;
        internal int Starts, Cancels;
        internal bool Dropped, BookmarkSeen;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            var url = request.RequestUri!; string route = url.AbsolutePath;
            if (url.GetLeftPart(UriPartial.Authority) != backend.GetLeftPart(UriPartial.Authority) || !(route == "/health" || route.StartsWith("/api/farm/draft-runs"))) throw new InvalidOperationException("Driver cannot address the kernel or another service.");
            bool submit = request.Method == HttpMethod.Post && route == "/api/farm/draft-runs";
            if (request.Method != HttpMethod.Get && !submit && !(request.Method == HttpMethod.Post && route.EndsWith("/cancel"))) throw new InvalidOperationException("Unsupported request.");
            if (submit)
            {
                Starts++; if (Starts != 1) throw new InvalidOperationException("No replay permitted.");
                var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(token)).RootElement;
                Id = body.GetProperty("id").GetString();
                BookmarkSeen = JsonDocument.Parse(File.ReadAllBytes(Bookmark!)).RootElement.GetProperty("Id").GetString() == Id;
                if (!BookmarkSeen) throw new InvalidOperationException("No durable request bookmark.");
                Write("request.json", body);
            }
            if (request.Method == HttpMethod.Post && route.EndsWith("/cancel")) Cancels++;
            var response = await base.SendAsync(request, token);
            var raw = await response.Content.ReadAsByteArrayAsync(token);
            File.AppendAllText(Path.Combine(Folder, "http.jsonl"), JsonSerializer.Serialize(new { utc = DateTime.UtcNow, method = request.Method.Method, route, status = (int)response.StatusCode, sha256 = Hash(raw), bytes = raw.Length }) + "\n");
            if (submit && scenario == "response-loss" && response.IsSuccessStatusCode)
            {
                Dropped = true; response.Dispose(); throw new HttpRequestException("TEST: admitted submission response discarded; recover the saved ID.");
            }
            return response;
        }
    }
}

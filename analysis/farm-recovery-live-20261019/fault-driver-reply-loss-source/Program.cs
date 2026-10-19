using System.IO;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Threading;

internal sealed class ReplyLoss : DelegatingHandler
{
    internal readonly List<object> Events = [];
    internal int AdmissionLosses, StatusLosses, Admissions;
    internal string? RequestId;
    readonly bool inject;
    readonly string output;
    internal ReplyLoss(bool inject, string output) : base(new SocketsHttpHandler())
    { this.inject = inject; this.output = output; }
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
    {
        const string route = "/api/farm/draft-recoveries";
        if (request.RequestUri is not { Scheme: "http", Host: "127.0.0.1", Port: 9915 })
            throw new InvalidOperationException("This probe only reaches the private candidate backend.");
        string path = request.RequestUri.AbsolutePath;
        bool admission = request.Method == HttpMethod.Post && path == route;
        bool status = request.Method == HttpMethod.Get && path.StartsWith(route + "/") && Guid.TryParse(path[(route.Length + 1)..], out _);
        if (request.Method == HttpMethod.Get && path != "/health" && path != route && path != route + "/eligibility" && !status)
            throw new InvalidOperationException("This probe only reads inspection status and eligibility.");
        if (request.Method != HttpMethod.Get && !admission)
            throw new InvalidOperationException("This probe cannot cancel or issue other backend operations.");
        if (admission)
        {
            Admissions++;
            using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(token));
            RequestId = body.RootElement.GetProperty("id").GetString();
            if (Admissions != 1) throw new InvalidOperationException("A second admission is forbidden.");
        }
        var response = await base.SendAsync(request, token);
        bool loseAdmission = inject && response.IsSuccessStatusCode && admission && AdmissionLosses == 0;
        bool loseStatus = inject && response.IsSuccessStatusCode && status && StatusLosses == 0;
        bool lose = loseAdmission || loseStatus;
        if (loseAdmission) AdmissionLosses++;
        if (loseStatus) StatusLosses++;
        // These are controlled receive failures after the real backend answered.
        // They do not claim TCP packet loss or terminate any phone command.
        if (lose) await response.Content.LoadIntoBufferAsync();
        Events.Add(new { method = request.Method.Method, path, status = (int)response.StatusCode,
            suppressed = lose, utc = DateTime.UtcNow, requestId = RequestId });
        File.WriteAllText(Path.Combine(output, "http-events.json"), JsonSerializer.Serialize(Events, new JsonSerializerOptions { WriteIndented = true }));
        if (lose)
        {
            response.Dispose();
            throw new HttpRequestException("Controlled candidate client reply loss: " + (admission ? "admission" : "status"));
        }
        return response;
    }
}

internal static class Program
{
    const BindingFlags Members = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
    static T Field<T>(object value, string name) => (T)value.GetType().GetField(name, Members)!.GetValue(value)!;
    static async Task Call(object value, string name)
    {
        Func<Task> call = () => (Task)value.GetType().GetMethod(name, Members)!.Invoke(value, null)!;
        await (Task)value.GetType().GetMethod("RunAsync", Members)!.Invoke(value, [call])!;
        Field<DispatcherTimer>(value, "_poll").Stop();
    }
    [STAThread] static int Main(string[] args)
    {
        bool validate = args.Length == 2 && args[0] == "--validate";
        if (!(args.Length == 1 || validate)) return 2;
        var options = JsonDocument.Parse(File.ReadAllBytes(args[^1])).RootElement.Clone();
        string mode = options.GetProperty("faultMode").GetString()!;
        if (mode is not ("lostAdmissionAndStatus" or "recoverOnly")) return 2;
        string output = options.GetProperty("output").GetString()! + (validate ? "-dry-run" : "");
        if (Directory.Exists(output)) throw new InvalidOperationException("Never reuse an attempt folder.");
        Directory.CreateDirectory(output);
        var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
        app.Dispatcher.BeginInvoke(async () =>
        {
            Window? window = null; int code = 0;
            var checks = new List<object>();
            void Write(string name, object value) => File.WriteAllText(Path.Combine(output, name), JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true }));
            void Check(string name, bool pass) { checks.Add(new { name, pass }); Write("checks.json", checks); if (!pass) throw new InvalidOperationException(name); }
            try
            {
                string assembly = options.GetProperty("assembly").GetString()!;
                Check("Exact prepared candidate assembly", Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(assembly))).ToLowerInvariant() == options.GetProperty("nativeSha256").GetString());
                using var loss = new ReplyLoss(mode == "lostAdmissionAndStatus", output);
                using var http = new HttpClient(loss) { Timeout = TimeSpan.FromSeconds(15) };
                const string backend = "http://127.0.0.1:9915";
                var loaded = Assembly.LoadFrom(assembly);
                var api = Activator.CreateInstance(loaded.GetType("IMouse2.FarmApiClient", true)!, Members, null, [http, backend], null)!;
                window = (Window)Activator.CreateInstance(loaded.GetType("IMouse2.FarmDraftRunWindow", true)!, Members, null,
                    [api, options.GetProperty("dataDirectory").GetString()!, options.GetProperty("draftId").GetString()!, options.GetProperty("revision").GetInt32(), "Retained saved draft", false, options.GetProperty("creationId").GetString()!], null)!;
                Check("No desktop window handle", new WindowInteropHelper(window).Handle == IntPtr.Zero);
                Check("Inspection route only", Field<string>(window, "_route") == "/api/farm/draft-recoveries" && Field<bool>(window, "_inspection"));
                if (validate) Write("validation.json", new { passed = true, phoneInput = false, serviceStarted = false, desktopControl = false });
                else
                {
                    using var health = JsonDocument.Parse(await http.GetStringAsync(backend + "/health"));
                    var cap = health.RootElement.GetProperty("draftRecovery");
                    Check("Exact isolated source and C24C inspection scope", health.RootElement.GetProperty("sourceHash").GetString() == options.GetProperty("backendSourceHash").GetString() && cap.GetProperty("storeId").GetString() == options.GetProperty("recoveryStoreId").GetString() && cap.GetProperty("enabled").GetBoolean() && cap.GetProperty("inspectionOnly").GetBoolean() && cap.GetProperty("device").GetString() == "C24C" && cap.GetProperty("account").GetString() == "xs.halle.xo" && !cap.GetProperty("publishing").GetBoolean() && !cap.GetProperty("messaging").GetBoolean());
                    await Call(window, "InitializeAsync");
                    if (mode == "lostAdmissionAndStatus")
                    {
                        Check("Native inspection Start is eligible", Field<Button>(window, "_start").IsEnabled);
                        await Call(window, "StartAsync");
                        Check("Lost admission leaves the durable original request", loss.Admissions == 1 && loss.AdmissionLosses == 1 && Field<object?>(window, "_pending") is not null && !Field<bool>(window, "_terminal") && Field<TextBlock>(window, "_status").Text.Contains("Controlled candidate client reply loss: admission"));
                        string bookmark = Path.Combine(options.GetProperty("dataDirectory").GetString()!, "farm-pending-draft-inspection.json");
                        File.Copy(bookmark, Path.Combine(output, "retained-bookmark.json"));
                        await Call(window, "RecoverAsync");
                        Check("Lost status keeps that same pending request", loss.StatusLosses == 1 && Field<object?>(window, "_pending") is not null && !Field<bool>(window, "_terminal") && Field<TextBlock>(window, "_status").Text.Contains("Controlled candidate client reply loss: status"));
                        var deadline = DateTime.UtcNow.AddMinutes(3);
                        while (!Field<bool>(window, "_terminal") && DateTime.UtcNow < deadline)
                        {
                            await Task.Delay(1800); await Call(window, "RecoverAsync");
                            Write("status.json", new { status = Field<TextBlock>(window, "_status").Text, utc = DateTime.UtcNow });
                        }
                        Check("One admission despite both lost replies", loss.Admissions == 1 && loss.AdmissionLosses == 1 && loss.StatusLosses == 1);
                    }
                    else Check("Reopened native bookmark issues GETs only", loss.Admissions == 0 && Field<string>(window, "_shownId") == options.GetProperty("expectedId").GetString());
                    Check("Bounded terminal inspection", Field<bool>(window, "_terminal"));
                    string id = Field<string>(window, "_shownId");
                    string raw = await http.GetStringAsync(backend + "/api/farm/draft-recoveries/" + id);
                    File.WriteAllText(Path.Combine(output, "result.json"), raw);
                    var result = JsonDocument.Parse(raw).RootElement.GetProperty("run");
                    Check("Matching saved draft observed", result.GetProperty("savedDraftVerified").GetBoolean() && result.GetProperty("inspectionOnly").GetBoolean() && !result.GetProperty("originalOutcomeChanged").GetBoolean() && !result.GetProperty("appRestartVerified").GetBoolean());
                    Check("Native result clears the reconciled bookmark", Field<object?>(window, "_pending") is null && Field<TextBlock>(window, "_status").Text.Contains("MATCHING SAVED DRAFT OBSERVED"));
                    Check("No publishing messaging or desktop control", !result.GetProperty("publishing").GetBoolean() && !result.GetProperty("messaging").GetBoolean() && new WindowInteropHelper(window).Handle == IntPtr.Zero);
                }
            }
            catch (Exception error) { code = 1; Write("failure.json", new { error = error.ToString(), utc = DateTime.UtcNow }); }
            finally
            {
                if (window is not null)
                {
                    if (!validate && !Field<bool>(window, "_terminal") && Field<object?>(window, "_pending") is not null)
                        Write("pending-at-exit.json", new { reviewRequired = true, automaticReplay = false });
                    // This diagnostic never sends Stop from a finally block. The
                    // bounded backend remains responsible for its existing lease.
                    window.GetType().GetField("_terminal", Members)!.SetValue(window, true);
                    Field<DispatcherTimer>(window, "_poll").Stop(); window.Close();
                }
                app.Shutdown(code);
            }
        });
        return app.Run();
    }
}

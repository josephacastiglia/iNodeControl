using System.IO;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Threading;

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
                using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
                const string backend = "http://127.0.0.1:9915";
                var loaded = Assembly.LoadFrom(assembly);
                var api = Activator.CreateInstance(loaded.GetType("IMouse2.FarmApiClient", true)!, Members, null, [http, backend], null)!;
                window = (Window)Activator.CreateInstance(loaded.GetType("IMouse2.FarmDraftRunWindow", true)!, Members, null,
                    [api, options.GetProperty("dataDirectory").GetString()!, options.GetProperty("draftId").GetString()!, options.GetProperty("revision").GetInt32(), "Retained saved draft", false, options.GetProperty("creationId").GetString()!], null)!;
                Check("No desktop window handle", new WindowInteropHelper(window).Handle == IntPtr.Zero);
                Check("Inspection route only", Field<string>(window, "_route") == "/api/farm/draft-recoveries" && Field<bool>(window, "_inspection"));
                if (validate) { Write("validation.json", new { passed = true, phoneInput = false, serviceStarted = false, desktopControl = false }); }
                else
                {
                    using var health = JsonDocument.Parse(await http.GetStringAsync(backend + "/health"));
                    var cap = health.RootElement.GetProperty("draftRecovery");
                    Check("Exact isolated source and C24C inspection scope", health.RootElement.GetProperty("sourceHash").GetString() == options.GetProperty("backendSourceHash").GetString() && cap.GetProperty("storeId").GetString() == options.GetProperty("recoveryStoreId").GetString() && cap.GetProperty("enabled").GetBoolean() && cap.GetProperty("inspectionOnly").GetBoolean() && cap.GetProperty("device").GetString() == "C24C" && cap.GetProperty("account").GetString() == "xs.halle.xo" && !cap.GetProperty("publishing").GetBoolean() && !cap.GetProperty("messaging").GetBoolean());
                    await Call(window, "InitializeAsync");
                    Write("initial-status.json", new { status = Field<TextBlock>(window, "_status").Text });
                    Check("Native inspection Start is eligible", Field<Button>(window, "_start").IsEnabled);
                    await Call(window, "StartAsync");
                    Check("Separate durable pending inspection", Field<object?>(window, "_pending") is not null || Field<bool>(window, "_terminal"));
                    var deadline = DateTime.UtcNow.AddMinutes(3);
                    while (!Field<bool>(window, "_terminal") && DateTime.UtcNow < deadline)
                    {
                        await Task.Delay(1800); await Call(window, "RecoverAsync");
                        Write("status.json", new { status = Field<TextBlock>(window, "_status").Text, utc = DateTime.UtcNow });
                    }
                    Check("Bounded terminal inspection", Field<bool>(window, "_terminal"));
                    string id = Field<string>(window, "_shownId");
                    string raw = await http.GetStringAsync(backend + "/api/farm/draft-recoveries/" + id); File.WriteAllText(Path.Combine(output, "result.json"), raw);
                    var result = JsonDocument.Parse(raw).RootElement.GetProperty("run");
                    Check("Matching saved draft observed", result.GetProperty("savedDraftVerified").GetBoolean() && result.GetProperty("inspectionOnly").GetBoolean() && !result.GetProperty("originalOutcomeChanged").GetBoolean() && !result.GetProperty("appRestartVerified").GetBoolean());
                    Check("Native result agrees with retained bookmark", Field<object?>(window, "_pending") is null && Field<TextBlock>(window, "_status").Text.Contains("MATCHING SAVED DRAFT OBSERVED"));
                    Check("No publishing messaging or desktop control", !result.GetProperty("publishing").GetBoolean() && !result.GetProperty("messaging").GetBoolean() && new WindowInteropHelper(window).Handle == IntPtr.Zero);
                }
            }
            catch (Exception error) { code = 1; Write("failure.json", new { error = error.ToString(), utc = DateTime.UtcNow }); }
            finally
            {
                if (window is not null)
                {
                    if (!validate && !Field<bool>(window, "_terminal") && Field<object?>(window, "_pending") is not null) try { await Call(window, "StopAsync"); } catch { }
                    window.GetType().GetField("_terminal", Members)!.SetValue(window, true);
                    Field<DispatcherTimer>(window, "_poll").Stop(); window.Close();
                }
                app.Shutdown(code);
            }
        });
        return app.Run();
    }
}

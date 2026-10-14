using System.Net;
using System.Text.Json;

namespace IMouse2.Kernel;

internal static class KernelStartupTests
{
    internal static async Task RunAsync(Action<bool, string> check)
    {
        void Reject(Action action, string label)
        {
            bool refused = false;
            try { action(); }
            catch (Exception ex) when (ex is ArgumentException or IOException or JsonException) { refused = true; }
            check(refused, label);
        }
        var defaults = KernelOptions.Parse([]);
        check(defaults.ReplyBoards.Length == 0, "HID reply observation is off unless explicitly scoped at startup");
        check(KernelOptions.Parse(["--input-pid", "C24C,C241", "--hid-replies-pid", "c24c"]).ReplyBoards.SequenceEqual(new[] { "c24c" }),
            "Reply observation can select a subset of enabled boards");
        foreach (var args in new[] {
            new[] { "--hid-replies-pid", "C24C" },
            new[] { "--input-pid", "C24C", "--hid-replies-pid", "C241" },
            new[] { "--input-pid", "C24C", "--hid-replies-pid", "C24C,c24c" },
            new[] { "--input-pid", "C24C", "--hid-replies-pid", "C24C," },
            new[] { "--input-pid", "C24C", "--hid-replies-pid", "C24C", "--hid-caps" } })
            Reject(() => KernelOptions.Parse(args), "Unsafe reply diagnostic scope refused: " + string.Join(' ', args));
        check(defaults.PreciseDelayMs == 7 && defaults.Home == HomeSequence.Vendor && defaults.Allowed.Length == 0
            && defaults.Prefix == "http://127.0.0.1:9913/api/", "Startup defaults retain pacing, Home and no enabled boards");
        check(KernelOptions.Parse(["--legacy"]).PreciseDelayMs == 0, "Legacy timing requires its explicit flag");
        var explicitOptions = KernelOptions.Parse(["http://localhost:12345/api", @"--data-dir=C:\candidate with spaces", "--precise-delay", "12", "--input-pid=C24C, C241", "--home-sequence", "command-h"]);
        check(explicitOptions.PreciseDelayMs == 12 && explicitOptions.DataDir == @"C:\candidate with spaces"
            && explicitOptions.Allowed.SequenceEqual(new[] { "C24C", "C241" }) && explicitOptions.Home == HomeSequence.CommandH,
            "Explicit startup values and paths with spaces are retained");
        foreach (var invalid in new[] {
            new[] { "--precise-delay", "0" }, new[] { "--precise-delay", "16" }, new[] { "--precise-delay", "bad" },
            new[] { "--precise-delay", "1.5" }, new[] { "--precise-delay", "999999999999" },
            new[] { "--precise-delay" }, new[] { "--precise-delay", "--legacy" }, new[] { "--precise-delay", "7", "--legacy" },
            new[] { "--data-dir=" }, new[] { "--data-dir", "one", "--data-dir=two" }, new[] { "--recievers", "file" },
            new[] { "--input-pid", "C24C," }, new[] { "--input-pid", "C24C,c24c" }, new[] { "--input-pid", "../" },
            new[] { "--home-sequence", "bad" }, new[] { "--precise-movement" },
            new[] { "http://localhost/api" }, new[] { "http://localhost:0/api/" }, new[] { "http://localhost:9913/api/?secret=x" },
            new[] { "http://localhost:9913/api/", "http://localhost:9914/api/" },
            new[] { "--validate-startup", "--hid-caps" }, new[] { "--hid-send", "C24C" },
            new[] { "--hid-caps", "--hid-replay", "C24C", "file" } })
            Reject(() => KernelOptions.Parse(invalid), "Invalid startup arguments refused: " + string.Join(' ', invalid));

        string folder = Path.Combine(Path.GetTempPath(), "imouse-startup-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        string deviceFile = Path.Combine(folder, "devices.json"), calibrationFile = Path.Combine(folder, "pointer-calibration.json"), receiverFile = Path.Combine(folder, "receivers.json");
        var phones = new[] { new Phone { deviceid = "test-phone", pid = "ABCD" } };
        var calibrations = new[] { new PointerCalibration("ABCD", 500, 1080, 14, 14, 5, 5) };
        var receivers = new[] { new ReceiverConfig("test-phone", "ABCD", "iMouse2-test", "test-startup-pipe", 7110, "02:49:4D:32:AB:CD") };
        void Save(string path, object data) => File.WriteAllText(path, JsonSerializer.Serialize(data));
        KernelOptions Options(params string[] extra) => KernelOptions.Parse(new[] { "--validate-startup", "--data-dir", folder, "--receivers", receiverFile }.Concat(extra).ToArray());
        try
        {
            Save(deviceFile, phones); Save(calibrationFile, calibrations); Save(receiverFile, receivers);
            var original = Directory.GetFiles(folder).ToDictionary(p => p, File.ReadAllBytes);
            var config = KernelConfiguration.Load(Options("--input-pid", "ABCD"));
            var report = JsonSerializer.SerializeToElement(config.ValidationReport());
            check(report.GetProperty("valid").GetBoolean() && !report.GetProperty("hardware_accessed").GetBoolean()
                && !report.GetProperty("listener_started").GetBoolean() && !report.GetProperty("receivers_started").GetBoolean()
                && original.All(p => File.ReadAllBytes(p.Key).SequenceEqual(p.Value)) && Directory.GetFiles(folder).Length == 3,
                "Valid saved configuration is read without changing files or starting components");
            Save(deviceFile, Array.Empty<Phone>());
            check(config.Store.All().Single().deviceid == "test-phone", "Validated device snapshot does not reread later file changes");
            Save(deviceFile, phones);
            File.WriteAllText(receiverFile, "[{\"DeviceId\":\"test-phone\",\"DeviceId\":\"other\"}]");
            Reject(() => KernelConfiguration.Load(Options()), "Duplicate JSON properties are refused before startup");
            foreach (string invalid in new[] { "null", "[null]", "{}", "[" })
            {
                File.WriteAllText(receiverFile, invalid);
                Reject(() => KernelConfiguration.Load(Options()), "Invalid receiver JSON shape refused: " + invalid);
            }
            Save(receiverFile, receivers);
            Save(deviceFile, new[] { phones[0], new Phone { deviceid = "other", pid = "abcd" } });
            Reject(() => KernelConfiguration.Load(Options()), "Duplicate saved board bindings are refused");
            Save(deviceFile, new[] { phones[0], new Phone { deviceid = "TEST-PHONE", pid = "ABCE" } });
            Reject(() => KernelConfiguration.Load(Options()), "Duplicate saved phone identities are refused");
            Save(deviceFile, phones);
            Save(calibrationFile, Array.Empty<PointerCalibration>());
            Reject(() => KernelConfiguration.Load(Options("--input-pid", "ABCD")), "An enabled board without calibration is refused");
            check(KernelConfiguration.Load(Options()).Options.Allowed.Length == 0, "Read-only input configuration can omit calibration");
            Save(calibrationFile, new[] { calibrations[0] with { PixelsPerUnitX = 0 } });
            Reject(() => KernelConfiguration.Load(Options()), "Invalid calibration arithmetic is refused before board enumeration");
            Save(calibrationFile, calibrations);
            Reject(() => KernelConfiguration.Load(Options("--input-pid", "ABCE")), "An enabled board without a receiver binding is refused");
            foreach (string discovery in new[] { "*", "unbound-ABCD" })
            {
                Save(deviceFile, new[] { new Phone { deviceid = discovery, pid = "ABCD" } });
                Save(receiverFile, new[] { receivers[0] with { DeviceId = discovery } });
                Reject(() => KernelConfiguration.Load(Options("--input-pid", "ABCD")), "Discovery or placeholder bindings cannot enable input: " + discovery);
            }
            Save(deviceFile, phones); Save(receiverFile, receivers);
            foreach (var bad in new[] { receivers[0] with { BoardPid = "../escape" }, receivers[0] with { Pipe = null! }, receivers[0] with { Name = null! }, receivers[0] with { Mac = null! } })
            {
                Save(receiverFile, new[] { bad });
                Reject(() => KernelConfiguration.Load(Options()), "Missing or unsafe receiver fields are refused");
            }
            Save(receiverFile, receivers);
            Reject(() => KernelConfiguration.Load(Options("--receiver", Path.Combine(folder, "missing.exe"))), "Missing receiver executable is refused");
            Reject(() => KernelConfiguration.Load(Options("--receiver-runtime", folder)), "A runtime without a receiver is refused");
            string dummy = Path.Combine(folder, "dummy.exe"); File.WriteAllText(dummy, "NOT AN EXECUTABLE; never run");
            Reject(() => KernelConfiguration.Load(Options("--receiver", dummy)), "Receiver startup needs an explicit runtime");
            Reject(() => KernelConfiguration.Load(Options("--receiver", dummy, "--receiver-runtime", folder)), "Incomplete native runtime is refused without starting its executable");

            // These are deliberately inert fixtures: validation checks presence,
            // not native loading. Exercise every plugin used by appsink/fakesink.
            string runtime = Path.Combine(folder, "runtime with spaces");
            Directory.CreateDirectory(Path.Combine(runtime, "bin"));
            var requiredFiles = new[] {
                "libexec/gstreamer-1.0/gst-plugin-scanner.exe",
                "lib/gstreamer-1.0/libgstapp.dll", "lib/gstreamer-1.0/libgstcoreelements.dll",
                "lib/gstreamer-1.0/libgstlibav.dll", "lib/gstreamer-1.0/libgstvideoparsersbad.dll",
                "lib/gstreamer-1.0/libgstvideoconvertscale.dll", "lib/gstreamer-1.0/libgstplayback.dll",
                "lib/gstreamer-1.0/libgstautodetect.dll", "lib/gstreamer-1.0/libgstaudioconvert.dll",
                "lib/gstreamer-1.0/libgstaudioresample.dll", "lib/gstreamer-1.0/libgstvolume.dll",
                "lib/gstreamer-1.0/libgstlevel.dll" };
            foreach (string relative in requiredFiles)
            {
                string path = Path.Combine(runtime, relative);
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                File.WriteAllText(path, "Presence fixture; never load");
            }
            var receiverOptions = Options("--receiver", dummy, "--receiver-runtime", runtime);
            var complete = KernelConfiguration.Load(receiverOptions);
            var completeReport = JsonSerializer.SerializeToElement(complete.ValidationReport());
            check(complete.RuntimePath == runtime && complete.ReceiverPath == dummy
                && completeReport.GetProperty("limitations").EnumerateArray().Any(item => item.GetString()!.Contains("dependency loading"))
                && !completeReport.GetProperty("receivers_started").GetBoolean(),
                "Complete runtime file fixture validates without executing or claiming native loading");
            foreach (string relative in requiredFiles)
            {
                string path = Path.Combine(runtime, relative);
                byte[] saved = File.ReadAllBytes(path);
                bool MissingIsReported()
                {
                    try { KernelConfiguration.Load(receiverOptions); return false; }
                    catch (ArgumentException ex) { return ex.Message.Contains(relative) && ex.Message.Contains("Verify the dependency package"); }
                }
                try
                {
                    File.Delete(path);
                    check(MissingIsReported(), "Missing runtime file is identified before receiver startup: " + relative);
                    File.WriteAllBytes(path, []);
                    check(MissingIsReported(), "Empty runtime file is refused before receiver startup: " + relative);
                }
                finally { File.WriteAllBytes(path, saved); }
            }
            string pluginAsDirectory = Path.Combine(runtime, "lib/gstreamer-1.0/libgstplayback.dll");
            File.Delete(pluginAsDirectory); Directory.CreateDirectory(pluginAsDirectory);
            Reject(() => KernelConfiguration.Load(receiverOptions), "A directory cannot stand in for a receiver plugin");
            check(KernelConfiguration.Load(Options()).RuntimePath.Length == 0,
                "External frame-pipe mode does not need a local receiver runtime");

            using var input = new InputRouter(config.Store, [], config.Calibrations, _ => throw new Exception("Unexpected HID access"));
            using var frames = new FrameStore("startup-tests-never-opened", "test-phone");
            int binds = 0, starts = 0;
            using (var failed = new ApiServer("http://localhost:12345/api/", config.Store, input, [("test", frames)],
                () => { binds++; throw new HttpListenerException(183, "Simulated address in use"); }))
            {
                bool refused = false;
                try { await failed.RunAsync(CancellationToken.None, () => starts++); } catch (HttpListenerException) { refused = true; }
                check(refused && binds == 1 && starts == 0, "Listener failure starts no receiver callback");
            }
            using var stopped = new CancellationTokenSource(); stopped.Cancel();
            using (var cancelled = new ApiServer("http://localhost:12345/api/", config.Store, input, [("test", frames)], () => binds++))
            {
                try { await cancelled.RunAsync(stopped.Token, () => starts++); } catch (OperationCanceledException) { }
                check(binds == 1 && starts == 0, "Cancellation before listen creates no listener or receiver");
            }
            using var duringBind = new CancellationTokenSource();
            using (var cancelled = new ApiServer("http://localhost:12345/api/", config.Store, input, [("test", frames)], () => { binds++; duringBind.Cancel(); }))
            {
                try { await cancelled.RunAsync(duringBind.Token, () => starts++); } catch (OperationCanceledException) { }
                check(binds == 2 && starts == 0, "Cancellation during listen prevents receiver startup");
            }
            using var done = new CancellationTokenSource();
            var order = new List<string>();
            using (var successful = new ApiServer("http://localhost:12345/api/", config.Store, input, [("test", frames)], () => order.Add("listen")))
            {
                await successful.RunAsync(done.Token, () => { order.Add("receivers"); done.Cancel(); });
                check(order.SequenceEqual(new[] { "listen", "receivers" }), "Receiver callback follows successful listener startup");
            }
        }
        finally { Directory.Delete(folder, recursive: true); }
    }
}

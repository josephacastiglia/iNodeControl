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
        Reject(() => KernelOptions.Parse(["--rack", "A"]), "--rack is not a kernel option: one kernel serves every configured board");
        string tmpFolder = Path.GetTempPath();
        var detached = KernelOptions.Parse(["--stop-file", Path.Combine(tmpFolder, "stop.txt"), "--console-log", Path.Combine(tmpFolder, "kernel.log")]);
        check(detached.StopFile == Path.Combine(Path.GetFullPath(tmpFolder), "stop.txt") && detached.ConsoleLog!.EndsWith("kernel.log"),
            "--stop-file and --console-log take full paths in an existing folder");
        Reject(() => KernelOptions.Parse(["--stop-file", Path.Combine(tmpFolder, "no-such-tmpFolder-" + Guid.NewGuid().ToString("N"), "stop.txt")]),
            "--stop-file refuses a missing tmpFolder");
        Reject(() => KernelOptions.Parse(["--stop-file", Path.Combine(tmpFolder, "x.txt"), "--console-log", Path.Combine(tmpFolder, "x.txt")]),
            "--stop-file and --console-log cannot be one file");
        string stopPath = Path.Combine(tmpFolder, "imouse-stop-" + Guid.NewGuid().ToString("N") + ".txt");
        var stopFile = new KernelStopFile(stopPath, 4242);
        check(!stopFile.Requested(), "No stop file: no stop");
        File.WriteAllText(stopPath, "999");
        check(!stopFile.Requested() && File.Exists(stopPath), "A stop file naming another process never stops this kernel");
        File.WriteAllText(stopPath, "not a pid");
        check(!stopFile.Requested(), "A malformed stop file never stops this kernel");
        File.WriteAllText(stopPath, "\uFEFF4242\r\n");
        check(stopFile.Requested() && !File.Exists(stopPath), "A stop file naming this PID (BOM and newline allowed) stops it once and is consumed");
        using (var watched = new CancellationTokenSource())
        {
            File.WriteAllText(stopPath, "1");   // Stale request from an earlier kernel: removed, ignored.
            var watch = stopFile.WatchAsync(watched, TimeSpan.FromMilliseconds(10));
            await Task.Delay(60);
            check(!watched.IsCancellationRequested && !File.Exists(stopPath), "A stale stop request is removed at start and ignored");
            File.WriteAllText(stopPath, "4242");
            await watch.WaitAsync(TimeSpan.FromSeconds(5));
            check(watched.IsCancellationRequested, "The stop watcher cancels the kernel exactly as Ctrl+C does");
        }
        check(defaults.HeldReceivers.Length == 0 && KernelOptions.Parse(["--hold-receivers", "C214, 724e"]).HeldReceivers.SequenceEqual(new[] { "C214", "724e" }),
            "Receivers start advertised unless explicitly held");
        foreach (var args in new[] {
            new[] { "--hold-receivers", "C214,c214" },
            new[] { "--hold-receivers", "C214," },
            new[] { "--hold-receivers", "Phone5" } })
            Reject(() => KernelOptions.Parse(args), "Invalid receiver hold refused: " + string.Join(' ', args));
        check(defaults.Home == HomeSequence.Vendor && defaults.Allowed.Length == 0
            && defaults.Prefix == "http://127.0.0.1:9913/api/", "Startup defaults retain Home and no enabled boards");
        var explicitOptions = KernelOptions.Parse(["http://localhost:12345/api", @"--data-dir=C:\candidate with spaces", "--input-pid=C24C, C241", "--home-sequence", "command-h"]);
        check(explicitOptions.DataDir == @"C:\candidate with spaces"
            && explicitOptions.Allowed.SequenceEqual(new[] { "C24C", "C241" }) && explicitOptions.Home == HomeSequence.CommandH,
            "Explicit startup values and paths with spaces are retained");
        foreach (var invalid in new[] {
            new[] { "--data-dir=" }, new[] { "--data-dir", "one", "--data-dir=two" }, new[] { "--recievers", "file" },
            new[] { "--input-pid", "C24C," }, new[] { "--input-pid", "C24C,c24c" }, new[] { "--input-pid", "../" },
            new[] { "--home-sequence", "bad" },
            new[] { "http://localhost/api" }, new[] { "http://localhost:0/api/" }, new[] { "http://localhost:9913/api/?secret=x" },
            new[] { "http://localhost:9913/api/", "http://localhost:9914/api/" } })
            Reject(() => KernelOptions.Parse(invalid), "Invalid startup arguments refused: " + string.Join(' ', invalid));
        // The API has no login, so the listener stays on this PC unless the operator asks otherwise in words.
        foreach (string local in new[] { "http://127.0.0.1:12345/api/", "http://localhost:12345/api/", "http://LOCALHOST:12345/api/",
            "http://[::1]:12345/api/", "http://127.0.0.2:12345/api/" })
            check(KernelOptions.Parse([local]).Prefix == local, "A loopback listener address needs no extra flag: " + local);
        foreach (string wildcard in new[] { "http://+:12345/api/", "http://*:12345/api/" })
        {
            Reject(() => KernelOptions.Parse([wildcard]), "A wildcard listener address is refused: " + wildcard);
            Reject(() => KernelOptions.Parse([wildcard, "--allow-network"]), "A wildcard listener address is refused even with --allow-network: " + wildcard);
        }
        foreach (string open in new[] { "http://0.0.0.0:12345/api/", "http://192.168.1.20:12345/api/",
            "http://[::]:12345/api/", "http://rack-pc:12345/api/", "http://localhost.example.com:12345/api/", "http://127.0.0.1.example.com:12345/api/" })
        {
            string refusal = "";
            try { KernelOptions.Parse([open]); } catch (ArgumentException ex) { refusal = ex.Message; }
            check(refusal.Contains("--allow-network") && refusal.Contains("127.0.0.1"), "A listener other machines could reach is refused unless explicitly allowed: " + open);
            check(KernelOptions.Parse(["--allow-network", open]).Prefix == open && KernelOptions.Parse([open, "--allow-network"]).Prefix == open,
                "The same address is accepted with --allow-network: " + open);
        }
        Reject(() => KernelOptions.Parse(["--allow-network", "--allow-network"]), "Repeated --allow-network is refused");
        Reject(() => KernelOptions.Parse(["--allow-network=yes"]), "--allow-network takes no value");
        // The kernel executable has no way to write to a board outside the leased API.
        foreach (var raw in new[] { new[] { "--hid-send", "C24C", "A100000000000000" }, new[] { "--hid-replay", "C24C", "file.json" }, new[] { "--hid-caps" } })
            Reject(() => KernelOptions.Parse(raw), "Raw board commands are not kernel options: " + raw[0]);

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
            check(report.GetProperty("listener_loopback_only").GetBoolean()
                && !JsonSerializer.SerializeToElement(KernelConfiguration.Load(Options("--allow-network", "http://0.0.0.0:12345/api/")).ValidationReport())
                    .GetProperty("listener_loopback_only").GetBoolean(),
                "The validation report says whether the listener is confined to this PC");
            Reject(() => KernelConfiguration.Load(KernelOptions.Parse(["--validate-startup", "--data-dir", folder])),
                "Startup without a saved receiver configuration is refused; there is no built-in phone");
            Save(deviceFile, Array.Empty<Phone>());
            check(config.Store.All().Single().deviceid == "test-phone", "Validated device snapshot does not reread later file changes");
            var borrowed = config.Store.All(); borrowed[0].pid = "FFFF"; borrowed.Clear();
            check(config.Store.All().Single().pid == "ABCD", "Caller snapshots cannot change the kernel's assignments");
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

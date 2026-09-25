using System.Diagnostics;
using System.Net.Http.Json;
using System.Text.Json;
using IMouse2.Kernel;

static class LiveMove
{
    public static async Task RunAsync(string[] args)
    {
        if (args.Length != 8) throw new ArgumentException("--move BOARD task|precise DELAY_MS X Y PROJECT_ROOT LABEL");
        string board = args[1], mode = args[2], root = Path.GetFullPath(args[6]), label = args[7];
        string id = board switch { "C24C" => "86:1D:4A:04:2F:F6", "C241" => "FE:A9:BC:D7:A0:44", _ => throw new ArgumentException("Unapproved board") };
        int delay = int.Parse(args[3]), x = int.Parse(args[4]), y = int.Parse(args[5]);
        if (mode is not ("task" or "precise") || delay is < 3 or > 20 || x is < 20 or > 480 || y is < 20 or > 1040
            || !System.Text.RegularExpressions.Regex.IsMatch(label, "^[a-zA-Z0-9-]+$")) throw new ArgumentException("Invalid probe arguments");
        if (Process.GetProcessesByName("iMouse2").Length != 0) throw new InvalidOperationException("Close console first to exclude pointer tracking");
        string output = Path.Combine(root, "analysis", "pointer-reliability-20260915");
        Directory.CreateDirectory(output);
        if (File.Exists(Path.Combine(output,label+".json"))) throw new IOException("Refusing to overwrite probe evidence");
        using var http = new HttpClient { BaseAddress = new Uri("http://127.0.0.1:9913/api/"), Timeout = TimeSpan.FromSeconds(15) };
        async Task<JsonElement> Get(string path) => (await http.GetFromJsonAsync<JsonElement>(path)).GetProperty("data");
        var status = await Get("kernel/status");
        if (string.Join(",",status.GetProperty("allowed").EnumerateArray().Select(v=>v.GetString()).Order()) != "C241,C24C") throw new InvalidOperationException("Input scope changed");
        var devices = (await Get("device/get")).GetProperty("list");
        foreach (var target in new[] { ("C24C", "86:1D:4A:04:2F:F6"), ("C241", "FE:A9:BC:D7:A0:44") })
        {
            var phone = devices.EnumerateArray().Single(d=>d.GetProperty("deviceid").GetString()==target.Item2);
            if (phone.GetProperty("pid").GetString()!=target.Item1 || phone.GetProperty("uid").GetString()!=target.Item1+"BFBD") throw new InvalidOperationException("Binding mismatch");
            var receiver=status.GetProperty("receivers").EnumerateArray().Single(r=>r.GetProperty("deviceid").GetString()==target.Item2);
            if (!receiver.GetProperty("live").GetBoolean() || receiver.GetProperty("name").GetString()!="iMouse2-"+target.Item1) throw new InvalidOperationException("Both independent streams must be live");
        }
        var calibration=JsonSerializer.Deserialize<List<PointerCalibration>>(File.ReadAllText(Path.Combine(root,"analysis","two-phone-config","pointer-calibration.json")))!.Single(c=>c.Pid==board);
        async Task Api(string fun, Dictionary<string,object> data)
        {
            data["id"] = id;
            using var response = await http.PostAsJsonAsync("", new { fun, data });
            response.EnsureSuccessStatusCode();
            var result = await response.Content.ReadFromJsonAsync<JsonElement>();
            if (result.GetProperty("data").GetProperty("code").GetInt32()!=0) throw new IOException(result.ToString());
        }
        async Task Shot(string identity,string suffix)
        {
            var bmp=await http.GetByteArrayAsync("pic/screenshot?id="+identity+"&binary=true");
            if (bmp.Length<54 || bmp[0]!=66 || bmp[1]!=77) throw new IOException("No live BMP");
            await File.WriteAllBytesAsync(Path.Combine(output,label+suffix+".bmp"),bmp);
        }
        await Api("/key/sendkey",new(){["fn_key"]="Home"});
        await Task.Delay(600);
        await Api("/mouse/reset",new());
        await Shot(id,"-origin");
        using var transport = new HidConnection(board);
        using var timer = new PreciseDelay();
        var gaps = new List<double>();
        int tx=Math.Max(0,(int)Math.Round((x-calibration.OriginX)/calibration.PixelsPerUnitX));
        int ty=Math.Max(0,(int)Math.Round((y-calibration.OriginY)/calibration.PixelsPerUnitY));
        int steps=Math.Max(tx,ty), px=0,py=0;
        var total=Stopwatch.StartNew();
        double sendMs=0,delayMs=0;
        try
        {
            for(int i=1;i<=steps;i++)
            {
                int nx=(int)Math.Round(tx*(double)i/steps),ny=(int)Math.Round(ty*(double)i/steps);
                var watch=Stopwatch.StartNew();
                await transport.SendAsync(HidProtocol.Mouse(0,(sbyte)(nx-px),(sbyte)(ny-py)),CancellationToken.None);
                sendMs+=watch.Elapsed.TotalMilliseconds; px=nx;py=ny;
                watch.Restart();
                if(mode=="precise") await timer.WaitAsync(delay); else await Task.Delay(delay);
                delayMs+=watch.Elapsed.TotalMilliseconds;gaps.Add(watch.Elapsed.TotalMilliseconds);
            }
            double moveMs=total.Elapsed.TotalMilliseconds;
            await transport.SendAsync(HidProtocol.Mouse(),CancellationToken.None);
            await Task.Delay(150);
            await Shot(id,"-endpoint");
            string other=id=="86:1D:4A:04:2F:F6"?"FE:A9:BC:D7:A0:44":"86:1D:4A:04:2F:F6";
            await Shot(other,"-other");
            var result=new { board,id,mode,delay,x,y,steps,sendMs,delayMs,moveMs,gaps, visual_result="inspect endpoint; no click sent",status };
            await File.WriteAllTextAsync(Path.Combine(output,label+".json"),JsonSerializer.Serialize(result,new JsonSerializerOptions{WriteIndented=true}));
            Console.WriteLine($"{label}: steps={steps} move={moveMs:F1}ms send={sendMs:F1}ms delay={delayMs:F1}ms");
        }
        finally
        {
            try { await transport.SendAsync(HidProtocol.Mouse(),CancellationToken.None); }
            finally { await Api("/mouse/reset",new()); }
        }
    }
}

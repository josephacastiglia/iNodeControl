using System.Diagnostics;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using IMouse2.Kernel;

static class LiveRouter
{
    public static async Task RunAsync(string[] args)
    {
        if(args.Length!=5) throw new ArgumentException("--router-suite BOARD legacy|precise|path|ms PROJECT_ROOT LABEL");
        string board=args[1], mode=args[2], root=Path.GetFullPath(args[3]), label=args[4];
        string id=board switch{"C24C"=>"86:1D:4A:04:2F:F6","C241"=>"FE:A9:BC:D7:A0:44",_=>throw new ArgumentException("Unapproved target")};
        string other=id=="86:1D:4A:04:2F:F6"?"FE:A9:BC:D7:A0:44":"86:1D:4A:04:2F:F6";
        bool timed=int.TryParse(mode, out int delay);
        if((mode is not("legacy" or "precise" or "path") && !(timed && delay is >=1 and <=15)) || !System.Text.RegularExpressions.Regex.IsMatch(label,"^[a-zA-Z0-9-]+$")) throw new ArgumentException("Invalid mode/label");
        if(timed) delay=int.Parse(mode);
        if(Process.GetProcessesByName("iMouse2").Length!=0) throw new InvalidOperationException("Close console before isolated test");
        string config=Path.Combine(root,"analysis","two-phone-config");
        string output=Path.Combine(root,"analysis","pointer-reliability-20260915",label);
        if(Directory.Exists(output)) throw new IOException("Refusing to overwrite evidence");
        Directory.CreateDirectory(output);
        using var http=new HttpClient{BaseAddress=new Uri("http://127.0.0.1:9913/api/"),Timeout=TimeSpan.FromSeconds(15)};
        async Task<JsonElement> Status()
        {
            var s=(await http.GetFromJsonAsync<JsonElement>("kernel/status")).GetProperty("data");
            if(string.Join(",",s.GetProperty("allowed").EnumerateArray().Select(v=>v.GetString()).Order())!="C241,C24C") throw new InvalidOperationException("Scope changed");
            foreach(var expected in new[]{("86:1D:4A:04:2F:F6","C24C"),("FE:A9:BC:D7:A0:44","C241")})
            {
                var r=s.GetProperty("receivers").EnumerateArray().Single(r=>r.GetProperty("deviceid").GetString()==expected.Item1);
                if(!r.GetProperty("live").GetBoolean() || r.GetProperty("name").GetString()!="iMouse2-"+expected.Item2) throw new InvalidOperationException("Stream not live");
            }
            return s;
        }
        var liveDevices=(await http.GetFromJsonAsync<JsonElement>("device/get")).GetProperty("data").GetProperty("list");
        var live=liveDevices.EnumerateArray().Single(d=>d.GetProperty("deviceid").GetString()==id);
        var store=new DeviceStore(Path.Combine(config,"devices.json"));
        var saved=store.All().Single(p=>p.deviceid==id);
        if(live.GetProperty("pid").GetString()!=board || live.GetProperty("uid").GetString()!=board+"BFBD" || saved.pid!=board || saved.uid!=board+"BFBD") throw new InvalidOperationException("Binding mismatch");
        var cals=JsonSerializer.Deserialize<List<PointerCalibration>>(File.ReadAllText(Path.Combine(config,"pointer-calibration.json")))!;
        var rows=new List<object>();
        var start=await Status();
        var recording=new LoggedTransport(board);
        using var router=new InputRouter(store,[board],cals,_=>recording,preciseDelayMs:mode=="legacy"?0:timed?delay:8);
        async Task<double> Input(string fun,object fields)
        {
            var data=JsonSerializer.Deserialize<Dictionary<string,object>>(JsonSerializer.Serialize(fields))!;data["id"]=id;
            var clock=Stopwatch.StartNew();
            var r=JsonSerializer.SerializeToElement(await router.DispatchAsync(fun,JsonSerializer.SerializeToElement(data)));
            if(r.GetProperty("code").GetInt32()!=0) throw new IOException(r.ToString());
            return clock.Elapsed.TotalMilliseconds;
        }
        async Task Shot(string identity,string name)
        {
            byte[] bmp=await http.GetByteArrayAsync("pic/screenshot?id="+identity+"&binary=true");
            if(bmp.Length<54 || bmp[0]!=66 || bmp[1]!=77) throw new IOException("Missing frame");
            await File.WriteAllBytesAsync(Path.Combine(output,name+".bmp"),bmp);
        }
        try
        {
            if(mode=="path")
            {
                await Input("/key/sendkey",new{fn_key="Home"});await Task.Delay(600);
                await Shot(other,"path-other-before");
                for(int round=0;round<3;round++)
                {
                    int pointIndex=0;
                    foreach(var point in new[]{(80,820),(400,820),(400,200),(80,200),(250,800)})
                    {
                        double moveMs=await Input("/mouse/move",new{x=point.Item1,y=point.Item2});
                        await Task.Delay(600); // Observe a settled video frame, not the movement animation.
                        await Shot(id,$"path-{round}-{pointIndex}-endpoint");
                        rows.Add(new{round,pointIndex,x=point.Item1,y=point.Item2,moveMs});pointIndex++;
                    }
                }
                double clickMs=await Input("/mouse/click",new{x=250,y=900,button=1});await Task.Delay(450);
                await Shot(id,"path-search");await Shot(other,"path-other-after");
                rows.Add(new{kind="search-after-15-tracked-moves",clickMs});
                await Input("/key/sendkey",new{fn_key="Home"});await Task.Delay(500);
                await File.WriteAllTextAsync(Path.Combine(output,"rows.json"),JsonSerializer.Serialize(rows,new JsonSerializerOptions{WriteIndented=true}));
                Console.WriteLine($"{board} continuous path: 15 movements, final click={clickMs:F1}ms; inspect endpoint images");
            }
            bool preciseSuite=mode=="precise" || timed;
            int count=mode=="path"?0:preciseSuite?5:2;
            var locations=preciseSuite?new[]{(80,140),(400,200),(120,500),(360,760)}:Array.Empty<(int,int)>();
            for(int trial=0;trial<count+locations.Length;trial++)
            {
                await Status();
                string name=$"trial-{trial:D2}";
                if(trial>=count)
                {
                    await Input("/key/sendkey",new{fn_key="Home"});await Task.Delay(600);
                    var point=locations[trial-count];
                    await Input("/mouse/move",new{x=point.Item1,y=point.Item2});
                    await Task.Delay(200);await Shot(id,name+"-off-location");
                }
                double homeMs=await Input("/key/sendkey",new{fn_key="Home"});await Task.Delay(600);
                await Shot(id,name+"-home");await Shot(other,name+"-other-before");
                int reportStart=recording.Reports.Count;
                var clock=Stopwatch.StartNew();
                double inputMs=await Input("/mouse/click",new{x=250,y=900,button=1});
                await Task.Delay(450);await Shot(id,name+"-search");
                double observedMs=clock.Elapsed.TotalMilliseconds;
                await Shot(other,name+"-other-after");
                rows.Add(new{trial,kind=trial<count?"home-search":"off-location-home-search",homeMs,inputMs,screenshot_after_send_ms=observedMs,
                    reports=recording.Reports.Skip(reportStart).ToArray(),visual_result="requires inspection"});
                await File.WriteAllTextAsync(Path.Combine(output,"rows.json"),JsonSerializer.Serialize(rows,new JsonSerializerOptions{WriteIndented=true}));
                Console.WriteLine($"{board} {mode} {name}: click {inputMs:F1}ms; image sampled {observedMs:F1}ms after send");
                await Input("/key/sendkey",new{fn_key="Home"});await Task.Delay(500);
            }
            var end=await Status();
            string assembly=typeof(InputRouter).Assembly.Location;
            await File.WriteAllTextAsync(Path.Combine(output,"session.json"),JsonSerializer.Serialize(new{board,mode,start,end,assembly,
                sha256=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(assembly))),note="Actual InputRouter/HidConnection; existing kernel used only for video. Dispatch time is not HTTP time."},new JsonSerializerOptions{WriteIndented=true}));
        }
        finally
        {
            router.Dispose();
            using var response=await http.PostAsJsonAsync("",new{fun="/mouse/reset",data=new{id}});
            var r=await response.Content.ReadFromJsonAsync<JsonElement>();
            if(r.GetProperty("data").GetProperty("code").GetInt32()!=0) throw new IOException("Failed to resynchronize running kernel after test");
        }
    }
    sealed class LoggedTransport(string board):IHidTransport
    {
        private readonly HidConnection _inner=new(board);
        public List<object> Reports{get;}=[];
        public async Task SendAsync(byte[] data,CancellationToken ct)
        {
            var clock=Stopwatch.StartNew();
            await _inner.SendAsync(data,ct);
            Reports.Add(new{hex=Convert.ToHexString(data),completed=Stopwatch.GetTimestamp(),write_ms=clock.Elapsed.TotalMilliseconds});
        }
        public void Dispose()=>_inner.Dispose();
    }
}

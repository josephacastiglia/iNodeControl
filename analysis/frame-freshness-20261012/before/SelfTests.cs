using System.Buffers.Binary;
using System.Diagnostics;
using System.IO.Pipes;
using System.Text.Json;
namespace IMouse2.Kernel;

public static class SelfTests
{
    private sealed class FakeReceiver : IReceiverHandle
    {
        public int Id { get; }
        public TaskCompletionSource Exit { get; } = new();
        public FakeReceiver(int id) => Id = id;
        public Task WaitForExitAsync(CancellationToken ct) => Exit.Task.WaitAsync(ct);
        public void Dispose() => Exit.TrySetResult();
    }
    private sealed class RecordingTransport : IHidTransport
    {
        public List<string> Reports {get;}=[];
        public bool Disposed;
        public int FailAt=-1;
        public Task SendAsync(byte[] data,CancellationToken ct)
        {
            Reports.Add(Convert.ToHexString(data));
            if(Reports.Count==FailAt) throw new IOException("Simulated disconnect");
            return Task.CompletedTask;
        }
        public void Dispose() => Disposed=true;
    }
    public static async Task<int> RunAsync()
    {
        int passed=0;
        void Check(bool ok,string message) { if(!ok) throw new Exception(message);passed++;Console.WriteLine("PASS "+message); }
        int Code(object response)=>JsonSerializer.SerializeToElement(response).GetProperty("code").GetInt32();
        string testDir=Path.Combine(Path.GetTempPath(),"imouse-kernel-test-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(testDir);
        string file=Path.Combine(testDir,"devices.json");
        File.WriteAllText(file,JsonSerializer.Serialize(new[]{new Phone{deviceid="test-one",pid="C24C"},new Phone{deviceid="test-two",pid="C214"}}));
        var writes=new RecordingTransport();
        using var router=new InputRouter(new DeviceStore(file),["C24C"],[new("C24C",500,1080,14,14,5.12,5.09)],_=>writes);
        JsonElement Data(object obj)=>JsonSerializer.SerializeToElement(obj);
        Check(Convert.ToHexString(HidProtocol.Mouse(1))=="A101000000000000","Down matches captured packet");
        Check(Convert.ToHexString(HidProtocol.Mouse(0,-127,-127))=="A100818100000000","Corner reset matches captured packet");
        Check(HidProtocol.Ascii(' ')==(0,44) && HidProtocol.Ascii('#')==(2,32),"ASCII space and shifted digit usages");
        Check(HidProtocol.Ascii('A')==(2,4) && HidProtocol.Ascii('z')==(0,29),"Letter modifiers match captured packets");
        Check(Code(await router.DispatchAsync("/mouse/reset",Data(new{id="test-one,test-two"})))==41 && writes.Reports.Count==0,"Unapproved batch target rejects whole request before output");
        bool invalid=false;
        try { await router.DispatchAsync("/mouse/click",Data(new{id="test-one",x=500,y=20})); } catch(ArgumentException) {invalid=true;}
        Check(invalid && writes.Reports.Count==0,"Out of bounds click sends nothing");
        await router.DispatchAsync("/mouse/click",Data(new{id="test-one",x=14,y=14,button=1}));
        Check(writes.Reports.Take(6).SequenceEqual(new[]{"A100000000000000","A200000000000000","A100818100000000","A100818100000000","A100818100000000","A100818100000000"}),"First absolute action releases inputs and establishes corner origin");
        Check(writes.Reports.TakeLast(2).SequenceEqual(new[]{"A101000000000000","A100000000000000"}),"Click holds then releases");
        int downAt = writes.Reports.IndexOf("A101000000000000");
        Check(downAt > 0 && writes.Reports[downAt - 1] == "A100000000000000", "Click settles with a zero-motion report before button down");
        writes.Reports.Clear();
        await router.DispatchAsync("/mouse/down",Data(new{id="test-one",button=1}));
        await router.DispatchAsync("/mouse/move",Data(new{id="test-one",x=24,y=14}));
        await router.DispatchAsync("/mouse/up",Data(new{id="test-one",button=1}));
        Check(writes.Reports.SequenceEqual(new[]{"A100000000000000","A101000000000000","A101010000000000","A101010000000000","A100000000000000"}),"Drag settles, then preserves held button during relative steps");
        writes.Reports.Clear();
        await router.DispatchAsync("/key/sendkey",Data(new{id="test-one",key="a b"}));
        Check(writes.Reports.Contains("A2002C0000000000"),"Space is emitted as USB usage 44 between letters");
        writes.Reports.Clear();
        await router.DispatchAsync("/key/sendkey",Data(new{id="test-one",fn_key="Home"}));
        Check(writes.Reports.Where(r=>r!="A200000000000000").SequenceEqual(new[]{"A2002B0000000000","A2080B0000000000"}),"Home reproduces observed Tab and GUI+H sequence");
        writes.Reports.Clear();
        await router.DispatchAsync("/mouse/click",Data(new{id="test-one",x=24,y=14}));
        Check(writes.Reports.Take(6).SequenceEqual(new[]{"A100000000000000","A200000000000000","A100818100000000","A100818100000000","A100818100000000","A100818100000000"}),
            "Home invalidates the pointer estimate; next click re-establishes origin");
        writes.Reports.Clear();
        writes.FailAt=2;
        Check(Code(await router.DispatchAsync("/mouse/reset",Data(new{id="test-one"})))==33,"Transport failure is reported");
        Check(writes.Disposed && writes.Reports.TakeLast(2).SequenceEqual(new[]{"A100000000000000","A200000000000000"}),"Failure releases inputs and discards handle");
        foreach (bool precise in new[]{false,true})
        {
            var firstTransport=new RecordingTransport();var recoveredTransport=new RecordingTransport();
            int opened=0;
            using var recovery=new InputRouter(new DeviceStore(file),["C24C"],
                [new("C24C",500,1080,14,14,5.12,5.09)],_=>++opened==1?firstTransport:recoveredTransport,preciseDelayMs: precise ? 7 : 0);
            await recovery.DispatchAsync("/mouse/move",Data(new{id="test-one",x=14,y=14}));
            firstTransport.FailAt=firstTransport.Reports.Count+2;
            Check(Code(await recovery.DispatchAsync("/mouse/move",Data(new{id="test-one",x=40,y=40})))==33,
                $"Movement failure is surfaced (precise={precise})");
            await recovery.DispatchAsync("/mouse/move",Data(new{id="test-one",x=24,y=14}));
            Check(opened==2 && recoveredTransport.Reports.Take(6).Count(r=>r=="A100818100000000")==4,
                $"Movement failure forces a new connection and corner reset (precise={precise})");
        }
        var legacyPackets=new RecordingTransport();var precisePackets=new RecordingTransport();
        foreach(var setting in new[]{(Precise:false,Transport:legacyPackets),(Precise:true,Transport:precisePackets)})
        {
            using var sample=new InputRouter(new DeviceStore(file),["C24C"],
                [new("C24C",500,1080,14,14,5.12,5.09)],_=>setting.Transport,preciseDelayMs: setting.Precise ? 7 : 0);
            await sample.DispatchAsync("/mouse/click",Data(new{id="test-one",x=100,y=200}));
            await sample.DispatchAsync("/key/sendkey",Data(new{id="test-one",fn_key="Home"}));
            await sample.DispatchAsync("/mouse/click",Data(new{id="test-one",x=100,y=200}));
            await sample.DispatchAsync("/mouse/swipe",Data(new{id="test-one",x1=100,y1=200,x2=120,y2=200,duration=100}));
        }
        Check(legacyPackets.Reports.SequenceEqual(precisePackets.Reports),
            "Precise pacing preserves all reset, movement, keyboard, click and swipe packets");
        Check(precisePackets.Reports.Count(r=>r=="A100818100000000")==8,
            "Precise clicks retain both cold-start and post-Home corner resets");
        byte[] bmp=new byte[70];bmp[0]=(byte)'B';bmp[1]=(byte)'M';
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(2),70);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(10),54);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(14),40);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(18),2);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(22),2);
        BinaryPrimitives.WriteInt16LittleEndian(bmp.AsSpan(26),1);
        BinaryPrimitives.WriteInt16LittleEndian(bmp.AsSpan(28),24);
        Check(FrameStore.ValidateBmp(bmp)==(2,2),"Padded bottom-up BMP accepted");
        using(var frames=new FrameStore("imouse-frame-test-"+Guid.NewGuid().ToString("N"),"test-one"))
        {
            // The separate pipe check below uses its own random name and synthetic pixels.
            Check(!frames.State.Live,"Video is offline before a receiver sends a frame");
        }
        string pipeName="imouse-frame-test-"+Guid.NewGuid().ToString("N");
        using(var frames=new FrameStore(pipeName,"test-one"))
        {
            var pump=frames.RunAsync();
            using(var client=new NamedPipeClientStream(".",pipeName,PipeDirection.Out,PipeOptions.Asynchronous))
            {
                await client.ConnectAsync(3000);
                async Task WaitFor(Func<bool> condition)
                {
                    for(int i=0;i<100 && !condition();i++) await Task.Delay(10);
                    if(!condition()) throw new Exception("Frame pipe condition timed out");
                }
                byte[] length=new byte[4];BinaryPrimitives.WriteInt32LittleEndian(length,bmp.Length);
                await client.WriteAsync(length);await client.WriteAsync(bmp);await client.FlushAsync();
                await WaitFor(()=>frames.Frames==1);
                Check(frames.State==(true,2,2),"Named pipe publishes validated receiver dimensions");
                await client.WriteAsync(length);await client.WriteAsync(bmp);await client.FlushAsync();
                await WaitFor(()=>frames.Frames==2);
                Check(frames.State.Live,"Identical live frames remain usable");
                await client.WriteAsync(new byte[4]);await client.FlushAsync();
                await WaitFor(()=>!frames.State.Live);
                Check(!frames.State.Live,"Receiver stop marker clears stale picture");
            }
            frames.Dispose();await pump;
        }
        var twoConfigs=new[]{new ReceiverConfig("test-one","C24C","iMouse2-C24C","test-pipe-one",7110,"02:49:4D:32:C2:4C"),
            new ReceiverConfig("test-two","C214","iMouse2-C214","test-pipe-two",7120,"02:49:4D:32:C2:14")};
        ReceiverFleet.Validate(twoConfigs,new DeviceStore(file).All());
        Check(true,"Two receivers accept distinct bindings, ports and identities");
        foreach(var badConfig in new[]{twoConfigs[1] with {Port=7111},twoConfigs[1] with {Pipe="test-pipe-one"},
            twoConfigs[1] with {Mac=twoConfigs[0].Mac},twoConfigs[1] with {BoardPid="C241"}})
        {
            invalid=false;
            try {ReceiverFleet.Validate([twoConfigs[0],badConfig],new DeviceStore(file).All());}catch(ArgumentException){invalid=true;}
            Check(invalid,"Conflicting or mismatched receiver configuration rejected");
        }
        var isolatedOne=new RecordingTransport();var isolatedTwo=new RecordingTransport();
        using(var twoRouter=new InputRouter(new DeviceStore(file),["C24C","C214"],
            [new("C24C",500,1080,14,14,5.12,5.09),new("C214",500,1080,14,14,5.12,5.09)],
            p=>p=="C24C"?isolatedOne:isolatedTwo))
        {
            await twoRouter.DispatchAsync("/mouse/click",Data(new{id="test-one",x=14,y=14}));
            Check(isolatedOne.Reports.Count>0 && isolatedTwo.Reports.Count==0,"Phone one input does not touch phone two");
            int before=isolatedOne.Reports.Count;
            await twoRouter.DispatchAsync("/mouse/click",Data(new{id="test-two",x=14,y=14}));
            Check(isolatedTwo.Reports.Count>0 && isolatedOne.Reports.Count==before,"Phone two input does not touch phone one");
        }
        string isolatedPipeOne="imouse-isolate-"+Guid.NewGuid().ToString("N"),isolatedPipeTwo="imouse-isolate-"+Guid.NewGuid().ToString("N");
        using(var firstFrames=new FrameStore(isolatedPipeOne,"test-one"))
        using(var secondFrames=new FrameStore(isolatedPipeTwo,"test-two"))
        {
            var firstPump=firstFrames.RunAsync();var secondPump=secondFrames.RunAsync();
            using(var firstClient=new NamedPipeClientStream(".",isolatedPipeOne,PipeDirection.Out,PipeOptions.Asynchronous))
            using(var secondClient=new NamedPipeClientStream(".",isolatedPipeTwo,PipeDirection.Out,PipeOptions.Asynchronous))
            {
                await firstClient.ConnectAsync(3000);await secondClient.ConnectAsync(3000);
                byte[] size=new byte[4];BinaryPrimitives.WriteInt32LittleEndian(size,bmp.Length);
                await firstClient.WriteAsync(size);await firstClient.WriteAsync(bmp);
                await secondClient.WriteAsync(size);await secondClient.WriteAsync(bmp);
                for(int i=0;i<100 && (!firstFrames.State.Live || !secondFrames.State.Live);i++) await Task.Delay(10);
                Check(firstFrames.State.Live && secondFrames.State.Live,"Independent receiver pipes publish both frames");
                firstClient.Dispose();
                for(int i=0;i<100 && firstFrames.State.Live;i++) await Task.Delay(10);
                Check(!firstFrames.State.Live && secondFrames.State.Live,"Disconnecting one pipe preserves the other phone's frame");
            }
            firstFrames.Dispose();secondFrames.Dispose();await Task.WhenAll(firstPump,secondPump);
        }
        bmp[28]=32;invalid=false;
        try{FrameStore.ValidateBmp(bmp);}catch(InvalidDataException){invalid=true;}
        Check(invalid,"Unexpected pixel format rejected");
        Check(AirplayProcess.LivePid(null)==0,"Missing receiver process reports pid 0");
        using(var dead=Process.Start(new ProcessStartInfo("cmd.exe","/c exit"){CreateNoWindow=true,UseShellExecute=false}))
        {
            dead!.WaitForExit(5000);
            Check(AirplayProcess.LivePid(dead)==0,"Exited receiver process reports pid 0");
        }
        int launches=0;
        using(var failing=new AirplaySupervisor(() => { launches++; var fake=new FakeReceiver(launches); fake.Exit.TrySetResult(); return fake; }, 2, TimeSpan.FromMilliseconds(1)))
        {
            await failing.RunAsync(CancellationToken.None);
            Check(failing.Info.State=="failed" && launches==3 && failing.Info.Restarts==3,"Retry limit stops after initial start plus two restarts");
        }
        var held=new FakeReceiver(9);
        using var stay=new CancellationTokenSource();
        using(var running=new AirplaySupervisor(() => held, 2, TimeSpan.FromMilliseconds(1)))
        {
            var run=running.RunAsync(stay.Token);
            for(int i=0;i<50 && running.Info.State!="running";i++) await Task.Delay(10);
            Check(running.Info is { State:"running", Pid:9, Restarts:0 },"Healthy receiver stays running with zero restarts");
            stay.Cancel();
            await run;
        }
        int recoveries=0; FakeReceiver? second=null;
        using var once=new CancellationTokenSource();
        using(var recovered=new AirplaySupervisor(() =>
        {
            recoveries++;
            var fake=new FakeReceiver(20+recoveries);
            if(recoveries==1) fake.Exit.TrySetResult(); else second=fake;
            return fake;
        }, 2, TimeSpan.FromMilliseconds(1)))
        {
            var run=recovered.RunAsync(once.Token);
            for(int i=0;i<80 && recovered.Info.Restarts<1;i++) await Task.Delay(10);
            for(int i=0;i<50 && recovered.Info.State!="running";i++) await Task.Delay(10);
            Check(recoveries==2 && recovered.Info is { State:"running", Restarts:1 },"One crash relaunches the receiver without failing");
            once.Cancel();
            await run;
        }
        await InputSessionTests.RunAsync(Check);
        File.Delete(file);Directory.Delete(testDir);
        Console.WriteLine($"{passed} tests passed; no real HID transport opened.");
        return 0;
    }
}

namespace IMouse2.Kernel;

public sealed record ReceiverConfig(string DeviceId,string BoardPid,string Name,string Pipe,int Port,string Mac);

public sealed class ReceiverFleet : IDisposable
{
    public sealed record Session(ReceiverConfig Config,FrameStore Frames,AirplaySupervisor? Supervisor);
    public List<Session> Sessions { get; } = [];

    public static void Validate(IReadOnlyList<ReceiverConfig> configs,IReadOnlyList<Phone> phones)
    {
        if(configs.Count is <1 or >19) throw new ArgumentException("This test build requires one to nineteen receivers.");
        foreach(var c in configs)
        {
            var discovery=c.DeviceId is "*" or "";
            if((!discovery && string.IsNullOrWhiteSpace(c.DeviceId)) || !c.Name.StartsWith("iMouse2-") ||
                !System.Text.RegularExpressions.Regex.IsMatch(c.Pipe,@"^[A-Za-z0-9-]+$") ||
                !System.Text.RegularExpressions.Regex.IsMatch(c.Mac,@"^02(:[0-9A-Fa-f]{2}){5}$") ||
                c.Port<1024 || c.Port>65533 || c.Port<=5353 && c.Port+2>=5353)
                throw new ArgumentException("Invalid receiver identity or ports.");
            if(!discovery && phones.Count(p=>p.deviceid==c.DeviceId && p.pid==c.BoardPid)!=1)
                throw new ArgumentException("Receiver must match exactly one saved phone/board binding.");
        }
        foreach(var selector in new Func<ReceiverConfig,string>[] {c=>c.DeviceId,c=>c.BoardPid,c=>c.Name,c=>c.Pipe,c=>c.Mac})
            if(configs.Select(selector).Distinct(StringComparer.OrdinalIgnoreCase).Count()!=configs.Count)
                throw new ArgumentException("Each receiver needs a unique phone, board, name, pipe and MAC.");
        if(configs.SelectMany(c=>Enumerable.Range(c.Port,3)).Distinct().Count()!=configs.Count*3)
            throw new ArgumentException("Receiver port ranges overlap.");
    }

    public ReceiverFleet(IReadOnlyList<ReceiverConfig> configs,DeviceStore store,string executable,string runtime,string dataDir)
    {
        Validate(configs,store.All());
        foreach(var c in configs)
        {
            var frames=new FrameStore(c.Pipe,c.DeviceId);
            var supervisor=executable.Length==0 ? null : new AirplaySupervisor(()=>
                new AirplayProcess(executable,runtime,c.Name,c.Pipe,c.DeviceId,
                    Path.Combine(dataDir,"receiver-"+c.BoardPid+".log"),c.Port,c.Mac));
            if(supervisor is not null) { frames.ReceiverPid=()=>supervisor.Info.Pid;frames.Receiver=()=>supervisor.Info; }
            Sessions.Add(new(c,frames,supervisor));
        }
    }
    public void Start(CancellationToken ct)
    {
        foreach(var s in Sessions)
        {
            _=s.Frames.RunAsync().ContinueWith(t=>Console.WriteLine("Frame pump failed for "+s.Config.Name+": "+t.Exception),TaskContinuationOptions.OnlyOnFaulted);
            if(s.Supervisor is not null) _=s.Supervisor.RunAsync(ct);
        }
    }
    public void Dispose() { foreach(var s in Sessions) {s.Supervisor?.Dispose();s.Frames.Dispose();} }
}

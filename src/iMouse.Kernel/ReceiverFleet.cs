namespace IMouse2.Kernel;

public sealed record ReceiverConfig(string DeviceId,string BoardPid,string Name,string Pipe,int Port,string Mac);

public sealed class ReceiverFleet : IDisposable, IAsyncDisposable
{
    public sealed record Session(ReceiverConfig Config,FrameStore Frames,AirplaySupervisor? Supervisor);
    public List<Session> Sessions { get; } = [];
    private sealed record RunningSession(Session Session, Task Frames, Task Supervisor);
    private readonly object _gate = new();
    private readonly List<RunningSession> _runs = [];
    private readonly HashSet<string> _held = new(StringComparer.OrdinalIgnoreCase);
    private bool _started;
    private CancellationToken _token;
    private Task? _shutdown;

    public static void Validate(IReadOnlyList<ReceiverConfig> configs,IReadOnlyList<Phone> phones)
    {
        if(configs.Count is <1 or >19) throw new ArgumentException("This test build requires one to nineteen receivers.");
        foreach(var c in configs)
        {
            if(c is null || c.BoardPid is null || !System.Text.RegularExpressions.Regex.IsMatch(c.BoardPid,@"^[0-9A-Fa-f]{4}$") || c.Name is null || c.Pipe is null || c.Mac is null)
                throw new ArgumentException("Invalid receiver record or board PID.");
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
            if(supervisor is not null) { frames.ReceiverPid=()=>supervisor.Info.Pid;frames.Receiver=()=>IsHeld(c.BoardPid) ? Held : supervisor.Info; }
            Sessions.Add(new(c,frames,supervisor));
        }
    }
    private static readonly ReceiverInfo Held = new("held", "Receiver not advertised yet; release it with /device/airplay/connect.", 0, 0);

    // A held receiver is not started, so no phone can list it until it is released.
    public bool IsHeld(string boardPid) { lock (_gate) return _held.Contains(boardPid); }

    public void Start(CancellationToken ct, IReadOnlyCollection<string>? hold = null)
    {
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_shutdown is not null, this);
            if (_started) throw new InvalidOperationException("A receiver fleet can start only once.");
            if (hold?.Any(pid => !Sessions.Any(s => s.Config.BoardPid.Equals(pid, StringComparison.OrdinalIgnoreCase))) == true)
                throw new ArgumentException("Every held receiver must be a configured board.");
            _started = true;
            _token = ct;
            foreach (var session in Sessions)
                if (hold?.Contains(session.Config.BoardPid, StringComparer.OrdinalIgnoreCase) == true) _held.Add(session.Config.BoardPid);
                else Run(session);
        }
    }

    /// <summary>Starts one held receiver. A started receiver stays advertised until the kernel stops.</summary>
    public object Advertise(string boardPid)
    {
        lock (_gate)
        {
            if (_shutdown is not null || !_started) return new { code = 42, message = "Receivers are not running." };
            var session = Sessions.FirstOrDefault(s => s.Config.BoardPid.Equals(boardPid, StringComparison.OrdinalIgnoreCase));
            if (session is null) return new { code = 36, message = "No receiver is configured for board " + boardPid + "." };
            if (!_held.Remove(session.Config.BoardPid))
                return new { code = 0, message = session.Config.Name + " is already advertised.", name = session.Config.Name, started = false };
            Run(session);
            return new { code = 0, message = session.Config.Name + " is now advertised.", name = session.Config.Name, started = true };
        }
    }

    private void Run(Session session)
    {
        // Retain every run before releasing the lifecycle lock. Native
        // startup and cleanup must never hold this lock or a UI thread.
        var frames = Task.Run(async () =>
        {
            try { await session.Frames.RunAsync().ConfigureAwait(false); }
            catch (Exception ex) { Console.WriteLine("Frame pump failed for " + session.Config.Name + ": " + ex); throw; }
        });
        var token = _token;
        var supervisor = session.Supervisor is { } child
            ? Task.Run(() => child.RunAsync(token)) : Task.CompletedTask;
        _runs.Add(new(session, frames, supervisor));
    }

    public Task ShutdownAsync()
    {
        lock (_gate)
        {
            // Every caller observes the same completion, including failures.
            // Pre-start disposal still cancels each session and forbids Start.
            return _shutdown ??= Task.Run(async () =>
            {
                // Held and never-started sessions are still disposed: that stops
                // their frame stores and forbids any later receiver start.
                var runs = _runs.Concat(Sessions.Where(s => !_runs.Any(r => ReferenceEquals(r.Session, s))).Select(s =>
                    new RunningSession(s, Task.CompletedTask, Task.CompletedTask))).ToArray();
                _held.Clear();
                var failures = await Task.WhenAll(runs.Select(StopAndJoinAsync)).ConfigureAwait(false);
                var errors = failures.SelectMany(f => f).ToArray();
                if (errors.Length != 0) throw new AggregateException("Receiver fleet shutdown was not fully confirmed.", errors);
            });
        }
    }

    private static async Task<List<Exception>> StopAndJoinAsync(RunningSession run)
    {
        var errors = new List<Exception>();
        void Record(string operation, Exception ex) => errors.Add(new IOException(
            run.Session.Config.Name + " " + operation + ": " + ex.Message, ex));
        // Initiate peer stops independently; one slow receiver must not delay
        // requesting cleanup of all the others. Each real child has its own
        // bounded exit confirmation in ReceiverProcessLifetime.
        await Task.Run(() =>
        {
            try { run.Session.Frames.Dispose(); } catch (Exception ex) { Record("frame stop failed", ex); }
            try { run.Session.Supervisor?.Dispose(); } catch (Exception ex) { Record("receiver stop failed", ex); }
        }).ConfigureAwait(false);
        try { await run.Supervisor.ConfigureAwait(false); } catch (Exception ex) { Record("supervisor failed", ex); }
        try { await run.Frames.ConfigureAwait(false); } catch (Exception ex) { Record("frame reader failed", ex); }
        // Dispose may find no current handle because the run already claimed
        // cleanup. Only after both paths join is its outcome final.
        if (run.Session.Supervisor?.CleanupFailure is { } failure)
            errors.Add(new IOException(run.Session.Config.Name + ": " + failure.Message));
        return errors;
    }

    public ValueTask DisposeAsync() => new(ShutdownAsync());
    public void Dispose() => ShutdownAsync().GetAwaiter().GetResult();
}

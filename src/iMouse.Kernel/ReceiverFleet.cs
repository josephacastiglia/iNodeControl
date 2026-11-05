namespace IMouse2.Kernel;

public sealed record ReceiverConfig(string DeviceId,string BoardPid,string Name,string Pipe,int Port,string Mac);

/// <summary>
/// Every configured receiver, each with its own frame store and, while advertised, its own
/// supervised UxPlay child. One receiver can be withdrawn (stopped and its AirPlay name sent a
/// goodbye), restarted (withdrawn, then started again) or advertised without touching any other
/// receiver, any input lease or the HTTP listener.
/// </summary>
public sealed class ReceiverFleet : IDisposable, IAsyncDisposable
{
    public sealed record Session(ReceiverConfig Config,FrameStore Frames);

    // One mutable slot per receiver. Every field is guarded by _gate.
    private sealed class Entry(Session session)
    {
        public readonly Session Session = session;
        public AirplaySupervisor? Supervisor;
        public Task SupervisorRun = Task.CompletedTask;
        public Task? FrameRun;
        public bool Held;
        public bool Withdrawn;          // Held because an operator withdrew it, not since startup.
        public string? Busy;            // "restarting" or "withdrawing" while a change is in flight.
        public Task Change = Task.CompletedTask;
        public int RetiredRestarts;     // Crash relaunches counted by supervisors already retired.
        public int Generation;          // Receiver children started by the fleet for this board.
        public string Note = "";        // Outcome of the last restart or withdrawal.
        public ReceiverInfo? Failure;   // A retired child whose exit was not confirmed.
    }

    public List<Session> Sessions { get; } = [];
    private readonly List<Entry> _entries = [];
    private readonly object _gate = new();
    private readonly Func<ReceiverConfig,IReceiverHandle>? _receiver;
    private readonly IReceiverWithdrawal _withdrawal;
    private readonly int _maxRestarts;
    private readonly TimeSpan _restartDelay;
    private bool _started;
    private CancellationToken _token;
    private Task? _shutdown;

    public static void Validate(IReadOnlyList<ReceiverConfig> configs,IReadOnlyList<Phone> phones)
    {
        // Two 20-phone racks on one PC (29 Oct): rack A's 19 boards and rack B's 20.
        if(configs.Count is <1 or >40) throw new ArgumentException("This test build requires one to forty receivers.");
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
        : this(configs,store,executable.Length==0 ? null : c=>new AirplayProcess(executable,runtime,c.Name,c.Pipe,c.DeviceId,
            Path.Combine(dataDir,"receiver-"+c.BoardPid+".log"),c.Port,c.Mac),new MdnsGoodbye()) { }

    // Tests supply fake receivers and a recording withdrawal; nothing native or networked.
    internal ReceiverFleet(IReadOnlyList<ReceiverConfig> configs,DeviceStore store,Func<ReceiverConfig,IReceiverHandle>? receiver,
        IReceiverWithdrawal withdrawal,int maxRestarts=AirplaySupervisor.DefaultMaxRestarts,TimeSpan? restartDelay=null)
    {
        Validate(configs,store.All());
        _receiver=receiver;
        _withdrawal=withdrawal;
        _maxRestarts=maxRestarts;
        _restartDelay=restartDelay ?? AirplaySupervisor.DefaultDelay;
        foreach(var c in configs)
        {
            var session=new Session(c,new FrameStore(c.Pipe,c.DeviceId));
            var entry=new Entry(session);
            if(receiver is not null)
            {
                session.Frames.ReceiverPid=()=>Info(entry).Pid;
                session.Frames.Receiver=()=>Info(entry);
            }
            Sessions.Add(session);
            _entries.Add(entry);
        }
    }

    private static readonly string HeldMessage = "Receiver not advertised yet; release it with /device/airplay/connect.";

    private ReceiverInfo Info(Entry entry)
    {
        lock (_gate)
        {
            int restarts = entry.RetiredRestarts + (entry.Supervisor?.Info.Restarts ?? 0);
            if (entry.Busy is { } busy)
                return new("restarting", "Receiver " + busy + " on request; other receivers are unaffected.", 0, restarts, entry.Generation);
            if (entry.Failure is { } failure) return failure with { Restarts = restarts, Generation = entry.Generation };
            if (entry.Held)
                return new("held", entry.Withdrawn ? "Receiver withdrawn on request" + (entry.Note.Length == 0 ? "" : " (" + entry.Note + ")")
                    + "; advertise it with /device/airplay/connect." : HeldMessage, 0, restarts, entry.Generation);
            var info = entry.Supervisor?.Info ?? new ReceiverInfo("stopped", "", 0, 0);
            return info with { Restarts = restarts, Generation = entry.Generation };
        }
    }

    // A held receiver is not started, so no phone can list it until it is released.
    public bool IsHeld(string boardPid) { lock (_gate) return Find(boardPid)?.Held == true; }

    private Entry? Find(string boardPid) => _entries.FirstOrDefault(e => e.Session.Config.BoardPid.Equals(boardPid, StringComparison.OrdinalIgnoreCase));

    public void Start(CancellationToken ct, IReadOnlyCollection<string>? hold = null)
    {
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_shutdown is not null, this);
            if (_started) throw new InvalidOperationException("A receiver fleet can start only once.");
            if (hold?.Any(pid => Find(pid) is null) == true)
                throw new ArgumentException("Every held receiver must be a configured board.");
            _started = true;
            _token = ct;
            foreach (var entry in _entries)
                if (hold?.Contains(entry.Session.Config.BoardPid, StringComparer.OrdinalIgnoreCase) == true) entry.Held = true;
                else Run(entry);
        }
    }

    /// <summary>Starts one held or withdrawn receiver. A started receiver stays advertised until it is withdrawn or the kernel stops.</summary>
    public object Advertise(string boardPid)
    {
        lock (_gate)
        {
            if (_shutdown is not null || !_started) return new { code = 42, message = "Receivers are not running." };
            var entry = Find(boardPid);
            if (entry is null) return new { code = 36, message = "No receiver is configured for board " + boardPid + "." };
            var name = entry.Session.Config.Name;
            if (entry.Busy is { } busy) return new { code = 409, message = name + " is " + busy + "; wait for it to finish.", name };
            if (entry.Failure is not null) return new { code = 409, message = name + "'s last receiver exit is unconfirmed; inspect it before starting another.", name };
            if (!entry.Held)
                return new { code = 0, message = name + " is already advertised.", name, started = false };
            entry.Held = false; entry.Withdrawn = false;
            Run(entry);
            return new { code = 0, message = name + " is now advertised.", name, started = true };
        }
    }

    /// <summary>Stops one receiver, confirms its exit, withdraws its AirPlay name, and starts it again
    /// unless <paramref name="hold"/> is set. Every other receiver keeps running.</summary>
    public Task<object> RestartAsync(string boardPid, bool hold = false) => ChangeAsync(boardPid, hold ? "withdrawing" : "restarting", hold);

    /// <summary>Stops one receiver and withdraws its AirPlay name; it stays held until advertised.</summary>
    public Task<object> WithdrawAsync(string boardPid) => ChangeAsync(boardPid, "withdrawing", true);

    private async Task<object> ChangeAsync(string boardPid, string action, bool hold)
    {
        Entry entry;
        AirplaySupervisor? retiring;
        Task retiringRun;
        TaskCompletionSource done = new(TaskCreationOptions.RunContinuationsAsynchronously);
        lock (_gate)
        {
            if (_shutdown is not null || !_started) return new { code = 42, message = "Receivers are not running." };
            if (_receiver is null) return new { code = 41, message = "This kernel hosts frame pipes only; it has no receiver to restart." };
            var found = Find(boardPid);
            if (found is null) return new { code = 36, message = "No receiver is configured for board " + boardPid + "." };
            entry = found;
            if (entry.Busy is { } busy) return new { code = 409, message = entry.Session.Config.Name + " is already " + busy + ".", name = entry.Session.Config.Name };
            if (entry.Failure is not null)
                return new { code = 409, message = entry.Session.Config.Name + "'s last receiver exit is unconfirmed; inspect it before starting another.", name = entry.Session.Config.Name };
            entry.Busy = action;
            entry.Change = done.Task;
            retiring = entry.Supervisor;
            retiringRun = entry.SupervisorRun;
        }
        var name = entry.Session.Config.Name;
        try
        {
            // 1. Stop this receiver's child and confirm its exit (bounded in ReceiverProcessLifetime).
            ReceiverInfo? unconfirmed = null;
            if (retiring is not null)
            {
                await Task.Run(retiring.Dispose).ConfigureAwait(false);
                try { await retiringRun.ConfigureAwait(false); }
                catch (Exception ex) { Console.WriteLine(name + " supervisor ended with: " + ex.Message); }
                unconfirmed = retiring.CleanupFailure;
            }
            lock (_gate)
            {
                if (retiring is not null && ReferenceEquals(entry.Supervisor, retiring))
                {
                    entry.RetiredRestarts += retiring.Info.Restarts;
                    entry.Supervisor = null; entry.SupervisorRun = Task.CompletedTask;
                }
                if (unconfirmed is not null)
                {
                    // Never withdraw a name or start a second child while the first may still be alive.
                    entry.Failure = unconfirmed; entry.Held = true; entry.Withdrawn = true;
                    entry.Note = "exit unconfirmed";
                    return new { code = 33, message = name + " was told to stop but its exit is unconfirmed; nothing was withdrawn or started. " + unconfirmed.Message, name };
                }
                entry.Held = true; entry.Withdrawn = true;
            }
            // 2. A killed UxPlay sends no goodbye; send it so phones drop the name now, not in 75 minutes.
            string goodbye;
            bool withdrawn;
            try
            {
                var interfaces = await Task.Run(() => _withdrawal.Withdraw(entry.Session.Config)).ConfigureAwait(false);
                goodbye = "goodbye sent on " + string.Join(", ", interfaces); withdrawn = true;
            }
            catch (Exception ex) { goodbye = "goodbye not sent: " + ex.Message; withdrawn = false; }
            Console.WriteLine(name + " " + action + ": " + goodbye);
            // 3. Start it again unless it is to stay withdrawn, and never once shutdown has begun.
            lock (_gate)
            {
                entry.Note = goodbye;
                if (hold)
                    return new { code = withdrawn ? 0 : 34, message = name + (withdrawn ? " is withdrawn and held." : " is stopped and held, but its name was not withdrawn: " + goodbye),
                        name, stopped = retiring is not null, withdrawn, started = false };
                if (_shutdown is not null)
                    return new { code = 42, message = name + " was stopped; the kernel is shutting down, so it was not started again.", name };
                entry.Held = false; entry.Withdrawn = false;
                Run(entry);
                return new { code = 0, message = name + " was restarted" + (withdrawn ? "." : "; its old name was not withdrawn: " + goodbye),
                    name, stopped = retiring is not null, withdrawn, started = true, generation = entry.Generation };
            }
        }
        finally
        {
            lock (_gate) entry.Busy = null;
            done.TrySetResult();
        }
    }

    private void Run(Entry entry)
    {
        // Retain every run before releasing the lifecycle lock. Native
        // startup and cleanup must never hold this lock or a UI thread.
        var session = entry.Session;
        entry.FrameRun ??= Task.Run(async () =>
        {
            try { await session.Frames.RunAsync().ConfigureAwait(false); }
            catch (Exception ex) { Console.WriteLine("Frame pump failed for " + session.Config.Name + ": " + ex); throw; }
        });
        if (_receiver is null) return;
        var config = session.Config;
        var factory = _receiver;
        var supervisor = new AirplaySupervisor(() => factory(config), _maxRestarts, _restartDelay);
        var token = _token;
        entry.Supervisor = supervisor;
        entry.SupervisorRun = Task.Run(() => supervisor.RunAsync(token));
        entry.Generation++;
    }

    public Task ShutdownAsync()
    {
        lock (_gate)
        {
            // Every caller observes the same completion, including failures.
            // Pre-start disposal still cancels each session and forbids Start.
            return _shutdown ??= Task.Run(async () =>
            {
                // A restart in flight finishes its stop first; it starts nothing once shutdown began.
                Task[] changes;
                lock (_gate) changes = _entries.Select(e => e.Change).ToArray();
                await Task.WhenAll(changes).ConfigureAwait(false);
                Entry[] entries;
                lock (_gate) entries = [.. _entries];
                var failures = await Task.WhenAll(entries.Select(StopAndJoinAsync)).ConfigureAwait(false);
                var errors = failures.SelectMany(f => f).ToArray();
                if (errors.Length != 0) throw new AggregateException("Receiver fleet shutdown was not fully confirmed.", errors);
            });
        }
    }

    private async Task<List<Exception>> StopAndJoinAsync(Entry entry)
    {
        AirplaySupervisor? supervisor; Task run; Task? frames; ReceiverInfo? earlier;
        lock (_gate) { supervisor = entry.Supervisor; run = entry.SupervisorRun; frames = entry.FrameRun; earlier = entry.Failure; }
        var name = entry.Session.Config.Name;
        var errors = new List<Exception>();
        void Record(string operation, Exception ex) => errors.Add(new IOException(name + " " + operation + ": " + ex.Message, ex));
        // Initiate peer stops independently; one slow receiver must not delay
        // requesting cleanup of all the others. Each real child has its own
        // bounded exit confirmation in ReceiverProcessLifetime.
        await Task.Run(() =>
        {
            try { entry.Session.Frames.Dispose(); } catch (Exception ex) { Record("frame stop failed", ex); }
            try { supervisor?.Dispose(); } catch (Exception ex) { Record("receiver stop failed", ex); }
        }).ConfigureAwait(false);
        try { await run.ConfigureAwait(false); } catch (Exception ex) { Record("supervisor failed", ex); }
        if (frames is not null) { try { await frames.ConfigureAwait(false); } catch (Exception ex) { Record("frame reader failed", ex); } }
        // Dispose may find no current handle because the run already claimed
        // cleanup. Only after both paths join is its outcome final.
        if (supervisor?.CleanupFailure is { } failure) errors.Add(new IOException(name + ": " + failure.Message));
        if (earlier is not null) errors.Add(new IOException(name + ": an earlier restart left an unconfirmed exit. " + earlier.Message));
        return errors;
    }

    public ValueTask DisposeAsync() => new(ShutdownAsync());
    public void Dispose() => ShutdownAsync().GetAwaiter().GetResult();
}

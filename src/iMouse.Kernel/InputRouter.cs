using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.Json;

namespace IMouse2.Kernel;

public sealed record PointerCalibration(string Pid, int Width, int Height, double OriginX,
    double OriginY, double PixelsPerUnitX, double PixelsPerUnitY);

/// <summary>
/// What fn_key=Home sends. Vendor is the sequence observed from IMService on 14 Sep (Tab, then
/// Left GUI+H) and stays the default. Its Tab is typed into a focused text field. The other two
/// are for a phone comparison only, chosen once at kernel startup with --home-sequence; each
/// still goes through the per-phone lease, the board's write gate, Stop and key release.
/// </summary>
public enum HomeSequence { Vendor, CommandH, CommandWake }

public sealed class InputRouter : IDisposable
{
    private readonly DeviceStore _store;
    private readonly Dictionary<string, PointerCalibration> _calibrations;
    private readonly HashSet<string> _allowed;
    private readonly Func<string,IHidTransport> _open;
    private readonly int _preciseDelayMs;
    private readonly ConcurrentDictionary<string, HidReplyTelemetry> _replyTelemetry = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _replyBoards;
    private readonly ConcurrentDictionary<string, BoardState> _states = new(StringComparer.OrdinalIgnoreCase);
    private sealed class BoardState
    {
        public readonly SemaphoreSlim Gate = new(1, 1);
        public IHidTransport? Connection;
        // An estimate of transmitted relative steps, not an iOS position acknowledgement.
        // Keyboard focus/input-mode changes and outside controllers can invalidate it.
        public bool Known;
        public int X, Y;
        public byte Buttons;
        public CancellationToken Cancellation;
        public Exception? ReleaseFailure;
    }
    public InputRouter(DeviceStore store, IEnumerable<string> allowed, IEnumerable<PointerCalibration> calibrations,
        Func<string,IHidTransport>? open=null, int preciseDelayMs=0, IEnumerable<string>? replyBoards=null)
    {
        _store = store;
        _preciseDelayMs = preciseDelayMs;
        _allowed = new(allowed, StringComparer.OrdinalIgnoreCase);
        _replyBoards = new(replyBoards ?? [], StringComparer.OrdinalIgnoreCase);
        if (!_replyBoards.IsSubsetOf(_allowed)) throw new ArgumentException("Reply diagnostics require an enabled input board.");
        _open = open ?? (pid => new HidConnection(pid, _replyBoards.Contains(pid)
            ? _replyTelemetry.GetOrAdd(pid, _ => new()) : null));
        _calibrations = calibrations.ToDictionary(c => c.Pid, StringComparer.OrdinalIgnoreCase);
        if (_calibrations.Values.Any(c => !ValidAxis(c.Width,c.OriginX,c.PixelsPerUnitX)
            || !ValidAxis(c.Height,c.OriginY,c.PixelsPerUnitY)))
            throw new ArgumentException("Invalid pointer calibration.");
    }
    private static bool ValidAxis(int size,double origin,double pixelsPerUnit)
    {
        if(size < 2 || !double.IsFinite(origin) || !double.IsFinite(pixelsPerUnit) || pixelsPerUnit <= 0) return false;
        // Movement converts calibrated endpoints to int before stepping. Reject overflow
        // at startup rather than turning a valid on-screen target into an unrelated move.
        double first = Math.Round(-origin / pixelsPerUnit);
        double last = Math.Round((size-1-origin) / pixelsPerUnit);
        return double.IsFinite(first) && double.IsFinite(last)
            && first > int.MinValue && last < int.MaxValue;
    }
    public InputRouter(DeviceStore store, IEnumerable<string> allowed, IEnumerable<PointerCalibration> calibrations,
        Func<string,IHidTransport>? open, bool preciseMovement)
        : this(store, allowed, calibrations, open, preciseMovement ? 8 : 0) {}
    public bool Enabled(string pid) => _allowed.Contains(pid) && _calibrations.ContainsKey(pid);
    public string[] Allowed => _allowed.ToArray();
    internal object DiagnosticConfiguration() => new
    {
        precise_movement_delay_ms = _preciseDelayMs,
        hid_reply_boards = _replyBoards.OrderBy(p => p).ToArray(),
        calibrations = _calibrations.Values.Select(c => new { pid = c.Pid, enabled = Enabled(c.Pid),
            width = c.Width, height = c.Height, origin_x = c.OriginX, origin_y = c.OriginY,
            pixels_per_unit_x = c.PixelsPerUnitX, pixels_per_unit_y = c.PixelsPerUnitY }).ToArray()
    };
    internal object ReplyDiagnostics() => new
    {
        mode = "observation only; no write waits or action acknowledgement",
        boards = _replyBoards.OrderBy(p => p).Select(pid => new
        { pid, observation = _replyTelemetry.TryGetValue(pid, out var state) ? state.Snapshot() : new HidReplyTelemetry().Snapshot() }).ToArray()
    };
    public HomeSequence Home { get; init; } = HomeSequence.Vendor;
    public string HomeSequenceName => Home switch { HomeSequence.CommandH => "command-h", HomeSequence.CommandWake => "command-wake", _ => "vendor" };
    public static HomeSequence ParseHomeSequence(string value) => value switch
    {
        "vendor" => HomeSequence.Vendor,
        "command-h" => HomeSequence.CommandH,
        "command-wake" => HomeSequence.CommandWake,
        _ => throw new ArgumentException($"--home-sequence must be vendor, command-h or command-wake, not \"{value}\"."),
    };

    public async Task<object> DispatchAsync(string fun, JsonElement data, CancellationToken cancellation = default)
    {
        if (fun == "/device/usb/restart") return new { code = 41, message = "Restart packet has not been decoded." };
        var ids = Text(data, "id").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Distinct().ToArray();
        if (ids.Length == 0) return new { code = 36, message = "id required" };
        var phones = _store.All();
        var targets = ids.Select(id => phones.SingleOrDefault(p => p.deviceid == id)
            ?? throw new KeyNotFoundException(id)).ToArray();
        // Validate every target and argument before sending anything to any board.
        if (targets.Any(p => !Enabled(p.pid))) return new { code = 41, message = "Every target needs an enabled, calibrated board." };
        if (targets.Select(p => p.pid).Distinct(StringComparer.OrdinalIgnoreCase).Count() != targets.Length)
            return new { code = 36, message = "Multiple phones claim the same board." };
        foreach (var phone in targets) Validate(fun, data, _calibrations[phone.pid]);
        var results = await Task.WhenAll(targets.Select(async phone =>
        {
            try { await ExecuteAsync(phone.pid, fun, data, cancellation); return new { id = phone.deviceid, code = 0, message = "ok" }; }
            catch (OperationCanceledException) { return new { id = phone.deviceid, code = 499, message = "Input cancelled" }; }
            catch (Exception ex) { return new { id = phone.deviceid, code = 33, message = ex.Message }; }
        }));
        return new { code = results.All(r => r.code == 0) ? 0 : 33, results };
    }

    public void ValidateCommand(string fun, JsonElement data, string pid)
    {
        if (fun is not ("/mouse/reset" or "/mouse/move" or "/mouse/down" or "/mouse/up" or "/mouse/click" or "/mouse/swipe" or "/key/sendkey"))
            throw new ArgumentException("Unsupported input operation.");
        if (!Enabled(pid)) throw new ArgumentException("Target needs an enabled, calibrated board.");
        Validate(fun, data, _calibrations[pid]);
    }

    // Cleanup deliberately ignores the cancelled command token. Transport writes have
    // their own two-second deadline. Never open an otherwise unused board just to stop it.
    public async Task ReleaseAsync(string pid)
    {
        if (!_states.TryGetValue(pid, out var state)) return;
        await state.Gate.WaitAsync();
        try
        {
            state.Known = false; state.Buttons = 0;
            if (state.Connection is null)
            {
                if (state.ReleaseFailure is not null) throw new IOException("Input release was not confirmed; check the board before restarting input.", state.ReleaseFailure);
                return;
            }
            try { await ReleaseReportsAsync(state); }
            finally { state.Connection.Dispose(); state.Connection = null; }
        }
        finally { state.Gate.Release(); }
    }

    private static async Task ReleaseReportsAsync(BoardState state)
    {
        Exception? failure = null;
        try { await state.Connection!.SendAsync(HidProtocol.Mouse(), CancellationToken.None); }
        catch (Exception ex) { failure = ex; }
        try { await state.Connection!.SendAsync(HidProtocol.Key(), CancellationToken.None); }
        catch (Exception ex) { failure ??= ex; }
        if (failure is not null) throw new IOException("Input release could not be confirmed.", failure);
    }

    private static void Validate(string fun, JsonElement data, PointerCalibration c)
    {
        if (fun is "/mouse/move" or "/mouse/click") ValidatePoint(data, "x", "y", c);
        if (fun is "/mouse/down" or "/mouse/up" or "/mouse/click")
            if (Number(data,"button",1) != 1) throw new ArgumentException("Only the verified left button is supported.");
        if (fun == "/mouse/swipe")
        {
            if(Text(data,"direction").Length>0) _=SwipePoints(data,c);
            else { ValidatePoint(data,"x1","y1",c); ValidatePoint(data,"x2","y2",c); }
            if (Number(data,"duration",300) is < 20 or > 5000) throw new ArgumentException("duration must be 20–5000 ms.");
        }
        if (fun == "/key/sendkey")
        {
            string key = Text(data,"fn_key"), value = Text(data,"key");
            if (key.Length > 0 && key is not ("Home" or "Enter" or "ENTER" or "Backspace" or "BACKSPACE" or "Tab" or "Escape" or "AppSwitch" or "ControlBar"))
                throw new ArgumentException("Function key has not been verified: " + key);
            if (value.Length > 1000 || (key.Length == 0 && value.Length == 0)) throw new ArgumentException("Provide a key or 1–1000 ASCII characters.");
            foreach (char ch in value) _ = HidProtocol.Ascii(ch);
        }
    }
    private static void ValidatePoint(JsonElement d, string x, string y, PointerCalibration c)
    {
        int px=Number(d,x,-1), py=Number(d,y,-1);
        if (px<0 || py<0 || px>=c.Width || py>=c.Height) throw new ArgumentException("Coordinates outside calibrated image.");
    }
    private async Task ExecuteAsync(string pid, string fun, JsonElement data, CancellationToken cancellation)
    {
        var state = _states.GetOrAdd(pid, _ => new());
        await state.Gate.WaitAsync(cancellation);
        try
        {
            state.Cancellation = cancellation;
            cancellation.ThrowIfCancellationRequested();
            state.Connection ??= _open(pid);
            var calibration = _calibrations[pid];
            switch (fun)
            {
                case "/mouse/reset": await ResetAsync(state); break;
                case "/mouse/move": await MoveAsync(state,calibration,Number(data,"x"),Number(data,"y")); break;
                case "/mouse/down":
                    await SettleAsync(state);
                    state.Buttons=1; await Send(state,HidProtocol.Mouse(1)); break;
                case "/mouse/up": state.Buttons=0; await Send(state,HidProtocol.Mouse()); break;
                case "/mouse/click":
                    await ClickAsync(state,calibration,Number(data,"x"),Number(data,"y"));
                    break;
                case "/mouse/swipe":
                    var (x1,y1,x2,y2)=SwipePoints(data,calibration);
                    await MoveAsync(state,calibration,x1,y1);
                    await SettleAsync(state);
                    try
                    {
                        state.Buttons=1; await Send(state,HidProtocol.Mouse(1));
                        await Task.Delay(80, state.Cancellation); // Let iOS register contact before the first movement.
                        await MoveAsync(state,calibration,x2,y2,Number(data,"duration",300));
                    }
                    finally { state.Buttons=0; await Send(state,HidProtocol.Mouse()); }
                    break;
                case "/key/sendkey":
                    string fn=Text(data,"fn_key");
                    if (fn=="Home")
                    {
                        if (Home == HomeSequence.Vendor) await Stroke(state,0,43);          // Tab: typed into a focused text field
                        else if (Home == HomeSequence.CommandWake) await Stroke(state,8,0); // Left GUI alone: types nothing
                        await Stroke(state,8,11);                                            // Left GUI+H
                        state.Known=false;
                    }
                    else if(fn is "AppSwitch" or "ControlBar")
                    {
                        await Stroke(state,0,43);
                        try
                        {
                            await Send(state,[0xA2,0,0,0,0,0,0,2]);await Task.Delay(45, state.Cancellation);
                            await Send(state,[0xA2,0,(byte)(fn=="AppSwitch"?0x52:6),0,0,0,0,2]);await Task.Delay(60, state.Cancellation);
                        }
                        finally { await Send(state,HidProtocol.Key());state.Known=false; }
                    }
                    else if (fn.Length>0) await Stroke(state,0,fn switch {"Enter" or "ENTER"=>40,"Backspace" or "BACKSPACE"=>42,"Tab"=>43,"Escape"=>41,_=>throw new ArgumentException(fn)});
                    else foreach (char ch in Text(data,"key")) { var (modifier,usage)=HidProtocol.Ascii(ch); await Stroke(state,modifier,usage); }
                    break;
                default: throw new ArgumentException("Unsupported input operation.");
            }
        }
        catch
        {
            state.Known=false; state.Buttons=0;
            if (state.Connection is not null)
            {
                try { await ReleaseReportsAsync(state); } catch (Exception ex) { state.ReleaseFailure = ex; }
                state.Connection.Dispose(); state.Connection=null;
            }
            throw;
        }
        finally { state.Gate.Release(); }
    }
    private static Task Send(BoardState state,byte[] report)
    {
        state.Cancellation.ThrowIfCancellationRequested();
        return state.Connection!.SendAsync(report, state.Cancellation);
    }
    private async Task ClickAsync(BoardState state, PointerCalibration calibration, int x, int y)
    {
        var sw = Stopwatch.StartNew();
        bool known = state.Known;
        var move = await MoveAsync(state, calibration, x, y);
        long afterMove = sw.ElapsedMilliseconds;
        await SettleAsync(state);
        long afterSettle = sw.ElapsedMilliseconds;
        try { state.Buttons = 1; await Send(state, HidProtocol.Mouse(1)); await Task.Delay(80, state.Cancellation); }
        finally { state.Buttons = 0; await Send(state, HidProtocol.Mouse()); }
        Console.WriteLine(
            $"click pid={calibration.Pid} known={known} reset={move.ResetMs}ms steps={move.Steps} send={move.SendMs}ms delay={move.DelayMs}ms settle={afterSettle - afterMove}ms button={sw.ElapsedMilliseconds - afterSettle}ms total={sw.ElapsedMilliseconds}ms");
    }
    // iOS AssistiveTouch often treats a click that starts while the pointer is still
    // walking as "the pointer arrived here", not as an activation. A zero-motion report
    // then a short wait lets the last relative step finish before the button goes down.
    // Do not double-click to paper over this.
    private static async Task SettleAsync(BoardState state)
    {
        await Send(state, HidProtocol.Mouse(state.Buttons));
        await Task.Delay(120, state.Cancellation);
    }
    private static async Task Stroke(BoardState state,byte modifier,byte usage)
    {
        await Send(state,HidProtocol.Key()); await Task.Delay(45, state.Cancellation);
        try { await Send(state,HidProtocol.Key(modifier,usage)); await Task.Delay(usage == 44 ? 90 : 60, state.Cancellation); }
        finally { await Send(state,HidProtocol.Key()); }
        await Task.Delay(35, state.Cancellation);
    }
    private static async Task ResetAsync(BoardState state)
    {
        state.Buttons=0; await Send(state,HidProtocol.Mouse()); await Send(state,HidProtocol.Key());
        for(int i=0;i<4;i++) { await Send(state,HidProtocol.Mouse(0,-127,-127)); await Task.Delay(10, state.Cancellation); }
        state.X=state.Y=0; state.Known=true;
    }
    private async Task<(int ResetMs, int Steps, int SendMs, int DelayMs)> MoveAsync(BoardState state,PointerCalibration c,int x,int y,int duration=0)
    {
        int resetMs = 0;
        if(!state.Known)
        {
            if(state.Buttons!=0) throw new InvalidOperationException("Reset the pointer before starting a drag.");
            var resetAt = Stopwatch.StartNew();
            await ResetAsync(state);
            resetMs = (int)resetAt.ElapsedMilliseconds;
        }
        int tx=Math.Max(0,(int)Math.Round((x-c.OriginX)/c.PixelsPerUnitX));
        int ty=Math.Max(0,(int)Math.Round((y-c.OriginY)/c.PixelsPerUnitY));
        int sx=state.X,sy=state.Y,steps=Math.Max(Math.Abs(tx-sx),Math.Abs(ty-sy));
        // Keep one-unit reports and calibration. Task.Delay(3) rounds near 15 ms on
        // this Windows host; opt-in precise pacing fixes that without skipping reset.
        // Held-button movement keeps its established gesture timing.
        using var pacing = _preciseDelayMs > 0 && duration == 0 && state.Buttons == 0 && steps > 0
            ? new MovementDelay() : null;
        int sendMs = 0, delayMs = 0;
        for(int i=1;i<=steps;i++)
        {
            int nx=sx+(int)Math.Round((tx-sx)*(double)i/steps),ny=sy+(int)Math.Round((ty-sy)*(double)i/steps);
            var sendAt = Stopwatch.StartNew();
            await Send(state,HidProtocol.Mouse(state.Buttons,(sbyte)(nx-state.X),(sbyte)(ny-state.Y)));
            sendMs += (int)sendAt.ElapsedMilliseconds;
            state.X=nx;state.Y=ny;
            var delayAt = Stopwatch.StartNew();
            int delay = Math.Max(3,duration/Math.Max(1,steps));
            if (pacing is null) await Task.Delay(delay, state.Cancellation);
            else await pacing.WaitAsync(_preciseDelayMs, state.Cancellation);
            delayMs += (int)delayAt.ElapsedMilliseconds;
        }
        return (resetMs, steps, sendMs, delayMs);
    }
    private static string Text(JsonElement d,string key) => d.ValueKind==JsonValueKind.Object && d.TryGetProperty(key,out var v)?v.ToString():"";
    private static (int X1,int Y1,int X2,int Y2) SwipePoints(JsonElement data,PointerCalibration c)
    {
        string direction=Text(data,"direction").ToLowerInvariant();
        if(direction.Length==0) return(Number(data,"x1"),Number(data,"y1"),Number(data,"x2"),Number(data,"y2"));
        double length=double.TryParse(Text(data,"len"),System.Globalization.NumberStyles.Float,
            System.Globalization.CultureInfo.InvariantCulture,out var parsed)?parsed:0.75;
        if(!double.IsFinite(length) || length<=0 || length>0.9) throw new ArgumentException("len must be greater than zero and at most 0.9.");
        int x=c.Width/2,y=c.Height/2,dx=(int)(c.Width*length/2),dy=(int)(c.Height*length/2);
        return direction switch {"up"=>(x,y+dy,x,y-dy),"down"=>(x,y-dy,x,y+dy),
            "left"=>(x+dx,y,x-dx,y),"right"=>(x-dx,y,x+dx,y),_=>throw new ArgumentException("Unknown swipe direction.")};
    }
    private static int Number(JsonElement d,string key,int fallback=0) => int.TryParse(Text(d,key),out int n)?n:fallback;
    public void Dispose()
    {
        foreach(var state in _states.Values)
        {
            if(state.Connection is not null)
            {
                try { ReleaseReportsAsync(state).GetAwaiter().GetResult(); } catch { }
                state.Connection.Dispose();
            }
        }
    }
}

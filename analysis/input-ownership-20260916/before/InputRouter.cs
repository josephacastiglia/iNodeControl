using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.Json;

namespace IMouse2.Kernel;

public sealed record PointerCalibration(string Pid, int Width, int Height, double OriginX,
    double OriginY, double PixelsPerUnitX, double PixelsPerUnitY);

public sealed class InputRouter : IDisposable
{
    private readonly DeviceStore _store;
    private readonly Dictionary<string, PointerCalibration> _calibrations;
    private readonly HashSet<string> _allowed;
    private readonly Func<string,IHidTransport> _open;
    private readonly bool _preciseMovement;
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
    }
    public InputRouter(DeviceStore store, IEnumerable<string> allowed, IEnumerable<PointerCalibration> calibrations,
        Func<string,IHidTransport>? open=null, bool preciseMovement=false)
    {
        _store = store;
        _open = open ?? (pid => new HidConnection(pid));
        _preciseMovement = preciseMovement;
        _allowed = new(allowed, StringComparer.OrdinalIgnoreCase);
        _calibrations = calibrations.ToDictionary(c => c.Pid, StringComparer.OrdinalIgnoreCase);
        if (_calibrations.Values.Any(c => c.Width < 2 || c.Height < 2 || !double.IsFinite(c.PixelsPerUnitX)
            || !double.IsFinite(c.PixelsPerUnitY) || c.PixelsPerUnitX <= 0 || c.PixelsPerUnitY <= 0))
            throw new ArgumentException("Invalid pointer calibration.");
    }
    public bool Enabled(string pid) => _allowed.Contains(pid) && _calibrations.ContainsKey(pid);
    public string[] Allowed => _allowed.ToArray();

    public async Task<object> DispatchAsync(string fun, JsonElement data)
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
            try { await ExecuteAsync(phone.pid, fun, data); return new { id = phone.deviceid, code = 0, message = "ok" }; }
            catch (Exception ex) { return new { id = phone.deviceid, code = 33, message = ex.Message }; }
        }));
        return new { code = results.All(r => r.code == 0) ? 0 : 33, results };
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
    private async Task ExecuteAsync(string pid, string fun, JsonElement data)
    {
        var state = _states.GetOrAdd(pid, _ => new());
        await state.Gate.WaitAsync();
        try
        {
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
                        await Task.Delay(80); // Let iOS register contact before the first movement.
                        await MoveAsync(state,calibration,x2,y2,Number(data,"duration",300));
                    }
                    finally { state.Buttons=0; await Send(state,HidProtocol.Mouse()); }
                    break;
                case "/key/sendkey":
                    string fn=Text(data,"fn_key");
                    if (fn=="Home") { await Stroke(state,0,43); await Stroke(state,8,11); state.Known=false; }
                    else if(fn is "AppSwitch" or "ControlBar")
                    {
                        await Stroke(state,0,43);
                        try
                        {
                            await Send(state,[0xA2,0,0,0,0,0,0,2]);await Task.Delay(45);
                            await Send(state,[0xA2,0,(byte)(fn=="AppSwitch"?0x52:6),0,0,0,0,2]);await Task.Delay(60);
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
                try { await Send(state,HidProtocol.Mouse()); await Send(state,HidProtocol.Key()); } catch { }
                state.Connection.Dispose(); state.Connection=null;
            }
            throw;
        }
        finally { state.Gate.Release(); }
    }
    private static Task Send(BoardState state,byte[] report) => state.Connection!.SendAsync(report,CancellationToken.None);
    private async Task ClickAsync(BoardState state, PointerCalibration calibration, int x, int y)
    {
        var sw = Stopwatch.StartNew();
        bool known = state.Known;
        var move = await MoveAsync(state, calibration, x, y);
        long afterMove = sw.ElapsedMilliseconds;
        await SettleAsync(state);
        long afterSettle = sw.ElapsedMilliseconds;
        try { state.Buttons = 1; await Send(state, HidProtocol.Mouse(1)); await Task.Delay(80); }
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
        await Task.Delay(120);
    }
    private static async Task Stroke(BoardState state,byte modifier,byte usage)
    {
        await Send(state,HidProtocol.Key()); await Task.Delay(45);
        try { await Send(state,HidProtocol.Key(modifier,usage)); await Task.Delay(usage == 44 ? 90 : 60); }
        finally { await Send(state,HidProtocol.Key()); }
        await Task.Delay(35);
    }
    private static async Task ResetAsync(BoardState state)
    {
        state.Buttons=0; await Send(state,HidProtocol.Mouse()); await Send(state,HidProtocol.Key());
        for(int i=0;i<4;i++) { await Send(state,HidProtocol.Mouse(0,-127,-127)); await Task.Delay(10); }
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
        using var pacing = _preciseMovement && duration == 0 && state.Buttons == 0 && steps > 0
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
            if (pacing is null) await Task.Delay(delay);
            else await pacing.WaitAsync(delay);
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
                try { Send(state,HidProtocol.Mouse()).GetAwaiter().GetResult(); Send(state,HidProtocol.Key()).GetAwaiter().GetResult(); } catch { }
                state.Connection.Dispose();
            }
        }
    }
}

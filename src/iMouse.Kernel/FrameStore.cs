using System.Buffers.Binary;
using System.IO.Pipes;
using System.Net;
using System.Globalization;

namespace IMouse2.Kernel;

/// <summary>Atomic receiver-delivery snapshot. Quiet means no new BMP for two seconds,
/// not proof that the phone or receiver failed. Sequence counts delivered BMPs, including
/// identical pixels; it is not a display count or a source capture timestamp.</summary>
public sealed record FrameDelivery(string Session, long Sequence, bool Connected, bool Available,
    int Width, int Height, double? AgeMs, string Status, string Message);

/// <summary>One explicitly assigned receiver session. Reuses two raw BMP buffers.</summary>
public sealed class FrameStore : IDisposable
{
    private readonly object _gate = new();
    private readonly CancellationTokenSource _stop = new();
    private readonly string _pipeName;
    private byte[] _current = [], _incoming = [];
    private int _length, _width, _height;
    private bool _connected;
    private readonly TimeProvider _clock;
    private readonly string _session = Guid.NewGuid().ToString("N");
    private long _frames;
    private long? _lastFrame;
    private string _deliveryState = "waiting", _deliveryMessage = "Waiting for the receiver frame pipe.";
    private int _runStarted;
    public const double QuietAfterMs = 2000;
    public string DeviceId { get; }
    public Func<int> ReceiverPid { get; set; } = () => 0;
    public Func<ReceiverInfo> Receiver { get; set; } = () => new("stopped", "", 0, 0);
    public long Frames { get { lock (_gate) return _frames; } }
    public FrameStore(string pipeName, string deviceId, TimeProvider? clock = null)
    {
        _pipeName = pipeName; DeviceId = deviceId; _clock = clock ?? TimeProvider.System;
    }
    public FrameDelivery Delivery { get { lock (_gate) return Snapshot(); } }
    // Caller holds _gate, including when pairing metadata with screenshot bytes.
    private FrameDelivery Snapshot()
    {
        double? age = _lastFrame is { } last
            ? Math.Max(0, _clock.GetElapsedTime(last, _clock.GetTimestamp()).TotalMilliseconds) : null;
        bool available = _connected && _length > 0;
        bool quiet = available && age >= QuietAfterMs;
        return new(_session, _frames, _connected, available, _width, _height, age,
            quiet ? "quiet" : _deliveryState,
            quiet ? "No new receiver frame for at least two seconds; a still screen or stalled delivery is possible." : _deliveryMessage);
    }
    public (bool Live,int Width,int Height) State
    {
        get { lock(_gate) return (_connected && _length>0,_width,_height); }
    }
    public Task RunAsync()
    {
        if (Interlocked.Exchange(ref _runStarted, 1) != 0)
            throw new InvalidOperationException("Frame pipe reader can only run once.");
        return Task.Run(async () =>
        {
            try
            {
                while (!_stop.IsCancellationRequested)
                {
                    using var pipe = new NamedPipeServerStream(_pipeName, PipeDirection.In, 1,
                        PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                    try
                    {
                        await pipe.WaitForConnectionAsync(_stop.Token);
                        await ReadConnectionAsync(pipe, _stop.Token);
                    }
                    catch (OperationCanceledException) when (_stop.IsCancellationRequested) { break; }
                    catch (IOException)
                    {
                        SetFailure("io_error", "Receiver frame pipe connection failed; waiting to reconnect.");
                        await Task.Delay(250, _stop.Token);
                    }
                }
            }
            catch (OperationCanceledException) when (_stop.IsCancellationRequested) { }
            catch (Exception)
            {
                SetFailure("reader_error", "Frame pipe reader stopped unexpectedly.");
                throw;
            }
            finally
            {
                lock (_gate)
                {
                    _connected = false; _length = 0; _width = _height = 0;
                    if (_stop.IsCancellationRequested)
                    { _deliveryState = "stopped"; _deliveryMessage = "Frame reader stopped."; }
                }
            }
        });
    }

    // The same decoder runs on a named pipe in production and a synthetic stream in tests.
    internal async Task ReadConnectionAsync(Stream pipe, CancellationToken ct)
    {
        byte[] prefix = new byte[4];
        lock (_gate)
        {
            _connected = true; _length = 0; _width = _height = 0;
            _deliveryState = "waiting"; _deliveryMessage = "Receiver connected; waiting for a complete frame.";
        }
        try
        {
            while (true)
            {
                await pipe.ReadExactlyAsync(prefix, ct);
                int length = BinaryPrimitives.ReadInt32LittleEndian(prefix);
                if (length == 0)
                {
                    lock (_gate)
                    {
                        _length = 0; _width = _height = 0;
                        _deliveryState = "stopped"; _deliveryMessage = "Receiver signalled the end of mirroring.";
                    }
                    continue;
                }
                if (length < 54 || length > 50 * 1024 * 1024) throw new InvalidDataException("Invalid BMP length.");
                if (_incoming.Length < length) _incoming = new byte[length];
                await pipe.ReadExactlyAsync(_incoming.AsMemory(0, length), ct);
                var (width, height) = ValidateBmp(_incoming.AsSpan(0, length));
                lock (_gate)
                {
                    (_incoming, _current) = (_current, _incoming);
                    _length = length; _width = width; _height = height; _frames++;
                    _lastFrame = _clock.GetTimestamp();
                    _deliveryState = "flowing"; _deliveryMessage = "";
                }
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        { SetFailure("stopped", "Frame reader stopped."); }
        catch (EndOfStreamException)
        { SetFailure("disconnected", "Receiver frame pipe disconnected; waiting to reconnect."); }
        catch (InvalidDataException ex)
        { SetFailure("invalid_frame", ex.Message); }
        catch (IOException)
        { SetFailure("io_error", "Receiver frame pipe read failed; waiting to reconnect."); }
        catch (Exception)
        {
            SetFailure("reader_error", "Unexpected receiver frame reader failure.");
            throw;
        }
        finally
        {
            lock (_gate) { _connected = false; _length = 0; _width = _height = 0; }
        }
    }
    private void SetFailure(string state, string message)
    {
        lock (_gate) { _deliveryState = state; _deliveryMessage = message; }
    }
    public bool WriteFrame(HttpListenerContext ctx,string id)
    {
        lock(_gate)
        {
            if(id!=DeviceId || !_connected || _length==0) return false;
            var delivery = Snapshot();
            WriteMetadata(delivery, ctx.Response.Headers);
            ctx.Response.ContentType="image/bmp";
            ctx.Response.Headers["Cache-Control"]="no-store";
            ctx.Response.ContentLength64=_length;
            ctx.Response.OutputStream.Write(_current,0,_length);
            ctx.Response.Close();
            return true;
        }
    }
    internal static void WriteMetadata(FrameDelivery delivery, WebHeaderCollection headers)
    {
        headers["X-iMouse-Frame-Session"] = delivery.Session;
        headers["X-iMouse-Frame-Sequence"] = delivery.Sequence.ToString(CultureInfo.InvariantCulture);
        headers["X-iMouse-Frame-Age-Ms"] = delivery.AgeMs!.Value.ToString("0.###", CultureInfo.InvariantCulture);
        headers["X-iMouse-Frame-Delivery"] = delivery.Status;
    }
    public static (int Width,int Height) ValidateBmp(ReadOnlySpan<byte> bmp)
    {
        if(bmp.Length<54 || bmp[0]!='B' || bmp[1]!='M' || BinaryPrimitives.ReadInt32LittleEndian(bmp[2..])!=bmp.Length
            || BinaryPrimitives.ReadInt32LittleEndian(bmp[10..])!=54 || BinaryPrimitives.ReadInt32LittleEndian(bmp[14..])!=40
            || BinaryPrimitives.ReadInt16LittleEndian(bmp[26..])!=1 || BinaryPrimitives.ReadInt16LittleEndian(bmp[28..])!=24
            || BinaryPrimitives.ReadInt32LittleEndian(bmp[30..])!=0) throw new InvalidDataException("Expected uncompressed 24-bit BMP.");
        int width=BinaryPrimitives.ReadInt32LittleEndian(bmp[18..]),height=BinaryPrimitives.ReadInt32LittleEndian(bmp[22..]);
        if(width<1 || height<1 || width>4096 || height>4096 || checked(54+((width*3+3)&~3)*height)!=bmp.Length)
            throw new InvalidDataException("Invalid BMP dimensions or stride.");
        return(width,height);
    }
    public void Dispose() { _stop.Cancel(); }
}

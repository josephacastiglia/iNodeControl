using System.Buffers.Binary;
using System.IO.Pipes;
using System.Net;

namespace IMouse2.Kernel;

/// <summary>One explicitly assigned receiver session. Reuses two raw BMP buffers.</summary>
public sealed class FrameStore : IDisposable
{
    private readonly object _gate = new();
    private readonly CancellationTokenSource _stop = new();
    private readonly string _pipeName;
    private byte[] _current = [], _incoming = [];
    private int _length, _width, _height;
    private bool _connected;
    public string DeviceId { get; }
    public Func<int> ReceiverPid { get; set; } = () => 0;
    public Func<ReceiverInfo> Receiver { get; set; } = () => new("stopped", "", 0, 0);
    public long Frames { get; private set; }
    public FrameStore(string pipeName,string deviceId) { _pipeName=pipeName; DeviceId=deviceId; }
    public (bool Live,int Width,int Height) State
    {
        get { lock(_gate) return (_connected && _length>0,_width,_height); }
    }
    public Task RunAsync() => Task.Run(async () =>
    {
        byte[] prefix=new byte[4];
        while(!_stop.IsCancellationRequested)
        {
            using var pipe=new NamedPipeServerStream(_pipeName,PipeDirection.In,1,PipeTransmissionMode.Byte,
                PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
            try
            {
                await pipe.WaitForConnectionAsync(_stop.Token);
                lock(_gate) _connected=true;
                while(!_stop.IsCancellationRequested)
                {
                    await pipe.ReadExactlyAsync(prefix,_stop.Token);
                    int length=BinaryPrimitives.ReadInt32LittleEndian(prefix);
                    if(length==0) { lock(_gate) { _length=0; } continue; }
                    if(length<54 || length>50*1024*1024) throw new InvalidDataException("Invalid BMP length.");
                    if(_incoming.Length<length) _incoming=new byte[length];
                    await pipe.ReadExactlyAsync(_incoming.AsMemory(0,length),_stop.Token);
                    var (width,height)=ValidateBmp(_incoming.AsSpan(0,length));
                    lock(_gate)
                    {
                        (_incoming,_current)=(_current,_incoming);
                        _length=length;_width=width;_height=height;Frames++;
                    }
                }
            }
            catch(OperationCanceledException) { break; }
            catch(EndOfStreamException)
            {
                Console.WriteLine("Frame pipe: receiver disconnected; waiting to reconnect.");
            }
            catch(IOException ex)
            {
                Console.WriteLine("Frame pipe: " + ex.Message + "; waiting to reconnect.");
            }
            catch(Exception ex) { Console.WriteLine("Frame pipe: " + ex.Message); }
            finally { lock(_gate) { _connected=false;_length=0; } }
        }
    });
    public bool WriteFrame(HttpListenerContext ctx,string id)
    {
        lock(_gate)
        {
            if(id!=DeviceId || !_connected || _length==0) return false;
            ctx.Response.ContentType="image/bmp";
            ctx.Response.Headers["Cache-Control"]="no-store";
            ctx.Response.ContentLength64=_length;
            ctx.Response.OutputStream.Write(_current,0,_length);
            ctx.Response.Close();
            return true;
        }
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

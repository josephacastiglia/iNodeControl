// Stand-in for uxplay.exe in off-rack trials: takes UxPlay's arguments, advertises nothing (no
// AirPlay, no mDNS), holds its TCP port like a receiver would, and sends a small BMP frame to the
// kernel's frame pipe (IMOUSE2_FRAME_PIPE) five times a second, reconnecting if the pipe drops.
// It runs until killed, as the kernel kills a real receiver.
using System.Buffers.Binary;
using System.IO.Pipes;
using System.Net;
using System.Net.Sockets;

string name = "", pipe = Environment.GetEnvironmentVariable("IMOUSE2_FRAME_PIPE") ?? "";
int port = 0;
for (int i = 0; i + 1 < args.Length; i++)
{
    if (args[i] == "-n") name = args[i + 1];
    if (args[i] == "-p") port = int.Parse(args[i + 1]);
}
if (!name.StartsWith("iMouse2-") || port == 0 || !pipe.StartsWith(@"\\.\pipe\")) { Console.Error.WriteLine("fake receiver: missing -n, -p or frame pipe"); return 2; }
var listener = new TcpListener(IPAddress.Loopback, port);
listener.Start();
Console.WriteLine($"fake receiver {name} on 127.0.0.1:{port}, pid {Environment.ProcessId}");

byte[] bmp = new byte[70];
bmp[0] = (byte)'B'; bmp[1] = (byte)'M';
BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(2), 70);
BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(10), 54);
BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(14), 40);
BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(18), 2);
BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(22), 2);
BinaryPrimitives.WriteInt16LittleEndian(bmp.AsSpan(26), 1);
BinaryPrimitives.WriteInt16LittleEndian(bmp.AsSpan(28), 24);
byte[] size = new byte[4];
BinaryPrimitives.WriteInt32LittleEndian(size, bmp.Length);
string pipeName = pipe[@"\\.\pipe\".Length..];
while (true)
{
    try
    {
        using var client = new NamedPipeClientStream(".", pipeName, PipeDirection.Out);
        client.Connect(5000);
        while (true)
        {
            client.Write(size); client.Write(bmp); client.Flush();
            Thread.Sleep(200);
        }
    }
    catch (Exception ex) when (ex is IOException or TimeoutException) { Thread.Sleep(250); }
}

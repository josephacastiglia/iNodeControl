using System.Runtime.InteropServices;
using Microsoft.Diagnostics.Tracing;

if (args.Length < 2)
{
    Console.Error.WriteLine("Usage: HidEtlDump <file.etl> dump <provider-substring> <id> [count]");
    return 1;
}

string path = args[0];
string mode = args[1];
if (mode != "dump") return 1;
string needle = args[2];
int id = int.Parse(args[3]);
int want = args.Length > 4 ? int.Parse(args[4]) : 5;
string? contains = args.Length > 5 ? args[5] : null;
int shown = 0;
using (var src = new ETWTraceEventSource(path))
{
    src.Dynamic.All += e =>
    {
        if (shown >= want) return;
        if ((int)e.ID != id) return;
        if (e.ProviderName is null || e.ProviderName.IndexOf(needle, StringComparison.OrdinalIgnoreCase) < 0) return;
        byte[] b = Bytes(e);
        string hex = Convert.ToHexString(b);
        if (contains is not null && hex.IndexOf(contains, StringComparison.OrdinalIgnoreCase) < 0
            && System.Text.Encoding.Unicode.GetString(b).IndexOf(contains, StringComparison.OrdinalIgnoreCase) < 0)
            return;
        Console.WriteLine($"{e.TimeStamp:HH:mm:ss.fff} id={e.ID} len={b.Length}");
        Console.WriteLine(hex);
        Console.WriteLine();
        shown++;
    };
    src.Process();
}
Console.WriteLine($"dumped {shown}");
return 0;

static byte[] Bytes(TraceEvent e)
{
    int n = e.EventDataLength;
    if (n <= 0) return [];
    var b = new byte[n];
    Marshal.Copy(e.DataStart, b, 0, n);
    return b;
}

using System.Text;

namespace IMouse2.Kernel;

/// <summary>
/// --console-log: what the kernel's console would show, written to a file for a detached launch.
/// The kernel prints a line for every request, so an unbounded file grows for as long as the rack
/// runs. Past <see cref="DefaultMaxBytes"/> the file is set aside as "name.1", replacing the one
/// before it, and a new file is begun: at most twice the cap is ever on disk. If something holds
/// the file in a way that blocks the rename, it is started again in place instead. A log that
/// cannot be written drops its text; it never throws into the kernel.
/// </summary>
internal sealed class ConsoleLogFile : TextWriter
{
    public const long DefaultMaxBytes = 16 * 1024 * 1024;
    private static readonly UTF8Encoding Utf8 = new(encoderShouldEmitUTF8Identifier: false);
    private readonly string _path;
    private readonly long _maxBytes;
    // Console.Out and Console.Error each wrap this writer in their own lock, so it needs its own.
    private readonly object _gate = new();
    private FileStream? _stream;
    private bool _closed;

    public override Encoding Encoding => Utf8;

    public ConsoleLogFile(string path, long maxBytes = DefaultMaxBytes)
    {
        if (maxBytes < 256) throw new ArgumentOutOfRangeException(nameof(maxBytes));
        _path = Path.GetFullPath(path);
        _maxBytes = maxBytes;
    }

    public override void Write(char value) => Append(value.ToString());
    public override void Write(string? value) => Append(value);
    public override void Write(char[] buffer, int index, int count) => Append(new string(buffer, index, count));
    // One call per line, so a line is never split by another thread or across two files.
    public override void WriteLine() => Append(CoreNewLineText);
    public override void WriteLine(string? value) => Append(value + CoreNewLineText);
    private static string CoreNewLineText => Environment.NewLine;

    private void Append(string? text)
    {
        if (string.IsNullOrEmpty(text)) return;
        byte[] bytes = Utf8.GetBytes(text);
        lock (_gate)
        {
            if (_closed) return;
            try
            {
                _stream ??= Open(FileMode.Append);
                if (_stream.Length > 0 && _stream.Length + bytes.Length > _maxBytes) StartNewFile();
                // Still over: the file could be neither set aside nor emptied. Do not grow it.
                if (_stream.Length > 0 && _stream.Length + bytes.Length > _maxBytes) return;
                _stream.Write(bytes); _stream.Flush();
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or NotSupportedException
                or ObjectDisposedException or System.Security.SecurityException)
            {
                // Drop this text and open the file afresh on the next write.
                try { _stream?.Dispose(); } catch (IOException) { }
                _stream = null;
            }
        }
    }

    private FileStream Open(FileMode mode) => new(_path, mode, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete);

    private void StartNewFile()
    {
        _stream!.Dispose(); _stream = null;
        string note;
        try
        {
            File.Move(_path, _path + ".1", overwrite: true);
            _stream = Open(FileMode.Append);
            note = "earlier output is in " + Path.GetFileName(_path) + ".1";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // A reader holds the file without allowing a rename: empty it where it is.
            _stream = Open(FileMode.Create);
            note = "earlier output was discarded because the file was in use; " + Path.GetFileName(_path) + ".1 is older";
        }
        byte[] first = Utf8.GetBytes("Kernel console log continues " + DateTime.UtcNow.ToString("o") + "; " + note + "." + Environment.NewLine);
        _stream.Write(first); _stream.Flush();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) lock (_gate) { _closed = true; _stream?.Dispose(); _stream = null; }
        base.Dispose(disposing);
    }
}

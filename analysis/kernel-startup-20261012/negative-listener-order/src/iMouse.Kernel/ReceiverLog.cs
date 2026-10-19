using System.Text;

namespace IMouse2.Kernel;

/// <summary>Bounded receiver output. File failures degrade diagnostics, not the receiver.</summary>
public sealed class ReceiverLog
{
    public const long DefaultMaxBytes = 4 * 1024 * 1024;
    private readonly string _path;
    private readonly long _maxBytes;
    private readonly object _gate = new();
    private string? _error;
    public string? Error { get { lock (_gate) return _error; } }

    public ReceiverLog(string path, long maxBytes = DefaultMaxBytes)
    {
        if (maxBytes < 256) throw new ArgumentOutOfRangeException(nameof(maxBytes));
        _path = Path.GetFullPath(path);
        _maxBytes = maxBytes;
    }

    public void Append(string? message)
    {
        if (message is null) return;
        lock (_gate)
        {
            try
            {
                // Bound both the stored line and its encoding buffer. Timestamp and suffix
                // remain readable even when a receiver emits an unusually long line.
                int maxChars = (int)Math.Min(4096, (_maxBytes - 128) / 4);
                if (message.Length > maxChars) message = message[..maxChars] + " [truncated]";
                byte[] line = Encoding.UTF8.GetBytes(DateTimeOffset.Now.ToString("O") + " " + message + Environment.NewLine);
                if (File.Exists(_path) && new FileInfo(_path).Length + line.Length > _maxBytes)
                    File.Move(_path, _path + ".1", overwrite: true);
                using (var stream = new FileStream(_path, FileMode.Append, FileAccess.Write, FileShare.Read))
                {
                    if (stream.Length + line.Length > _maxBytes)
                        throw new IOException("Receiver log changed during append; line not written.");
                    stream.Write(line);
                }
                _error = null;
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException
                or ArgumentException or NotSupportedException or System.Security.SecurityException)
            {
                // DataReceived runs on a background callback: letting a file error escape
                // here could terminate the whole kernel while other phones are healthy.
                string detail = ex.Message.Length > 300 ? ex.Message[..300] : ex.Message;
                _error = "Receiver log unavailable: " + detail;
            }
        }
    }
}

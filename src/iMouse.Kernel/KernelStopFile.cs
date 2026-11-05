namespace IMouse2.Kernel;

/// <summary>
/// A graceful stop that does not depend on a console. A kernel launched detached from any session
/// (WMI, so it survives the Claude app restarting) may not receive Ctrl+C, so Stop-Multiphone.ps1
/// writes this kernel's process ID into the stop file; the kernel then runs exactly the Ctrl+C
/// shutdown (input released, every receiver stopped and confirmed). A file naming another process,
/// or garbage, is left alone and never stops this kernel.
/// </summary>
internal sealed class KernelStopFile
{
    private readonly string _path;
    private readonly int _pid;
    public KernelStopFile(string path, int pid) { _path = Path.GetFullPath(path); _pid = pid; }

    /// <summary>True (and the request consumed) only when the file names this process.</summary>
    internal bool Requested()
    {
        string text;
        try { text = File.ReadAllText(_path).Trim().TrimStart('\uFEFF'); }
        catch (Exception ex) when (ex is FileNotFoundException or DirectoryNotFoundException or IOException or UnauthorizedAccessException) { return false; }
        if (!int.TryParse(text, out int pid) || pid != _pid) return false;
        try { File.Delete(_path); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        return true;
    }

    public async Task WatchAsync(CancellationTokenSource stop, TimeSpan? interval = null)
    {
        // A request left from an earlier kernel names a dead PID and is ignored; remove it so it
        // cannot confuse the operator.
        try { if (File.Exists(_path) && !Requested()) File.Delete(_path); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        while (!stop.IsCancellationRequested)
        {
            try { await Task.Delay(interval ?? TimeSpan.FromMilliseconds(500), stop.Token); }
            catch (OperationCanceledException) { return; }
            if (Requested())
            {
                Console.WriteLine("Stop requested through " + _path + "; shutting down as on Ctrl+C.");
                stop.Cancel();
                return;
            }
        }
    }
}

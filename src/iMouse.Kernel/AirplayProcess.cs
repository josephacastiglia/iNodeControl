using System.Diagnostics;

namespace IMouse2.Kernel;

public sealed class AirplayProcess : IReceiverHandle
{
    private readonly ReceiverProcessLifetime _lifetime;
    private readonly ReceiverLog _log;
    public string? DiagnosticWarning => _log.Error;
    /// <summary>0 if the child has exited. Status used to keep advertising a dead PID.</summary>
    public int Id => _lifetime.Id;
    public Task WaitForExitAsync(CancellationToken ct) => _lifetime.WaitForExitAsync(ct);

    public static int LivePid(Process? process)
    {
        if (process is null) return 0;
        try { return process.HasExited ? 0 : process.Id; }
        catch (InvalidOperationException) { return 0; }
    }
    public AirplayProcess(string executable,string runtime,string name,string pipe,string clientId,string logPath,
        int port=7110,string mac="02:49:4D:32:C2:4C")
    {
        var start=new ProcessStartInfo(Path.GetFullPath(executable))
        {
            UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,
            WorkingDirectory=Path.GetDirectoryName(Path.GetFullPath(executable))!
        };
        var runtimeRoot=Path.GetFullPath(runtime);
        start.Environment["PATH"]=Path.Combine(runtimeRoot,"bin") + ";" + Environment.GetEnvironmentVariable("PATH");
        start.Environment["GST_PLUGIN_SYSTEM_PATH_1_0"]=Path.Combine(runtimeRoot,"lib","gstreamer-1.0");
        start.Environment["GST_PLUGIN_SCANNER_1_0"]=Path.Combine(runtimeRoot,"libexec","gstreamer-1.0","gst-plugin-scanner.exe");
        start.Environment["IMOUSE2_FRAME_PIPE"]="\\\\.\\pipe\\"+pipe;
        foreach(var argument in new[]{"-n",name,"-nh","-s","500x1080","-fps","30","-avdec",
            "-vs","appsink","-as","fakesink","-p",port.ToString()})
            start.ArgumentList.Add(argument);
        if(clientId is not ("*" or ""))
        {
            start.ArgumentList.Add("-restrict");
            start.ArgumentList.Add("-allow");
            start.ArgumentList.Add(clientId);
        }
        start.ArgumentList.Add("-m");
        start.ArgumentList.Add(mac);
        _log = new ReceiverLog(logPath);
        void Log(object sender,DataReceivedEventArgs e)
        {
            _log.Append(e.Data);
        }
        var process=new Process { StartInfo=start, EnableRaisingEvents=true };
        process.OutputDataReceived+=Log;process.ErrorDataReceived+=Log;
        _lifetime = new ReceiverProcessLifetime(new SystemReceiverProcess(process));
    }
    public void Dispose()
    {
        _lifetime.Dispose();
    }
}

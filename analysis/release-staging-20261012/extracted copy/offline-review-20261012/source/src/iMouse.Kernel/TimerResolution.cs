using System.Runtime.InteropServices;
namespace IMouse2.Kernel;
public sealed class TimerResolution : IDisposable
{
    private readonly bool _active = timeBeginPeriod(1)==0;
    public void Dispose() { if(_active) timeEndPeriod(1); }
    [DllImport("winmm.dll")] private static extern uint timeBeginPeriod(uint period);
    [DllImport("winmm.dll")] private static extern uint timeEndPeriod(uint period);
}

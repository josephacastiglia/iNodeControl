# Prints the integrity level (and elevation) of processes, read-only. UIPI silently drops input
# sent from a lower-integrity process to a higher-integrity window.
param([int[]]$ProcessIds = @($PID))
Add-Type -Namespace IL -Name U -MemberDefinition @'
[DllImport("advapi32.dll", SetLastError=true)] public static extern bool OpenProcessToken(IntPtr p, uint access, out IntPtr token);
[DllImport("advapi32.dll", SetLastError=true)] public static extern bool GetTokenInformation(IntPtr t, int cls, IntPtr info, int len, out int ret);
[DllImport("advapi32.dll")] public static extern IntPtr GetSidSubAuthority(IntPtr sid, uint i);
[DllImport("advapi32.dll")] public static extern IntPtr GetSidSubAuthorityCount(IntPtr sid);
[DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
[DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
'@
foreach ($id in $ProcessIds) {
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    if (-not $p) { "$id not running"; continue }
    $h = [IL.U]::OpenProcess(0x1000, $false, $id)   # PROCESS_QUERY_LIMITED_INFORMATION
    $t = [IntPtr]::Zero
    if ($h -eq [IntPtr]::Zero -or -not [IL.U]::OpenProcessToken($h, 0x8, [ref]$t)) { "$id $($p.ProcessName): token not readable (error $([Runtime.InteropServices.Marshal]::GetLastWin32Error()))"; continue }
    $len = 0; [void][IL.U]::GetTokenInformation($t, 25, [IntPtr]::Zero, 0, [ref]$len)
    $buf = [Runtime.InteropServices.Marshal]::AllocHGlobal($len)
    [void][IL.U]::GetTokenInformation($t, 25, $buf, $len, [ref]$len)
    $sid = [Runtime.InteropServices.Marshal]::ReadIntPtr($buf)
    $count = [Runtime.InteropServices.Marshal]::ReadByte([IL.U]::GetSidSubAuthorityCount($sid))
    $rid = [Runtime.InteropServices.Marshal]::ReadInt32([IL.U]::GetSidSubAuthority($sid, [uint32]($count - 1)))
    $level = switch ($rid) { 0x1000 { 'Low' } 0x2000 { 'Medium' } 0x2100 { 'Medium+' } 0x3000 { 'High (elevated)' } 0x4000 { 'System' } default { '0x{0:X}' -f $rid } }
    '{0,6} {1,-22} integrity={2}' -f $id, $p.ProcessName, $level
    [Runtime.InteropServices.Marshal]::FreeHGlobal($buf); [void][IL.U]::CloseHandle($t); [void][IL.U]::CloseHandle($h)
}

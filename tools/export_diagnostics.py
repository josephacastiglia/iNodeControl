"""One read-only diagnostic export. Does not acquire leases or restart anything."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import urllib.request
import winreg
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOAK_STATUS = ROOT / "analysis" / "gate10-endurance-20260916" / "status.json"
BINARIES = ("iMouse2.Kernel.dll", "iMouse2.exe", "uxplay.exe")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


class RTL_OSVERSIONINFOW(ctypes.Structure):
    _fields_ = [
        ("dwOSVersionInfoSize", wintypes.DWORD),
        ("dwMajorVersion", wintypes.DWORD),
        ("dwMinorVersion", wintypes.DWORD),
        ("dwBuildNumber", wintypes.DWORD),
        ("dwPlatformId", wintypes.DWORD),
        ("szCSDVersion", wintypes.WCHAR * 128),
    ]


kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
kernel32.GlobalMemoryStatusEx.restype = wintypes.BOOL
ntdll.RtlGetVersion.argtypes = [ctypes.POINTER(RTL_OSVERSIONINFOW)]
ntdll.RtlGetVersion.restype = ctypes.c_long


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def api_base(url: str) -> str:
    url = url.rstrip("/")
    return url if url.endswith("/api") else url + "/api"


def get_json(url: str, timeout: float = 8) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def window_titles() -> dict[int, str]:
    found: dict[int, str] = {}

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        if buf.value and pid.value not in found:
            found[pid.value] = buf.value
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def memory() -> dict:
    stat = MEMORYSTATUSEX(dwLength=ctypes.sizeof(MEMORYSTATUSEX))
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        raise OSError("GlobalMemoryStatusEx failed")
    return {
        "load_percent": int(stat.dwMemoryLoad),
        "total_bytes": int(stat.ullTotalPhys),
        "available_bytes": int(stat.ullAvailPhys),
        "used_bytes": int(stat.ullTotalPhys - stat.ullAvailPhys),
    }


def windows_version() -> dict:
    info = RTL_OSVERSIONINFOW(dwOSVersionInfoSize=ctypes.sizeof(RTL_OSVERSIONINFOW))
    if ntdll.RtlGetVersion(ctypes.byref(info)) != 0:
        raise OSError("RtlGetVersion failed")
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
        product, _ = winreg.QueryValueEx(key, "ProductName")
        display, _ = winreg.QueryValueEx(key, "DisplayVersion")
        ubr, _ = winreg.QueryValueEx(key, "UBR")
    build = int(info.dwBuildNumber)
    name = "Windows 11" if build >= 22000 else "Windows 10"
    edition = str(product).replace("Windows 10", "").replace("Windows 11", "").strip() or "Desktop"
    return {
        "name": f"{name} {edition}",
        "version": f"{info.dwMajorVersion}.{info.dwMinorVersion}.{build}.{ubr}",
        "display_version": display,
        "platform": platform.platform(),
    }


def processes() -> list[dict]:
    script = r"""
$ErrorActionPreference = 'Stop'
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -in @('iMouse2.exe','iMouse2.Kernel.exe','uxplay.exe') } |
  ForEach-Object {
    [pscustomobject]@{
      pid = $_.ProcessId
      parent = $_.ParentProcessId
      name = $_.Name
      path = $_.ExecutablePath
      command = $_.CommandLine
      started = if ($_.CreationDate) { $_.CreationDate.ToUniversalTime().ToString('o') } else { $null }
    }
  } | ConvertTo-Json -Compress
"""
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, timeout=40, check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or "process query failed")
    parsed = json.loads(done.stdout)
    return parsed if isinstance(parsed, list) else [parsed]


def mirror_state(pid: int) -> dict:
    script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$p = Get-Process -Id {int(pid)} -ErrorAction Stop
$root = [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
function Toggle([string]$name) {{
  $cond = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::NameProperty, $name)
  $el = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
  if ($null -eq $el) {{ return $null }}
  $pat = $el.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
  return [int]$pat.Current.ToggleState -eq 1
}}
@{{ mirror_to_all = Toggle 'Mirror the master''s actions to every phone' }} | ConvertTo-Json -Compress
"""
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, timeout=25, check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or "mirror state unreadable")
    return json.loads(done.stdout)


def arg_value(command: str, flag: str) -> str | None:
    match = re.search(rf'(?:^|\s){re.escape(flag)}\s+"([^"]+)"|(?:^|\s){re.escape(flag)}\s+(\S+)', command or "")
    if not match:
        return None
    return match.group(1) or match.group(2)


def pacing_ms(command: str, log_text: str) -> int:
    logged = re.search(r"high-resolution (\d+) ms", log_text)
    if logged:
        return int(logged.group(1))
    if "legacy Task.Delay" in log_text or "--legacy" in (command or ""):
        return 0
    flagged = re.search(r"--precise-delay\s+(\d+)", command or "")
    return int(flagged.group(1)) if flagged else 7


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def uptime_s(started: str | None) -> float | None:
    if not started:
        return None
    then = datetime.fromisoformat(started)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - then).total_seconds(), 1)


def collect(url: str) -> dict:
    errors: list[str] = []
    base = api_base(url)
    exported_at = utc_now()
    kernel_status = get_json(base + "/kernel/status")["data"]
    devices = get_json(base + "/device/get")["data"]["list"]
    boards_usb = {row["pid"].upper(): row for row in get_json(base + "/config/usb/get")["data"]["list"]}
    try:
        input_status = get_json(base + "/input/status")["data"]
    except Exception as exc:
        input_status = {}
        errors.append(f"input status: {exc}")

    procs = processes()
    titles = window_titles()
    kernels = [p for p in procs if p["name"].lower() == "imouse2.kernel.exe" and base.split("/api")[0] in (p.get("command") or "")]
    if len(kernels) != 1:
        kernels = [p for p in procs if p["name"].lower() == "imouse2.kernel.exe"]
    if len(kernels) != 1:
        raise RuntimeError(f"expected one kernel process, found {len(kernels)}")
    kernel = kernels[0]
    command = kernel.get("command") or ""
    data_dir = Path(arg_value(command, "--data-dir") or "")
    log_text = ""
    log_path = data_dir / "kernel-stdout.log"
    if log_path.is_file():
        log_text = "".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[:12])
    else:
        errors.append(f"kernel log missing: {log_path}")
    stderr_path = data_dir / "kernel-stderr.log"
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace").strip() if stderr_path.is_file() else ""
    if stderr:
        errors.append("kernel stderr: " + stderr[:500])

    consoles = [p for p in procs if p["name"].lower() == "imouse2.exe"]
    titled = [p for p in consoles if titles.get(p["pid"])]
    console = titled[0] if len(titled) == 1 else next((p for p in consoles if titles.get(p["pid"], "").startswith("iMouse")), consoles[0] if consoles else None)
    if console is None:
        errors.append("console process not found")
        console = {}
    mirror = {"mirror_to_all": None, "batch_mode": None}
    if console.get("pid"):
        try:
            mirror = mirror_state(console["pid"])
        except Exception as exc:
            errors.append(f"mirror-to-all: {exc}")
    settings_path = Path(console["path"]).parent / "data" / "settings.json" if console.get("path") else None
    settings = {}
    if settings_path and settings_path.is_file():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    elif console.get("path"):
        errors.append(f"console settings missing: {settings_path}")

    receivers_file = Path(arg_value(command, "--receivers") or "")
    configured = json.loads(receivers_file.read_text(encoding="utf-8")) if receivers_file.is_file() else []
    if not configured:
        errors.append(f"receiver map missing: {receivers_file}")
    by_device = {row.get("DeviceId"): row for row in configured}
    ux_by_pid = {p["pid"]: p for p in procs if p["name"].lower() == "uxplay.exe"}
    receivers = []
    for row in kernel_status.get("receivers") or []:
        cfg = by_device.get(row.get("deviceid"), {})
        ux = ux_by_pid.get(row.get("receiver_pid"), {})
        port_match = re.search(r"(?:^|\s)-p\s+(\d+)", ux.get("command") or "")
        port = cfg.get("Port")
        if port_match and port and int(port_match.group(1)) != int(port):
            errors.append(f"{row.get('name')} port {port} != process -p {port_match.group(1)}")
        if port_match and port is None:
            port = int(port_match.group(1))
        state = row.get("receiver_state")
        if state != "mirroring":
            errors.append(f"{row.get('name')} state {state}")
        receivers.append({
            "name": row.get("name"),
            "pid": row.get("receiver_pid"),
            "port": port,
            "device_id": row.get("deviceid"),
            "state": state,
            "frames": row.get("frames"),
            "restarts": row.get("receiver_restarts"),
        })

    calibration_path = data_dir / "pointer-calibration.json"
    calibrations = json.loads(calibration_path.read_text(encoding="utf-8")) if calibration_path.is_file() else []
    by_pid = {str(row.get("Pid", "")).upper(): row for row in calibrations}
    boards = []
    for device in devices:
        pid = str(device.get("pid") or "").upper()
        cal = by_pid.get(pid)
        if not cal:
            errors.append(f"no calibration for {pid}")
            calibration = None
        else:
            calibration = {
                "width": cal.get("Width"),
                "height": cal.get("Height"),
                "origin": {"x": cal.get("OriginX"), "y": cal.get("OriginY")},
                "scale": {"x": cal.get("PixelsPerUnitX"), "y": cal.get("PixelsPerUnitY")},
            }
        boards.append({
            "pid": device.get("pid"),
            "uid": device.get("uid"),
            "device_id": device.get("deviceid"),
            "name": device.get("name"),
            "usb_state": (boards_usb.get(pid) or {}).get("state"),
            "calibration": calibration,
        })

    binary_paths = {
        "iMouse2.Kernel.dll": Path(kernel["path"]).with_name("iMouse2.Kernel.dll"),
        "iMouse2.exe": Path(console["path"]) if console.get("path") else None,
        "uxplay.exe": Path(arg_value(command, "--receiver") or (next(iter(ux_by_pid.values()), {}).get("path") or "")),
    }
    binaries = []
    for name in BINARIES:
        path = binary_paths.get(name)
        if not path or not path.is_file():
            errors.append(f"missing binary {name}: {path}")
            binaries.append({"name": name, "path": str(path) if path else None, "sha256": None})
            continue
        stat = path.stat()
        binaries.append({
            "name": name,
            "path": str(path),
            "sha256": sha256(path),
            "bytes": stat.st_size,
            "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        })

    for phone in input_status.get("phones") or []:
        if phone.get("stopped") or phone.get("release_failed"):
            errors.append(f"input {phone.get('id')}: {phone.get('message')}")

    soak = None
    if SOAK_STATUS.is_file():
        raw = json.loads(SOAK_STATUS.read_text(encoding="utf-8"))
        memory_roll = raw.get("memory_10m") or {}
        soak = {
            "source": str(SOAK_STATUS.relative_to(ROOT)).replace("\\", "/"),
            "running": raw.get("running"),
            "pid": raw.get("pid"),
            "at": raw.get("at"),
            "started_at": raw.get("started_at"),
            "elapsed_s": raw.get("elapsed_s"),
            "samples": raw.get("samples"),
            "interactions": raw.get("interactions"),
            "error": raw.get("error"),
            "memory": {
                "window_s": (raw.get("schedule") or {}).get("memory_window_s"),
                "rolling": {k: v for k, v in memory_roll.items() if k != "by_pid"},
                "by_pid": memory_roll.get("by_pid"),
            },
            "last_interaction": raw.get("last_interaction"),
            "phone_frames": [
                {"name": p.get("name"), "frames": p.get("frames"), "frame_delta": p.get("frame_delta"), "restarts": p.get("receiver_restarts")}
                for p in raw.get("phones") or []
            ],
        }
        for phone in raw.get("phones") or []:
            if phone.get("live") and phone.get("frame_delta") == 0:
                errors.append(f"{phone.get('name')} frames stalled at {phone.get('frames')}")
        if raw.get("error"):
            errors.append(f"gate10: {raw['error']}")
    else:
        errors.append(f"gate10 status missing: {SOAK_STATUS}")

    pace = pacing_ms(command, log_text)
    return {
        "exported_at": exported_at,
        "timestamps": {
            "exported_at": exported_at,
            "kernel_started_at": kernel.get("started"),
            "soak_at": None if soak is None else soak.get("at"),
        },
        "kernel": {
            "endpoint": base,
            "pid": kernel["pid"],
            "uptime_s": uptime_s(kernel.get("started")),
            "started_at": kernel.get("started"),
            "pacing_ms": pace,
            "pacing": f"high-resolution {pace} ms" if pace else "legacy Task.Delay",
            "allowed": kernel_status.get("allowed"),
            "input": kernel_status.get("input"),
            "input_protocol": kernel_status.get("input_protocol"),
            "input_leases_required": kernel_status.get("input_leases_required"),
            "executable": kernel.get("path"),
            "command": command,
        },
        "console": {
            "pid": console.get("pid"),
            "window_title": titles.get(console.get("pid")),
            "address": settings.get("address"),
            "theme": settings.get("theme"),
            "mirror_to_all": mirror.get("mirror_to_all"),
            "executable": console.get("path"),
            "other_pids": [p["pid"] for p in consoles if p["pid"] != console.get("pid")],
        },
        "receivers": receivers,
        "boards": boards,
        "binaries": binaries,
        "system": {
            "windows": windows_version(),
            "logical_cpus": os.cpu_count(),
            "memory": memory(),
        },
        "settings": {
            "address": settings.get("address"),
            "theme": settings.get("theme"),
            "data_dir": str(data_dir),
            "receivers_file": str(receivers_file),
            "allowed": kernel_status.get("allowed"),
            "mirror_to_all": mirror.get("mirror_to_all"),
        },
        "gate10": soak,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write one self-contained fleet diagnostic JSON file.")
    parser.add_argument("--url", default="http://127.0.0.1:9913/api")
    parser.add_argument("--out", default=str(ROOT / "analysis" / "diagnostics"))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = collect(args.url)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out / f"diagnostics-{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"export failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

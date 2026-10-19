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
import urllib.parse
import uuid
import winreg
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOAK_STATUS = ROOT / "analysis" / "gate10-endurance-20260916" / "status.json"
BINARIES = ("iMouse2.Kernel.dll", "iMouse2.dll", "iMouse2.exe", "uxplay.exe")

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
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("expected an HTTP(S) service address")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("service address must not contain credentials, query or fragment")
    _ = parsed.port  # Validate the port before collecting anything.
    path = parsed.path.rstrip("/")
    if not path.endswith("/api"):
        path += "/api"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


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
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
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
        capture_output=True, text=True, encoding="utf-8", timeout=40, check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or "process query failed")
    parsed = json.loads(done.stdout) if done.stdout.strip() else []
    if parsed is None:
        return []
    rows = parsed if isinstance(parsed, list) else [parsed]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid process-query response")
    return rows


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


def command_args(command: str) -> list[str]:
    """Parse a recorded Windows command line without running it."""
    if not command:
        return []
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    count = ctypes.c_int()
    values = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not values:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [values[i] for i in range(count.value)]
    finally:
        kernel32.LocalFree(ctypes.cast(values, ctypes.c_void_p))


def arg_value(command: str, flag: str) -> str | None:
    args = command_args(command)
    for i, arg in enumerate(args):
        if arg.startswith(flag + "="):
            return arg[len(flag) + 1:]
        if arg == flag:
            return args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else None
    return None


def pacing_ms(command: str, log_text: str) -> int | None:
    logged = re.search(r"high-resolution (\d+) ms", log_text)
    if logged:
        return int(logged.group(1))
    if "legacy Task.Delay" in log_text or "--legacy" in command_args(command):
        return 0
    flagged = arg_value(command, "--precise-delay")
    return int(flagged) if flagged and flagged.isdigit() else None


def capture(errors: list[str], label: str, action, fallback):
    try:
        return action()
    except Exception as exc:
        errors.append(f"{label}: {type(exc).__name__}: {exc}")
        return fallback


def object_rows(value) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("expected a list of objects")
    return value


def read_file(path: Path | None, expected, errors: list[str], label: str):
    def read():
        if path is None:
            raise ValueError("effective path is unknown")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if expected is list:
            return object_rows(data)
        if not isinstance(data, dict):
            raise ValueError("expected an object")
        return data
    return capture(errors, label, read, [] if expected is list else {})


def console_settings_path(console: dict) -> Path | None:
    command = console.get("command") or ""
    explicit = arg_value(command, "--data-dir")
    flags = command_args(command)
    if explicit is None or explicit == "":
        if any(flag == "--data-dir" or flag.startswith("--data-dir=") for flag in flags):
            return None
    if explicit:
        folder = Path(explicit)
        return folder / "settings.json" if folder.is_absolute() else None
    if any(flag in flags for flag in ("--self-test", "--ui-test", "--smoke-test", "--wall-test", "--mirror-test", "--fps-test")):
        return None  # Test modes choose temporary folders; do not read operator settings.
    appdata = os.environ.get("APPDATA")
    return Path(appdata) / "iMouse2/settings.json" if appdata else None


SECRET_KEYS = {"token", "tokens", "password", "passwd", "secret", "apikey", "authorization",
               "cookie", "cookies", "credential", "credentials", "accesstoken", "refreshtoken",
               "serial", "serialnumber"}


def safe_report(value):
    """Remove known credential fields/patterns; reports still contain rack identities and paths."""
    if isinstance(value, dict):
        return {key: "[redacted]" if re.sub(r"[-_]", "", key.lower()) in SECRET_KEYS else safe_report(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [safe_report(item) for item in value]
    if not isinstance(value, str):
        return value
    names = r"token|password|passwd|secret|api[-_]?key|access[-_]?token|refresh[-_]?token"
    literal = r'''(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}]+)'''
    value = re.sub(rf"(?i)(--(?:{names})(?:=|\s+)){literal}", r"\1[redacted]", value)
    value = re.sub(rf'''(?i)(["']?\b(?:{names})\b["']?\s*[:=]\s*){literal}''', r"\1[redacted]", value)
    value = re.sub(r"(?i)(\bBearer\s+)\S+", r"\1[redacted]", value)
    value = re.sub(r"(?i)(https?://)[^/\s@]+@", r"\1[redacted]@", value)
    return value


def write_report(report: dict, out: Path) -> Path:
    # Serialize before creating a file: malformed data must not leave a truncated export.
    serialized = json.dumps(safe_report(report), indent=2, allow_nan=False)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
    path = out / f"diagnostics-{stamp}-{uuid.uuid4().hex[:8]}.json"
    with path.open("x", encoding="utf-8") as handle:
        try:
            handle.write(serialized)
        except BaseException:
            handle.close()
            path.unlink(missing_ok=True)  # This newly created export only.
            raise
    return path


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


def collect(url: str, *, console_pid: int | None = None, include_ui: bool = False) -> dict:
    errors: list[str] = []
    base = api_base(url)
    exported_at = utc_now()

    def read_api(route, rows=False):
        def read():
            reply = get_json(base + route)
            if not isinstance(reply, dict) or reply.get("code") not in (None, 0):
                raise ValueError("unsuccessful or malformed service response")
            data = reply.get("data")
            if not isinstance(data, dict) or data.get("code") not in (None, 0):
                raise ValueError("unsuccessful or malformed service data")
            return object_rows(data.get("list")) if rows else data
        return capture(errors, route, read, [] if rows else {})

    kernel_status = read_api("/kernel/status")
    devices = read_api("/device/get", rows=True)
    usb = read_api("/config/usb/get", rows=True)
    input_status = read_api("/input/status")
    boards_usb = {str(row.get("pid", "")).upper(): row for row in usb}
    procs = capture(errors, "processes", lambda: object_rows(processes()), [])
    titles = capture(errors, "window titles", window_titles, {}) if include_ui else {}

    def matches_endpoint(proc):
        for arg in command_args(proc.get("command") or ""):
            if arg.startswith(("http://", "https://")):
                try:
                    if api_base(arg) == base:
                        return True
                except ValueError:
                    pass
        return False

    kernels = [p for p in procs if str(p.get("name", "")).lower() == "imouse2.kernel.exe" and matches_endpoint(p)]
    kernel = kernels[0] if len(kernels) == 1 else {}
    if not kernel:
        errors.append(f"kernel identity: expected one process for {base}, found {len(kernels)}; not guessing")
    command = kernel.get("command") or ""
    folder_arg = arg_value(command, "--data-dir")
    data_dir = Path(folder_arg) if folder_arg and Path(folder_arg).is_absolute() else None
    if data_dir is None:
        errors.append("kernel data directory unknown")

    def log_prefix(name, count, characters=None):
        if data_dir is None:
            return ""
        def read():
            with (data_dir / name).open(encoding="utf-8", errors="replace") as handle:
                if characters is not None:
                    return handle.read(characters)
                return "".join(handle.readline() for _ in range(count))
        return capture(errors, name, read, "")

    log_text = log_prefix("kernel-stdout.log", 12)
    stderr = log_prefix("kernel-stderr.log", 0, characters=500).strip() if data_dir and (data_dir / "kernel-stderr.log").is_file() else ""
    if stderr:
        errors.append("kernel stderr: " + stderr)

    consoles = [p for p in procs if str(p.get("name", "")).lower() == "imouse2.exe"]
    candidates = [p for p in consoles if p.get("pid") == console_pid] if console_pid is not None else consoles
    console = candidates[0] if len(candidates) == 1 else {}
    if not console:
        errors.append(f"console identity: expected one console, found {len(candidates)}; specify --console-pid rather than guessing")
    mirror = {"mirror_to_all": None}
    if include_ui and console.get("pid"):
        mirror = capture(errors, "mirror-to-all", lambda: mirror_state(console["pid"]), mirror)
    settings_path = console_settings_path(console) if console else None
    settings = read_file(settings_path, dict, errors, "console settings")

    receiver_arg = arg_value(command, "--receivers")
    receivers_file = Path(receiver_arg) if receiver_arg and Path(receiver_arg).is_absolute() else None
    configured = read_file(receivers_file, list, errors, "receiver map")
    by_device = {str(row.get("DeviceId", "")).casefold(): row for row in configured}
    ux_by_pid = {p.get("pid"): p for p in procs if str(p.get("name", "")).lower() == "uxplay.exe"}
    receiver_rows = capture(errors, "receiver status", lambda: object_rows(kernel_status.get("receivers", [])), [])
    receivers = []
    for row in receiver_rows:
        cfg = by_device.get(str(row.get("deviceid", "")).casefold(), {})
        ux = ux_by_pid.get(row.get("receiver_pid"), {})
        process_port = arg_value(ux.get("command") or "", "-p")
        port = cfg.get("Port")
        if process_port:
            actual_port = capture(errors, "receiver port", lambda: int(process_port), None)
            if port is not None and actual_port is not None and str(actual_port) != str(port):
                errors.append(f"{row.get('name')} port {port} != process -p {actual_port}")
            if port is None:
                port = actual_port
        if row.get("receiver_state") != "mirroring":
            errors.append(f"{row.get('name')} state {row.get('receiver_state')}")
        if not ux:
            errors.append(f"{row.get('name')} receiver process not found")
        elif kernel and ux.get("parent") != kernel.get("pid"):
            errors.append(f"{row.get('name')} receiver parent does not match this kernel")
        receivers.append({
            "name": row.get("name"), "pid": row.get("receiver_pid"), "port": port,
            "device_id": row.get("deviceid"), "state": row.get("receiver_state"),
            "live": row.get("live"), "frames": row.get("frames"), "restarts": row.get("receiver_restarts"),
        })

    calibrations = read_file(data_dir / "pointer-calibration.json" if data_dir else None, list, errors, "calibration")
    by_pid = {str(row.get("Pid", "")).upper(): row for row in calibrations}
    boards = []
    for device in devices:
        pid = str(device.get("pid") or "").upper()
        cal = by_pid.get(pid)
        if not cal:
            errors.append(f"no calibration for {pid}")
        boards.append({
            "pid": device.get("pid"), "uid": device.get("uid"),
            "device_id": device.get("deviceid"), "name": device.get("name"),
            "usb_state": (boards_usb.get(pid) or {}).get("state"),
            "calibration": None if not cal else {
                "width": cal.get("Width"), "height": cal.get("Height"),
                "origin": {"x": cal.get("OriginX"), "y": cal.get("OriginY")},
                "scale": {"x": cal.get("PixelsPerUnitX"), "y": cal.get("PixelsPerUnitY")},
            },
        })

    kernel_path = Path(kernel["path"]) if kernel.get("path") else None
    console_path = Path(console["path"]) if console.get("path") else None
    receiver_path = arg_value(command, "--receiver")
    binary_paths = {
        "iMouse2.Kernel.dll": kernel_path.with_name("iMouse2.Kernel.dll") if kernel_path else None,
        "iMouse2.dll": console_path.with_name("iMouse2.dll") if console_path else None,
        "iMouse2.exe": console_path,
        "uxplay.exe": Path(receiver_path) if receiver_path else None,
    }
    binaries = []
    for name in BINARIES:
        path = binary_paths.get(name)
        def record_binary():
            if path is None or not path.is_absolute():
                raise ValueError("verified binary path unavailable")
            stat = path.stat()
            return {"name": name, "path": str(path), "sha256": sha256(path), "bytes": stat.st_size,
                    "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")}
        binaries.append(capture(errors, f"binary {name}", record_binary,
                                {"name": name, "path": str(path) if path else None, "sha256": None}))

    phones = capture(errors, "input phones", lambda: object_rows(input_status.get("phones", [])), [])
    for phone in phones:
        if phone.get("stopped") or phone.get("release_failed"):
            errors.append(f"input {phone.get('id')}: {phone.get('message')}")

    soak = None
    if SOAK_STATUS.is_file():
        raw = read_file(SOAK_STATUS, dict, errors, "gate10 snapshot")
        memory_roll = raw.get("memory_10m") if isinstance(raw.get("memory_10m"), dict) else {}
        soak = {
            "source": str(SOAK_STATUS), "source_kind": "saved telemetry; not live-verified",
            "running": raw.get("running"), "pid": raw.get("pid"), "at": raw.get("at"),
            "started_at": raw.get("started_at"), "elapsed_s": raw.get("elapsed_s"),
            "samples": raw.get("samples"), "interactions": raw.get("interactions"),
            "error": raw.get("error"), "memory": memory_roll,
            "last_interaction": raw.get("last_interaction"),
        }
    else:
        errors.append(f"gate10 snapshot missing: {SOAK_STATUS}")

    pace = pacing_ms(command, log_text)
    windows = capture(errors, "Windows version", windows_version, None)
    mem = capture(errors, "system memory", memory, None)
    uptime = capture(errors, "kernel uptime", lambda: uptime_s(kernel.get("started")), None)
    return {
        "schema_version": 2, "collection_status": "partial" if errors else "complete",
        "exported_at": exported_at, "ui_state_collected": include_ui,
        "timestamps": {"exported_at": exported_at, "kernel_started_at": kernel.get("started"),
                       "soak_at": None if soak is None else soak.get("at")},
        "kernel": {
            "endpoint": base, "pid": kernel.get("pid"), "uptime_s": uptime,
            "started_at": kernel.get("started"), "pacing_ms": pace,
            "pacing": "unknown" if pace is None else (f"high-resolution {pace} ms" if pace else "legacy Task.Delay"),
            "allowed": kernel_status.get("allowed"), "input": kernel_status.get("input"),
            "input_protocol": kernel_status.get("input_protocol"),
            "input_leases_required": kernel_status.get("input_leases_required"),
            "executable": kernel.get("path"), "command": command,
        },
        "console": {
            "pid": console.get("pid"), "window_title": titles.get(console.get("pid")),
            "address": settings.get("address"), "theme": settings.get("theme"),
            "address_source": "persisted settings; active connection not verified",
            "address_argument": arg_value(console.get("command") or "", "--address"),
            "settings_path": str(settings_path) if settings_path else None,
            "mirror_to_all": mirror.get("mirror_to_all"), "executable": console.get("path"),
            "other_pids": [p.get("pid") for p in consoles if p.get("pid") != console.get("pid")],
        },
        "receivers": receivers, "boards": boards, "binaries": binaries,
        "system": {"windows": windows, "logical_cpus": os.cpu_count(), "memory": mem},
        "settings": {
            "address": settings.get("address"), "theme": settings.get("theme"),
            "data_dir": str(data_dir) if data_dir else None,
            "console_data_dir": str(settings_path.parent) if settings_path else None,
            "receivers_file": str(receivers_file) if receivers_file else None,
            "allowed": kernel_status.get("allowed"), "mirror_to_all": mirror.get("mirror_to_all"),
        },
        "gate10": soak, "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write one self-contained fleet diagnostic JSON file.")
    parser.add_argument("--url", default="http://127.0.0.1:9913/api")
    parser.add_argument("--out", default=str(ROOT / "analysis" / "diagnostics"))
    parser.add_argument("--console-pid", type=int, help="identify the console explicitly when several are running")
    parser.add_argument("--include-ui-state", action="store_true", help="opt in to read-only window/mirror state collection")
    args = parser.parse_args(argv)
    out = Path(args.out)
    report = collect(args.url, console_pid=args.console_pid, include_ui=args.include_ui_state)
    path = write_report(report, out)
    print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"export failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

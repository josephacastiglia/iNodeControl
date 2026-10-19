"""Gate 6 preparation, not release acceptance. Does not restart the kernel.

Measures API request or UIA invocation to kernel screenshot arrival. This does
not measure physical clicks or the console's display path. Polls retain first
change and first heuristically correct frame separately. Misses are not retried.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
import hashlib
import json
import os
import queue
import re
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from windows_command_line import command_args

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
C24C = "86:1D:4A:04:2F:F6"
C241 = "FE:A9:BC:D7:A0:44"
PROTECTED = ("rows.json", "preflight-frames.json", "end-status.json")
MISS_MS = 5000.0
CANDIDATE_MARK = "imouse-candidate-5\\imouse2.exe"
INSTALLED_MARKS = (
    "\\release\\imouse2\\imouse2.exe",
    "\\release\\imouse2-two-phone-candidate\\imouse2.exe",
    "\\imousexp\\",
)
HELD = {}
ALLOW_C241 = False
RUN = None
CONSOLE = {"pid": None, "phone": "C24C"}
UIA_OWNS = {"on": False}
UIA_HELPER_TIMEOUT = 20.0
UIA_HELPER_CLEANUP_TIMEOUT = 2.0
UIA_HELPER_MAX_OUTPUT = 65536


def phone_plan(allow_c241=False):
    rows = [("C24C", C24C, "C241", C241)]
    if allow_c241:
        rows.append(("C241", C241, "C24C", C24C))
    return rows


def assert_target(pid):
    for part in str(pid or "").split(","):
        if part == C241 and not ALLOW_C241:
            raise SystemExit("refusing live command to C241; pass --allow-c241")


def norm_path(path):
    return str(path).replace("/", "\\").lower()


def accept_console(exe, console_path=None):
    norm = norm_path(exe)
    if any(mark in norm for mark in INSTALLED_MARKS):
        raise SystemExit(f"refusing installed console: {exe}")
    if not norm.endswith("\\imouse2.exe"):
        raise SystemExit(f"not iMouse2.exe: {exe}")
    if console_path:
        if norm != norm_path(console_path):
            raise SystemExit("console path does not match the explicitly selected candidate")
        return exe
    if CANDIDATE_MARK in norm:
        return exe
    raise SystemExit(f"pid is not a candidate console: {exe}")


def check_console(api_only, console_pid, exe=None, console_path=None):
    if api_only:
        return None
    if not console_pid:
        raise SystemExit("UIA mode requires --console-pid")
    return accept_console(exe, console_path)
def bind_console(console_pid, console_path=None, read_identity=None):
    if not console_pid:
        raise SystemExit("UIA mode requires --console-pid")
    read_identity = process_identity if read_identity is None else read_identity
    identity = read_identity(console_pid)
    exe = identity["exe"]
    check_console(False, console_pid, exe, console_path)
    if type(identity.get("started")) is not int or identity["started"] <= 0:
        raise SystemExit("console process start time is not verified")
    CONSOLE.update(pid=int(console_pid), exe=exe, started=identity["started"])
    return exe




def process_identity(pid):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        raise SystemExit(f"cannot open console pid {pid}")
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            raise SystemExit(f"cannot read path for pid {pid}")
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise SystemExit(f"cannot read start time for pid {pid}")
        created = times[0]
        return {"exe": buf.value, "started": (created.dwHighDateTime << 32) | created.dwLowDateTime}
    finally:
        kernel.CloseHandle(handle)


def read_console_command(pid):
    """Read one process command line, never enumerate windows or start an app."""
    script = ("$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
              f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}';"
              "if($null -eq $p -or -not $p.CommandLine){throw 'command line unavailable'};"
              "$p.CommandLine | ConvertTo-Json -Compress")
    done = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                          capture_output=True, text=True, encoding="utf-8", timeout=10)
    if done.returncode:
        raise ValueError("candidate command line could not be verified")
    command = json.loads(done.stdout)
    if not isinstance(command, str) or not command:
        raise ValueError("candidate command line unavailable")
    return command_args(command)


def endpoint(url):
    """Explicit origin only; never allow an implicit/vendor-service port."""
    if not isinstance(url, str) or any(ord(c) < 32 for c in url) or url.strip() != url:
        raise ValueError("explicit service URL required")
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.port in (None, 9911)
            or not 1 <= parsed.port <= 65535 or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/", "/api", "/api/") or parsed.query or parsed.fragment):
        raise ValueError("service URL needs an explicit non-vendor port and no credentials or extra path")
    host = parsed.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    return f"{parsed.scheme}://{host}:{parsed.port}"


def candidate_args(args):
    values = {}
    for i in range(1, len(args)):
        arg = args[i]
        if i > 1 and args[i - 1] == "--data-dir":
            continue
        if arg == "--data-dir":
            value = args[i + 1] if i + 1 < len(args) else ""
            key = arg
        elif arg.startswith("--data-dir=") or arg.startswith("--address="):
            key, value = arg.split("=", 1)
        else:
            raise ValueError("candidate must use normal startup with only data-dir/address options")
        if not value.strip() or value.startswith("--") or key in values:
            raise ValueError("empty or duplicate candidate startup option")
        values[key] = value
    return values


def validate_candidate_profile(exe, args, data_dir, expected_hash, appdata=None):
    if not data_dir or not expected_hash or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
        raise ValueError("UIA requires --console-data-dir and the exact --console-sha256")
    if not args or norm_path(args[0]) != norm_path(exe):
        raise ValueError("command line executable does not match candidate process")
    values = candidate_args(args)
    actual = values.get("--data-dir", "")
    if not Path(actual).is_absolute() or not Path(data_dir).is_absolute():
        raise ValueError("candidate data directory must be explicitly absolute")
    folder = Path(actual).resolve(strict=True)
    expected = Path(data_dir).resolve(strict=True)
    shared_root = appdata if appdata is not None else os.environ.get("APPDATA")
    if not shared_root:
        raise ValueError("operator settings location cannot be verified")
    shared = (Path(shared_root) / "iMouse2").resolve()
    adjacent = (Path(exe).parent / "data").resolve()
    if (folder != expected or not folder.is_dir() or folder == Path(folder.anchor)
            or folder == shared or shared in folder.parents or folder in shared.parents
            or folder == adjacent or adjacent in folder.parents):
        raise ValueError("candidate must use its own dedicated data directory")
    settings = folder / "settings.json"
    if settings.resolve(strict=True).parent != folder:
        raise ValueError("candidate settings must remain inside the isolated directory")
    with settings.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("candidate settings exceeds 64 KiB")
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("trackPointer") is not False:
        raise ValueError("candidate settings must explicitly disable hover tracking")
    service = endpoint(BASE)
    if endpoint(document.get("address")) != service or (
            "--address" in values and endpoint(values["--address"]) != service):
        raise ValueError("candidate and runner service addresses do not match")
    assembly = Path(exe).with_suffix(".dll")
    digest = hashlib.sha256(assembly.read_bytes()).hexdigest()
    if digest != expected_hash.lower():
        raise ValueError("candidate managed binary hash does not match")
    return {"data_directory": str(folder), "settings_sha256": hashlib.sha256(raw).hexdigest(),
            "assembly": str(assembly), "assembly_sha256": digest, "address": service,
            "saved_track_pointer": False, "active_connection_verified": False}


def prepare_console(pid, path, data_dir, expected_hash):
    if not path:
        raise ValueError("UIA requires the exact --console-path")
    exe = bind_console(pid, path)
    args = read_console_command(pid)
    current = process_identity(pid)
    if current != {key: CONSOLE[key] for key in ("exe", "started")}:
        raise ValueError("candidate process changed while verifying command line")
    profile = validate_candidate_profile(exe, args, data_dir, expected_hash)
    CONSOLE["profile"] = profile
    CONSOLE["args"] = args
    return profile


def verify_bound_profile():
    profile = CONSOLE.get("profile")
    if profile is None:
        raise ValueError("candidate isolation has not been verified")
    actual = validate_candidate_profile(CONSOLE["exe"], CONSOLE["args"],
                                        profile["data_directory"], profile["assembly_sha256"])
    if actual != profile:
        raise ValueError("candidate settings changed after preflight")


def validate_preflight(first, second, ownership):
    """The declared two-phone workload must be live and free before acquisition."""
    for state in (first, second):
        if (not isinstance(state, dict) or type(state.get("code")) is not int or state["code"] != 0
                or type(state.get("input_protocol")) is not int or state["input_protocol"] != 1
                or state.get("input_leases_required") is not True or not isinstance(state.get("receivers"), list)):
            raise ValueError("kernel ownership protocol could not be verified")
        if len(state["receivers"]) != 2:
            raise ValueError("this timing profile requires exactly the two declared receivers")
    verified = []
    for name, device in (("C24C", C24C), ("C241", C241)):
        matches = [[r for r in state["receivers"] if isinstance(r, dict) and r.get("name") == "iMouse2-" + name]
                   for state in (first, second)]
        if any(len(rows) != 1 for rows in matches):
            raise ValueError(f"{name}: expected one receiver in both samples")
        before, after = (rows[0] for rows in matches)
        for row in (before, after):
            if (row.get("deviceid") != device or row.get("live") is not True
                    or type(row.get("frames")) is not int or row["frames"] < 0
                    or type(row.get("receiver_pid")) is not int or row["receiver_pid"] <= 0
                    or not isinstance(row.get("frame_session"), str) or not row["frame_session"]):
                raise ValueError(f"{name}: identity or live frame state is unverified")
        if (after["frames"] <= before["frames"] or after["receiver_pid"] != before["receiver_pid"]
                or after["frame_session"] != before["frame_session"]):
            raise ValueError(f"{name}: receiver changed or frames stopped during preflight")
        verified.append({"name": name, "id": device, "receiver_pid": after["receiver_pid"],
                         "frame_session": after["frame_session"], "frames_before": before["frames"], "frames_after": after["frames"]})
    if not released_targets(ownership, [C24C, C241]):
        raise ValueError("phones are owned, active, releasing, unresolved or missing; no input sent")
    for row in ownership["phones"]:
        if (not isinstance(row, dict) or any(row.get(k) is not False
                for k in ("owned", "active", "releasing", "release_failed", "stopped"))
                or type(row.get("generation")) is not int or row["generation"] < 0):
            raise ValueError("rack input is not idle and ready; no takeover or automatic Resume")
    return {"verified_receivers": verified, "input_idle": True,
            "input_generations": {r["id"]: r["generation"] for r in ownership["phones"]},
            "physical_identity_verified": False, "gate6_acceptance": False}


def require_idle_observers(snapshot, preflight, targets):
    observers = [device for device in preflight["input_generations"] if device not in targets]
    if not observers:
        return
    if not released_targets(snapshot, observers):
        raise ValueError("another phone is active, owned or unresolved; timing trial not sent")
    for device in observers:
        row = next(r for r in snapshot["phones"] if r.get("id") == device)
        if (row.get("stopped") is not False or type(row.get("generation")) is not int
                or row["generation"] != preflight["input_generations"][device]):
            raise ValueError("another phone's control generation changed; timing trial not sent")


def selected_ok(title, phone):
    text = title or ""
    other = "C241" if phone == "C24C" else "C24C"
    return phone in text and other not in text


def anchor_start(invoked_ms, now_ms, now_perf):
    return now_perf - (now_ms - float(invoked_ms)) / 1000.0


def note_invoked(invoked_ms, t_box=None, now_ms=None, now_perf=None):
    print("invoked_ms", invoked_ms, flush=True)
    if t_box is not None:
        now_ms = time.time() * 1000 if now_ms is None else now_ms
        now_perf = time.perf_counter() if now_perf is None else now_perf
        t_box[0] = anchor_start(invoked_ms, now_ms, now_perf)
    return invoked_ms


def open_run(root, run_id):
    root = Path(root).resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", run_id):
        raise SystemExit("run id must be a single directory name")
    runs = (root / "runs").resolve()
    dest = runs / run_id
    if runs.parent != root or dest.resolve().parent != runs:
        raise SystemExit("refusing run directory outside evidence runs/")
    try:
        dest.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise SystemExit(f"refusing to reuse existing run: {dest}") from None
    return dest


def guard(root, dest, name):
    root = Path(root).resolve()
    dest = Path(dest).resolve()
    runs = (root / "runs").resolve()
    path = (dest / name).resolve()
    if path == (root / name).resolve() and name in PROTECTED:
        raise SystemExit(f"refusing to overwrite historical evidence: {name}")
    if runs.parent != root or dest.parent != runs or path.parent != dest:
        raise SystemExit(f"refusing artifact outside this run: {name}")
    return path


def dump(root, dest, name, obj):
    guard(root, dest, name).write_text(json.dumps(obj, indent=2), encoding="utf-8")


VISIBLE_MAD = 18.0
SETTLE_MAD = 2.5
BUTTONS = {"home": "HomeButton", "appswitch": "AppButton", "controlcenter": "CtrlBarButton"}
FN_KEYS = {"home": "Home", "appswitch": "AppSwitch", "controlcenter": "ControlBar"}
# ponytail: absolute luma bands, retune after a live Spotlight/Home pair if they misclassify
SEARCH_BAND = (0.78, 0.90)
UPPER_BAND = (0.18, 0.55)

SELF_CHECK = False


def api(method, url, body=None, timeout=20):
    if SELF_CHECK:
        raise AssertionError("live hardware call")
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return round((time.perf_counter() - t0) * 1000, 1), raw


def post(fun, payload, timeout=15):
    if isinstance(payload, dict) and payload.get("id"):
        assert_target(payload["id"])
    ms, raw = api("POST", BASE + "/", {"fun": fun, "data": payload}, timeout=timeout)
    body = json.loads(raw)
    data = body.get("data", body)
    code = data.get("code")
    if code not in (0, None):
        raise RuntimeError(f"{fun} code={code} body={body}")
    return ms, data


def status():
    _, raw = api("GET", BASE + "/kernel/status", timeout=5)
    return json.loads(raw)["data"]


def input_status():
    _, raw = api("POST", BASE + "/", {"fun": "/input/status", "data": {}}, timeout=5)
    return json.loads(raw)["data"]


def fetch_shot(pid):
    assert_target(pid)
    _, raw = api("GET", f"{BASE}/pic/screenshot?id={pid}&binary=true", timeout=8)
    if not raw.startswith(b"BM"):
        raise RuntimeError(f"not BMP: {raw[:80]!r}")
    return raw


def shot(pid, name, dest=None):
    raw = fetch_shot(pid)
    guard(OUT, dest or RUN, name).write_bytes(raw)
    return len(raw)


def hold_lease(ids, lease_ms=120000):
    assert_target(ids)
    _, data = post("/input/acquire", {"id": ids, "lease_ms": lease_ms})
    for row in data["leases"]:
        HELD[row["id"]] = row["token"]
    return HELD[ids] if "," not in str(ids) else dict(HELD)


def drop_lease(ids=None):
    if ids is None:
        targets = dict(HELD)
    else:
        targets = {i: HELD[i] for i in str(ids).split(",") if i in HELD}
    if not targets:
        return
    post("/input/release", {"id": ",".join(targets), "tokens": targets})
    for i in targets:
        HELD.pop(i, None)


def need_token(pid):
    assert_target(pid)
    if pid not in HELD:
        hold_lease(pid)
    return HELD[pid]


def home_pair(pid, token):
    a, _ = post("/key/sendkey", {"id": pid, "token": token, "fn_key": "Home"}, timeout=8)
    time.sleep(0.15)
    b, _ = post("/key/sendkey", {"id": pid, "token": token, "fn_key": "Home"}, timeout=8)
    return a, b
def home_via(pid, token, api_only, n=1, uia=None, api=None):
    """Home setup/dismiss. UIA uses the console lease; API keeps the harness lease."""
    if not api_only:
        if pid in HELD:
            drop_lease(pid)
        press = uia or uia_invoke
        for i in range(n):
            if i:
                time.sleep(0.15)
            # An incomplete helper reply cannot prove the console received nothing.
            UIA_OWNS["on"] = True
            press("HomeButton")
        return (0, 0) if n > 1 else 0
    times = []
    for i in range(n):
        if i:
            time.sleep(0.15)
        if api:
            ms, _data = api(pid, token)
        else:
            ms, _data = post("/key/sendkey", {"id": pid, "token": token, "fn_key": "Home"}, timeout=8)
        times.append(ms)
    return (times[0], times[-1]) if n > 1 else times[0]




def mad(a, b):
    """Mean absolute byte diff. Same sampler as tools/measure_display_latency.py."""
    pa, pb = a[54:], b[54:]
    n = min(len(pa), len(pb))
    step = 24
    total = count = 0
    for i in range(0, n, step):
        total += abs(pa[i] - pb[i])
        count += 1
    return total / count if count else 0


def score(polls, threshold=VISIBLE_MAD):
    first = next((p["ms"] for p in polls if p["mad_from_start"] >= threshold), None)
    settled = None
    if first is not None:
        low = 0
        for p in polls:
            if p["ms"] < first:
                continue
            if p["mad_from_prev"] < SETTLE_MAD:
                low += 1
                if low >= 2:
                    settled = p["ms"]
                    break
            else:
                low = 0
    return first, settled


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    return round(s[min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))], 1)


def band_stats(raw, y0f, y1f):
    if len(raw) < 54 or raw[:2] != b"BM":
        return None
    off = struct.unpack_from("<I", raw, 10)[0]
    w = struct.unpack_from("<i", raw, 18)[0]
    h = struct.unpack_from("<i", raw, 22)[0]
    bits = struct.unpack_from("<H", raw, 28)[0]
    if w <= 0 or h == 0 or bits != 24:
        return None
    bottom_up = h > 0
    h = abs(h)
    stride = ((w * 3 + 3) // 4) * 4
    y0 = min(h - 1, max(0, int(h * y0f)))
    y1 = min(h, max(y0 + 1, int(h * y1f)))
    total = bright = 0
    luma = 0.0
    for y in range(y0, y1, 2):
        row = (h - 1 - y) if bottom_up else y
        base = off + row * stride
        for x in range(0, w, 4):
            i = base + x * 3
            if i + 2 >= len(raw):
                return None
            b, g, r = raw[i], raw[i + 1], raw[i + 2]
            v = (r + g + b) / 3
            luma += v
            total += 1
            if v >= 220:
                bright += 1
    if not total:
        return None
    return luma / total, bright / total


def visual_state(frame):
    search = band_stats(frame, *SEARCH_BAND)
    upper = band_stats(frame, *UPPER_BAND)
    if not search or not upper:
        return "unknown"
    search_luma, search_white = search
    upper_luma, _ = upper
    if search_white >= 0.45 and upper_luma < 90:
        return "search"
    if search_white < 0.25 and upper_luma >= 70:
        return "home"
    return "other"


def classify(frame, baseline=None):
    state = visual_state(frame)
    if state != "other" or baseline is None:
        return state
    sw = band_stats(frame, *SEARCH_BAND)
    bw = band_stats(baseline, *SEARCH_BAND)
    if not sw or not bw:
        return state
    delta = mad(baseline, frame)
    if delta >= VISIBLE_MAD and sw[1] >= bw[1] + 0.15:
        return "search"
    if delta < SETTLE_MAD and visual_state(baseline) == "home":
        return "home"
    return state


def mirror_guard_ps():
    return (
        "$boxes=$script:root.FindAll([System.Windows.Automation.TreeScope]::Descendants,"
        "(New-Object System.Windows.Automation.PropertyCondition("
        "[System.Windows.Automation.AutomationElement]::ControlTypeProperty,"
        "[System.Windows.Automation.ControlType]::CheckBox)));"
        "foreach($c in $boxes){"
        "$id=[string]$c.Current.AutomationId;$nm=[string]$c.Current.Name;"
        "if($id -eq 'BatchMode' -or $id -eq 'SelectAllBox' -or $id -like 'Mirror*' -or $nm -like 'Mirror*'){"
        "$tog=[string]$c.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState;"
        "if($tog -ne 'Off'){throw ('mirror not Off: '+$id+' '+$nm+' '+$tog)}}};"
        "if($null -eq (Find-Id 'SelectAllBox')){throw 'no mirror checkbox'};"
    )


def run_uia_helper(command, t_box=None, timeout=None):
    """Bound both stdout and process exit, preserving the streamed action timestamp.

    Killing this child stops the helper, not an input already accepted by the
    console. Any helper failure remains an unknown outcome; never retry it.
    """
    timeout = UIA_HELPER_TIMEOUT if timeout is None else timeout
    if timeout <= 0:
        raise ValueError("console helper timeout must be positive")
    deadline = time.monotonic() + timeout
    proc = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    output = queue.Queue()

    def read_stdout():
        try:
            for line in proc.stdout:
                output.put(("line", line))
        except Exception as exc:
            output.put(("error", exc))
        finally:
            output.put(("eof", None))

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    invoked = None
    lines = []
    size = 0
    completed = False

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise RuntimeError(f"console helper timed out after {timeout:g}s; input outcome unknown; do not retry")
        return seconds

    try:
        while True:
            try:
                kind, value = output.get(timeout=remaining())
            except queue.Empty:
                remaining()  # Raise the same timeout for silence or an open pipe.
                continue
            if kind == "error":
                raise RuntimeError(f"console helper output failed: {value}; input outcome unknown") from value
            if kind == "eof":
                break
            size += len(value)
            if size > UIA_HELPER_MAX_OUTPUT:
                raise RuntimeError("console helper output limit exceeded; input outcome unknown; do not retry")
            lines.append(value)
            text = value.strip()
            if invoked is None and text.isdigit():
                invoked = note_invoked(int(text), t_box)
            if text == "ok":
                completed = True
        try:
            code = proc.wait(timeout=remaining())
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"console helper timed out after {timeout:g}s; input outcome unknown; do not retry") from None
        raw = "".join(lines)
        if code or not completed or invoked is None:
            raise RuntimeError(f"console helper failed (exit {code}): {raw[:200]}; input outcome unknown")
        return invoked
    except BaseException as exc:
        try:
            if proc.poll() is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            proc.wait(timeout=UIA_HELPER_CLEANUP_TIMEOUT)
        except Exception as cleanup_error:
            raise RuntimeError(
                f"{exc}; helper PID {proc.pid} cleanup failed: {cleanup_error}; input outcome unknown"
            ) from exc
        raise
    finally:
        reader.join(timeout=UIA_HELPER_CLEANUP_TIMEOUT)
        # Closing a pipe while another thread is blocked reading it can itself
        # hang. An inherited open pipe cannot extend the caller's deadline.
        if not reader.is_alive() and proc.stdout is not None:
            proc.stdout.close()


def console_root_ps():
    """Bind each helper to the same process lifetime, not merely a reusable PID."""
    pid = CONSOLE.get("pid")
    exe, started = CONSOLE.get("exe"), CONSOLE.get("started")
    if not pid or not exe or type(started) is not int or started <= 0:
        raise SystemExit("console identity must be bound before UIA")
    accept_console(exe, exe)
    literal = "'" + exe.replace("'", "''") + "'"
    return (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes;"
        "function Assert-Console{"
        f"$p=Get-Process -Id {int(pid)} -EA Stop;"
        f"if($p.Path -ine {literal} -or $p.StartTime.ToUniversalTime().ToFileTimeUtc() -ne {started})"
        "{throw 'console identity changed; no action sent'};"
        "if($p.MainWindowHandle -eq 0){throw 'console has no window'};"
        "$script:root=[System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle);"
        f"if($script:root.Current.ProcessId -ne {int(pid)}){{throw 'wrong window process'}}"
        "};Assert-Console;"
        "function Find-Id($id){"
        "$c=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id);"
        "return $script:root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$c)};"
    )


def console_scope_ps(require_hover_off=False):
    phone = CONSOLE.get("phone") or "C24C"
    if phone not in ("C24C", "C241"):
        raise SystemExit(f"refusing UIA for {phone}")
    if phone == "C241":
        assert_target(C241)
    other = "C241" if phone == "C24C" else "C24C"
    expected = endpoint(BASE).replace("'", "''")
    return (
        "$title=Find-Id 'SelectedTitle';"
        "if($null -eq $title){throw 'no SelectedTitle'};"
        "$name=$title.Current.Name;"
        f"if($name -notlike '*{phone}*' -or $name -like '*{other}*'){{throw ('selected ' + $name)}}; "
        + mirror_guard_ps()
        + ("$hover=Find-Id 'TrackPointer';if($null -eq $hover){throw 'hover state unavailable'};"
           "$hoverState=[string]$hover.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState;"
           "if($hoverState -ne 'Off'){throw 'hover tracking must be Off'};"
           "$connection=Find-Id 'ConnectionStatus';"
           "if($null -eq $connection -or $connection.Current.Name -cne 'Connected to iMouse'){throw 'console not connected'};"
           "$actual=$null;"
           "if(-not [Uri]::TryCreate($connection.Current.HelpText,[UriKind]::Absolute,[ref]$actual)){throw 'active service unavailable'};"
           f"$expected=[Uri]'{expected}';"
           "if($actual.Scheme -ne $expected.Scheme -or $actual.Host -ne $expected.Host -or "
           "$actual.Port -ne $expected.Port -or $actual.UserInfo -ne '' -or $actual.AbsolutePath -ne '/' "
           "-or $actual.Query -ne '' -or $actual.Fragment -ne ''){throw 'active service mismatch'};"
           if require_hover_off else "")
    )


def uia_invoke(automation_id, t_box=None):
    if automation_id not in BUTTONS.values():
        raise ValueError(automation_id)
    verify_bound_profile()
    script = console_root_ps() + console_scope_ps(require_hover_off=True) + (
        "Assert-Console;"
        f"$el=Find-Id '{automation_id}';"
        "if($null -eq $el -or -not $el.Current.IsEnabled -or $el.Current.IsOffscreen){throw 'button unavailable'};"
        "$inv=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds();"
        "Write-Output $inv;"
        "[Console]::Out.Flush();"
        "$el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke();"
        "'ok'"
    )
    return run_uia_helper(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        t_box,
    )


def disconnect_script():
    # Disconnect cancels the console queue and awaits its token-scoped releases.
    # Opening Settings is a local UI action; there is no Home/Stop/API fallback.
    return console_root_ps() + console_scope_ps() + (
        "Assert-Console;$settings=Find-Id 'SettingsButton';"
        "if($null -eq $settings -or -not $settings.Current.IsEnabled){throw 'Settings unavailable'};"
        "$settings.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke();"
        "$until=[DateTime]::UtcNow.AddSeconds(2);$el=$null;"
        "do{Assert-Console;$el=Find-Id 'DisconnectButton';"
        "if($null -ne $el -and $el.Current.IsEnabled -and -not $el.Current.IsOffscreen){break};"
        "Start-Sleep -Milliseconds 50}while([DateTime]::UtcNow -lt $until);"
        "if($null -eq $el -or -not $el.Current.IsEnabled -or $el.Current.IsOffscreen){throw 'Disconnect unavailable'};"
        + console_scope_ps() +
        "Assert-Console;"
        "Write-Output ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds());[Console]::Out.Flush();"
        "$el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke();"
        "$until=[DateTime]::UtcNow.AddSeconds(12);"
        "do{Assert-Console;$status=Find-Id 'ConnectionStatus';$input=Find-Id 'InputStateText';"
        "$disconnect=Find-Id 'DisconnectButton';"
        "if($null -ne $status -and $null -ne $input -and $null -ne $disconnect -and "
        "$status.Current.Name -ceq 'Disconnected' -and $input.Current.Name -ceq 'Input released' "
        "-and -not $disconnect.Current.IsEnabled){'ok';exit 0};"
        "Start-Sleep -Milliseconds 100}while([DateTime]::UtcNow -lt $until);"
        "throw 'Disconnect did not confirm input release'"
    )


def released_targets(snapshot, targets):
    """A missing/malformed/owned row is unknown, never evidence of release."""
    if (not isinstance(snapshot, dict) or type(snapshot.get("code")) is not int or snapshot["code"] != 0
            or type(snapshot.get("protocol")) is not int or snapshot["protocol"] != 1):
        return False
    rows = snapshot.get("phones")
    if not isinstance(rows, list):
        return False
    for target in targets:
        matches = [row for row in rows if isinstance(row, dict) and row.get("id") == target]
        if len(matches) != 1 or any(matches[0].get(k) is not False
                for k in ("owned", "active", "releasing", "release_failed")):
            return False
    return bool(targets)


def release_console(targets):
    # UIA timeout still permits a read-only status check, but a free target alone
    # cannot prove the console disconnected (it might reacquire on its next action).
    outcome = {"console_disconnect": "unconfirmed", "target_free": False}
    try:
        run_uia_helper(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-Command", disconnect_script()])
        outcome["console_disconnect"] = "confirmed"
    except (Exception, SystemExit) as ex:
        outcome["disconnect_error"] = str(ex)[:500]
    try:
        _, raw = api("GET", BASE + "/input/status", timeout=3)
        snapshot = json.loads(raw)["data"]
        outcome["target_free"] = released_targets(snapshot, targets)
    except Exception as ex:
        outcome["status_error"] = str(ex)[:500]
    return outcome


def api_action(category, pid, token):
    if category == "search":
        return post(
            "/mouse/click",
            {"id": pid, "token": token, "x": 250, "y": 900, "button": 1},
            timeout=12,
        )
    return post(
        "/key/sendkey",
        {"id": pid, "token": token, "fn_key": FN_KEYS[category]},
        timeout=8,
    )


def fire(category, pid, token, t_box, api_only=False, uia=None, api=None, release=None):
    """Use only the requested route. A rejected UIA action must never become API input."""
    uia = uia_invoke if uia is None else uia
    api = api_action if api is None else api
    release = drop_lease if release is None else release
    if not api_only:
        button = BUTTONS.get(category)
        if button is None:
            raise ValueError(f"{category} requires --api-only; no console action is implemented")
        if pid in HELD:
            release(pid)
        UIA_OWNS["on"] = True
        invoked = uia(button, t_box)
        if t_box[0] is None:
            raise RuntimeError("console invocation did not provide its start time")
        return {
            "via": "uia",
            # InvokePattern completion is not a kernel acknowledgement.
            "dispatch_ms": None,
            "ui_invoke_elapsed_ms": round((time.perf_counter() - t_box[0]) * 1000, 1),
            "code": None,
            "invoked_ms": invoked,
        }
    t_box[0] = time.perf_counter()
    ms, data = api(category, pid, token)
    return {"via": "api", "dispatch_ms": ms, "code": data.get("code"), "invoked_ms": None}


def poll_during(fetch, before, act, budget, threshold=VISIBLE_MAD, expect=None, baseline=None):
    polls = []
    lock = threading.Lock()
    stop = threading.Event()
    t_box = [None]
    last = [before]
    fetch_errors = [0]
    first_correct = [None]
    settled = [None]

    def loop():
        prev = before
        origin = None
        stable = 0
        while not stop.is_set():
            start = t_box[0]
            if start is None:
                time.sleep(0.001)
                continue
            if origin != start:
                origin = start
                with lock:
                    polls.clear()
                prev = before
                stable = 0
            if time.perf_counter() >= start + budget:
                break
            try:
                frame = fetch()
            except Exception:
                fetch_errors[0] += 1
                stop.wait(0.01)
                continue
            arrived = time.perf_counter()
            # A fetch may outlive the trial. Never accept its late result.
            if stop.is_set() or arrived > start + budget or t_box[0] != start:
                break
            item = {
                "ms": round((arrived - start) * 1000, 1),
                "mad_from_start": round(mad(before, frame), 2),
                "mad_from_prev": round(mad(prev, frame), 2),
                "visual": classify(frame, baseline if baseline is not None else before),
            }
            prev = frame
            with lock:
                last[0] = frame
                polls.append(item)
                changed = item["mad_from_start"] >= threshold
                correct = expect is not None and changed and item["visual"] == expect
                if correct and first_correct[0] is None:
                    first_correct[0] = item["ms"]
                eligible = correct if expect is not None else changed
                stable = stable + 1 if eligible and item["mad_from_prev"] < SETTLE_MAD else 0
                if stable >= 2:
                    settled[0] = item["ms"]
                    stop.set()
            stop.wait(0.005)

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    try:
        meta = act(t_box)
    except Exception as ex:
        meta = {"via": "error", "error": str(ex)[:200], "dispatch_ms": None, "code": None}
        stop.set()
    except BaseException:
        stop.set()
        th.join(timeout=2)
        raise
    if t_box[0] is None:
        meta = dict(meta) if isinstance(meta, dict) else {}
        meta.setdefault("error", "action did not provide its start time")
        stop.set()
        t_box[0] = time.perf_counter()
    deadline = t_box[0] + budget
    while time.perf_counter() < deadline and not stop.is_set():
        time.sleep(0.02)
    stop.set()
    th.join(timeout=2)
    with lock:
        shot = list(polls)
        frame = last[0]
    first, _ = score(shot, threshold)
    meta = dict(meta) if isinstance(meta, dict) else {}
    meta["first_correct_ms"] = first_correct[0]
    meta["fetch_errors"] = fetch_errors[0]
    return shot, frame, meta, first, settled[0]


def observe(fetch, before, act, expect=None, budget=5.0, baseline=None):
    polls, frame, meta, first, settled = poll_during(
        fetch, before, act, budget, expect=expect, baseline=baseline
    )
    state = classify(frame, baseline if baseline is not None else before)
    visual_ok = None if expect is None else state == expect
    first_correct = meta.get("first_correct_ms")
    error = meta.get("error")
    if not error and meta.get("code") not in (None, 0):
        error = f"command refused: code {meta['code']}"
    miss = bool(error) or (first_correct is None or not visual_ok if expect is not None else first is None)
    return {
        "first_visible_ms": first,
        "first_correct_ms": first_correct,
        "settled_ms": settled,
        "dispatch_ms": meta.get("dispatch_ms"),
        "ui_invoke_elapsed_ms": meta.get("ui_invoke_elapsed_ms"),
        "via": meta.get("via"),
        "code": meta.get("code"),
        "error": error,
        "fetch_errors": meta.get("fetch_errors", 0),
        "invoked_ms": meta.get("invoked_ms"),
        "visual": state,
        "visual_ok": visual_ok,
        "correctness_checked": expect is not None,
        "miss": miss,
        "retry": False,
        "poll_count": len(polls),
        "polls": polls,
        "frame": frame,
    }


def keep(rows, row):
    row["retry"] = False
    rows.append(row)
    return row


def summarize(rows):
    groups = {}
    for row in rows:
        cat = groups.setdefault(row.get("category", "search"), {})
        key = f"{row.get('phone', 'unknown')}/{row.get('via', 'unknown')}"
        cat.setdefault(key, []).append(row)
    out = {}
    for cat, measurements in groups.items():
        parts = {}
        for key, samples in measurements.items():
            checked = all(r.get("correctness_checked") is True for r in samples)
            field = "first_correct_ms" if checked else "first_visible_ms"
            lat = [MISS_MS if r.get("miss") or r.get(field) is None else r[field] for r in samples]
            parts[key] = {
                "n": len(samples), "kept": len(samples),
                "misses": sum(bool(r.get("miss")) or r.get(field) is None for r in samples),
                "p50": pct(lat, 50), "p95": pct(lat, 95),
                "metric": field, "correctness_checked": checked,
                "correctness_note": "heuristic frame classification; not console presentation validation" if checked
                else "transition only; correctness unverified",
            }
        # Do not mix phones or API dispatch with UIA invocation in a percentile.
        bucket = dict(next(iter(parts.values()))) if len(parts) == 1 else {
            "n": sum(p["n"] for p in parts.values()),
            "kept": sum(p["kept"] for p in parts.values()),
            "misses": sum(p["misses"] for p in parts.values()),
            "p50": None, "p95": None,
            "correctness_checked": all(p["correctness_checked"] for p in parts.values()),
            "correctness_note": "separate measurements by phone and input route",
        }
        bucket["measurements"] = parts
        out[cat] = bucket
    return out


def make_bmp(w, h, paint):
    stride = ((w * 3 + 3) // 4) * 4
    pixels = bytearray(stride * h)
    for y in range(h):
        row = (h - 1 - y) * stride
        for x in range(w):
            r, g, b = paint(x, y, h)
            i = row + x * 3
            pixels[i] = b
            pixels[i + 1] = g
            pixels[i + 2] = r
    size = 54 + len(pixels)
    hdr = struct.pack("<2sIHHI", b"BM", size, 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(pixels), 0, 0, 0, 0)
    return hdr + info + bytes(pixels)


def solid(level, n=400):
    return b"\0" * 54 + bytes([level]) * n


def self_check():
    global SELF_CHECK
    SELF_CHECK = True
    HELD.clear()
    UIA_OWNS["on"] = False
    polls = [
        {"ms": 40.0, "mad_from_start": 0.0, "mad_from_prev": 0.0},
        {"ms": 80.0, "mad_from_start": 1.0, "mad_from_prev": 1.0},
        {"ms": 120.0, "mad_from_start": 30.0, "mad_from_prev": 29.0},
        {"ms": 160.0, "mad_from_start": 40.0, "mad_from_prev": 10.0},
        {"ms": 200.0, "mad_from_start": 41.0, "mad_from_prev": 1.0},
        {"ms": 240.0, "mad_from_start": 41.0, "mad_from_prev": 0.4},
    ]
    assert score(polls) == (120.0, 240.0)
    assert score([{"ms": 50.0, "mad_from_start": 1.0, "mad_from_prev": 1.0}]) == (None, None)
    assert pct([10, 20, 30, 40, 50], 50) == 30
    assert pct([10, 20, 30, 40, 50], 95) == 50
    assert pct([], 50) is None

    def paint_search(x, y, h):
        fy = y / h
        if 0.78 <= fy < 0.90:
            return (255, 255, 255)
        if 0.18 <= fy < 0.55:
            return (20, 20, 20)
        return (10, 10, 10)

    def paint_home(x, y, h):
        fy = y / h
        if 0.78 <= fy < 0.90:
            return (90, 90, 90)
        if 0.18 <= fy < 0.55:
            return (150, 150, 150)
        return (120, 120, 120)

    def paint_rel(x, y, h):
        fy = y / h
        if 0.78 <= fy < 0.90 and x % 8 == 0:
            return (255, 255, 255)
        return (100, 100, 100)

    home = make_bmp(48, 40, paint_home)
    search = make_bmp(48, 40, paint_search)
    relative = make_bmp(48, 40, paint_rel)
    assert len(home) == 54 + ((48 * 3 + 3) // 4) * 4 * 40
    assert visual_state(home) == "home"
    assert visual_state(search) == "search"
    assert visual_state(relative) == "other"
    assert classify(relative, home) == "search"
    assert classify(home, home) == "home"

    script = [
        (0.00, solid(0)),
        (0.04, solid(0)),
        (0.10, solid(40)),
        (0.14, solid(80)),
        (0.18, solid(90)),
        (0.22, solid(91)),
        (0.26, solid(91)),
    ]
    idx = [0]
    t_seen = [None]

    def fetch():
        while t_seen[0] is None:
            time.sleep(0.001)
        if idx[0] >= len(script):
            return script[-1][1]
        delay, frame = script[idx[0]]
        idx[0] += 1
        remain = t_seen[0] + delay - time.perf_counter()
        if remain > 0:
            time.sleep(remain)
        return frame

    def act(t_box):
        t_box[0] = time.perf_counter()
        t_seen[0] = t_box[0]
        return {"via": "api", "dispatch_ms": 1.0, "code": 0}

    hit = observe(fetch, solid(0), act, expect=None, budget=1.0)
    assert hit["first_visible_ms"] is not None and 60 < hit["first_visible_ms"] < 180
    assert hit["settled_ms"] is not None and hit["settled_ms"] >= hit["first_visible_ms"]
    assert any(p["ms"] < hit["first_visible_ms"] and p["mad_from_start"] < VISIBLE_MAD for p in hit["polls"])
    assert hit["miss"] is False and hit["retry"] is False
    assert score(hit["polls"]) == (hit["first_visible_ms"], hit["settled_ms"])

    calls = {"n": 0}

    def miss_act(t_box):
        calls["n"] += 1
        t_box[0] = time.perf_counter()
        return {"via": "api", "dispatch_ms": 3.0, "code": 0}

    miss = observe(lambda: solid(1), solid(0), miss_act, expect="search", budget=0.05)
    assert calls["n"] == 1
    assert miss["first_visible_ms"] is None and miss["miss"] is True and miss["retry"] is False

    rows = []
    for _ in range(3):
        keep(rows, {"category": "search", "miss": True, "first_visible_ms": None, "retry": True})
    assert len(rows) == 3 and all(r["miss"] and r["retry"] is False for r in rows)

    sample = []
    for i in range(100):
        sample.append({
            "category": "search",
            "first_visible_ms": None if i == 7 else float(i + 1),
            "first_correct_ms": None if i == 7 else float(i + 1),
            "correctness_checked": True,
            "miss": i == 7,
        })
    sample.append({"category": "home", "first_visible_ms": 12.0, "first_correct_ms": 12.0,
                   "correctness_checked": True, "miss": False})
    sample.append({"category": "appswitch", "first_visible_ms": 20.0, "miss": False})
    summary = summarize(sample)
    assert summary["search"]["n"] == 100
    assert summary["search"]["kept"] == 100
    assert summary["search"]["misses"] == 1
    penalized = [float(i + 1) for i in range(100) if i != 7] + [MISS_MS]
    assert summary["search"]["p50"] == pct(penalized, 50)
    assert summary["search"]["p95"] == pct(penalized, 95)
    assert summary["home"]["n"] == 1 and summary["home"]["misses"] == 0
    assert summary["search"]["correctness_checked"] is True
    assert summary["home"]["correctness_checked"] is True
    assert summary["appswitch"]["correctness_checked"] is False

    api_calls = {"n": 0}

    def boom(_id, t_box=None):
        raise RuntimeError("no console")

    def fake_api(category, pid, token):
        api_calls["n"] += 1
        return 15.0, {"code": 0}

    t_box = [None]
    try:
        fire("home", "id", "tok", t_box, uia=boom, api=fake_api)
        raise AssertionError("rejected UIA action did not abort")
    except RuntimeError as ex:
        assert str(ex) == "no console"
    assert api_calls["n"] == 0 and t_box[0] is None

    def no_api(*_a):
        raise AssertionError("API ran after UIA success")

    t_box = [None]

    def timed_uia(automation_id, t_box=None):
        assert automation_id == "CtrlBarButton"
        assert t_box is not None and t_box[0] is None
        return note_invoked(4200, t_box, now_ms=4230, now_perf=time.perf_counter())

    direct = fire("controlcenter", "id", "tok", t_box, uia=timed_uia, api=no_api)
    assert direct["via"] == "uia" and direct["invoked_ms"] == 4200 and api_calls["n"] == 0
    assert direct["dispatch_ms"] is None and direct["ui_invoke_elapsed_ms"] >= 0
    assert t_box[0] is not None

    t_box = [None]
    search_fire = fire("search", "id", "tok", t_box, api_only=True, uia=boom, api=fake_api)
    assert search_fire["via"] == "api" and api_calls["n"] == 1

    def already_act(t_box):
        t_box[0] = time.perf_counter()
        return {"via": "api", "dispatch_ms": 0.0, "code": 0}

    already = observe(lambda: home, home, already_act, expect="home", budget=0.04)
    assert already["visual"] == "home" and already["visual_ok"] is True and already["miss"] is True
    assert already["first_correct_ms"] is None

    hits = [{"category": "search", "first_visible_ms": 100.0, "miss": False} for _ in range(10)]
    assert summarize(hits)["search"]["p95"] == 100.0
    dirty = hits + [{"category": "search", "first_visible_ms": None, "miss": True}]
    assert summarize(dirty)["search"]["p95"] == 5000.0
    assert summarize(dirty)["search"]["misses"] == 1

    assert [row[0] for row in phone_plan(False)] == ["C24C"]
    assert [row[0] for row in phone_plan(True)] == ["C24C", "C241"]
    try:
        assert_target(C241)
        raise AssertionError("C241 allowed by default")
    except SystemExit as ex:
        assert "allow-c241" in str(ex)

    cand = r"C:\Users\joey_\AppData\Local\Temp\claude\imouse-candidate-5\iMouse2.exe"
    assert accept_console(cand) == cand
    installed = r"C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0\release\iMouse2-two-phone-candidate\iMouse2.exe"
    try:
        accept_console(installed)
        raise AssertionError("installed console accepted")
    except SystemExit:
        pass
    try:
        accept_console(r"C:\iMouseXP\iMouse2.exe", r"C:\iMouseXP\iMouse2.exe")
        raise AssertionError("vendor console accepted")
    except SystemExit:
        pass
    other = r"D:\builds\lab\iMouse2.exe"
    assert accept_console(other, other) == other
    try:
        check_console(False, None, cand)
        raise AssertionError("missing console pid")
    except SystemExit as ex:
        assert "console-pid" in str(ex)
    assert check_console(True, None) is None
    assert selected_ok("XR C24C", "C24C")
    assert not selected_ok("XR C241", "C24C")
    assert not selected_ok("Select an iPhone", "C24C")

    released = []
    HELD[C24C] = "tok"

    def fake_release(ids):
        released.append(ids)
        HELD.pop(ids, None)

    def ok_uia(_aid, box=None):
        assert C24C not in HELD
        return note_invoked(1000, box, now_ms=1040, now_perf=time.perf_counter())

    leased = fire("home", C24C, "tok", [None], uia=ok_uia, api=no_api, release=fake_release)
    assert released == [C24C] and leased["invoked_ms"] == 1000 and C24C not in HELD

    def anchored(box):
        note_invoked(9_000_000, box, now_ms=9_000_040, now_perf=time.perf_counter())
        return {"via": "uia", "dispatch_ms": 1.0, "code": None, "invoked_ms": 9_000_000}

    timed = observe(lambda: solid(80), solid(0), anchored, expect=None, budget=0.12)
    assert timed["first_visible_ms"] is not None and timed["first_visible_ms"] >= 30
    assert abs(anchor_start(1000, 1250, 10.0) - 9.75) < 1e-9

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name in PROTECTED:
            (root / name).write_text("historical", encoding="utf-8")
        dest = open_run(root, "self-check")
        dump(root, dest, "rows.json", [{"phone": "C24C"}])
        dump(root, dest, "manifest.json", {"phones": ["C24C"]})
        dump(root, dest, "end-status.json", {"ok": True})
        dump(root, dest, "preflight-frames.json", {"live": {}})
        guard(root, dest, "c24c.bmp").write_bytes(b"BM")
        for name in PROTECTED:
            assert (root / name).read_text(encoding="utf-8") == "historical"
        assert json.loads((dest / "rows.json").read_text(encoding="utf-8"))[0]["phone"] == "C24C"
        assert dest == root / "runs" / "self-check"
        try:
            guard(root, root, "rows.json")
            raise AssertionError("historical overwrite allowed")
        except SystemExit:
            pass
        assert (root / "rows.json").read_text(encoding="utf-8") == "historical"

    seen = []

    def spy_exe(pid):
        seen.append(pid)
        raise AssertionError("process_exe ran")

    try:
        bind_console(None, read_identity=spy_exe)
        raise AssertionError("missing console pid")
    except SystemExit as ex:
        assert "console-pid" in str(ex)
    assert seen == []
    assert bind_console(1, read_identity=lambda pid: {"exe": cand, "started": 1}) == cand

    guard_ps = mirror_guard_ps()
    for key in ("BatchMode", "SelectAllBox", "Mirror*", "-ne 'Off'"):
        assert key in guard_ps
    assert "-eq 'On'" not in guard_ps
    assert "Indeterminate" not in guard_ps or "-ne 'Off'" in guard_ps

    HELD.clear()
    pressed = []

    def fake_home(aid, t_box=None):
        assert aid == "HomeButton"
        pressed.append(aid)
        return 1

    assert home_via(C24C, None, False, n=2, uia=fake_home) == (0, 0)
    assert home_via(C24C, None, False, n=1, uia=fake_home) == 0
    assert pressed == ["HomeButton", "HomeButton", "HomeButton"] and HELD == {}
    assert UIA_OWNS["on"] is True

    def no_uia(*_a, **_k):
        raise AssertionError("UIA in api-only")

    def fake_send(pid, token):
        assert token == "keep"
        return 4.0, {"code": 0}

    assert home_via(C24C, "keep", True, n=1, uia=no_uia, api=fake_send) == 4.0
    HELD[C24C] = "keep"
    rel = []
    kept = fire(
        "appswitch",
        C24C,
        "keep",
        [None],
        api_only=True,
        uia=no_uia,
        api=lambda c, p, t: (3.0, {"code": 0}),
        release=lambda i: rel.append(i),
    )
    assert kept["via"] == "api" and rel == [] and HELD[C24C] == "keep"
    HELD.clear()
    UIA_OWNS["on"] = False
    print("self-check ok", summary["search"]["p50"], summary["search"]["p95"], summary["search"]["misses"])

    SELF_CHECK = False
    return 0


def save_frame(name, frame, dest=None):
    if frame and frame.startswith(b"BM"):
        guard(OUT, dest or RUN, name).write_bytes(frame)
        return len(frame)
    return 0


def live(n, categories, api_only, allow_c241=False, console_pid=None, console_path=None,
         console_data_dir=None, console_sha256=None):
    global ALLOW_C241, RUN
    cats = categories or ["search"]
    if not api_only and any(cat not in BUTTONS for cat in cats):
        raise SystemExit("search requires --api-only; console search input is not implemented")
    ALLOW_C241 = bool(allow_c241)
    plan = phone_plan(ALLOW_C241)
    UIA_OWNS["on"] = False
    if not api_only and allow_c241:
        raise ValueError("UIA mode currently supports C24C only; no automatic console selection")
    run_id = time.strftime("%Y%m%d-%H%M%S")
    dest = open_run(OUT, run_id)
    RUN = dest
    ids = ",".join(pid for _, pid, *_ in plan)
    rows = []
    dump(OUT, dest, "manifest.json", {
        "run_id": run_id, "phones": [name for name, *_ in plan], "categories": cats,
        "api_only": api_only, "allow_c241": ALLOW_C241, "console_pid": console_pid,
        "console_identity": None,
        "out": str(dest), "frame_source": "kernel screenshot endpoint, not console presentation",
        "action_origin": "API request" if api_only else "UI Automation InvokePattern, not physical click",
        "gate6_acceptance": False,
    })
    state = {"status": "running", "phase": "preflight"}
    cleanup = {"api_acquire": "not_attempted",
               "api_release": "no_known_tokens",
               "console_release": "not_applicable" if api_only else "no_action_attempted"}
    try:
        dump(OUT, dest, "run-state.json", state)
        if not api_only:
            profile = prepare_console(console_pid, console_path, console_data_dir, console_sha256)
            dump(OUT, dest, "candidate-preflight.json", {
                "identity": {key: CONSOLE.get(key) for key in ("pid", "exe", "started")}, "profile": profile})
        first = status()
        time.sleep(1.0)
        second = status()
        ownership = input_status()
        # Preserve the observations even if validation refuses any action.
        dump(OUT, dest, "preflight-frames.json", {"before": first, "after": second, "input": ownership})
        preflight = validate_preflight(first, second, ownership)
        dump(OUT, dest, "preflight-result.json", preflight)
        state["phase"] = "acquire" if api_only else "trial"
        if api_only:
            cleanup["api_acquire"] = "unconfirmed"
            # Acquisition can store some returned tokens before failing. Cleanup
            # must cover that partial result, without guessing any missing token.
            hold_lease(ids)
            cleanup["api_acquire"] = "confirmed"
        for name, pid, oname, oid in plan:
            CONSOLE["phone"] = name
            for category in cats:
                for cycle in range(1, n + 1):
                    try:
                        state["phase"] = "ownership-check"
                        require_idle_observers(input_status(), preflight, ids.split(","))
                        state["phase"] = "renew"
                        if api_only and HELD:
                            post("/input/renew", {"id": ",".join(HELD), "tokens": dict(HELD)})
                        state["phase"] = "trial"
                        row = run_cycle(name, pid, oname, oid, category, cycle, api_only, dest)
                    except (Exception, SystemExit) as ex:
                        row = {"phone": name, "category": category, "cycle": cycle,
                               "via": "api" if api_only else "uia", "miss": True,
                               "failure_stage": state["phase"],
                               "action_attempted": False if state["phase"] in ("renew", "ownership-check") else None,
                               "error": str(ex)[:200], "first_visible_ms": None,
                               "first_correct_ms": None, "correctness_checked": category in ("home", "search")}
                    keep(rows, row)
                    dump(OUT, dest, "rows.json", rows)
                    dump(OUT, dest, "summary.json", summarize(rows))
                    print(
                        f"{name} {category} c{cycle} via={row.get('via')} "
                        f"invoked={row.get('invoked_ms')} first={row.get('first_visible_ms')} "
                        f"settled={row.get('settled_ms')} miss={row.get('miss')}",
                        flush=True,
                    )
                    if row.get("error") or row.get("miss"):
                        reason = row.get("error") or "expected visual response was not confirmed"
                        raise SystemExit(f"trial aborted; saved failure in {dest}: {reason}")
        state["phase"] = "end-status"
        end = status()
        stuck = input_status()
        summary = summarize(rows)
        dump(OUT, dest, "end-status.json", {"kernel": end, "input": stuck, "summary": summary})
        state.update(status="complete", phase="complete")
    except BaseException as ex:
        state.update(status="aborted", error=str(ex)[:500])
        raise
    finally:
        release_error = None
        cleanup["known_phones_before_release"] = sorted(HELD)
        if HELD:
            try:
                drop_lease()
                cleanup["api_release"] = "confirmed"
                print("released", flush=True)
            except Exception as ex:
                release_error = ex
                cleanup.update(api_release="unconfirmed", error=str(ex)[:500])
                print("RELEASE FAILED", ex, flush=True)
        cleanup["remaining_known_phones"] = sorted(HELD)
        cleanup["console_action_attempted"] = UIA_OWNS["on"] if not api_only else False
        if not api_only and UIA_OWNS["on"]:
            cleanup["console_release"] = "unconfirmed"
            try:
                result = release_console([pid for _, pid, *_ in plan])
                cleanup["console_cleanup"] = result
                if result.get("console_disconnect") != "confirmed" or result.get("target_free") is not True:
                    raise RuntimeError("console disconnect or target release was not confirmed")
                cleanup["console_release"] = "confirmed"
                UIA_OWNS["on"] = False
            except (Exception, SystemExit) as ex:
                cleanup["console_error"] = str(ex)[:500]
                release_error = ex
        state["trial_rows"] = len(rows)
        state["cleanup_failed"] = release_error is not None
        if release_error is not None and state["status"] == "complete":
            state["status"] = "cleanup_failed"
        # Release is attempted before evidence writes, even if the disk is full.
        # A missing acquisition reply cannot establish that no lease was granted.
        # Console release needs both a completed Disconnect and free target status.
        dump(OUT, dest, "run-state.json", state)
        dump(OUT, dest, "cleanup.json", cleanup)
        if release_error is not None:
            raise RuntimeError(f"lease release unconfirmed: {release_error}") from release_error
    print("done", len(rows), json.dumps(summarize(rows)), flush=True)


def run_cycle(name, pid, oname, oid, category, cycle, api_only, dest):
    CONSOLE["phone"] = name
    if category == "search" and not api_only:
        raise SystemExit("search requires --api-only")
    token = need_token(pid) if api_only else None
    if category == "search":
        before = fetch_shot(pid)

        homes = {}

        def home_act(t_box):
            t_box[0] = time.perf_counter()
            homes["a"], homes["b"] = home_pair(pid, token)
            return {"via": "api", "dispatch_ms": homes["b"], "code": 0}

        home = observe(lambda: fetch_shot(pid), before, home_act, expect="home", budget=3.0)
        if home.get("error") or not home["visual_ok"]:
            raise RuntimeError(home.get("error") or "setup did not reach Home")
        before_click = home["frame"] or before

        def click_act(t_box):
            return fire("search", pid, token, t_box, api_only=True)

        click = observe(
            lambda: fetch_shot(pid), before_click, click_act, expect="search", budget=5.0, baseline=before_click
        )
        click["via"] = "api"
        target = f"{name.lower()}-c{cycle}-search.bmp"
        other = f"{oname.lower()}-iso-during-{name.lower()}-c{cycle}.bmp"
        t_len = save_frame(target, click["frame"], dest)
        if oid == C241 and not ALLOW_C241:
            o_len = 0
        else:
            o_len = shot(oid, other, dest)
        dismiss_ms = None
        if not click.get("error") and not click["miss"]:
            try:
                dismiss_ms, _ = post("/key/sendkey", {"id": pid, "token": token, "fn_key": "Home"}, timeout=8)
            except Exception as ex:
                click["error"] = f"dismiss failed: {ex}"[:200]
                click["miss"] = True
        expect = "search"
        return {
            **{key: value for key, value in click.items() if key != "frame"},
            "phone": name,
            "cycle": cycle,
            "category": "search",
            "home1_ms": homes["a"],
            "home2_ms": homes["b"],
            "home_first_visible_ms": home["first_visible_ms"],
            "home_settled_ms": home["settled_ms"],
            "home_visual": home["visual"],
            "home_visual_ok": home["visual_ok"],
            "dispatch_ms": click["dispatch_ms"],
            "click_code": click.get("code"),
            "via": click["via"],
            "first_visible_ms": click["first_visible_ms"],
            "settled_ms": click["settled_ms"],
            "visual": click["visual"],
            "visual_ok": click["visual_ok"],
            "miss": click["miss"],
            "search_bmp": target,
            "search_bytes": t_len,
            "isolation_bmp": other,
            "isolation_bytes": o_len,
            "dismiss_ms": dismiss_ms,
            "poll_count": click["poll_count"],
            "invoked_ms": click.get("invoked_ms"),
            "correctness_checked": bool(expect is not None),
        }

    if category == "home":
        # UIA mode requires an already prepared non-Home screen. Never acquire an
        # API lease just to set up a console measurement, or time Home-on-Home.
        if api_only:
            post("/mouse/click", {"id": pid, "token": token, "x": 250, "y": 900, "button": 1}, timeout=12)

            def wait_act(t_box):
                t_box[0] = time.perf_counter()
                return {"via": "wait"}

            observe(lambda: fetch_shot(pid), fetch_shot(pid), wait_act, expect="search", budget=2.0)
        before = fetch_shot(pid)
        if classify(before) != "search":
            raise RuntimeError("Home trial requires a prepared Search screen; measured Home was not sent")
    elif api_only:
        home_pair(pid, token)
        before = fetch_shot(pid)
    else:
        home_via(pid, None, False, n=2)
        before = fetch_shot(pid)

    expect = "home" if category == "home" else None

    def act(t_box):
        return fire(category, pid, token, t_box, api_only=api_only)

    obs = observe(lambda: fetch_shot(pid), before, act, expect=expect, budget=5.0, baseline=before)
    obs["via"] = "api" if api_only else "uia"
    target = f"{name.lower()}-c{cycle}-{category}.bmp"
    save_frame(target, obs["frame"], dest)
    if category != "home" and not obs.get("error") and not obs["miss"]:
        try:
            if api_only:
                post("/key/sendkey", {"id": pid, "token": token, "fn_key": "Home"}, timeout=8)
            else:
                home_via(pid, None, False, n=1)
        except Exception as ex:
            obs["error"] = f"dismiss failed: {ex}"[:200]
            obs["miss"] = True
    return {
        **{key: value for key, value in obs.items() if key != "frame"},
        "phone": name,
        "cycle": cycle,
        "category": category,
        "via": obs["via"],
        "dispatch_ms": obs["dispatch_ms"],
        "code": obs.get("code"),
        "first_visible_ms": obs["first_visible_ms"],
        "settled_ms": obs["settled_ms"],
        "visual": obs["visual"],
        "visual_ok": obs["visual_ok"],
        "miss": obs["miss"],
        "poll_count": obs["poll_count"],
        "bmp": target,
        "invoked_ms": obs.get("invoked_ms"),
        "correctness_checked": bool(expect is not None),
    }


def summarize_console_timing(report):
    """Read an opt-in console diagnostic snapshot. No UI/transport, no pass verdict.

    A frame after a handler may be an unrelated animation. Preserve that temporal
    relationship without calling it a correct response or physical display time.
    """
    trace = report.get("console", {}).get("response_timing")
    if not isinstance(trace, dict) or trace.get("schema_version") != 1:
        raise ValueError("missing or unsupported console response timing snapshot")

    def integer(value, name, minimum=0):
        if type(value) is not int or value < minimum:
            raise ValueError(f"invalid {name}")
        return value

    frequency = integer(trace.get("timestamp_frequency"), "timestamp frequency", 1)
    captured = integer(trace.get("captured_at"), "capture timestamp")
    capacity = integer(trace.get("capacity"), "capacity", 1)
    dropped = integer(trace.get("dropped_events"), "dropped event count")
    if dropped:
        raise ValueError("timing snapshot dropped events; cannot summarize incomplete capture")
    events = trace.get("events")
    if capacity > 65536 or not isinstance(events, list) or len(events) > capacity:
        raise ValueError("invalid timing event list or capacity")
    requests, starts, endings, frames = {}, {}, {}, {}
    last_time = 0
    for expected_index, event in enumerate(events, 1):
        if not isinstance(event, dict) or type(event.get("index")) is not int or event["index"] != expected_index:
            raise ValueError("missing, reordered or duplicate timing event")
        tick = integer(event.get("timestamp"), "event timestamp")
        integer(event.get("epoch"), "event epoch")
        if tick < last_time or tick > captured:
            raise ValueError("non-monotonic timing event")
        last_time = tick
        kind = event.get("kind")
        targets = event.get("targets")
        if not isinstance(targets, str):
            raise ValueError("invalid event targets")
        if kind == "bitmap_applied":
            indices, entries = frames.setdefault((targets, event["epoch"]), ([], []))
            indices.append(event["index"])
            entries.append(event)
        elif kind == "preview_reset":
            continue
        elif kind in ("action_requested", "command_started", "action_finished"):
            action = integer(event.get("action_id"), "action id", 1)
            collection = {"action_requested": requests, "command_started": starts, "action_finished": endings}[kind]
            if action in collection:
                raise ValueError("duplicate action phase")
            if kind != "action_requested":
                request = requests.get(action)
                if request is None or action in endings or any(event.get(k) != request.get(k)
                        for k in ("epoch", "targets", "operation", "origin")):
                    raise ValueError("action phase does not match its original request")
                if kind == "action_finished" and event.get("outcome") == "command_completed" and action not in starts:
                    raise ValueError("completed action has no command start")
            collection[action] = event
        else:
            raise ValueError("unsupported timing event kind")

    rows = []
    for action, request in requests.items():
        start, end = starts.get(action), endings.get(action)
        single_phone = bool(request["targets"]) and "," not in request["targets"]
        indices, entries = frames.get((request["targets"], request["epoch"]), ([], []))
        after = bisect_right(indices, request["index"])
        frame = entries[after] if single_phone and after < len(entries) else None
        def elapsed(event, origin=request):
            return None if event is None else round((event["timestamp"] - origin["timestamp"]) * 1000 / frequency, 3)
        rows.append({
            "action_id": action, "epoch": request["epoch"], "targets": request["targets"],
            "origin": request.get("origin"), "operation": request.get("operation"),
            "outcome": end.get("outcome") if end else "incomplete",
            "queue_ms": elapsed(start), "handler_to_finish_ms": elapsed(end),
            "command_ms": elapsed(end, start) if start is not None else None,
            "first_bitmap_after_handler_ms": elapsed(frame),
            "frame_session": frame.get("frame_session") if frame else None,
            "frame_sequence": frame.get("frame_sequence") if frame else None,
            "correctness_verified": False,
        })
    return {"schema_version": 1, "recording_id": trace.get("recording_id"), "gate6_acceptance": False,
            "metric_scope": "Console handler to selected-preview bitmap application, not physical click or display scan-out. "
                            "A later bitmap does not establish causation or correct response; group display is not covered.",
            "actions": rows}


def main():
    p = argparse.ArgumentParser(description="Gate 6 preparation: action-to-kernel-frame timing (not gate acceptance)")
    offline = p.add_mutually_exclusive_group()
    offline.add_argument("--self-check", action="store_true")
    offline.add_argument("--analyze-console-trace", type=Path, metavar="DIAGNOSTICS_JSON",
                         help="offline only: summarize an opt-in console timing snapshot; never contact the rack")
    p.add_argument("--n", type=int, default=5, help="observations per category per phone; gate wants >= 100")
    p.add_argument("--category", action="append", choices=["search", "home", "appswitch", "controlcenter"])
    p.add_argument("--api-only", action="store_true", help="hold the lease and drive via HTTP; skip UIA")
    p.add_argument("--allow-c241", action="store_true", help="allow live commands to C241")
    p.add_argument("--console-pid", type=int, help="dedicated candidate PID; UIA runs disconnect it on completion or failure")
    p.add_argument("--console-path", help="exact candidate exe path, required for UIA")
    p.add_argument("--console-data-dir", help="explicit isolated candidate profile, required for UIA")
    p.add_argument("--console-sha256", help="expected iMouse2.dll SHA-256, required for UIA")
    args = p.parse_args()
    if args.self_check:
        raise SystemExit(self_check())
    if args.analyze_console_trace is not None:
        # Cap the read itself, even if the file grows after a stat call.
        with args.analyze_console_trace.open("rb") as source:
            raw = source.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise SystemExit("diagnostic input exceeds 32 MiB")
        try:
            print(json.dumps(summarize_console_timing(json.loads(raw)), indent=2))
        except (ValueError, TypeError, AttributeError) as ex:
            raise SystemExit(f"invalid console timing evidence: {ex}") from ex
        return
    if args.n < 1:
        raise SystemExit("--n must be >= 1")
    live(args.n, args.category, args.api_only, args.allow_c241, args.console_pid, args.console_path,
         args.console_data_dir, args.console_sha256)


if __name__ == "__main__":
    main()

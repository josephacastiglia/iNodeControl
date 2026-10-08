"""Gate 6 release validation. Single-id API. Does not restart the kernel.

Measures console-action to first visible response. The fixed 0.8s sleep is gone:
a screenshot poller (same MAD loop as tools/measure_display_latency.py) records
first_visible_ms and settled_ms. Misses are kept and not retried.
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

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
    if CANDIDATE_MARK in norm:
        return exe
    if console_path and norm == norm_path(console_path):
        return exe
    raise SystemExit(f"pid is not a candidate console: {exe}")


def check_console(api_only, console_pid, exe=None, console_path=None):
    if api_only:
        return None
    if not console_pid:
        raise SystemExit("UIA mode requires --console-pid")
    return accept_console(exe, console_path)
def bind_console(console_pid, console_path=None, read_exe=None):
    if not console_pid:
        raise SystemExit("UIA mode requires --console-pid")
    read_exe = process_exe if read_exe is None else read_exe
    exe = read_exe(console_pid)
    check_console(False, console_pid, exe, console_path)
    CONSOLE["pid"] = int(console_pid)
    return exe




def process_exe(pid):
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
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        raise SystemExit(f"cannot open console pid {pid}")
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            raise SystemExit(f"cannot read path for pid {pid}")
        return buf.value
    finally:
        kernel.CloseHandle(handle)


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
    dest = Path(root) / "runs" / run_id
    if dest.resolve() == Path(root).resolve():
        raise SystemExit("refusing to write artifacts at evidence root")
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def guard(root, dest, name):
    root = Path(root).resolve()
    path = (Path(dest) / name).resolve()
    if path == (root / name).resolve() and name in PROTECTED:
        raise SystemExit(f"refusing to overwrite historical evidence: {name}")
    if root not in path.parents or "runs" not in path.parts:
        raise SystemExit(f"refusing artifact outside runs/: {name}")
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
            press("HomeButton")
        UIA_OWNS["on"] = True
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


def uia_invoke(automation_id, t_box=None):
    if not automation_id.isalnum():
        raise ValueError(automation_id)
    pid = CONSOLE.get("pid")
    phone = CONSOLE.get("phone") or "C24C"
    if not pid:
        raise SystemExit("UIA mode requires --console-pid")
    if phone not in ("C24C", "C241"):
        raise SystemExit(f"refusing UIA for {phone}")
    if phone == "C241":
        assert_target(C241)
    other = "C241" if phone == "C24C" else "C24C"
    script = (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes;"
        f"$p=Get-Process -Id {int(pid)} -EA Stop;"
        "if($p.MainWindowHandle -eq 0){throw 'console has no window'};"
        "$script:root=[System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle);"
        "function Find-Id($id){"
        "$c=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id);"
        "return $script:root.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$c)};"
        "$title=Find-Id 'SelectedTitle';"
        "if($null -eq $title){throw 'no SelectedTitle'};"
        "$name=$title.Current.Name;"
        f"if($name -notlike '*{phone}*' -or $name -like '*{other}*'){{throw ('selected ' + $name)}}; "
        + mirror_guard_ps()
        +
        f"$el=Find-Id '{automation_id}';"
        "if($null -eq $el){throw 'no button'};"
        "$inv=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds();"
        "Write-Output $inv;"
        "[Console]::Out.Flush();"
        "$el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke();"
        "'ok'"
    )
    proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    invoked = None
    lines = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            s = line.strip()
            if invoked is None and s.isdigit():
                invoked = note_invoked(int(s), t_box)
        code = proc.wait(timeout=20)
    except Exception:
        proc.kill()
        raise
    raw = "".join(lines)
    if code or "ok" not in raw or invoked is None:
        raise RuntimeError(raw[:200])
    return invoked


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
    """UIA invoke for Home / AppSwitch / ControlCenter, else API. t_box[0] is Invoke time."""
    uia = uia_invoke if uia is None else uia
    api = api_action if api is None else api
    release = drop_lease if release is None else release
    button = None if api_only else BUTTONS.get(category)
    err = None
    released = False
    if button:
        if pid in HELD:
            release(pid)
            released = True
        try:
            invoked = uia(button, t_box)
            if t_box[0] is None:
                t_box[0] = time.perf_counter()
            UIA_OWNS["on"] = True
            return {
                "via": "uia",
                "dispatch_ms": round((time.perf_counter() - t_box[0]) * 1000, 1),
                "code": None,
                "fallback": None,
                "invoked_ms": invoked,
            }
        except Exception as ex:
            if t_box[0] is not None:
                raise
            err = str(ex)[:200]
            if released:
                token = need_token(pid)
    t_box[0] = time.perf_counter()
    ms, data = api(category, pid, token)
    return {"via": "api", "dispatch_ms": ms, "code": data.get("code"), "fallback": err, "invoked_ms": None}


def poll_during(fetch, before, act, budget, threshold=VISIBLE_MAD):
    polls = []
    lock = threading.Lock()
    stop = threading.Event()
    t_box = [None]
    last = [before]

    def loop():
        prev = before
        origin = None
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
            try:
                frame = fetch()
            except Exception:
                continue
            item = {
                "ms": round((time.perf_counter() - start) * 1000, 1),
                "mad_from_start": round(mad(before, frame), 2),
                "mad_from_prev": round(mad(prev, frame), 2),
            }
            prev = frame
            last[0] = frame
            with lock:
                if t_box[0] != start:
                    continue
                polls.append(item)
                shot = list(polls)
            if score(shot, threshold)[1] is not None:
                stop.set()

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    try:
        meta = act(t_box)
    except Exception as ex:
        meta = {"via": "error", "error": str(ex)[:200], "dispatch_ms": None, "code": None}
    if t_box[0] is None:
        t_box[0] = time.perf_counter()
    deadline = t_box[0] + budget
    while time.perf_counter() < deadline and not stop.is_set():
        time.sleep(0.02)
    stop.set()
    th.join(timeout=2)
    with lock:
        shot = list(polls)
    first, settled = score(shot, threshold)
    return shot, last[0], meta if isinstance(meta, dict) else {"via": "api"}, first, settled


def observe(fetch, before, act, expect=None, budget=5.0, baseline=None):
    polls, frame, meta, first, settled = poll_during(fetch, before, act, budget)
    state = classify(frame, baseline if baseline is not None else before)
    visual_ok = None if expect is None else state == expect
    miss = visual_ok is False if expect is not None else first is None
    return {
        "first_visible_ms": first,
        "settled_ms": settled,
        "dispatch_ms": meta.get("dispatch_ms"),
        "via": meta.get("via"),
        "code": meta.get("code"),
        "fallback": meta.get("fallback"),
        "invoked_ms": meta.get("invoked_ms"),
        "visual": state,
        "visual_ok": visual_ok,
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
    out = {}
    for row in rows:
        bucket = out.setdefault(row.get("category", "search"), {"n": 0, "misses": 0, "kept": 0, "lat": []})
        bucket["n"] += 1
        bucket["kept"] += 1
        if row.get("miss") or row.get("first_visible_ms") is None:
            bucket["misses"] += 1
            bucket["lat"].append(MISS_MS)
        else:
            bucket["lat"].append(row["first_visible_ms"])
    for cat, bucket in out.items():
        lat = bucket.pop("lat")
        bucket["p50"] = pct(lat, 50)
        bucket["p95"] = pct(lat, 95)
        checked = cat in ("search", "home")
        bucket["correctness_checked"] = checked
        bucket["correctness_note"] = (
            "verified via screen classifier" if checked
            else "visible change only (MAD >= 18); structural correctness unclassified without ground-truth reference"
        )
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
            "miss": i == 7,
        })
    sample.append({"category": "home", "first_visible_ms": 12.0, "miss": False})
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
    fallback = fire("home", "id", "tok", t_box, uia=boom, api=fake_api)
    assert fallback["via"] == "api" and fallback["fallback"] and api_calls["n"] == 1
    assert t_box[0] is not None

    def no_api(*_a):
        raise AssertionError("API ran after UIA success")

    t_box = [None]

    def timed_uia(automation_id, t_box=None):
        assert automation_id == "CtrlBarButton"
        assert t_box is not None and t_box[0] is None
        return note_invoked(4200, t_box, now_ms=4230, now_perf=time.perf_counter())

    direct = fire("controlcenter", "id", "tok", t_box, uia=timed_uia, api=no_api)
    assert direct["via"] == "uia" and direct["invoked_ms"] == 4200 and api_calls["n"] == 1
    assert t_box[0] is not None

    t_box = [None]
    search_fire = fire("search", "id", "tok", t_box, uia=boom, api=fake_api)
    assert search_fire["via"] == "api" and api_calls["n"] == 2

    def already_act(t_box):
        t_box[0] = time.perf_counter()
        return {"via": "api", "dispatch_ms": 0.0, "code": 0}

    already = observe(lambda: home, home, already_act, expect="home", budget=0.04)
    assert already["visual"] == "home" and already["visual_ok"] is True and already["miss"] is False

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
        bind_console(None, read_exe=spy_exe)
        raise AssertionError("missing console pid")
    except SystemExit as ex:
        assert "console-pid" in str(ex)
    assert seen == []
    assert bind_console(1, read_exe=lambda pid: cand) == cand

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


def live(n, categories, api_only, allow_c241=False, console_pid=None, console_path=None):
    global ALLOW_C241, RUN
    ALLOW_C241 = bool(allow_c241)
    plan = phone_plan(ALLOW_C241)
    UIA_OWNS["on"] = False
    if not api_only:
        bind_console(console_pid, console_path)
    run_id = time.strftime("%Y%m%d-%H%M%S")
    dest = open_run(OUT, run_id)
    RUN = dest
    s1 = status()
    time.sleep(1.0)
    s2 = status()
    pre = {
        "frames_before": {r["name"]: r["frames"] for r in s1["receivers"]},
        "frames_after_1s": {r["name"]: r["frames"] for r in s2["receivers"]},
        "live": {r["name"]: r["live"] for r in s2["receivers"]},
        "pids": {r["name"]: r["receiver_pid"] for r in s2["receivers"]},
    }
    dump(OUT, dest, "preflight-frames.json", pre)
    print("preflight", pre, "run", dest, flush=True)
    wanted = {f"iMouse2-{name}" for name, *_ in plan}
    missing = [key for key in wanted if key not in pre["frames_before"]]
    if missing:
        raise SystemExit(f"target receiver missing: {missing}")
    if any(pre["frames_after_1s"][key] <= pre["frames_before"][key] for key in wanted):
        raise SystemExit("frames not advancing")
    ids = ",".join(pid for _, pid, *_ in plan)
    cats = categories or ["search"]
    rows = []
    if api_only:
        hold_lease(ids)
    try:
        for name, pid, oname, oid in plan:
            CONSOLE["phone"] = name
            for category in cats:
                for cycle in range(1, n + 1):
                    if api_only and HELD:
                        post("/input/renew", {"id": ",".join(HELD), "tokens": dict(HELD)})
                    row = run_cycle(name, pid, oname, oid, category, cycle, api_only, dest)
                    keep(rows, row)
                    dump(OUT, dest, "rows.json", rows)
                    print(
                        f"{name} {category} c{cycle} via={row.get('via')} "
                        f"invoked={row.get('invoked_ms')} first={row.get('first_visible_ms')} "
                        f"settled={row.get('settled_ms')} miss={row.get('miss')}",
                        flush=True,
                    )
        end = status()
        stuck = input_status()
        summary = summarize(rows)
        dump(OUT, dest, "end-status.json", {"kernel": end, "input": stuck, "summary": summary})
        dump(OUT, dest, "manifest.json", {
            "run_id": run_id,
            "phones": [name for name, *_ in plan],
            "categories": cats,
            "api_only": api_only,
            "allow_c241": ALLOW_C241,
            "console_pid": console_pid,
            "out": str(dest),
        })
        print("done", len(rows), json.dumps(summary), flush=True)
    finally:
        if HELD:
            try:
                drop_lease()
                print("released", flush=True)
            except Exception as ex:
                print("RELEASE FAILED", ex, flush=True)
                raise


def run_cycle(name, pid, oname, oid, category, cycle, api_only, dest):
    CONSOLE["phone"] = name
    # ponytail: search click needs the harness lease; don't mix it after UIA owns the console lease
    if category == "search" and not api_only and UIA_OWNS["on"]:
        raise SystemExit("console holds the lease after UIA; run search with --api-only")
    token = need_token(pid) if api_only or category == "search" else None
    if category == "search":
        before = fetch_shot(pid)

        homes = {}

        def home_act(t_box):
            t_box[0] = time.perf_counter()
            homes["a"], homes["b"] = home_pair(pid, token)
            return {"via": "api", "dispatch_ms": homes["b"], "code": 0}

        home = observe(lambda: fetch_shot(pid), before, home_act, expect="home", budget=3.0)
        before_click = home["frame"] or before

        def click_act(t_box):
            return fire("search", pid, token, t_box, api_only=True)

        click = observe(
            lambda: fetch_shot(pid), before_click, click_act, expect="search", budget=5.0, baseline=before_click
        )
        target = f"{name.lower()}-c{cycle}-search.bmp"
        other = f"{oname.lower()}-iso-during-{name.lower()}-c{cycle}.bmp"
        t_len = save_frame(target, click["frame"], dest)
        if oid == C241 and not ALLOW_C241:
            o_len = 0
        else:
            o_len = shot(oid, other, dest)
        dismiss_ms, _ = post("/key/sendkey", {"id": pid, "token": token, "fn_key": "Home"}, timeout=8)
        expect = "search"
        return {
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
            "miss": click["miss"] or home["miss"],
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
        # ponytail: after UIA owns the lease, skip API search-open; Home stays on HomeButton
        if api_only or not UIA_OWNS["on"]:
            token = need_token(pid)
            post("/mouse/click", {"id": pid, "token": token, "x": 250, "y": 900, "button": 1}, timeout=12)

            def wait_act(t_box):
                t_box[0] = time.perf_counter()
                return {"via": "wait"}

            observe(lambda: fetch_shot(pid), fetch_shot(pid), wait_act, expect="search", budget=2.0)
        before = fetch_shot(pid)
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
    target = f"{name.lower()}-c{cycle}-{category}.bmp"
    save_frame(target, obs["frame"], dest)
    if category != "home":
        if api_only or category == "search":
            token = need_token(pid)
            post("/key/sendkey", {"id": pid, "token": token, "fn_key": "Home"}, timeout=8)
        else:
            home_via(pid, None, False, n=1)
    return {
        "phone": name,
        "cycle": cycle,
        "category": category,
        "via": obs["via"],
        "fallback": obs["fallback"],
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


def main():
    p = argparse.ArgumentParser(description="Gate 6 console-action to visible-response latency")
    p.add_argument("--self-check", action="store_true")
    p.add_argument("--n", type=int, default=5, help="observations per category per phone; gate wants >= 100")
    p.add_argument("--category", action="append", choices=["search", "home", "appswitch", "controlcenter"])
    p.add_argument("--api-only", action="store_true", help="hold the lease and drive via HTTP; skip UIA")
    p.add_argument("--allow-c241", action="store_true", help="allow live commands to C241")
    p.add_argument("--console-pid", type=int, help="candidate console PID; required unless --api-only")
    p.add_argument("--console-path", help="expected console exe if it is not imouse-candidate-5")
    args = p.parse_args()
    if args.self_check:
        raise SystemExit(self_check())
    if args.n < 1:
        raise SystemExit("--n must be >= 1")
    live(args.n, args.category, args.api_only, args.allow_c241, args.console_pid, args.console_path)


if __name__ == "__main__":
    main()

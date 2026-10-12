"""Gate 10 soak with explicit live/target opt-in. Never restarts kernel or receivers."""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROTATION = ["C24C", "C241", "C214", "724E", "*"]
WINDOW_S = 600
SPOTLIGHT_MAD = 20.0  # ponytail: gate11 spotlight was 45-80, home noise <2
DISMISS_MAD = 18.0

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x2
WM_NULL = 0
SMTO_ABORTIFHUNG = 0x2


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


class FT(ctypes.Structure):
    _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]


k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32FirstW.restype = wintypes.BOOL
k32.Process32NextW.restype = wintypes.BOOL
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
k32.GetProcessTimes.restype = wintypes.BOOL
k32.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(FT), ctypes.POINTER(FT), ctypes.POINTER(FT), ctypes.POINTER(FT)]
psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
user32.SendMessageTimeoutW.restype = wintypes.BOOL
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def roll(vals: list[int]) -> dict | None:
    if not vals:
        return None
    return {"median": int(round(statistics.median(vals))), "peak": max(vals), "n": len(vals)}


def trim(points: list[dict], now: float, window: float = WINDOW_S) -> list[dict]:
    cut = now - window
    return [p for p in points if p["t"] >= cut]


def memory_roll(points: list[dict]) -> dict:
    by: dict[str, dict] = {}
    pids = {pid for p in points for pid in p["by_pid"]}
    for pid in pids:
        ws = [p["by_pid"][pid]["ws"] for p in points if pid in p["by_pid"]]
        pm = [p["by_pid"][pid]["pm"] for p in points if pid in p["by_pid"]]
        by[str(pid)] = {"working_set": roll(ws), "private": roll(pm)}
    return {
        "window_s": WINDOW_S,
        "samples": len(points),
        "total": {
            "working_set": roll([p["total_ws"] for p in points]),
            "private": roll([p["total_pm"] for p in points]),
        },
        "by_pid": by,
    }


def snapshot() -> dict[int, dict]:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value:
        return {}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    out: dict[int, dict] = {}
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        out[entry.th32ProcessID] = {"name": entry.szExeFile, "parent": entry.th32ParentProcessID}
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return out


def image_name(pid: int) -> str | None:
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    buf = ctypes.create_unicode_buffer(520)
    n = wintypes.DWORD(520)
    ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
    k32.CloseHandle(h)
    return buf.value if ok else None


def visible_titles() -> dict[int, str]:
    found: dict[int, str] = {}

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value and pid.value not in found:
            found[pid.value] = buf.value
        return True

    proc = WNDENUMPROC(cb)
    user32.EnumWindows(proc, 0)
    return found


def responding(pid: int, titles: dict[int, str]) -> bool:
    # ponytail: 400ms hung check; .NET waits 5s, too slow for a 15s sample
    title = titles.get(pid)
    if not title:
        return True
    hwnd = wintypes.HWND()
    found = {"hwnd": 0}

    def cb(handle, _lp):
        if not user32.IsWindowVisible(handle):
            return True
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(handle, buf, 256)
            if buf.value:
                found["hwnd"] = handle
                return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    if not found["hwnd"]:
        return True
    result = wintypes.DWORD()
    ok = user32.SendMessageTimeoutW(found["hwnd"], WM_NULL, 0, 0, SMTO_ABORTIFHUNG, 400, ctypes.byref(result))
    return bool(ok)


def proc_metrics(pid: int, titles: dict[int, str]) -> dict:
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return {"pid": pid, "alive": False, "responding": False}
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    mem_ok = psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    created, exited, kern, user = FT(), FT(), FT(), FT()
    time_ok = k32.GetProcessTimes(h, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kern), ctypes.byref(user))
    k32.CloseHandle(h)
    cpu = None
    if time_ok:
        cpu = round((((kern.hi << 32) | kern.lo) + ((user.hi << 32) | user.lo)) / 1e7, 3)
    return {
        "pid": pid,
        "alive": True,
        "working_set": int(pmc.WorkingSetSize) if mem_ok else None,
        "private_bytes": int(pmc.PrivateUsage) if mem_ok else None,
        "cpu_s": cpu,
        "responding": responding(pid, titles),
    }


def discover(status: dict, procs: dict[int, dict], titles: dict[int, str]) -> dict:
    receivers = status.get("receivers") or []
    rec_pids = [int(r["receiver_pid"]) for r in receivers if r.get("receiver_pid")]
    parents = {procs[p]["parent"] for p in rec_pids if p in procs}
    kernel = None
    if len(parents) == 1:
        parent = next(iter(parents))
        name = (procs.get(parent) or {}).get("name", "")
        if name.lower().startswith("imouse2.kernel"):
            kernel = parent
    consoles = [pid for pid, title in titles.items() if title.startswith("iMouse") and (procs.get(pid) or {}).get("name", "").lower() == "imouse2.exe"]
    console = pick_console(consoles, titles)
    return {"kernel_pid": kernel, "console_pid": console, "console_pids": consoles, "receivers": receivers}

def pick_console(consoles: list[int], titles: dict[int, str]) -> int | None:
    named = [pid for pid in consoles if "console" in titles.get(pid, "").lower()]
    pool = named or consoles
    return pool[0] if pool else None


def bind_fleet(base: str) -> dict[str, int]:
    ident = discover(kernel_status(base), snapshot(), visible_titles())
    kernel, console = ident["kernel_pid"], ident["console_pid"]
    if not kernel or not console:
        raise SystemExit(f"live fleet incomplete kernel={kernel} console={console}")
    return {"kernel_pid": kernel, "console_pid": console}


def http(method: str, url: str, body: dict | None = None, timeout: float = 8):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        status = resp.status
    return round((time.perf_counter() - t0) * 1000, 1), status, raw


def kernel_status(base: str) -> dict:
    _, _, raw = http("GET", base + "/kernel/status", timeout=5)
    return json.loads(raw)["data"]


def post(base: str, fun: str, payload: dict, timeout: float = 20) -> dict:
    ms, http_status, raw = http("POST", base + "/", {"fun": fun, "data": payload}, timeout=timeout)
    body = json.loads(raw)
    data = body.get("data") or {}
    return {
        "fun": fun,
        "http": http_status,
        "code": data.get("code"),
        "message": data.get("message"),
        "rtt_ms": ms,
        "results": data.get("results"),
        "leases": data.get("leases"),
        "data": data,
    }


def shot(base: str, device_id: str) -> tuple[float, bytes]:
    q = urllib.parse.quote(device_id, safe=":")
    ms, _, raw = http("GET", f"{base}/pic/screenshot?id={q}&binary=true", timeout=8)
    if not raw.startswith(b"BM"):
        raise RuntimeError(raw[:80].decode("utf-8", "replace"))
    return ms, raw


def mad(a: bytes, b: bytes) -> float:
    if not a.startswith(b"BM") or not b.startswith(b"BM"):
        return 0.0
    pa, pb = a[54:], b[54:]
    n = min(len(pa), len(pb))
    if n < 1000:
        return 0.0
    total = count = 0
    for i in range(0, n, 24):
        total += abs(pa[i] - pb[i])
        count += 1
    return round(total / count, 2) if count else 0.0


def phone_row(receivers: list[dict], label: str) -> dict | None:
    if label == "*":
        return next((r for r in receivers if r.get("deviceid") == "*"), None)
    return next((r for r in receivers if str(r.get("name", "")).endswith(label)), None)


def selected_receivers(receivers, labels):
    if not labels or len(set(labels)) != len(labels):
        raise ValueError("explicit, unique --phone names are required")
    selected = []
    for label in labels:
        matches = [row for row in receivers if row.get("name") == "iMouse2-" + label]
        if len(matches) != 1:
            raise ValueError(f"phone {label}: expected one named receiver, found {len(matches)}")
        row = matches[0]
        device = row.get("deviceid")
        if not isinstance(device, str) or not device or device == "*" or device.startswith("unbound-"):
            raise ValueError(f"phone {label}: unresolved device binding")
        selected.append(row)
    if len({row["deviceid"] for row in selected}) != len(selected):
        raise ValueError("two selected receivers share a device binding")
    return selected


def read_input_status(base):
    ms, status, raw = http("GET", base + "/input/status", timeout=5)
    reply = json.loads(raw)
    data = reply.get("data") if isinstance(reply, dict) else None
    if status != 200 or not isinstance(reply, dict) or reply.get("code") not in (None, 0) or not isinstance(data, dict) or data.get("code") != 0:
        raise RuntimeError("input status unavailable or unsuccessful")
    phones = data.get("phones")
    if not isinstance(phones, list) or any(not isinstance(row, dict) for row in phones):
        raise RuntimeError("invalid input status")
    return ms, phones


def require_ready(phones, ids):
    for device in ids:
        rows = [row for row in phones if row.get("id") == device]
        if len(rows) != 1:
            raise RuntimeError(f"input status missing or ambiguous for {device}")
        row = rows[0]
        blocked = [key for key in ("owned", "active", "stopped", "releasing", "release_failed") if row.get(key) is not False]
        if blocked:
            raise RuntimeError(f"phone {device} is not ready ({', '.join(blocked)}); no takeover or automatic Resume")


def tokens_for(call: dict) -> dict[str, str]:
    return {row["id"]: row["token"] for row in call.get("leases") or [] if row.get("token")}


def call_succeeded(call):
    results = call.get("results")
    return call.get("code") == 0 and call.get("http") in (None, 200) and (
        results is None or isinstance(results, list) and all(isinstance(row, dict) and row.get("code") == 0 for row in results))


def send(base: str, fun: str, payload: dict, ids: str, tokens: dict[str, str]) -> dict:
    body = {"id": ids, "tokens": {i: tokens[i] for i in ids.split(",")}, **payload}
    result = post(base, fun, body, timeout=20)
    if not call_succeeded(result):
        raise RuntimeError(f"{fun} refused or failed; outcome unknown, no retry")
    return result


def poll_shot(base: str, device_id: str, before: bytes, threshold: float, budget: float) -> tuple[bytes, float, float]:
    deadline = time.perf_counter() + budget
    last = before
    score = 0.0
    ms = 0.0
    while True:
        ms, last = shot(base, device_id)
        score = mad(before, last)
        if score >= threshold or time.perf_counter() >= deadline:
            return last, score, ms
        time.sleep(0.25)


def interact(base: str, receivers: list[dict], label: str, out: Path, cycle: int) -> dict:
    t0 = time.perf_counter()
    row: dict = {"kind": "interaction", "at": utc(), "cycle": cycle, "target": label, "ok": False}
    target = phone_row(receivers, label)
    if not target:
        row["error"] = "target missing from kernel status"
        row["latency_s"] = round(time.perf_counter() - t0, 3)
        return row
    ids = [r["deviceid"] for r in receivers]
    group = ",".join(ids)
    device_id = target["deviceid"]
    tokens: dict[str, str] = {}
    try:
        status_ms, phones = read_input_status(base)
        row["input_status_ms"] = status_ms
        require_ready(phones, ids)
        acquired = post(base, "/input/acquire", {"id": group, "lease_ms": 60000}, timeout=8)
        returned = tokens_for(acquired)
        tokens = {device: token for device, token in returned.items() if device in ids}
        row["acquire_code"] = acquired["code"]
        row["acquire_ms"] = acquired["rtt_ms"]
        if acquired["code"] != 0 or set(returned) != set(ids):
            row["error"] = acquired.get("message") or "acquire failed"
            return row
        send(base, "/mouse/reset", {}, device_id, tokens)
        home = send(base, "/key/sendkey", {"fn_key": "Home"}, device_id, tokens)
        time.sleep(0.8)
        _, home_bmp = shot(base, device_id)
        t_click = time.perf_counter()
        click = send(base, "/mouse/click", {"x": 250, "y": 900, "button": 1}, device_id, tokens)
        spot, spot_mad, shot_ms = poll_shot(base, device_id, home_bmp, SPOTLIGHT_MAD, 2.8)
        opened = spot_mad >= SPOTLIGHT_MAD
        dismiss = send(base, "/key/sendkey", {"fn_key": "Home"}, device_id, tokens)
        after, dismiss_mad, _ = poll_shot(base, device_id, spot, DISMISS_MAD, 3.0)
        dismissed = opened and dismiss_mad >= DISMISS_MAD
        t_group = time.perf_counter()
        group_home = send(base, "/key/sendkey", {"fn_key": "Home"}, group, tokens)
        time.sleep(0.5)

        def one(device: str):
            try:
                ms, raw = shot(base, device)
                return device, {"ok": raw.startswith(b"BM"), "bytes": len(raw), "shot_ms": ms}
            except Exception as ex:
                return device, {"ok": False, "error": str(ex)}

        with ThreadPoolExecutor(max_workers=5) as pool:
            group_shots = dict(pool.map(one, ids))
        if cycle == 0 or not opened or not dismissed:
            shots = out / "shots"
            shots.mkdir(exist_ok=True)
            slug = "phone5" if label == "*" else label.lower()
            (shots / f"c{cycle}-{slug}-spotlight.bmp").write_bytes(spot)
            (shots / f"c{cycle}-{slug}-dismiss.bmp").write_bytes(after)
        row.update({
            "ok": bool(opened and dismissed and group_home["code"] == 0 and all(v.get("ok") for v in group_shots.values())),
            "home_rtt_ms": home["rtt_ms"],
            "click_rtt_ms": click["rtt_ms"],
            "click_code": click["code"],
            "click_results": click.get("results"),
            "spotlight_mad": spot_mad,
            "spotlight_open": opened,
            "spotlight_shot_ms": shot_ms,
            "click_to_shot_ms": round((time.perf_counter() - t_click) * 1000, 1),
            "dismiss_rtt_ms": dismiss["rtt_ms"],
            "dismiss_mad": dismiss_mad,
            "dismissed": dismissed,
            "group_home_rtt_ms": group_home["rtt_ms"],
            "group_home_code": group_home["code"],
            "group_home_results": group_home.get("results"),
            "group_home_ms": round((time.perf_counter() - t_group) * 1000, 1),
            "group_shots": group_shots,
        })
    except Exception as ex:
        row["error"] = str(ex)
    finally:
        if tokens:
            try:
                row["release"] = post(base, "/input/release", {"id": ",".join(tokens), "tokens": tokens}, timeout=8)
            except Exception as ex:
                row["release"] = {"code": -1, "message": str(ex)}
        row["latency_s"] = round(time.perf_counter() - t0, 3)
    return row


def sample(base: str, prev_frames: dict, prev_cpu: dict, mem: list[dict], started: float, expected: dict) -> dict:
    now_m = time.monotonic()
    titles = visible_titles()
    procs = snapshot()
    err = None
    status: dict = {}
    try:
        status = kernel_status(base)
    except Exception as ex:
        err = str(ex)
    ident = discover(status, procs, titles) if status else {"kernel_pid": None, "console_pid": None, "console_pids": [], "receivers": []}
    watched = []
    if ident["kernel_pid"]:
        watched.append((ident["kernel_pid"], "kernel", None))
    for pid in ident["console_pids"]:
        watched.append((pid, "console", None))
    for rec in ident["receivers"]:
        if rec.get("receiver_pid"):
            watched.append((int(rec["receiver_pid"]), "receiver", rec.get("deviceid")))
    metrics = []
    by_pid = {}
    for pid, role, device_id in watched:
        row = proc_metrics(pid, titles)
        row["role"] = role
        row["name"] = (procs.get(pid) or {}).get("name")
        if device_id:
            row["deviceid"] = device_id
        prev = prev_cpu.get(pid)
        if row.get("cpu_s") is not None and prev is not None:
            row["cpu_delta_s"] = round(row["cpu_s"] - prev, 3)
        if row.get("cpu_s") is not None:
            prev_cpu[pid] = row["cpu_s"]
        metrics.append(row)
        if row.get("alive") and row.get("working_set") is not None:
            by_pid[pid] = {"ws": row["working_set"], "pm": row["private_bytes"] or 0}
    receivers = []
    for rec in ident["receivers"]:
        did = rec.get("deviceid")
        frames = rec.get("frames")
        delta = None if frames is None or did not in prev_frames else frames - prev_frames[did]
        if frames is not None:
            prev_frames[did] = frames
        receivers.append({
            "deviceid": did,
            "name": rec.get("name"),
            "receiver_pid": rec.get("receiver_pid"),
            "receiver_restarts": rec.get("receiver_restarts"),
            "receiver_state": rec.get("receiver_state"),
            "live": rec.get("live"),
            "frames": frames,
            "frame_delta": delta,
        })
    point = {
        "t": now_m,
        "total_ws": sum(v["ws"] for v in by_pid.values()),
        "total_pm": sum(v["pm"] for v in by_pid.values()),
        "by_pid": by_pid,
    }
    mem.append(point)
    del mem[:-240]
    window = trim(mem, now_m)
    return {
        "kind": "sample",
        "at": utc(),
        "elapsed_s": round(now_m - started, 1),
        "logical_cpus": os.cpu_count(),
        "error": err,
        "kernel_pid": ident["kernel_pid"],
        "console_pid": ident["console_pid"],
        "console_pids": ident["console_pids"],
        "fleet_match": ident["kernel_pid"] == expected.get("kernel_pid") and ident["console_pid"] == expected.get("console_pid"),
        "receivers": receivers,
        "processes": metrics,
        "memory_10m": memory_roll(window),
    }


def write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def status_doc(sample_row: dict, args, started_at: str, started: float, n_sample: int, n_interact: int, last_ix: dict | None, rotate: int, expected: dict) -> dict:
    now_m = time.monotonic()
    duration = args.duration_hours * 3600
    phones = []
    for rec in sample_row.get("receivers") or []:
        label = "*" if rec.get("deviceid") == "*" else str(rec.get("name", "")).rsplit("-", 1)[-1]
        phones.append({**rec, "label": label})
    return {
        "gate": 10,
        "operator": "Grok 4.7",
        "running": True,
        "pid": os.getpid(),
        "started_at": started_at,
        "at": utc(),
        "elapsed_s": round(now_m - started, 1),
        "remaining_s": round(max(0, duration - (now_m - started)), 1),
        "duration_s": duration,
        "schedule": {
            "sample_interval_s": args.sample_interval,
            "interaction_interval_s": args.interaction_interval,
            "memory_window_s": WINDOW_S,
            "rotation": args.phone,
            "next_target": ROTATION[rotate % len(ROTATION)],
        },
        "samples": n_sample,
        "interactions": n_interact,
        "kernel_pid": sample_row.get("kernel_pid"),
        "console_pid": sample_row.get("console_pid"),
        "console_pids": sample_row.get("console_pids"),
        "fleet_match": sample_row.get("fleet_match"),
        "expected": expected,
        "phones": phones,
        "processes": sample_row.get("processes"),
        "memory_10m": sample_row.get("memory_10m"),
        "last_interaction": last_ix,
        "error": sample_row.get("error"),
    }


def refuse_second(pidfile: Path) -> None:
    if not pidfile.exists():
        return
    try:
        old = int(pidfile.read_text().strip())
    except ValueError:
        pidfile.unlink(missing_ok=True)
        return
    name = image_name(old) or ""
    if "python" in name.lower():
        raise SystemExit(f"soak already running pid {old}")
    pidfile.unlink(missing_ok=True)


def release_pid_marker(pidfile):
    if pidfile.is_file() and pidfile.read_text(encoding="utf-8").strip() == str(os.getpid()):
        pidfile.unlink()


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--duration-hours", type=float, default=8)
    p.add_argument("--sample-interval", type=float, default=15)
    p.add_argument("--interaction-interval", type=float, default=300)
    p.add_argument("--url", default="http://127.0.0.1:9913/api")
    p.add_argument("--out", default=str(ROOT / "analysis" / "gate10-endurance-20260916"))
    p.add_argument("--self-check", action="store_true")
    p.add_argument("--live", action="store_true", help="explicitly opt in to a coordinated hardware run")
    p.add_argument("--phone", action="append", help="approved receiver suffix, e.g. C24C; repeat for group members")
    args = p.parse_args(argv)
    if args.self_check:
        assert roll([1, 3, 5]) == {"median": 3, "peak": 5, "n": 3}
        kept = trim([{"t": 100}, {"t": 500}, {"t": 900}], 1000, 600)
        assert [x["t"] for x in kept] == [500, 900]
        assert pick_console([1, 2], {1: "iMouse", 2: "iMouse 2.0 — iPhone Console"}) == 2
        assert pick_console([9], {9: "iMouse"}) == 9
        assert pick_console([], {}) is None
        me = proc_metrics(os.getpid(), {})
        assert me["alive"] and me["working_set"] > 0
        print("self-check ok", me["working_set"])
        return 0
    if not args.live or not args.phone:
        p.error("hardware runs require --live and explicit --phone names")
    if len(set(args.phone)) != len(args.phone):
        p.error("--phone names must be unique")
    if any(not math.isfinite(value) or value <= 0 for value in (args.duration_hours, args.sample_interval, args.interaction_interval)):
        p.error("duration and intervals must be finite and positive")
    out = Path(args.out)
    if any((out / name).exists() for name in ("telemetry.jsonl", "status.json")):
        p.error("output contains prior evidence; use a new empty run directory")
    out.mkdir(parents=True, exist_ok=True)
    pidfile = out / "soak.pid"
    refuse_second(pidfile)
    expected = bind_fleet(args.url)
    approved = selected_receivers(kernel_status(args.url).get("receivers") or [], args.phone)
    approved_ids = {row["name"]: row["deviceid"] for row in approved}
    _, phones = read_input_status(args.url)
    require_ready(phones, approved_ids.values())
    with pidfile.open("x", encoding="utf-8") as marker:
        marker.write(str(os.getpid()))
    log_path = out / "telemetry.jsonl"
    status_path = out / "status.json"
    started = time.monotonic()
    started_at = utc()
    end = started + args.duration_hours * 3600
    next_sample = started
    next_ix = started
    rotate = 0
    n_sample = 0
    n_ix = 0
    last_ix = None
    last_sample = {}
    prev_frames: dict = {}
    prev_cpu: dict = {}
    mem: list[dict] = []
    try:
        log = log_path.open("x", encoding="utf-8", buffering=1)
    except BaseException:
        release_pid_marker(pidfile)
        raise
    print(f"soak pid={os.getpid()} duration_h={args.duration_hours} out={out}", flush=True)
    failure = None
    try:
        while time.monotonic() < end:
            now = time.monotonic()
            if now >= next_sample:
                last_sample = sample(args.url, prev_frames, prev_cpu, mem, started, expected)
                log.write(json.dumps(last_sample) + "\n")
                n_sample += 1
                write_json(status_path, status_doc(last_sample, args, started_at, started, n_sample, n_ix, last_ix, rotate, expected))
                print(f"sample {n_sample} phones={len(last_sample.get('receivers') or [])} kernel={last_sample.get('kernel_pid')}", flush=True)
                if last_sample.get("error") or last_sample.get("fleet_match") is not True:
                    raise RuntimeError("fleet sampling failed or identity mismatched; recorded, no input sent")
                next_sample = now + args.sample_interval
            if time.monotonic() >= next_ix:
                try:
                    receivers = kernel_status(args.url).get("receivers") or []
                except Exception as ex:
                    receivers = []
                    print("status before interact failed", ex, flush=True)
                selected = selected_receivers(receivers, args.phone)
                if {row["name"]: row["deviceid"] for row in selected} != approved_ids:
                    raise RuntimeError("phone binding changed during the run; no input sent")
                label = args.phone[rotate % len(args.phone)]
                last_ix = interact(args.url, selected, label, out, n_ix)
                last_ix["elapsed_s"] = round(time.monotonic() - started, 1)
                log.write(json.dumps(last_ix) + "\n")
                n_ix += 1
                rotate += 1
                if last_sample:
                    write_json(status_path, status_doc(last_sample, args, started_at, started, n_sample, n_ix, last_ix, rotate, expected))
                print(f"interact {n_ix} target={label} ok={last_ix.get('ok')} spotlight={last_ix.get('spotlight_open')}", flush=True)
                if not last_ix.get("ok") or not call_succeeded(last_ix.get("release") or {}):
                    raise RuntimeError("interaction failed or release unconfirmed; saved result, no retry or automatic Resume")
                next_ix = time.monotonic() + args.interaction_interval
            delay = min(next_sample, next_ix, end) - time.monotonic()
            if delay > 0:
                time.sleep(delay)
    except BaseException as exc:
        failure = str(exc)
        raise
    finally:
        try:
            log.close()
            if last_sample:
                doc = status_doc(last_sample, args, started_at, started, n_sample, n_ix, last_ix, rotate, expected)
                doc["running"] = False
                doc["stop_reason"] = "failure" if failure else ("duration" if time.monotonic() >= end else "exit")
                doc["failure"] = failure
                write_json(status_path, doc)
        finally:
            release_pid_marker(pidfile)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""45-minute C24C-only stability loop. Logs to analysis/stability-c24c/. Prints DONE/FAILED only."""
from __future__ import annotations

import json, os, subprocess, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ID = "86:1D:4A:04:2F:F6"
BOARD = "C24C"
UID = "C24CBFBD"
BASE = "http://127.0.0.1:9913/api"
DURATION_S = 45 * 60
INTERVAL_S = 3 * 60
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "stability-c24c"
LOG = OUT / "run.jsonl"
SUMMARY = OUT / "summary.json"
SHOTS = OUT / "shots"

KERNEL_PID = 39096
CONSOLE_PID = 16672


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(row: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def http_json(method: str, url: str, body: dict | None = None, timeout: int = 20) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def screenshot(path: Path) -> bytes:
    url = f"{BASE}/pic/screenshot?id={ID}&binary=true"
    with urllib.request.urlopen(url, timeout=8) as resp:
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    if b"BM" != raw[:2]:
        raise RuntimeError(f"not bmp {ctype} {raw[:120]!r}")
    path.write_bytes(raw)
    return raw


def send(fun: str, data: dict) -> None:
    j = http_json("POST", BASE + "/", {"fun": fun, "data": data}, timeout=40)
    if j.get("status") != 200 or (j.get("data") or {}).get("code") != 0:
        raise RuntimeError(f"{fun} {j}")


def mad(a: bytes, b: bytes) -> float:
    pa, pb = a[54:], b[54:]
    n = min(len(pa), len(pb))
    if n < 1000:
        return 0.0
    step = 24
    total = 0
    count = 0
    for i in range(0, n, step):
        total += abs(pa[i] - pb[i])
        count += 1
    return total / count


def proc(pid: int) -> dict | None:
    cmd = [
        "powershell", "-NoProfile", "-Command",
        f"$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue;"
        "if($p){ @{Id=$p.Id; Name=$p.ProcessName; WS=[int64]$p.WorkingSet64; PM=[int64]$p.PagedMemorySize64} | ConvertTo-Json }"
        "else { '{}' }",
    ]
    raw = subprocess.check_output(cmd, text=True).strip()
    if not raw or raw == "{}":
        return None
    return json.loads(raw)


def uxplay() -> dict | None:
    cmd = [
        "powershell", "-NoProfile", "-Command",
        "Get-Process uxplay -ErrorAction SilentlyContinue | Select-Object -First 1 Id,ProcessName,@{n='WS';e={[int64]$_.WorkingSet64}} | ConvertTo-Json",
    ]
    raw = subprocess.check_output(cmd, text=True).strip()
    if not raw:
        return None
    return json.loads(raw)


def identity_ok(dev: dict) -> str | None:
    if dev.get("deviceid") != ID:
        return f"unexpected device {dev.get('deviceid')}"
    if dev.get("pid") != BOARD or dev.get("uid") != UID:
        return f"bind {dev.get('pid')}/{dev.get('uid')}"
    return None


def cycle(i: int, prev_frames: int) -> dict:
    row: dict = {"t": utc(), "cycle": i, "ok": True, "failures": []}
    st = http_json("GET", BASE + "/kernel/status")["data"]
    dev = http_json("GET", BASE + "/device/get")["data"]["list"][0]
    row["status"] = st
    row["device"] = {"pid": dev.get("pid"), "uid": dev.get("uid"), "state": dev.get("state"), "video_state": dev.get("video_state")}
    bad = identity_ok(dev)
    if bad:
        row["failures"].append(bad)
    k = proc(KERNEL_PID)
    c = proc(CONSOLE_PID)
    u = uxplay()
    row["procs"] = {"kernel": k, "console": c, "uxplay": u}
    if k is None:
        row["failures"].append("kernel process gone")
    if c is None:
        row["failures"].append("console process gone")
    if not st.get("live"):
        row["failures"].append("video not live")
    frames = int(st.get("frames") or 0)
    row["frames"] = frames
    row["frame_delta"] = frames - prev_frames if prev_frames else None
    if prev_frames and st.get("live") and frames <= prev_frames:
        row["failures"].append(f"frame stall {prev_frames}->{frames}")
    row["restarts"] = st.get("receiver_restarts")

    send("/key/sendkey", {"id": ID, "fn_key": "Home"})
    time.sleep(0.9)
    home = screenshot(SHOTS / f"{i:02d}-home.bmp")
    send("/mouse/click", {"id": ID, "x": 250, "y": 900, "button": 1})
    time.sleep(1.1)
    search = screenshot(SHOTS / f"{i:02d}-search.bmp")
    search_mad = mad(home, search)
    row["search_mad"] = round(search_mad, 2)
    if search_mad < 8:
        row["failures"].append(f"search click did not change screen mad={search_mad:.1f}")
    send("/key/sendkey", {"id": ID, "fn_key": "Home"})
    time.sleep(0.9)
    home2 = screenshot(SHOTS / f"{i:02d}-home2.bmp")
    send("/mouse/swipe", {"id": ID, "direction": "left", "len": 0.75, "duration": 400})
    time.sleep(1.0)
    left = screenshot(SHOTS / f"{i:02d}-swipe-left.bmp")
    left_mad = mad(home2, left)
    row["swipe_left_mad"] = round(left_mad, 2)
    if left_mad < 6:
        row["failures"].append(f"swipe left did not change screen mad={left_mad:.1f}")
    send("/mouse/swipe", {"id": ID, "direction": "right", "len": 0.75, "duration": 400})
    time.sleep(1.0)
    back = screenshot(SHOTS / f"{i:02d}-swipe-back.bmp")
    back_mad = mad(home2, back)
    row["swipe_back_mad"] = round(back_mad, 2)
    send("/key/sendkey", {"id": ID, "fn_key": "Home"})
    time.sleep(0.6)
    if row["failures"]:
        row["ok"] = False
    return row


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    if LOG.exists():
        LOG.unlink()
    start = time.time()
    cycles = []
    prev_frames = 0
    start_restarts = None
    start_mem = None
    i = 0
    try:
        while True:
            row = cycle(i, prev_frames)
            cycles.append(row)
            log(row)
            prev_frames = int(row.get("frames") or 0)
            if start_restarts is None:
                start_restarts = row.get("restarts")
            if start_mem is None and row["procs"]["kernel"]:
                start_mem = row["procs"]["kernel"]["WS"]
            fatal = [f for f in row["failures"] if f.startswith("kernel") or f.startswith("console") or "bind" in f]
            if fatal:
                summary(cycles, start, start_restarts, start_mem, False, fatal[0])
                print("FAILED: " + fatal[0])
                return 1
            elapsed = time.time() - start
            if elapsed >= DURATION_S:
                break
            sleep_for = INTERVAL_S - (elapsed % INTERVAL_S)
            if sleep_for < 5:
                sleep_for += INTERVAL_S
            # Stay on home between cycles.
            time.sleep(min(sleep_for, INTERVAL_S))
            i += 1
            if time.time() - start >= DURATION_S:
                break
    except Exception as ex:
        log({"t": utc(), "error": str(ex)})
        summary(cycles, start, start_restarts, start_mem, False, str(ex))
        print("FAILED: " + str(ex))
        return 1
    ok = all(c.get("ok") for c in cycles) and len(cycles) >= 10
    reason = "all cycles passed" if ok else "one or more cycles failed"
    summary(cycles, start, start_restarts, start_mem, ok, reason)
    print(("DONE: " if ok else "FAILED: ") + reason + f" cycles={len(cycles)}")
    return 0 if ok else 1


def summary(cycles, start, start_restarts, start_mem, ok, reason):
    kernel_ws = [c["procs"]["kernel"]["WS"] for c in cycles if c.get("procs", {}).get("kernel")]
    ux_ws = [c["procs"]["uxplay"]["WS"] for c in cycles if c.get("procs", {}).get("uxplay")]
    fails = [c for c in cycles if not c.get("ok")]
    restarts = [c.get("restarts") for c in cycles]
    out = {
        "started": datetime.fromtimestamp(start, timezone.utc).isoformat(),
        "ended": utc(),
        "duration_s": round(time.time() - start, 1),
        "cycles": len(cycles),
        "passed": sum(1 for c in cycles if c.get("ok")),
        "failed_cycles": [c["cycle"] for c in fails],
        "reason": reason,
        "ready_for_two_phone": bool(ok and not fails),
        "kernel_pid_expected": KERNEL_PID,
        "console_pid_expected": CONSOLE_PID,
        "receiver_restarts": {"start": start_restarts, "end": restarts[-1] if restarts else None},
        "memory": {
            "kernel_ws_start": kernel_ws[0] if kernel_ws else None,
            "kernel_ws_end": kernel_ws[-1] if kernel_ws else None,
            "kernel_ws_max": max(kernel_ws) if kernel_ws else None,
            "uxplay_ws_max": max(ux_ws) if ux_ws else None,
        },
        "search_mad": [c.get("search_mad") for c in cycles],
        "swipe_left_mad": [c.get("swipe_left_mad") for c in cycles],
        "failures": [c["failures"] for c in fails],
        "ok": ok,
    }
    SUMMARY.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

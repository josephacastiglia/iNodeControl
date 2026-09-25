"""Video-only alternating master windows, then timed screenshots, then Search visuals."""
from __future__ import annotations

import json, re, subprocess, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "c241-master-20260915"
PS = ROOT / "tools" / "read_ui.ps1"
BASE = "http://127.0.0.1:9913/api"
PHONES = [
    ("C24C", "86:1D:4A:04:2F:F6", "XR C24C"),
    ("C241", "FE:A9:BC:D7:A0:44", "Phone in hand - C241"),
]
FPS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*fps", re.I)
GAP_RE = re.compile(r"(\d+)/(\d+)\s*ms")
SLOW_RE = re.compile(r"(\d+)\s*slow", re.I)


def api(method, url, body=None, timeout=40):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    return time.perf_counter() - t0, ctype, raw


def status():
    _, _, raw = api("GET", BASE + "/kernel/status")
    return json.loads(raw)["data"]


def recs(st):
    return {r["deviceid"]: r for r in st["receivers"]}


def send(phone_id, fun, **data):
    elapsed, _, raw = api("POST", BASE + "/", {"fun": fun, "data": {"id": phone_id, **data}})
    j = json.loads(raw)
    if j.get("status") != 200 or j["data"].get("code") != 0:
        raise RuntimeError(raw.decode())
    return elapsed


def shot(phone_id):
    elapsed, ctype, raw = api("GET", f"{BASE}/pic/screenshot?id={phone_id}&binary=true", timeout=8)
    if raw[:2] != b"BM":
        raise RuntimeError("not bmp")
    return elapsed, raw


def ui(action="read", select=""):
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS), "-Action", action]
    if select:
        cmd += ["-Select", select]
    raw = subprocess.check_output(cmd, text=True).strip()
    return json.loads(raw)


def parse_frame(text: str) -> dict:
    fps = FPS_RE.search(text or "")
    gap = GAP_RE.search(text or "")
    slow = SLOW_RE.search(text or "")
    return {
        "displayed_fps": float(fps.group(1)) if fps else None,
        "p50_ms": int(gap.group(1)) if gap else None,
        "p95_ms": int(gap.group(2)) if gap else None,
        "slow": int(slow.group(1)) if slow else None,
        "raw": text,
    }


def home_both():
    for _, pid, _ in PHONES:
        send(pid, "/key/sendkey", fn_key="Home")
        time.sleep(0.35)


def video_window(master_tag, master_id, label, seconds=20):
    ui("read", select=label)
    time.sleep(1.0)
    s0 = recs(status())
    t0 = time.perf_counter()
    reads = []
    while time.perf_counter() - t0 < seconds:
        u = ui()
        reads.append({"t": round(time.perf_counter() - t0, 2), **parse_frame(u.get("frame", "")), "selected": u.get("selected")})
        time.sleep(1.15)
    s1 = recs(status())
    dt = time.perf_counter() - t0
    shown = [r["displayed_fps"] for r in reads if r["displayed_fps"] is not None]
    received = {}
    for tag, pid, _ in PHONES:
        received[tag] = {
            "received_fps": round((s1[pid]["frames"] - s0[pid]["frames"]) / dt, 2),
            "delta": s1[pid]["frames"] - s0[pid]["frames"],
            "restarts": s1[pid]["receiver_restarts"],
            "live": s1[pid]["live"],
        }
    return {
        "master": master_tag,
        "selected": label,
        "duration_s": round(dt, 2),
        "note": "displayed_fps is RateMeter over ~2s of unique Present() calls; received_fps is all pipe frames in this whole window",
        "received": received,
        "displayed_mean": round(sum(shown) / len(shown), 2) if shown else None,
        "displayed_min": min(shown) if shown else None,
        "displayed_max": max(shown) if shown else None,
        "displayed_n": len(shown),
        "p50_ms": [r["p50_ms"] for r in reads if r["p50_ms"] is not None],
        "p95_ms": [r["p95_ms"] for r in reads if r["p95_ms"] is not None],
        "reads": reads,
    }


def screenshot_timings(master_tag, label, n=12):
    ui("read", select=label)
    time.sleep(0.5)
    rows = []
    for tag, pid, _ in PHONES:
        times = []
        for _i in range(n):
            elapsed, raw = shot(pid)
            times.append(round(elapsed * 1000, 1))
        rows.append({"master": master_tag, "target": tag, "n": n, "ms": times, "mean_ms": round(sum(times) / len(times), 1), "max_ms": max(times)})
    return rows


def search_visual(tag, phone_id, other_id, n):
    send(phone_id, "/key/sendkey", fn_key="Home")
    time.sleep(0.9)
    _, before = shot(phone_id)
    _, other_before = shot(other_id)
    t0 = time.perf_counter()
    api_s = send(phone_id, "/mouse/click", x=250, y=900, button=1)
    time.sleep(0.45)
    _, after = shot(phone_id)
    _, other_after = shot(other_id)
    path = OUT / f"search-{tag}-{n}-after.bmp"
    path.write_bytes(after)
    (OUT / f"search-{tag}-{n}-before.bmp").write_bytes(before)
    return {
        "phone": tag,
        "api_ms": round(api_s * 1000, 1),
        "shot_after_ms": round((time.perf_counter() - t0) * 1000, 1),
        "after_path": str(path),
        "other_unchanged_hint_mad": None,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    opened = ui("activity")
    if not opened.get("frame"):
        raise SystemExit("open Activity first: FrameStatus empty")
    home_both()
    time.sleep(0.8)

    order = ["C24C", "C241", "C24C", "C241"]
    windows = []
    for i, tag in enumerate(order):
        pid = next(p for t, p, _ in PHONES if t == tag)
        label = next(l for t, p, l in PHONES if t == tag)
        home_both()
        time.sleep(0.5)
        row = video_window(tag, pid, label, 20)
        row["seq"] = i
        windows.append(row)
        print(json.dumps({k: row[k] for k in row if k != "reads"}))

    timings = []
    for tag in ("C24C", "C241"):
        label = next(l for t, p, l in PHONES if t == tag)
        timings.extend(screenshot_timings(tag, label, 10))
        print("shot", timings[-2:])

    searches = []
    # C24C master, Search on each phone separately
    ui("read", select="XR C24C")
    searches.append(search_visual("C24C", PHONES[0][1], PHONES[1][1], 0))
    time.sleep(0.4)
    send(PHONES[0][1], "/key/sendkey", fn_key="Home")
    time.sleep(0.6)
    searches.append(search_visual("C241-while-C24C-master", PHONES[1][1], PHONES[0][1], 0))
    send(PHONES[1][1], "/key/sendkey", fn_key="Home")
    time.sleep(0.5)
    ui("read", select="Phone in hand - C241")
    time.sleep(0.8)
    searches.append(search_visual("C241-while-C241-master", PHONES[1][1], PHONES[0][1], 1))
    send(PHONES[1][1], "/key/sendkey", fn_key="Home")

    out = {
        "video_windows": windows,
        "screenshot_ms": timings,
        "searches": searches,
        "displayed_note": "FrameStatus displayed_fps is unique Present() marks in a ~2s window; it does not count duplicate BMPs. received_fps counts every pipe frame over the whole ~20s window.",
    }
    (OUT / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", OUT / "results.json")


if __name__ == "__main__":
    main()

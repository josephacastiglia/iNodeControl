"""Displayed FPS via Activity FrameStatus vs received FPS; concurrent input-to-visible."""
from __future__ import annotations

import json, re, subprocess, threading, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "display-latency-20260915"
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


def mad(a, b):
    pa, pb = a[54:], b[54:]
    n = min(len(pa), len(pb))
    step = 24
    total = count = 0
    for i in range(0, n, step):
        total += abs(pa[i] - pb[i])
        count += 1
    return total / count if count else 0


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


def sample_both(tag, label, seconds=18):
    ui("read", select=label)
    time.sleep(0.8)
    s0 = recs(status())
    t0 = time.perf_counter()
    reads = []
    while time.perf_counter() - t0 < seconds:
        u = ui()
        reads.append({"t": round(time.perf_counter() - t0, 2), **parse_frame(u.get("frame", "")), "selected": u.get("selected")})
        time.sleep(1.1)
    s1 = recs(status())
    dt = time.perf_counter() - t0
    shown = [r["displayed_fps"] for r in reads if r["displayed_fps"] is not None]
    received = {}
    for _, pid, _ in PHONES:
        received[pid] = {
            "name": s1[pid]["name"],
            "received_fps": round((s1[pid]["frames"] - s0[pid]["frames"]) / dt, 2),
            "delta": s1[pid]["frames"] - s0[pid]["frames"],
            "restarts": s1[pid]["receiver_restarts"],
        }
    return {
        "master": tag,
        "selected": label,
        "duration_s": round(dt, 2),
        "received": received,
        "displayed_mean": round(sum(shown) / len(shown), 2) if shown else None,
        "displayed_min": min(shown) if shown else None,
        "displayed_max": max(shown) if shown else None,
        "p50_ms": [r["p50_ms"] for r in reads if r["p50_ms"] is not None],
        "p95_ms": [r["p95_ms"] for r in reads if r["p95_ms"] is not None],
        "reads": reads,
    }


def input_trial(tag, phone_id, other_id, n, kind):
    send(phone_id, "/key/sendkey", fn_key="Home")
    time.sleep(0.9)
    before_self = shot(phone_id)[1]
    before_other = shot(other_id)[1]
    if kind == "home":
        send(phone_id, "/mouse/click", x=250, y=900, button=1)
        time.sleep(1.0)
        before_self = shot(phone_id)[1]
    polls = []
    stop = threading.Event()

    def poller():
        last = before_self
        t0 = t_send[0]
        while not stop.is_set():
            try:
                fetch, frame = shot(phone_id)
            except Exception:
                continue
            now = time.perf_counter()
            polls.append({
                "ms": round((now - t0) * 1000, 1),
                "fetch_ms": round(fetch * 1000, 1),
                "mad_from_start": round(mad(before_self, frame), 2),
                "mad_from_prev": round(mad(last, frame), 2),
            })
            last = frame

    t_send = [0.0]
    th = threading.Thread(target=poller, daemon=True)
    t_send[0] = time.perf_counter()
    th.start()
    if kind == "search":
        api_s = send(phone_id, "/mouse/click", x=250, y=900, button=1)
    elif kind == "home":
        api_s = send(phone_id, "/key/sendkey", fn_key="Home")
    else:
        api_s = send(phone_id, "/mouse/swipe", direction="left", len=0.75, duration=400)
    time.sleep(0.45)
    stop.set()
    th.join(timeout=2)
    api_return = api_s * 1000
    first = next((p["ms"] for p in polls if p["mad_from_start"] >= (8 if kind == "swipe" else 18)), None)
    settled = None
    if first is not None:
        low = 0
        for p in polls:
            if p["ms"] < first:
                continue
            if p["mad_from_prev"] < 2.5:
                low += 1
                if low >= 2:
                    settled = p["ms"]
                    break
            else:
                low = 0
    if kind == "search":
        send(phone_id, "/key/sendkey", fn_key="Home")
        time.sleep(0.5)
    elif kind == "swipe":
        send(phone_id, "/mouse/swipe", direction="right", len=0.75, duration=400)
        time.sleep(0.6)
        send(phone_id, "/key/sendkey", fn_key="Home")
        time.sleep(0.4)
    after = polls[-1] if polls else None
    other_after = shot(other_id)[1]
    return {
        "phone": tag,
        "kind": kind,
        "n": n,
        "api_ms": round(api_return, 1),
        "first_visible_ms": first,
        "settled_ms": settled,
        "other_mad": round(mad(before_other, other_after), 2),
        "poll_count": len(polls),
        "polls": polls[:40],
        "last_mad": None if after is None else after["mad_from_start"],
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    opened = ui("activity")
    (OUT / "uia-after-activity.json").write_text(json.dumps(opened, indent=2), encoding="utf-8")
    if not opened.get("frame"):
        raise SystemExit("FrameStatus still empty after opening Activity")

    fps = []
    for tag, phone_id, label in PHONES:
        row = sample_both(tag, label, 18)
        fps.append(row)
        print(json.dumps({k: row[k] for k in row if k != "reads"}))

    trials = []
    for tag, phone_id, label in PHONES:
        ui("read", select=label)
        other = next(p for t, p, _ in PHONES if p != phone_id)
        for kind in ("search", "home", "swipe"):
            trials.append(input_trial(tag, phone_id, other, 1, kind))
            print(json.dumps({k: trials[-1][k] for k in trials[-1] if k != "polls"}))
            time.sleep(0.25)

    out = {
        "fps": fps,
        "input": trials,
        "activity_required": True,
        "instrumentation": "none; FrameStatus is in the collapsed Activity drawer",
        "console_id": opened.get("console_id"),
    }
    (OUT / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", OUT / "results.json")


if __name__ == "__main__":
    main()

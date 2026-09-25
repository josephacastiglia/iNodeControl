"""Precise-movement candidate: Home→Search, off-location, swipes. C24C/C241 only."""
from __future__ import annotations
import json, time, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parents[1] / "analysis" / "precise-candidate-deploy-20260915"
PHONES = [("C24C", "86:1D:4A:04:2F:F6"), ("C241", "FE:A9:BC:D7:A0:44")]
CYCLES = 5
LOCATIONS = [(80, 140), (400, 200), (120, 500), (360, 760)]


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


def send(pid, fun, **data):
    elapsed, _, raw = api("POST", BASE + "/", {"fun": fun, "data": {"id": pid, **data}})
    j = json.loads(raw)
    if j.get("status") != 200 or j["data"].get("code") != 0:
        raise RuntimeError(raw.decode())
    return elapsed


def shot(pid):
    _, ctype, raw = api("GET", f"{BASE}/pic/screenshot?id={pid}&binary=true", timeout=8)
    if raw[:2] != b"BM":
        raise RuntimeError("not bmp")
    return raw


def recs():
    return {
        r["deviceid"]: {
            "name": r["name"], "live": r["live"], "frames": r["frames"],
            "restarts": r["receiver_restarts"],
        }
        for r in status()["receivers"]
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    start = recs()
    if not all(pid in start and start[pid]["live"] for _, pid in PHONES):
        raise SystemExit("both phones must be live before input")
    rows = []
    for tag, pid in PHONES:
        other = next(p for t, p in PHONES if p != pid)
        send(pid, "/key/sendkey", fn_key="Home")
        time.sleep(0.7)
        for n in range(CYCLES):
            home_ms = send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.5)
            t0 = time.perf_counter()
            api_s = send(pid, "/mouse/click", x=250, y=900, button=1)
            time.sleep(0.5)
            vis = shot(pid)
            vis_ms = (time.perf_counter() - t0) * 1000
            (OUT / f"{tag}-cycle{n:02d}-search.bmp").write_bytes(vis)
            (OUT / f"{tag}-cycle{n:02d}-other.bmp").write_bytes(shot(other))
            send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.4)
            rows.append({
                "phone": tag, "kind": "cycle", "n": n,
                "home_ms": round(home_ms * 1000, 1),
                "api_ms": round(api_s * 1000, 1),
                "shot_after_ms": round(vis_ms, 1),
            })
            print(rows[-1])
        for i, (x, y) in enumerate(LOCATIONS):
            send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.45)
            move_ms = send(pid, "/mouse/click", x=x, y=y, button=1)
            time.sleep(0.45)
            (OUT / f"{tag}-loc{i}-after-move.bmp").write_bytes(shot(pid))
            home_ms = send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.5)
            t0 = time.perf_counter()
            api_s = send(pid, "/mouse/click", x=250, y=900, button=1)
            time.sleep(0.5)
            vis = shot(pid)
            vis_ms = (time.perf_counter() - t0) * 1000
            (OUT / f"{tag}-loc{i}-search.bmp").write_bytes(vis)
            (OUT / f"{tag}-loc{i}-other.bmp").write_bytes(shot(other))
            send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.35)
            rows.append({
                "phone": tag, "kind": "from-location", "n": i, "from": [x, y],
                "move_api_ms": round(move_ms * 1000, 1),
                "home_ms": round(home_ms * 1000, 1),
                "api_ms": round(api_s * 1000, 1),
                "shot_after_ms": round(vis_ms, 1),
            })
            print(rows[-1])
        send(pid, "/key/sendkey", fn_key="Home")
        time.sleep(0.5)
        before = shot(pid)
        (OUT / f"{tag}-pre-swipe.bmp").write_bytes(before)
        swipe_ms = send(pid, "/mouse/swipe", direction="left", len=0.75, duration=400)
        time.sleep(0.7)
        (OUT / f"{tag}-swipe-left.bmp").write_bytes(shot(pid))
        send(pid, "/mouse/swipe", direction="right", len=0.75, duration=400)
        time.sleep(0.6)
        send(pid, "/key/sendkey", fn_key="Home")
        time.sleep(0.4)
        rows.append({"phone": tag, "kind": "swipe-left", "api_ms": round(swipe_ms * 1000, 1)})
        print(rows[-1])
    end = recs()
    out = {
        "start": start, "end": end, "rows": rows,
        "kernel": "release/iMouse2-kernel-precise-candidate/iMouse2.Kernel.exe --precise-movement",
        "rollback": "release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe",
    }
    (OUT / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", OUT / "results.json")


if __name__ == "__main__":
    main()

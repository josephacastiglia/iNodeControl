"""After-candidate Home → Search → Home. Visual Spotlight check. C24C/C241 only."""
from __future__ import annotations
import json, time, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parents[1] / "analysis" / "click-after-home-20260915"
PHONES = [("C24C", "86:1D:4A:04:2F:F6"), ("C241", "FE:A9:BC:D7:A0:44")]
CYCLES = 3


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
    return {r["name"]: {"live": r["live"], "frames": r["frames"], "restarts": r["receiver_restarts"]} for r in status()["receivers"]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    before = recs()
    rows = []
    for tag, pid in PHONES:
        other = next(p for t, p in PHONES if p != pid)
        for n in range(CYCLES):
            send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.7)
            home = shot(pid)
            (OUT / f"after-{tag}-{n}-home.bmp").write_bytes(home)
            t0 = time.perf_counter()
            api_s = send(pid, "/mouse/click", x=250, y=900, button=1)
            time.sleep(0.45)
            vis = shot(pid)
            vis_ms = (time.perf_counter() - t0) * 1000
            (OUT / f"after-{tag}-{n}-search.bmp").write_bytes(vis)
            other_img = shot(other)
            (OUT / f"after-{tag}-{n}-other.bmp").write_bytes(other_img)
            send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.5)
            rows.append({
                "phone": tag, "n": n,
                "api_ms": round(api_s * 1000, 1),
                "shot_after_ms": round(vis_ms, 1),
                "search_path": f"after-{tag}-{n}-search.bmp",
            })
            print(rows[-1])
    after = recs()
    out = {"before": before, "after": after, "cycles": rows, "kernel_log": "kernel.out.log"}
    (OUT / "after-results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote after-results.json")


if __name__ == "__main__":
    main()

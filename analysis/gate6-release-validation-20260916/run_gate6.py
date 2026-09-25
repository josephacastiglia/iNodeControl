"""Gate 6 release validation. Single-id API. Does not restart the kernel."""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
C24C = "86:1D:4A:04:2F:F6"
C241 = "FE:A9:BC:D7:A0:44"
PHONES = [("C24C", C24C, "C241", C241), ("C241", C241, "C24C", C24C)]


def api(method, url, body=None, timeout=20):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return round((time.perf_counter() - t0) * 1000, 1), raw


def post(fun, payload, timeout=15):
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


def shot(pid, name):
    ms, raw = api("GET", f"{BASE}/pic/screenshot?id={pid}&binary=true", timeout=8)
    if not raw.startswith(b"BM"):
        raise RuntimeError(f"{name} not BMP: {raw[:180]!r}")
    (OUT / name).write_bytes(raw)
    return ms, len(raw)


def home_pair(pid, token):
    a, _ = post("/key/sendkey", {"id": pid, "token": token, "fn_key": "Home"}, timeout=8)
    time.sleep(0.15)
    b, _ = post("/key/sendkey", {"id": pid, "token": token, "fn_key": "Home"}, timeout=8)
    return a, b


def main():
    s1 = status()
    time.sleep(1.0)
    s2 = status()
    pre = {
        "frames_before": {r["name"]: r["frames"] for r in s1["receivers"]},
        "frames_after_1s": {r["name"]: r["frames"] for r in s2["receivers"]},
        "live": {r["name"]: r["live"] for r in s2["receivers"]},
        "pids": {r["name"]: r["receiver_pid"] for r in s2["receivers"]},
    }
    (OUT / "preflight-frames.json").write_text(json.dumps(pre, indent=2), encoding="utf-8")
    print("preflight", pre, flush=True)
    if any(pre["frames_after_1s"][k] <= pre["frames_before"][k] for k in pre["frames_before"]):
        raise SystemExit("frames not advancing")

    _, acquired = post("/input/acquire", {"id": f"{C24C},{C241}", "lease_ms": 120000})
    tokens = {row["id"]: row["token"] for row in acquired["leases"]}
    rows = []
    try:
        for name, pid, oname, oid in PHONES:
            for n in range(1, 6):
                post("/input/renew", {"id": f"{C24C},{C241}", "tokens": tokens})
                h1, h2 = home_pair(pid, tokens[pid])
                time.sleep(0.8)
                click_ms, click = post(
                    "/mouse/click",
                    {"id": pid, "token": tokens[pid], "x": 250, "y": 900, "button": 1},
                    timeout=12,
                )
                time.sleep(0.8)
                target = f"{name.lower()}-c{n}-search.bmp"
                other = f"{oname.lower()}-iso-during-{name.lower()}-c{n}.bmp"
                t_ms, t_len = shot(pid, target)
                o_ms, o_len = shot(oid, other)
                dismiss_ms, _ = post(
                    "/key/sendkey", {"id": pid, "token": tokens[pid], "fn_key": "Home"}, timeout=8
                )
                row = {
                    "phone": name,
                    "cycle": n,
                    "home1_ms": h1,
                    "home2_ms": h2,
                    "dispatch_ms": click_ms,
                    "click_code": click.get("code"),
                    "search_bmp": target,
                    "search_shot_ms": t_ms,
                    "search_bytes": t_len,
                    "isolation_bmp": other,
                    "isolation_shot_ms": o_ms,
                    "isolation_bytes": o_len,
                    "dismiss_ms": dismiss_ms,
                }
                rows.append(row)
                (OUT / "rows.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
                print(f"{name} c{n} dispatch={click_ms}ms", flush=True)
        end = status()
        stuck = input_status()
        (OUT / "end-status.json").write_text(
            json.dumps({"kernel": end, "input": stuck}, indent=2), encoding="utf-8"
        )
        print("done", len(rows), flush=True)
    finally:
        try:
            rel_ms, rel = post("/input/release", {"id": f"{C24C},{C241}", "tokens": tokens})
            print("released", rel_ms, rel.get("code"), rel.get("message"), flush=True)
        except Exception as ex:
            print("RELEASE FAILED", ex, flush=True)
            raise


if __name__ == "__main__":
    main()

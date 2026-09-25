"""Diagnostic retry. Does not restart the kernel."""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
PHONES = [
    ("C24C", "86:1D:4A:04:2F:F6"),
    ("C241", "FE:A9:BC:D7:A0:44"),
    ("C214", "8A:23:B5:71:35:8D"),
    ("F215", "3A:DC:15:FB:DD:EC"),
]
GROUP = ",".join(pid for _, pid in PHONES)
TARGETS = ["C24C", "F215"]


def now():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


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
    data = body.get("data") or {}
    return ms, data


def send(fun, payload, ids, tokens, timeout=15):
    ms, data = post(fun, {"id": ids, "tokens": {i: tokens[i] for i in ids.split(",")}, **payload}, timeout=timeout)
    if data.get("code") != 0:
        raise RuntimeError(f"{fun} {ids} {data}")
    return {"fun": fun, "id": ids, "rtt_ms": ms, "code": data.get("code"), "at": now(), "results": data.get("results")}


def shot(device_id, stem):
    ms, raw = api("GET", f"{BASE}/pic/screenshot?id={device_id}&binary=true", timeout=8)
    if not raw.startswith(b"BM"):
        raise RuntimeError(stem)
    (OUT / stem).write_bytes(raw)
    return {"bmp": stem, "shot_ms": ms, "bytes": len(raw)}


def main():
    ms, data = post("/input/acquire", {"id": GROUP, "lease_ms": 90000})
    if data.get("code") != 0:
        raise SystemExit(f"acquire {data}")
    tokens = {row["id"]: row["token"] for row in data["leases"]}
    log = {"acquire_ms": ms, "targets": []}
    try:
        for name in TARGETS:
            device_id = dict(PHONES)[name]
            row = {"target": name}
            row["home"] = send("/key/sendkey", {"fn_key": "Home"}, device_id, tokens)
            time.sleep(0.8)
            t0 = time.perf_counter()
            row["click1"] = send("/mouse/click", {"x": 250, "y": 900, "button": 1}, device_id, tokens)
            time.sleep(1.0)
            row["after_click1"] = shot(device_id, f"retry-{name.lower()}-click1.bmp")
            row["click1_visible_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            t1 = time.perf_counter()
            row["click2"] = send("/mouse/click", {"x": 250, "y": 900, "button": 1}, device_id, tokens)
            time.sleep(1.0)
            row["after_click2"] = shot(device_id, f"retry-{name.lower()}-click2.bmp")
            row["click2_visible_ms"] = round((time.perf_counter() - t1) * 1000, 1)
            row["dismiss"] = send("/key/sendkey", {"fn_key": "Home"}, device_id, tokens)
            time.sleep(0.8)
            row["after_home"] = shot(device_id, f"retry-{name.lower()}-home.bmp")
            log["targets"].append(row)
            print(name, "click1", row["click1"]["rtt_ms"], "click2", row["click2"]["rtt_ms"], flush=True)
        log["others_after"] = {name: shot(pid, f"retry-others-{name.lower()}.bmp") for name, pid in PHONES}
    finally:
        ms, data = post("/input/release", {"id": GROUP, "tokens": tokens})
        log["release"] = {"rtt_ms": ms, "code": data.get("code"), "message": data.get("message")}
        print("released", data.get("code"), data.get("message"), flush=True)
    (OUT / "retry-log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

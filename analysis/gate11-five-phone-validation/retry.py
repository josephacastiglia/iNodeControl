"""Retry the two Gate 11 misses. Does not restart the kernel."""
from __future__ import annotations

import json
import struct
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
PHONES = [
    ("C24C", "86:1D:4A:04:2F:F6"),
    ("C241", "FE:A9:BC:D7:A0:44"),
    ("C214", "8A:23:B5:71:35:8D"),
    ("724E", "3A:DC:15:FB:DD:EC"),
    ("*", "*"),
]
GROUP = ",".join(pid for _, pid in PHONES)


def now():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def slug(name):
    return "phone5" if name == "*" else name.lower()


def api(method, url, body=None, timeout=20):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        status = resp.status
    return round((time.perf_counter() - t0) * 1000, 1), status, raw


def post(fun, payload, timeout=20):
    ms, http, raw = api("POST", BASE + "/", {"fun": fun, "data": payload}, timeout=timeout)
    body = json.loads(raw)
    data = body.get("data") or {}
    out = {"fun": fun, "http": http, "code": data.get("code"), "message": data.get("message"), "rtt_ms": ms, "at": now(), "id": payload.get("id")}
    if "results" in data:
        out["results"] = data["results"]
    return out, data


def bmp_pixels(raw):
    off = struct.unpack_from("<I", raw, 10)[0]
    w = struct.unpack_from("<i", raw, 18)[0]
    h = abs(struct.unpack_from("<i", raw, 22)[0])
    bits = struct.unpack_from("<H", raw, 28)[0]
    stride = ((w * (bits // 8) + 3) // 4) * 4
    return raw[off:], w, h, bits, stride


def mad(a, b):
    pa, wa, ha, _, sa = bmp_pixels(a)
    pb, wb, hb, _, sb = bmp_pixels(b)
    if (wa, ha, sa) != (wb, hb, sb):
        return 999.0
    total = n = 0
    for y in range(80, ha - 140, 4):
        row = y * sa
        for x in range(0, wa * 3, 24):
            i = row + x
            total += abs(pa[i] - pb[i]) + abs(pa[i + 1] - pb[i + 1]) + abs(pa[i + 2] - pb[i + 2])
            n += 3
    return round(total / max(1, n), 2)


def shot(device_id):
    q = urllib.parse.quote(device_id, safe=":")
    ms, http, raw = api("GET", f"{BASE}/pic/screenshot?id={q}&binary=true", timeout=8)
    if not raw.startswith(b"BM"):
        raise RuntimeError(raw[:80])
    return ms, http, raw


def capture(stem, t0, baseline):
    def one(item):
        name, device_id = item
        ms, http, raw = shot(device_id)
        path = OUT / f"{stem}-{slug(name)}.bmp"
        path.write_bytes(raw)
        row = {"bmp": path.name, "shot_ms": ms, "visible_ms": round((time.perf_counter() - t0) * 1000, 1), "within_5s": (time.perf_counter() - t0) <= 5.0, "_raw": raw}
        if name in baseline:
            row["mad_vs_home"] = mad(baseline[name], raw)
        return name, row

    with ThreadPoolExecutor(max_workers=5) as pool:
        return dict(pool.map(one, PHONES))


def strip(caps):
    return {k: {kk: vv for kk, vv in v.items() if kk != "_raw"} for k, v in caps.items()}


def main():
    baseline = {name: (OUT / f"baseline-home-{slug(name)}.bmp").read_bytes() for name, _ in PHONES}
    _, status = post("/input/status", {})
    stopped = [row["id"] for row in status.get("phones") or [] if row.get("stopped")]
    if stopped:
        gens = {row["id"]: row.get("generation", 0) for row in status["phones"]}
        resumed, _ = post("/input/resume", {"id": ",".join(stopped), "expected_generations": {i: gens[i] for i in stopped}})
        print("resume", resumed["code"], stopped, flush=True)
        if resumed["code"] != 0:
            raise SystemExit(resumed)
    acquired, data = post("/input/acquire", {"id": GROUP, "lease_ms": 120000})
    tokens = {row["id"]: row["token"] for row in data.get("leases") or []}
    if acquired["code"] != 0 or set(tokens) != {pid for _, pid in PHONES}:
        raise SystemExit(acquired)
    log = {"at": now(), "acquire_code": acquired["code"]}

    def send(fun, payload, ids):
        call, _ = post(fun, {"id": ids, "tokens": {i: tokens[i] for i in ids.split(",")}, **payload})
        if call["code"] != 0:
            raise RuntimeError(call)
        return call

    try:
        phone = "*"
        send("/key/sendkey", {"fn_key": "Home"}, phone)
        time.sleep(0.8)
        t0 = time.perf_counter()
        click = send("/mouse/click", {"x": 250, "y": 900, "button": 1}, phone)
        time.sleep(1.0)
        cap1 = capture("retry-a-phone5-1s", t0, baseline)
        mad1 = cap1["*"]["mad_vs_home"]
        cap2 = None
        if mad1 < 20 and (time.perf_counter() - t0) < 4.6:
            remain = 4.6 - (time.perf_counter() - t0)
            if remain > 0:
                time.sleep(remain)
            cap2 = capture("retry-a-phone5-4s", t0, baseline)
        log["phone5_isolated"] = {
            "search_rtt_ms": click["rtt_ms"],
            "search_code": click["code"],
            "at_1s": strip(cap1),
            "at_4s": strip(cap2) if cap2 else None,
        }
        print("phone5", mad1, None if not cap2 else cap2["*"]["mad_vs_home"], flush=True)
        send("/key/sendkey", {"fn_key": "Home"}, phone)
        time.sleep(0.8)

        send("/key/sendkey", {"fn_key": "Home"}, GROUP)
        time.sleep(0.8)
        t_click = time.perf_counter()
        group_click = send("/mouse/click", {"x": 250, "y": 900, "button": 1}, GROUP)
        time.sleep(1.0)
        spot = capture("retry-b-spotlight", t_click, baseline)
        t_home = time.perf_counter()
        group_home = send("/key/sendkey", {"fn_key": "Home"}, GROUP)
        time.sleep(0.8)
        home1 = capture("retry-b-home-0.8s", t_home, baseline)
        home2 = None
        if home1["C24C"]["mad_vs_home"] > 20 and (time.perf_counter() - t_home) < 4.6:
            remain = 4.6 - (time.perf_counter() - t_home)
            if remain > 0:
                time.sleep(remain)
            home2 = capture("retry-b-home-4s", t_home, baseline)
        log["group"] = {
            "search_rtt_ms": group_click["rtt_ms"],
            "home_rtt_ms": group_home["rtt_ms"],
            "spotlight": strip(spot),
            "home_0_8s": strip(home1),
            "home_4s": strip(home2) if home2 else None,
        }
        print("group spot", {k: v["mad_vs_home"] for k, v in spot.items()}, flush=True)
        print("group home", {k: v["mad_vs_home"] for k, v in home1.items()}, None if not home2 else home2["C24C"]["mad_vs_home"], flush=True)
        send("/mouse/up", {}, GROUP)
    finally:
        rel, _ = post("/input/release", {"id": GROUP, "tokens": tokens})
        log["release"] = {"code": rel.get("code"), "message": rel.get("message")}
        print("released", rel.get("code"), flush=True)
    (OUT / "retry-log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

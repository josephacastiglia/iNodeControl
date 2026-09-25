"""Gate 11 final 4-phone validation. Does not restart the kernel."""
from __future__ import annotations

import json
import struct
import subprocess
import time
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
]
GROUP = ",".join(pid for _, pid in PHONES)
BY_ID = {pid: name for name, pid in PHONES}


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
        status = resp.status
    return round((time.perf_counter() - t0) * 1000, 1), status, raw


def kernel_status():
    ms, http, raw = api("GET", BASE + "/kernel/status", timeout=5)
    return ms, http, json.loads(raw)["data"]


def post(fun, payload, timeout=20):
    ms, http, raw = api("POST", BASE + "/", {"fun": fun, "data": payload}, timeout=timeout)
    body = json.loads(raw)
    data = body.get("data") or {}
    out = {
        "fun": fun,
        "http": http,
        "code": data.get("code"),
        "message": data.get("message"),
        "rtt_ms": ms,
        "at": now(),
        "id": payload.get("id"),
    }
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
    ms, http, raw = api("GET", f"{BASE}/pic/screenshot?id={device_id}&binary=true", timeout=8)
    if not raw.startswith(b"BM"):
        raise RuntimeError("not bmp " + raw[:80].decode("utf-8", "replace"))
    return ms, http, raw


def capture(stem, t0, baseline):
    def one(item):
        name, device_id = item
        ms, http, raw = shot(device_id)
        path = OUT / f"{stem}-{name.lower()}.bmp"
        path.write_bytes(raw)
        row = {
            "bmp": path.name,
            "http": http,
            "shot_ms": ms,
            "bytes": len(raw),
            "wh": list(bmp_pixels(raw)[1:3]),
            "visible_ms": round((time.perf_counter() - t0) * 1000, 1),
            "within_5s": (time.perf_counter() - t0) <= 5.0,
            "_raw": raw,
        }
        if baseline and name in baseline:
            row["mad_vs_home"] = mad(baseline[name], raw)
        return name, row

    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(pool.map(one, PHONES))


def strip(caps):
    return {k: {kk: vv for kk, vv in v.items() if kk != "_raw"} for k, v in caps.items()}


def frames_of(data):
    rows = []
    for r in data.get("receivers") or []:
        rows.append({
            "name": BY_ID.get(r.get("deviceid"), r.get("name")),
            "deviceid": r.get("deviceid"),
            "live": r.get("live"),
            "frames": r.get("frames"),
            "receiver_state": r.get("receiver_state"),
            "receiver_pid": r.get("receiver_pid"),
            "receiver_restarts": r.get("receiver_restarts"),
        })
    return rows


def pidof(image):
    out = subprocess.check_output(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"], text=True)
    pids = []
    for line in out.splitlines():
        if image.lower() not in line.lower():
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


def main():
    t_pre = time.perf_counter()
    pre_ms, _, pre = kernel_status()
    time.sleep(2.0)
    pre2_ms, _, pre2 = kernel_status()
    a = {r["deviceid"]: r for r in frames_of(pre)}
    b = {r["deviceid"]: r for r in frames_of(pre2)}
    poll = []
    for name, device_id in PHONES:
        poll.append({
            "name": name,
            "live": [a[device_id]["live"], b[device_id]["live"]],
            "frames": [a[device_id]["frames"], b[device_id]["frames"]],
            "delta": b[device_id]["frames"] - a[device_id]["frames"],
            "restarts": [a[device_id]["receiver_restarts"], b[device_id]["receiver_restarts"]],
            "receiver_pid": b[device_id]["receiver_pid"],
            "state": b[device_id]["receiver_state"],
            "advancing": bool(a[device_id]["live"] and b[device_id]["live"] and b[device_id]["frames"] > a[device_id]["frames"]),
        })
    if not (len(poll) == 4 and all(p["advancing"] and p["restarts"] == [0, 0] for p in poll)):
        raise SystemExit("preflight failed " + json.dumps(poll))
    print("preflight ok", [(p["name"], p["delta"], p["receiver_pid"]) for p in poll], flush=True)

    acquired, acquire_data = post("/input/acquire", {"id": GROUP, "lease_ms": 120000}, timeout=8)
    tokens = {row["id"]: row["token"] for row in acquire_data.get("leases") or []}
    if acquired["code"] != 0 or set(tokens) != {pid for _, pid in PHONES}:
        raise SystemExit("acquire failed " + json.dumps(acquired))

    def send(fun, payload, ids):
        body = {"id": ids, "tokens": {i: tokens[i] for i in ids.split(",")}, **payload}
        call, _data = post(fun, body, timeout=20)
        if call["code"] != 0:
            raise RuntimeError(f"{fun} {ids} failed: {call}")
        return call

    log = {"at": now(), "kernel_pids": pidof("iMouse2.Kernel.exe"), "poll": poll, "acquire": acquired, "part_a": []}
    try:
        send("/key/sendkey", {"fn_key": "Home"}, GROUP)
        time.sleep(0.8)
        t_base = time.perf_counter()
        base = capture("final-baseline-home", t_base, None)
        baseline = {k: v["_raw"] for k, v in base.items()}
        log["baseline"] = strip(base)

        for name, device_id in PHONES:
            t_home = time.perf_counter()
            home = send("/key/sendkey", {"fn_key": "Home"}, device_id)
            time.sleep(0.8)
            t_search = time.perf_counter()
            click = send("/mouse/click", {"x": 250, "y": 900, "button": 1}, device_id)
            time.sleep(1.0)
            caps = capture(f"final-a-{name.lower()}-search", t_search, baseline)
            effect = max(v["visible_ms"] for v in caps.values())
            row = {
                "target": name,
                "home_rtt_ms": home["rtt_ms"],
                "search_rtt_ms": click["rtt_ms"],
                "search_code": click["code"],
                "effect_ms": effect,
                "within_5s": effect <= 5000,
                "capture": strip(caps),
            }
            log["part_a"].append(row)
            print("A", name, "rtt", click["rtt_ms"], "effect", effect, {k: v.get("mad_vs_home") for k, v in caps.items()}, flush=True)
            send("/key/sendkey", {"fn_key": "Home"}, device_id)
            time.sleep(0.8)

        t_b1 = time.perf_counter()
        b_home1 = send("/key/sendkey", {"fn_key": "Home"}, GROUP)
        time.sleep(0.8)
        c_home1 = capture("final-b-home-before", t_b1, baseline)
        t_b2 = time.perf_counter()
        b_search = send("/mouse/click", {"x": 250, "y": 900, "button": 1}, GROUP)
        time.sleep(1.0)
        c_search = capture("final-b-spotlight", t_b2, baseline)
        t_b3 = time.perf_counter()
        b_home2 = send("/key/sendkey", {"fn_key": "Home"}, GROUP)
        time.sleep(0.8)
        c_home2 = capture("final-b-home-after", t_b3, baseline)
        log["part_b"] = {
            "home_before": {"rtt_ms": b_home1["rtt_ms"], "code": b_home1["code"], "effect_ms": max(v["visible_ms"] for v in c_home1.values()), "capture": strip(c_home1)},
            "search": {"rtt_ms": b_search["rtt_ms"], "code": b_search["code"], "effect_ms": max(v["visible_ms"] for v in c_search.values()), "capture": strip(c_search)},
            "home_after": {"rtt_ms": b_home2["rtt_ms"], "code": b_home2["code"], "effect_ms": max(v["visible_ms"] for v in c_home2.values()), "capture": strip(c_home2)},
        }
        print("B", log["part_b"]["search"]["effect_ms"], {k: v.get("mad_vs_home") for k, v in c_search.items()}, flush=True)
        mouse_up = send("/mouse/up", {}, GROUP)
        _, held = post("/input/status", {})
        log["mouse_up"] = mouse_up
        log["input_while_leased"] = held.get("phones")
    finally:
        rel, _ = post("/input/release", {"id": GROUP, "tokens": tokens}, timeout=8)
        log["release"] = rel
        print("released", rel["code"], rel.get("message"), flush=True)

    time.sleep(1.0)
    end_ms, _, end = kernel_status()
    time.sleep(2.0)
    end2_ms, _, end2 = kernel_status()
    _, after = post("/input/status", {})
    ea = {r["deviceid"]: r for r in frames_of(end)}
    eb = {r["deviceid"]: r for r in frames_of(end2)}
    log["postflight"] = {
        "status_ms": [end_ms, end2_ms],
        "frames": [
            {
                "name": name,
                "live": eb[device_id]["live"],
                "restarts": eb[device_id]["receiver_restarts"],
                "pid": eb[device_id]["receiver_pid"],
                "delta": eb[device_id]["frames"] - ea[device_id]["frames"],
                "frames": [ea[device_id]["frames"], eb[device_id]["frames"]],
            }
            for name, device_id in PHONES
        ],
    }
    log["input_after_release"] = after.get("phones")
    log["elapsed_s"] = round(time.perf_counter() - t_pre, 1)
    log["pre_status_ms"] = [pre_ms, pre2_ms]
    (OUT / "capture-final.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print("done", log["elapsed_s"], flush=True)


if __name__ == "__main__":
    main()

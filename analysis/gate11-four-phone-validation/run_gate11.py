"""Gate 11 four-phone validation. Does not restart the kernel."""
from __future__ import annotations

import json
import struct
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
PHONES = [
    ("C24C", "86:1D:4A:04:2F:F6", 16160),
    ("C241", "FE:A9:BC:D7:A0:44", 1624),
    ("C214", "8A:23:B5:71:35:8D", 22872),
    ("F215", "3A:DC:15:FB:DD:EC", 12332),
]
GROUP = ",".join(pid for _, pid, _ in PHONES)
KERNEL_PID = 29564
LOG = Path(r"C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0\analysis\four-phone-config\kernel-stdout.log")
BY_ID = {pid: name for name, pid, _ in PHONES}


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
    if fun == "/input/acquire":
        out["lease_ids"] = [row.get("id") for row in data.get("leases") or []]
    return out, data


def slim_receivers(data):
    rows = []
    for r in data.get("receivers") or []:
        name = BY_ID.get(r.get("deviceid"), r.get("name"))
        rows.append({
            "name": name,
            "deviceid": r.get("deviceid"),
            "live": r.get("live"),
            "frames": r.get("frames"),
            "receiver_state": r.get("receiver_state"),
            "receiver_pid": r.get("receiver_pid"),
            "receiver_restarts": r.get("receiver_restarts"),
            "receiver_message": r.get("receiver_message"),
        })
    return rows


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


def band_mean(raw, y0, y1):
    px, w, h, bits, stride = bmp_pixels(raw)
    if bits != 24:
        return None
    # BMP rows are bottom-up.
    total = n = 0
    for y in range(y0, min(y1, h), 2):
        src = (h - 1 - y) * stride
        for x in range(0, w, 4):
            i = src + x * 3
            total += px[i] + px[i + 1] + px[i + 2]
            n += 3
    return round(total / max(1, n), 1)


def shot(device_id):
    ms, http, raw = api("GET", f"{BASE}/pic/screenshot?id={device_id}&binary=true", timeout=8)
    if not raw.startswith(b"BM"):
        raise RuntimeError("not bmp " + raw[:80].decode("utf-8", "replace"))
    return ms, http, raw


def capture(stem, t0):
    def one(item):
        name, device_id, _pid = item
        ms, http, raw = shot(device_id)
        path = OUT / f"{stem}-{name.lower()}.bmp"
        path.write_bytes(raw)
        return name, {
            "bmp": path.name,
            "http": http,
            "shot_ms": ms,
            "bytes": len(raw),
            "wh": list(bmp_pixels(raw)[1:3]),
            "visible_ms": round((time.perf_counter() - t0) * 1000, 1),
            "within_5s": (time.perf_counter() - t0) <= 5.0,
            "band_y860_940": band_mean(raw, 860, 940),
            "band_y980_1040": band_mean(raw, 980, 1040),
            "_raw": raw,
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(pool.map(one, PHONES))


def strip(caps):
    return {k: {kk: vv for kk, vv in v.items() if kk != "_raw"} for k, v in caps.items()}


def annotate(caps, prev):
    for name, row in caps.items():
        if prev and name in prev:
            row["mad_vs_prev"] = mad(prev[name], row["_raw"])
        row["changed"] = row.get("mad_vs_prev", 0) >= 8.0
    return caps


def proc_alive(pid):
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid} -ErrorAction Stop).ProcessName"],
            text=True,
            timeout=8,
        ).strip()
        return out
    except Exception as ex:
        return f"missing:{ex}"


def main():
    log_start = LOG.read_text(encoding="utf-8", errors="replace").count("\n") if LOG.exists() else 0
    t_pre = time.perf_counter()
    pre_ms, pre_http, pre = kernel_status()
    time.sleep(1.0)
    pre2_ms, pre2_http, pre2 = kernel_status()
    frames = []
    for a in pre["receivers"]:
        b = next(x for x in pre2["receivers"] if x["deviceid"] == a["deviceid"])
        frames.append({
            "deviceid": a["deviceid"],
            "name": BY_ID.get(a["deviceid"], a.get("name")),
            "live": [a.get("live"), b.get("live")],
            "state": [a.get("receiver_state"), b.get("receiver_state")],
            "frames": [a.get("frames"), b.get("frames")],
            "delta": (b.get("frames") or 0) - (a.get("frames") or 0),
            "receiver_pid": [a.get("receiver_pid"), b.get("receiver_pid")],
            "receiver_restarts": [a.get("receiver_restarts"), b.get("receiver_restarts")],
            "advancing": bool(b.get("live") and a.get("live") and b.get("frames", 0) > a.get("frames", 0)),
        })
    _, input_before = post("/input/status", {})
    preflight = {
        "at": now(),
        "sample_gap_s": 1.0,
        "status_ms": [pre_ms, pre2_ms],
        "http": [pre_http, pre2_http],
        "kernel_pid_expected": KERNEL_PID,
        "kernel_process": proc_alive(KERNEL_PID),
        "console_process": proc_alive(27016),
        "allowed": pre.get("allowed"),
        "input": pre.get("input"),
        "input_protocol": pre.get("input_protocol"),
        "input_leases_required": pre.get("input_leases_required"),
        "frames": frames,
        "all_advancing": all(f["advancing"] for f in frames) and len(frames) == 4,
        "restarts_zero": all(f["receiver_restarts"] == [0, 0] for f in frames),
        "pids_match": all(
            f["receiver_pid"][0] == expected and f["receiver_pid"][0] == f["receiver_pid"][1]
            for f, (_, _, expected) in zip(frames, PHONES)
        ),
        "input_before": {k: input_before.get(k) for k in ("code", "phones", "protocol")},
        "t0_receivers": slim_receivers(pre),
        "t1_receivers": slim_receivers(pre2),
    }
    (OUT / "preflight.json").write_text(json.dumps(preflight, indent=2), encoding="utf-8")
    print("preflight", preflight["all_advancing"], preflight["restarts_zero"], preflight["pids_match"], flush=True)
    if not (preflight["all_advancing"] and preflight["restarts_zero"] and preflight["pids_match"]):
        raise SystemExit("preflight failed")

    acquired, acquire_data = post("/input/acquire", {"id": GROUP, "lease_ms": 120000}, timeout=8)
    leases = acquire_data.get("leases") or []
    tokens = {row["id"]: row["token"] for row in leases}
    print("acquire", acquired["code"], acquired.get("lease_ids"), flush=True)
    if acquired["code"] != 0 or set(tokens) != {pid for _, pid, _ in PHONES}:
        (OUT / "acquire-failed.json").write_text(json.dumps(acquired, indent=2), encoding="utf-8")
        raise SystemExit("acquire failed")

    def send(fun, payload, ids):
        body = {"id": ids, "tokens": {i: tokens[i] for i in ids.split(",")}, **payload}
        call, _data = post(fun, body, timeout=15)
        if call["code"] != 0:
            raise RuntimeError(f"{fun} {ids} failed: {call}")
        return call

    def renew():
        call, _data = post("/input/renew", {"id": GROUP, "tokens": tokens}, timeout=8)
        if call["code"] != 0:
            raise RuntimeError(f"renew failed: {call}")
        return call

    log = {"preflight": preflight, "acquire": acquired, "part_a": [], "part_b": [], "probe": {}}
    prev = {}
    try:
        renew()
        t_settle = time.perf_counter()
        settle = [
            send("/key/sendkey", {"fn_key": "Home"}, GROUP),
            send("/key/sendkey", {"fn_key": "Home"}, GROUP),
        ]
        time.sleep(0.8)
        base = annotate(capture("baseline-home", t_settle), None)
        prev = {k: v["_raw"] for k, v in base.items()}
        log["settle"] = {"requests": settle, "capture": strip(base), "visible_ms": round((time.perf_counter() - t_settle) * 1000, 1)}
        print("settled", flush=True)

        for name, device_id, _pid in PHONES:
            renew()
            t_home = time.perf_counter()
            home = send("/key/sendkey", {"fn_key": "Home"}, device_id)
            time.sleep(0.8)
            t_search = time.perf_counter()
            click = send("/mouse/click", {"x": 250, "y": 900, "button": 1}, device_id)
            time.sleep(1.0)
            caps = annotate(capture(f"a-{name.lower()}-search", t_search), prev)
            prev = {k: v["_raw"] for k, v in caps.items()}
            t_dismiss = time.perf_counter()
            dismiss = send("/key/sendkey", {"fn_key": "Home"}, device_id)
            time.sleep(0.8)
            back = annotate(capture(f"a-{name.lower()}-home", t_dismiss), prev)
            prev = {k: v["_raw"] for k, v in back.items()}
            row = {
                "target": name,
                "deviceid": device_id,
                "home": home,
                "search": click,
                "search_capture": strip(caps),
                "dismiss": dismiss,
                "home_capture": strip(back),
                "search_effect_ms": max(caps[n]["visible_ms"] for n, _, _ in PHONES),
                "dismiss_effect_ms": max(back[n]["visible_ms"] for n, _, _ in PHONES),
            }
            log["part_a"].append(row)
            (OUT / "capture-log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
            print("A", name, "search_rtt", click["rtt_ms"], "effect_ms", row["search_effect_ms"], flush=True)

        renew()
        t_b1 = time.perf_counter()
        b_home1 = send("/key/sendkey", {"fn_key": "Home"}, GROUP)
        time.sleep(0.8)
        c_home1 = annotate(capture("b-home-before", t_b1), prev)
        prev = {k: v["_raw"] for k, v in c_home1.items()}
        t_b2 = time.perf_counter()
        b_search = send("/mouse/click", {"x": 250, "y": 900, "button": 1}, GROUP)
        time.sleep(1.0)
        c_search = annotate(capture("b-spotlight", t_b2), prev)
        prev = {k: v["_raw"] for k, v in c_search.items()}
        t_b3 = time.perf_counter()
        b_home2 = send("/key/sendkey", {"fn_key": "Home"}, GROUP)
        time.sleep(0.8)
        c_home2 = annotate(capture("b-home-after", t_b3), prev)
        prev = {k: v["_raw"] for k, v in c_home2.items()}
        log["part_b"] = {
            "home_before": {"request": b_home1, "wait_s": 0.8, "capture": strip(c_home1), "effect_ms": max(c_home1[n]["visible_ms"] for n, _, _ in PHONES)},
            "search": {"request": b_search, "wait_s": 1.0, "capture": strip(c_search), "effect_ms": max(c_search[n]["visible_ms"] for n, _, _ in PHONES)},
            "home_after": {"request": b_home2, "wait_s": 0.8, "capture": strip(c_home2), "effect_ms": max(c_home2[n]["visible_ms"] for n, _, _ in PHONES)},
        }
        print("B effects", log["part_b"]["home_before"]["effect_ms"], log["part_b"]["search"]["effect_ms"], log["part_b"]["home_after"]["effect_ms"], flush=True)

        t_probe = time.perf_counter()
        mouse_up = send("/mouse/up", {}, GROUP)
        time.sleep(0.4)
        probe_caps = annotate(capture("probe-mouseup", t_probe), prev)
        _, input_held = post("/input/status", {})
        log["probe"] = {
            "mouse_up": mouse_up,
            "capture": strip(probe_caps),
            "input_while_leased": {k: input_held.get(k) for k in ("code", "phones")},
        }
        (OUT / "capture-log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    finally:
        try:
            rel, rel_data = post("/input/release", {"id": GROUP, "tokens": tokens}, timeout=8)
            log["release"] = rel
            print("released", rel["code"], rel.get("message"), flush=True)
        except Exception as ex:
            log["release_error"] = str(ex)
            print("RELEASE FAILED", ex, flush=True)
            raise

    time.sleep(0.3)
    end_ms, end_http, end = kernel_status()
    _, input_after = post("/input/status", {})
    log_lines = []
    if LOG.exists():
        log_lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[log_start:]
    log["kernel_after"] = {
        "status_ms": end_ms,
        "http": end_http,
        "receivers": slim_receivers(end),
        "kernel_process": proc_alive(KERNEL_PID),
        "receiver_processes": {name: proc_alive(pid) for name, _id, pid in PHONES},
    }
    log["input_after_release"] = {k: input_after.get(k) for k in ("code", "phones")}
    log["kernel_log_new"] = log_lines
    log["elapsed_s"] = round(time.perf_counter() - t_pre, 1)
    (OUT / "capture-log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print("done", log["elapsed_s"], flush=True)


if __name__ == "__main__":
    main()

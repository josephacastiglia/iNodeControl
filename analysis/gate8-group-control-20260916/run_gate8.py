"""Gate 8 group control. Comma-list dispatch only. Does not touch process lifetime."""
from __future__ import annotations

import hashlib
import json
import struct
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
GROUP = "86:1D:4A:04:2F:F6,FE:A9:BC:D7:A0:44"
PHONES = [("C24C", "86:1D:4A:04:2F:F6"), ("C241", "FE:A9:BC:D7:A0:44")]
DLL = Path(r"C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0\release\iMouse2-kernel-two-phone\iMouse2.Kernel.dll")
LOG = Path(r"C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0\analysis\two-phone-config\kernel-stdout.log")
KNOWN = "A995CF5B92AEE4393E164FA4CE68D446A3F63D4D0CAAA73B5ACB6DCF587851BF"


def api(method, url, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        status = resp.status
    return (time.perf_counter() - t0) * 1000, status, raw


def kernel_status():
    ms, http, raw = api("GET", BASE + "/kernel/status")
    body = json.loads(raw)
    return ms, body["data"]


def call(fun, payload, device_id=GROUP):
    ms, http, raw = api("POST", BASE + "/", {"fun": fun, "data": {"id": device_id, **payload}})
    body = json.loads(raw)
    data = body.get("data") or {}
    return {
        "fun": fun,
        "id": device_id,
        "payload": payload,
        "http": http,
        "code": data.get("code"),
        "message": data.get("message"),
        "rtt_ms": round(ms, 1),
        "at": datetime.now().astimezone().isoformat(),
        "results": data.get("results") or data.get("list"),
        "raw_keys": list(data.keys()),
    }


def shot(device_id):
    ms, http, raw = api("GET", f"{BASE}/pic/screenshot?id={device_id}&binary=true", timeout=8)
    if raw[:2] != b"BM":
        raise RuntimeError("not bmp: " + raw[:120].decode(errors="replace"))
    return ms, http, raw


def save_bmp(name, raw):
    (OUT / name).write_bytes(raw)
    return name


def bmp_meta(raw):
    off = struct.unpack_from("<I", raw, 10)[0]
    w = struct.unpack_from("<i", raw, 18)[0]
    h = abs(struct.unpack_from("<i", raw, 22)[0])
    bits = struct.unpack_from("<H", raw, 28)[0]
    stride = ((w * (bits // 8) + 3) // 4) * 4
    return raw[off:], w, h, bits, stride


def mad(a, b):
    pa, wa, ha, _, sa = bmp_meta(a)
    pb, wb, hb, _, sb = bmp_meta(b)
    if (wa, ha, sa) != (wb, hb, sb):
        return 999.0
    y0, y1 = 80, ha - 140
    total = n = 0
    for y in range(y0, y1, 4):
        row = y * sa
        for x in range(0, wa * 3, 24):
            i = row + x
            total += abs(pa[i] - pb[i]) + abs(pa[i + 1] - pb[i + 1]) + abs(pa[i + 2] - pb[i + 2])
            n += 3
    return total / max(1, n)


def capture_both(stem, before=None, t0=None):
    out = {}
    for tag, pid in PHONES:
        ms, http, raw = shot(pid)
        bmp = save_bmp(f"{tag.lower()}-{stem}.bmp", raw)
        row = {
            "bmp": bmp,
            "png": bmp.replace(".bmp", ".png"),
            "shot_ms": round(ms, 1),
            "http": http,
            "bytes": len(raw),
            "wh": bmp_meta(raw)[1:3],
        }
        if before and t0 is not None and tag in before:
            row["mad_vs_before"] = round(mad(before[tag], raw), 2)
            row["visible_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            row["within_5s"] = row["visible_ms"] <= 5000 and row["mad_vs_before"] >= 8.0
        out[tag] = row
        out[tag]["_raw"] = raw
    return out


def strip_raw(caps):
    return {k: {kk: vv for kk, vv in v.items() if kk != "_raw"} for k, v in caps.items()}


def main():
    dll = hashlib.sha256(DLL.read_bytes()).hexdigest().upper()
    log_start = LOG.read_text(encoding="utf-8", errors="replace").count("\n") if LOG.exists() else None
    pre_ms, pre = kernel_status()
    time.sleep(0.5)
    pre2_ms, pre2 = kernel_status()
    frames = []
    for a in pre["receivers"]:
        b = next(x for x in pre2["receivers"] if x["deviceid"] == a["deviceid"])
        frames.append({
            "deviceid": a["deviceid"],
            "name": a["name"],
            "live": a["live"],
            "state": a["receiver_state"],
            "frames_before": a["frames"],
            "frames_after": b["frames"],
            "delta": b["frames"] - a["frames"],
            "advancing": b["frames"] > a["frames"] and a["live"] and b["live"],
        })

    steps = []
    # settle both to home before the measured sequence
    settle = [call("/key/sendkey", {"fn_key": "Home"}), call("/key/sendkey", {"fn_key": "Home"})]
    time.sleep(0.8)
    base = capture_both("baseline-home")
    base_raw = {k: v["_raw"] for k, v in base.items()}

    def step(name, fun, payload, wait_s, stem):
        before = {k: v["_raw"] for k, v in capture_both(stem + "-before").items()} if False else None
        t0 = time.perf_counter()
        req = call(fun, payload)
        time.sleep(wait_s)
        caps = capture_both(stem, before=None, t0=t0)
        # compare to previous raws passed in closure via last
        return req, caps, t0

    last = base_raw
    sequence = []

    def run_step(n, name, fun, payload, wait_s, stem):
        nonlocal last
        t0 = time.perf_counter()
        req = call(fun, payload)
        time.sleep(wait_s)
        caps = capture_both(stem)
        for tag, row in caps.items():
            row["mad_vs_prev"] = round(mad(last[tag], row["_raw"]), 2)
            row["visible_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            row["within_5s"] = row["visible_ms"] <= 5000
            row["changed"] = row["mad_vs_prev"] >= 8.0
        sequence.append({
            "step": n,
            "name": name,
            "request": req,
            "wait_s": wait_s,
            "phones": strip_raw(caps),
            "both_changed": all(caps[t]["changed"] for t, _ in PHONES),
            "both_within_5s": all(caps[t]["within_5s"] and caps[t]["changed"] for t, _ in PHONES),
        })
        last = {k: v["_raw"] for k, v in caps.items()}
        print(n, name, req["code"], req["rtt_ms"], {t: caps[t]["mad_vs_prev"] for t, _ in PHONES}, flush=True)
        return caps

    run_step(1, "parallel_home", "/key/sendkey", {"fn_key": "Home"}, 0.8, "step1-home")
    run_step(2, "parallel_search_click", "/mouse/click", {"x": 250, "y": 900, "button": 1}, 1.0, "step2-spotlight")
    run_step(3, "parallel_dismiss", "/key/sendkey", {"fn_key": "Home"}, 0.8, "step3-home")
    run_step(4, "parallel_swipe_left", "/mouse/swipe", {"direction": "left", "len": 0.75, "duration": 400}, 1.0, "step4-swipe-left")
    run_step(5, "parallel_swipe_right", "/mouse/swipe", {"direction": "right", "len": 0.75, "duration": 400}, 1.0, "step5-swipe-right")
    run_step(6, "parallel_settle_home", "/key/sendkey", {"fn_key": "Home"}, 0.8, "step6-home")

    # cancellation: hold, stop (not implemented on rollback), immediate null mouse report
    t_down = time.perf_counter()
    down = call("/mouse/down", {"button": 1})
    stop = call("/input/stop", {})
    up = call("/mouse/up", {"button": 1})
    null_report = call("/mouse/up", {})
    release_ms = round((time.perf_counter() - t_down) * 1000, 1)
    time.sleep(0.4)
    after_release = capture_both("step7-after-release")
    for tag, row in after_release.items():
        row["mad_vs_prev"] = round(mad(last[tag], row["_raw"]), 2)
    # clean Home must still work; a stuck drag would move icons or ignore the key
    t_home = time.perf_counter()
    home_after = call("/key/sendkey", {"fn_key": "Home"})
    time.sleep(0.8)
    home_caps = capture_both("step7-home-after-release")
    for tag, row in home_caps.items():
        row["mad_vs_release"] = round(mad(after_release[tag]["_raw"], row["_raw"]), 2)
        row["visible_ms"] = round((time.perf_counter() - t_home) * 1000, 1)
        row["within_5s"] = row["visible_ms"] <= 5000
    # second Home settles page 1 if the first left an app
    home2 = call("/key/sendkey", {"fn_key": "Home"})
    time.sleep(0.8)
    home2_caps = capture_both("step7-home-settled")

    end_ms, end = kernel_status()
    log_lines = []
    if LOG.exists() and log_start is not None:
        log_lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[log_start:]

    out = {
        "model": "Grok 4.7",
        "model_id": "xai-oauth/grok-4.7",
        "at": datetime.now().astimezone().isoformat(),
        "kernel_pid": 31944,
        "kernel_url": BASE,
        "group_id": GROUP,
        "dll_sha256": dll,
        "dll_matches_known_rollback": dll == KNOWN,
        "input_stop_in_rollback_dll": False,
        "preflight": {
            "status_ms": [round(pre_ms, 1), round(pre2_ms, 1)],
            "allowed": pre.get("allowed"),
            "input": pre.get("input"),
            "frames": frames,
            "both_live_advancing": all(f["advancing"] for f in frames) and len(frames) == 2,
        },
        "settle_home": settle,
        "baseline": strip_raw(base),
        "steps": sequence,
        "cancellation": {
            "mouse_down": down,
            "input_stop": stop,
            "mouse_up": up,
            "null_mouse_up": null_report,
            "release_rtt_ms": release_ms,
            "stop_implemented": stop.get("code") == 0,
            "release_path": "mouse/up null report because /input/stop returned code 41",
            "buttons_released": up.get("code") == 0 and null_report.get("code") == 0,
            "buttons_note": "Rollback kernel has no /input/status and does not expose state.Buttons. /mouse/up is the null button report (Buttons=0) in this build.",
            "after_release": strip_raw(after_release),
            "home_after": home_after,
            "home_after_caps": strip_raw(home_caps),
            "home_settle": home2,
            "home_settled": strip_raw(home2_caps),
        },
        "kernel_after": end,
        "kernel_after_ms": round(end_ms, 1),
        "kernel_log_new": log_lines[-80:],
        "pid_unchanged_check": "caller must confirm PID 31944 still iMouse2.Kernel",
    }
    (OUT / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote results", flush=True)


if __name__ == "__main__":
    main()

"""Identify Phone 4's USB board by opening Control Center over direct HID.

Does not restart kernel PID 29564. Uses the already-built kernel only as
--hid-replay, which returns before the HTTP server or receivers start.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image

KERNEL = r"C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0\release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe"
BASE = "http://127.0.0.1:9913/api"
PHONE = "3A:DC:15:FB:DD:EC"
KERNEL_PID = 29564
OUT = Path(__file__).resolve().parent
CANDIDATES = ["3523", "764E", "374C", "724E", "9515", "7949", "704E", "694E", "1814", "E414", "F215"]
NULL = "A200000000000000"
TAB = "A2002B0000000000"
GUI_H = "A2080B0000000000"
CHORD_PREFIX = "A200000000000002"
CONTROLBAR = "A200060000000002"


def now():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def bmp_pixels(raw):
    off = struct.unpack_from("<I", raw, 10)[0]
    w = struct.unpack_from("<i", raw, 18)[0]
    h = abs(struct.unpack_from("<i", raw, 22)[0])
    bits = struct.unpack_from("<H", raw, 28)[0]
    stride = ((w * (bits // 8) + 3) // 4) * 4
    return memoryview(raw)[off:], w, h, bits, stride


def mad(a, b):
    pa, w, h, bits, stride = bmp_pixels(a)
    pb, w2, h2, bits2, stride2 = bmp_pixels(b)
    if (w, h, bits, stride) != (w2, h2, bits2, stride2) or bits != 24:
        return 999.0
    total = n = 0
    row_bytes = w * 3
    for y in range(0, h, 2):
        row = y * stride
        for x in range(0, row_bytes, 6):
            i = row + x
            total += abs(pa[i] - pb[i]) + abs(pa[i + 1] - pb[i + 1]) + abs(pa[i + 2] - pb[i + 2])
            n += 3
    return round(total / max(1, n), 2)


def shot():
    req = urllib.request.Request(f"{BASE}/pic/screenshot?id={PHONE}&binary=true")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read()
    if not raw.startswith(b"BM"):
        raise RuntimeError(raw[:80])
    return raw, round((time.perf_counter() - t0) * 1000, 1)


def save_png(raw, name):
    path = OUT / name
    Image.open(io.BytesIO(raw)).save(path, "PNG")
    return {"file": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def kernel_alive():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {KERNEL_PID} -ErrorAction SilentlyContinue).ProcessName"],
        capture_output=True, text=True, timeout=15,
    )
    return "iMouse2.Kernel" in out.stdout


def replay(pid, steps, label):
    path = OUT / f"replay-{label}-{pid}.json"
    path.write_text(json.dumps([{"Hex": h, "DelayMs": d} for h, d in steps]), encoding="utf-8")
    t0 = time.perf_counter()
    proc = subprocess.run(
        [KERNEL, "--hid-replay", pid, str(path)],
        capture_output=True, text=True, timeout=25,
    )
    return {
        "pid": pid,
        "label": label,
        "exit": proc.returncode,
        "ms": round((time.perf_counter() - t0) * 1000, 1),
        "stdout": proc.stdout.strip()[-500:],
        "stderr": proc.stderr.strip()[-500:],
    }


def stroke(report, hold_ms=60):
    return [(NULL, 45), (report, hold_ms), (NULL, 35)]


def controlbar():
    # InputRouter fn_key=ControlBar. Assignment bytes A2 00 2B then A2 01 10 are not this chord.
    return stroke(TAB) + [(CHORD_PREFIX, 45), (CONTROLBAR, 60), (NULL, 0)]


def home_once():
    return stroke(TAB) + stroke(GUI_H)


def mouse(buttons, dx, dy):
    return f"A1{buttons:02X}{dx & 0xFF:02X}{dy & 0xFF:02X}00000000"


def search_click():
    origin, ppu = 14, 5.1
    tx = max(0, round((250 - origin) / ppu))
    ty = max(0, round((900 - origin) / ppu))
    steps = max(tx, ty)
    reports = [(mouse(0, 0, 0), 0), (NULL, 0)]
    reports += [(mouse(0, -127, -127), 10)] * 4
    sx = sy = 0
    for i in range(1, steps + 1):
        nx = round(tx * i / steps)
        ny = round(ty * i / steps)
        reports.append((mouse(0, nx - sx, ny - sy), 7))
        sx, sy = nx, ny
    reports += [(mouse(0, 0, 0), 120), (mouse(1, 0, 0), 80), (mouse(0, 0, 0), 0)]
    return reports, {"tx": tx, "ty": ty, "steps": steps, "origin": origin, "ppu": ppu, "x": 250, "y": 900}


def main():
    if not kernel_alive():
        raise SystemExit(f"kernel {KERNEL_PID} is not running")
    log = {
        "model": "grok-4.7",
        "phone": PHONE,
        "kernel_pid": KERNEL_PID,
        "kernel_left_running": True,
        "started": now(),
        "controlbar_reports": [h for h, _ in controlbar()],
        "controlbar_note": "Assignment bytes A2002B0000000000 then A201100000000000 are not ControlBar. Used verified kernel chord.",
        "candidates": [],
        "match": None,
    }
    baseline, shot_ms = shot()
    time.sleep(0.8)
    idle, _ = shot()
    log["baseline"] = save_png(baseline, "phone4-baseline.png")
    log["baseline"]["shot_ms"] = shot_ms
    log["baseline"]["wh"] = list(bmp_pixels(baseline)[1:3])
    log["idle_mad"] = mad(baseline, idle)
    print(f"baseline {log['baseline']['wh']} idle_mad={log['idle_mad']}", flush=True)

    matched = None
    cc_raw = None
    for pid in CANDIDATES:
        row = {"pid": pid, "at": now()}
        row["hid"] = replay(pid, controlbar(), "controlbar")
        time.sleep(0.8)
        raw, row["shot_ms"] = shot()
        row["mad"] = mad(baseline, raw)
        row["png"] = save_png(raw, f"phone4-probe-{pid}.png")["file"]
        print(f"{pid} mad={row['mad']} exit={row['hid']['exit']}", flush=True)
        if row["mad"] > 10.0 and row["hid"]["exit"] == 0:
            time.sleep(0.35)
            raw2, _ = shot()
            row["mad_persist"] = mad(baseline, raw2)
            if row["mad_persist"] > 10.0:
                row["matched"] = True
                cc_raw = raw2
                log["matched_cc"] = save_png(raw2, "phone4-matched-cc.png")
                log["candidates"].append(row)
                matched = pid
                break
            row["note"] = "transient mad, not a persistent overlay"
        row["home"] = replay(pid, home_once(), "home")
        log["candidates"].append(row)
        time.sleep(0.25)

    if matched:
        log["dismiss"] = replay(matched, home_once() + home_once(), "home2")
        time.sleep(0.8)
        after, _ = shot()
        log["after_dismiss"] = save_png(after, "phone4-after-dismiss.png")
        log["after_dismiss"]["mad_vs_baseline"] = mad(baseline, after)
        log["after_dismiss"]["mad_vs_cc"] = mad(after, cc_raw)
        click, meta = search_click()
        before_click, _ = shot()
        log["click_before"] = save_png(before_click, "phone4-search-before.png")
        log["click_hid"] = replay(matched, click, "search")
        log["click_plan"] = meta
        time.sleep(0.9)
        searched, _ = shot()
        log["click_after"] = save_png(searched, "phone4-search-after.png")
        log["click_after"]["mad_vs_before"] = mad(before_click, searched)
        replay(matched, home_once(), "home-after-search")
        time.sleep(0.6)
        final, _ = shot()
        log["final_home"] = save_png(final, "phone4-final-home.png")
        log["match"] = matched

    log["kernel_still_alive"] = kernel_alive()
    log["finished"] = now()
    (OUT / "results.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print("MATCH", matched, "kernel", log["kernel_still_alive"], flush=True)


if __name__ == "__main__":
    main()

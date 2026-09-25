"""Prove board 9515 controls the live iMouse2-Phone5 frame. Does not restart the kernel."""
from __future__ import annotations

import hashlib
import io
import json
import struct
import subprocess
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

from PIL import Image

KERNEL = r"C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0\release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe"
BASE = "http://127.0.0.1:9913/api"
PHONE_MAC = "D6:5E:EE:14:38:88"
SESSION = "*"  # running kernel keys iMouse2-Phone5 as devices.json deviceid, not the AirPlay MAC
BOARD = "9515"
OUT = Path(__file__).resolve().parent
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


def kernel_pid():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='iMouse2.Kernel.exe'\" | Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True, timeout=15,
    )
    ids = [int(x) for x in out.stdout.split() if x.isdigit()]
    return ids[0] if ids else 0


def http_get(url):
    t0 = time.perf_counter()
    with urllib.request.urlopen(url, timeout=8) as resp:
        raw = resp.read()
    return raw, round((time.perf_counter() - t0) * 1000, 1)


def shot():
    raw, ms = http_get(f"{BASE}/pic/screenshot?id={urllib.parse.quote(SESSION)}&binary=true")
    if not raw.startswith(b"BM"):
        raise RuntimeError(raw[:120])
    return raw, ms


def save(raw, stem):
    bmp = OUT / f"{stem}.bmp"
    png = OUT / f"{stem}.png"
    bmp.write_bytes(raw)
    Image.open(io.BytesIO(raw)).save(png, "PNG")
    return {
        "bmp": bmp.name,
        "png": png.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "png_bytes": png.stat().st_size,
    }


def replay(steps, label):
    path = OUT / f"replay-{label}.json"
    path.write_text(json.dumps([{"Hex": h, "DelayMs": d} for h, d in steps]), encoding="utf-8")
    t0 = time.perf_counter()
    proc = subprocess.run([KERNEL, "--hid-replay", BOARD, str(path)], capture_output=True, text=True, timeout=40)
    return {
        "board": BOARD,
        "label": label,
        "reports": len(steps),
        "exit": proc.returncode,
        "ms": round((time.perf_counter() - t0) * 1000, 1),
        "stdout": proc.stdout.strip()[-500:],
        "stderr": proc.stderr.strip()[-500:],
    }


def stroke(report, hold_ms=60):
    return [(NULL, 45), (report, hold_ms), (NULL, 35)]


def controlbar():
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
    return reports, {"tx": tx, "ty": ty, "steps": steps, "origin": origin, "ppu": ppu, "x": 250, "y": 900, "pacing_ms": 7}


def main():
    import urllib.parse
    pid = kernel_pid()
    if not pid:
        raise SystemExit("kernel not running")
    log = {
        "model": "grok-4.7",
        "phone": PHONE_MAC,
        "board": BOARD,
        "board_uid": "9515BEBD",
        "session_id": SESSION,
        "receiver": "iMouse2-Phone5",
        "port": 7150,
        "kernel_pid": pid,
        "kernel_pid_assignment": 29564,
        "kernel_left_running": True,
        "started": now(),
        "screenshot_id_note": "Running kernel session key is devices.json deviceid '*', not the AirPlay MAC. Requested id returned Unknown receiver device. Frames are the live iMouse2-Phone5 session whose receiver log names this MAC.",
    }
    mac_raw, mac_ms = http_get(f"{BASE}/pic/screenshot?id={urllib.parse.quote(PHONE_MAC)}&binary=true")
    log["requested_id_attempt"] = {"ms": mac_ms, "bytes": len(mac_raw), "body": mac_raw[:160].decode("utf-8", "replace")}
    baseline, log["baseline_ms"] = shot()
    log["baseline"] = save(baseline, "01-baseline")
    idle, _ = shot()
    log["idle_mad"] = mad(baseline, idle)
    log["controlbar_reports"] = [h for h, _ in controlbar()]
    log["controlbar"] = replay(controlbar(), "controlbar")
    time.sleep(0.8)
    cc, log["controlbar_shot_ms"] = shot()
    log["controlbar_frame"] = save(cc, "02-controlbar")
    log["controlbar_mad"] = mad(baseline, cc)
    log["control_center_opened"] = log["controlbar_mad"] > 10.0
    homes = home_once() + home_once()
    log["home_after_controlbar"] = replay(homes, "home-after-controlbar")
    time.sleep(0.8)
    home, _ = shot()
    log["home_frame"] = save(home, "03-home")
    log["home_mad_vs_controlbar"] = mad(cc, home)
    log["home_mad_vs_baseline"] = mad(baseline, home)
    click, plan = search_click()
    log["click_plan"] = plan
    log["search"] = replay(click, "search")
    time.sleep(0.8)
    spot, _ = shot()
    log["spotlight_frame"] = save(spot, "04-spotlight")
    log["spotlight_mad"] = mad(home, spot)
    log["spotlight_opened"] = log["spotlight_mad"] > 10.0
    log["home_after_spotlight"] = replay(homes, "home-after-spotlight")
    time.sleep(0.8)
    final, _ = shot()
    log["final_home"] = save(final, "05-final-home")
    log["final_mad_vs_spotlight"] = mad(spot, final)
    log["kernel_still_alive"] = kernel_pid() == pid
    log["finished"] = now()
    (OUT / "results.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(json.dumps({k: log[k] for k in (
        "kernel_pid", "controlbar_mad", "control_center_opened", "spotlight_mad",
        "spotlight_opened", "kernel_still_alive", "controlbar", "search")}, indent=2))


if __name__ == "__main__":
    main()

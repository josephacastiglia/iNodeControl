"""Gate 5 everyday controls. Single-id API. No retries. Does not touch process lifetime."""
from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
PHONES = [("C24C", "86:1D:4A:04:2F:F6"), ("C241", "FE:A9:BC:D7:A0:44")]
THRESHOLD = 5.0
DLL = Path(r"C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0\release\iMouse2-kernel-two-phone\iMouse2.Kernel.dll")
KNOWN_DLL = "A995CF5B92AEE4393E164FA4CE68D446A3F63D4D0CAAA73B5ACB6DCF587851BF"


def api(method, url, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return time.perf_counter() - t0, raw


def status():
    _, raw = api("GET", BASE + "/kernel/status")
    return json.loads(raw)["data"]


def send(pid, fun, payload):
    elapsed, raw = api("POST", BASE + "/", {"fun": fun, "data": {"id": pid, **payload}})
    body = json.loads(raw)
    if body.get("status") != 200 or body["data"].get("code") != 0:
        raise RuntimeError(raw.decode(errors="replace")[:500])
    return elapsed, body["data"].get("code")


def shot(pid):
    elapsed, raw = api("GET", f"{BASE}/pic/screenshot?id={pid}&binary=true", timeout=8)
    if raw[:2] != b"BM":
        raise RuntimeError("not bmp: " + raw[:80].decode(errors="replace"))
    return elapsed, raw


def save(name, raw):
    (OUT / name).write_bytes(raw)
    return name


def bmp_body(raw):
    off = struct.unpack_from("<I", raw, 10)[0]
    w = struct.unpack_from("<i", raw, 18)[0]
    h = abs(struct.unpack_from("<i", raw, 22)[0])
    bits = struct.unpack_from("<H", raw, 28)[0]
    stride = ((w * (bits // 8) + 3) // 4) * 4
    return raw[off:], w, h, stride


def mad(a, b):
    pa, wa, ha, sa = bmp_body(a)
    pb, wb, hb, sb = bmp_body(b)
    if (wa, ha, sa) != (wb, hb, sb):
        return 999.0
    # Skip clock (top of screen = high y in bottom-up BMP) and home indicator.
    y0, y1 = 80, ha - 140
    total = 0
    n = 0
    for y in range(y0, y1, 4):
        row = y * sa
        for x in range(0, wa * 3, 24):
            i = row + x
            total += abs(pa[i] - pb[i]) + abs(pa[i + 1] - pb[i + 1]) + abs(pa[i + 2] - pb[i + 2])
            n += 3
    return total / max(1, n)


def poll(pid, before, t0, name):
    """First body change after the request, still inside the 5s budget when possible."""
    last = before
    shot_ms = 0.0
    changed = None
    while True:
        elapsed = time.perf_counter() - t0
        if elapsed >= THRESHOLD and changed is None:
            break
        if changed is not None and time.perf_counter() - t0 >= min(THRESHOLD, changed[0] + 0.35):
            break
        shot_ms, raw = shot(pid)
        last = raw
        delta = mad(before, raw)
        if changed is None and delta >= 8.0:
            changed = (time.perf_counter() - t0, delta)
        if changed is None and time.perf_counter() - t0 >= THRESHOLD:
            break
        if changed is None:
            time.sleep(0.12)
    visible = None if changed is None else round(changed[0] * 1000, 1)
    delta = None if changed is None else round(changed[1], 2)
    path = save(name, last)
    return {
        "bmp": path,
        "visible_ms": visible,
        "within_5s": visible is not None and visible <= 5000,
        "mad": delta if delta is not None else round(mad(before, last), 2),
        "shot_ms": round(shot_ms * 1000, 1),
        "changed": changed is not None,
    }


def iso(other, name):
    ms, raw = shot(other)
    return {"bmp": save(name, raw), "shot_ms": round(ms * 1000, 1)}


def home_both():
    out = []
    for tag, pid in PHONES:
        ms, code = send(pid, "/key/sendkey", {"fn_key": "Home"})
        out.append({"phone": tag, "api_ms": round(ms * 1000, 1), "code": code})
    time.sleep(0.7)
    return out


def main():
    pre = json.loads((OUT / "predeclared-cases.json").read_text(encoding="utf-8"))
    guard = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(OUT / "minimize-console.ps1")],
        capture_output=True, text=True, timeout=30,
    )
    guard_json = json.loads(guard.stdout)
    if guard.returncode != 0 or not guard_json.get("iconic") or guard_json.get("mirror_on_count"):
        raise SystemExit("pre-input guard failed: " + guard.stdout)

    dll_hash = hashlib.sha256(DLL.read_bytes()).hexdigest().upper()
    log = Path(r"C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0\analysis\two-phone-config\kernel-stdout.log")
    log_start = log.read_text(encoding="utf-8", errors="replace").count("\n") if log.exists() else None
    start = status()
    rows = []
    setup = home_both()
    baselines = {}
    for tag, pid in PHONES:
        _, raw = shot(pid)
        baselines[tag] = save(f"{tag.lower()}-baseline-home.bmp", raw)

    for tag, pid in PHONES:
        other_tag, other = next(p for p in PHONES if p[0] != tag)

        before = (OUT / baselines[tag]).read_bytes()
        t0 = time.perf_counter()
        api_ms, code = send(pid, "/key/sendkey", {"fn_key": "ControlBar"})
        effect = poll(pid, before, t0, f"{tag.lower()}-control-center.bmp")
        other_shot = iso(other, f"{other_tag.lower()}-iso-during-{tag.lower()}-control-center.bmp")
        t1 = time.perf_counter()
        dismiss_ms, dismiss_code = send(pid, "/key/sendkey", {"fn_key": "Home"})
        dismiss = poll(pid, (OUT / effect["bmp"]).read_bytes(), t1, f"{tag.lower()}-control-center-dismiss.bmp")
        dismiss_iso = iso(other, f"{other_tag.lower()}-iso-during-{tag.lower()}-control-center-dismiss.bmp")
        rows.append({
            "phone": tag, "case": "control_center", "api_ms": round(api_ms * 1000, 1), "code": code,
            "expected": "Control Center visible within 5s", **effect,
            "isolation_bmp": other_shot["bmp"], "isolation_shot_ms": other_shot["shot_ms"],
            "dismiss_api_ms": round(dismiss_ms * 1000, 1), "dismiss_code": dismiss_code,
            "dismiss_bmp": dismiss["bmp"], "dismiss_visible_ms": dismiss["visible_ms"],
            "dismiss_within_5s": dismiss["within_5s"], "dismiss_iso_bmp": dismiss_iso["bmp"],
        })
        print("control", tag, effect["visible_ms"], flush=True)

        before = (OUT / dismiss["bmp"]).read_bytes()
        t0 = time.perf_counter()
        api_ms, code = send(pid, "/key/sendkey", {"fn_key": "AppSwitch"})
        effect = poll(pid, before, t0, f"{tag.lower()}-app-switcher.bmp")
        other_shot = iso(other, f"{other_tag.lower()}-iso-during-{tag.lower()}-app-switcher.bmp")
        t1 = time.perf_counter()
        dismiss_ms, dismiss_code = send(pid, "/key/sendkey", {"fn_key": "Home"})
        dismiss = poll(pid, (OUT / effect["bmp"]).read_bytes(), t1, f"{tag.lower()}-app-switcher-dismiss.bmp")
        dismiss_iso = iso(other, f"{other_tag.lower()}-iso-during-{tag.lower()}-app-switcher-dismiss.bmp")
        rows.append({
            "phone": tag, "case": "app_switcher", "api_ms": round(api_ms * 1000, 1), "code": code,
            "expected": "App Switcher cards visible within 5s", **effect,
            "isolation_bmp": other_shot["bmp"], "isolation_shot_ms": other_shot["shot_ms"],
            "dismiss_api_ms": round(dismiss_ms * 1000, 1), "dismiss_code": dismiss_code,
            "dismiss_bmp": dismiss["bmp"], "dismiss_visible_ms": dismiss["visible_ms"],
            "dismiss_within_5s": dismiss["within_5s"], "dismiss_iso_bmp": dismiss_iso["bmp"],
        })
        print("switcher", tag, effect["visible_ms"], flush=True)

        home_ms, home_code = send(pid, "/key/sendkey", {"fn_key": "Home"})
        time.sleep(0.7)
        _, home_raw = shot(pid)
        home_bmp = save(f"{tag.lower()}-text-home.bmp", home_raw)
        t0 = time.perf_counter()
        click_ms, click_code = send(pid, "/mouse/click", {"x": 250, "y": 900, "button": 1})
        spot = poll(pid, home_raw, t0, f"{tag.lower()}-spotlight.bmp")
        spot_iso = iso(other, f"{other_tag.lower()}-iso-during-{tag.lower()}-spotlight.bmp")
        t0 = time.perf_counter()
        type_ms, type_code = send(pid, "/key/sendkey", {"key": "iMouse2026"})
        typed = poll(pid, (OUT / spot["bmp"]).read_bytes(), t0, f"{tag.lower()}-typed.bmp")
        typed_iso = iso(other, f"{other_tag.lower()}-iso-during-{tag.lower()}-typed.bmp")
        t0 = time.perf_counter()
        bk_ms = []
        bk_code = []
        for _ in range(4):
            ms, code = send(pid, "/key/sendkey", {"fn_key": "Backspace"})
            bk_ms.append(round(ms * 1000, 1))
            bk_code.append(code)
        backed = poll(pid, (OUT / typed["bmp"]).read_bytes(), t0, f"{tag.lower()}-backspace.bmp")
        backed_iso = iso(other, f"{other_tag.lower()}-iso-during-{tag.lower()}-backspace.bmp")
        t1 = time.perf_counter()
        dismiss_ms, dismiss_code = send(pid, "/key/sendkey", {"fn_key": "Home"})
        dismiss = poll(pid, (OUT / backed["bmp"]).read_bytes(), t1, f"{tag.lower()}-text-dismiss.bmp")
        dismiss_iso = iso(other, f"{other_tag.lower()}-iso-during-{tag.lower()}-text-dismiss.bmp")
        rows.append({
            "phone": tag, "case": "text_and_backspace",
            "home_api_ms": round(home_ms * 1000, 1), "home_code": home_code, "home_bmp": home_bmp,
            "click": {"x": 250, "y": 900, "api_ms": round(click_ms * 1000, 1), "code": click_code},
            "spotlight": spot, "spotlight_iso": spot_iso["bmp"],
            "typed_api_ms": round(type_ms * 1000, 1), "typed_code": type_code,
            "typed_expected": "iMouse2026", "typed": typed, "typed_iso": typed_iso["bmp"],
            "backspace_api_ms": bk_ms, "backspace_codes": bk_code,
            "backspace_expected": "iMouse", "backspace": backed, "backspace_iso": backed_iso["bmp"],
            "dismiss_api_ms": round(dismiss_ms * 1000, 1), "dismiss_code": dismiss_code,
            "dismiss": dismiss, "dismiss_iso": dismiss_iso["bmp"],
        })
        print("text", tag, typed["visible_ms"], backed["visible_ms"], flush=True)

        _, pre_raw = shot(pid)
        pre_bmp = save(f"{tag.lower()}-pre-swipe.bmp", pre_raw)
        t0 = time.perf_counter()
        left_ms, left_code = send(pid, "/mouse/swipe", {"direction": "left", "len": 0.75, "duration": 400})
        left = poll(pid, pre_raw, t0, f"{tag.lower()}-swipe-left.bmp")
        left_iso = iso(other, f"{other_tag.lower()}-iso-during-{tag.lower()}-swipe-left.bmp")
        t0 = time.perf_counter()
        right_ms, right_code = send(pid, "/mouse/swipe", {"direction": "right", "len": 0.75, "duration": 400})
        right = poll(pid, (OUT / left["bmp"]).read_bytes(), t0, f"{tag.lower()}-swipe-right.bmp")
        right_iso = iso(other, f"{other_tag.lower()}-iso-during-{tag.lower()}-swipe-right.bmp")
        up_ms, up_code = send(pid, "/mouse/up", {"button": 1})
        rows.append({
            "phone": tag, "case": "swipes", "pre_bmp": pre_bmp,
            "left_api_ms": round(left_ms * 1000, 1), "left_code": left_code,
            "left_expected": "Home page 2 within 5s", "left": left, "left_iso": left_iso["bmp"],
            "right_api_ms": round(right_ms * 1000, 1), "right_code": right_code,
            "right_expected": "Home page 1 within 5s", "right": right, "right_iso": right_iso["bmp"],
            "mouse_up_ms": round(up_ms * 1000, 1), "mouse_up_code": up_code,
        })
        print("swipe", tag, left["visible_ms"], right["visible_ms"], flush=True)

    for _, pid in PHONES:
        send(pid, "/mouse/up", {"button": 1})
    end = status()
    log_lines = []
    if log.exists() and log_start is not None:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        log_lines = lines[log_start:]
    out = {
        "predeclared": pre["cases"],
        "guard": guard_json,
        "dll_sha256": dll_hash,
        "dll_matches_known_rollback": dll_hash == KNOWN_DLL,
        "setup_home": setup,
        "baselines": baselines,
        "start": start,
        "end": end,
        "kernel_log_new": log_lines,
        "rows": rows,
    }
    (OUT / "timings.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote timings", len(rows), "log", len(log_lines), flush=True)


if __name__ == "__main__":
    main()

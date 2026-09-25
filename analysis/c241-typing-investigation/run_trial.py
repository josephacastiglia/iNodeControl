"""C241 typing trial. Targets FE:A9:BC:D7:A0:44 only. Does not touch process lifetime."""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
C241 = "FE:A9:BC:D7:A0:44"
log = []


def api(method, url, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return time.perf_counter() - t0, raw


def send(fun, payload):
    elapsed, raw = api("POST", BASE + "/", {"fun": fun, "data": {"id": C241, **payload}})
    body = json.loads(raw)
    entry = {"fun": fun, "id": C241, "payload": payload, "ms": round(elapsed * 1000, 1), "body": body}
    log.append(entry)
    print(json.dumps(entry)[:600], flush=True)
    if body.get("status") != 200 or body.get("data", {}).get("code") != 0:
        raise RuntimeError(raw.decode(errors="replace")[:500])
    return entry


def shot(name):
    elapsed, raw = api("GET", f"{BASE}/pic/screenshot?id={C241}&binary=true", timeout=8)
    if raw[:2] != b"BM":
        raise RuntimeError("not bmp: " + raw[:80].decode(errors="replace"))
    bmp = OUT / (Path(name).stem + ".bmp")
    bmp.write_bytes(raw)
    png = OUT / name
    ps = (
        "Add-Type -AssemblyName System.Drawing; "
        f"$img=[System.Drawing.Image]::FromFile('{bmp}'); "
        f"$img.Save('{png}', [System.Drawing.Imaging.ImageFormat]::Png); $img.Dispose()"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], check=True)
    print(f"saved {name} {len(raw)} bytes shot_ms={elapsed*1000:.1f}", flush=True)
    return name


def phase_main():
    send("/key/sendkey", {"fn_key": "Home"})
    time.sleep(0.5)
    send("/key/sendkey", {"fn_key": "Home"})
    time.sleep(0.8)
    shot("c241-home.png")
    send("/mouse/click", {"x": 250, "y": 900, "button": 1})
    time.sleep(1.0)
    shot("c241-spotlight.png")
    send("/key/sendkey", {"key": "test123"})
    time.sleep(0.8)
    shot("c241-typed.png")


def phase_fallback():
    send("/mouse/click", {"x": 200, "y": 1006, "button": 1})
    time.sleep(0.4)
    send("/key/sendkey", {"key": "abc"})
    time.sleep(0.5)
    shot("c241-after-tap.png")
    send("/key/sendkey", {"fn_key": "Tab"})
    time.sleep(0.4)
    send("/key/sendkey", {"key": "xyz"})
    time.sleep(0.5)
    shot("c241-after-tab.png")


def phase_home():
    send("/key/sendkey", {"fn_key": "Home"})
    time.sleep(0.5)
    send("/key/sendkey", {"fn_key": "Home"})
    time.sleep(0.6)
    shot("c241-final-home.png")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "main"
    {"main": phase_main, "fallback": phase_fallback, "home": phase_home}[which]()
    path = OUT / "trial-log.json"
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    path.write_text(json.dumps(prev + log, indent=2), encoding="utf-8")
    print(which, "done", flush=True)

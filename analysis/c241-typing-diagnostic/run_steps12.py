"""C241 typing diagnostic steps 1-2. Single id only. Does not touch process lifetime."""
import json
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
C241 = "FE:A9:BC:D7:A0:44"
C24C = "86:1D:4A:04:2F:F6"
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


def send(pid, fun, payload):
    elapsed, raw = api("POST", BASE + "/", {"fun": fun, "data": {"id": pid, **payload}})
    body = json.loads(raw)
    entry = {"fun": fun, "id": pid, "payload": payload, "ms": round(elapsed * 1000, 1), "body": body}
    log.append(entry)
    print(json.dumps(entry)[:500], flush=True)
    if body.get("status") != 200 or body.get("data", {}).get("code") != 0:
        raise RuntimeError(raw.decode(errors="replace")[:500])
    return entry


def shot(pid, name):
    elapsed, raw = api("GET", f"{BASE}/pic/screenshot?id={pid}&binary=true", timeout=8)
    if raw[:2] != b"BM":
        raise RuntimeError("not bmp: " + raw[:80].decode(errors="replace"))
    path = OUT / name
    path.write_bytes(raw)
    png = path.with_suffix(".png")
    ps = (
        "Add-Type -AssemblyName System.Drawing; "
        f"$img=[System.Drawing.Image]::FromFile('{path}'); "
        f"$img.Save('{png}', [System.Drawing.Imaging.ImageFormat]::Png); $img.Dispose()"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], check=True)
    print(f"saved {name} {len(raw)} bytes shot_ms={elapsed*1000:.1f}", flush=True)
    return name


send(C241, "/key/sendkey", {"fn_key": "Home"})
time.sleep(0.8)
send(C241, "/mouse/click", {"x": 250, "y": 900, "button": 1})
time.sleep(1.0)
shot(C241, "c241-step1-settled.bmp")
send(C241, "/key/sendkey", {"key": "hello"})
time.sleep(0.8)
shot(C241, "c241-step2-typed.bmp")
shot(C24C, "c24c-iso-after-step2.bmp")
(OUT / "steps12-log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
print("steps12 done", flush=True)

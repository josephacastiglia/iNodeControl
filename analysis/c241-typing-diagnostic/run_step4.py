"""Corrected in-field click plus single-key probes. C241 only."""
import json
import subprocess
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
    entry = {"fun": fun, "payload": payload, "ms": round(elapsed * 1000, 1), "body": body}
    log.append(entry)
    print(json.dumps(entry)[:400], flush=True)
    if body.get("status") != 200 or body.get("data", {}).get("code") != 0:
        raise RuntimeError(raw.decode(errors="replace")[:500])


def shot(name):
    _, raw = api("GET", f"{BASE}/pic/screenshot?id={C241}&binary=true", timeout=8)
    if raw[:2] != b"BM":
        raise RuntimeError("not bmp")
    path = OUT / name
    path.write_bytes(raw)
    png = path.with_suffix(".png")
    ps = (
        "Add-Type -AssemblyName System.Drawing; "
        f"$img=[System.Drawing.Image]::FromFile('{path}'); "
        f"$img.Save('{png}', [System.Drawing.Imaging.ImageFormat]::Png); $img.Dispose()"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], check=True)
    print("saved", name, flush=True)


send("/key/sendkey", {"fn_key": "Home"})
time.sleep(0.8)
send("/mouse/click", {"x": 250, "y": 900, "button": 1})
time.sleep(1.0)
shot("c241-step4-spotlight.bmp")
# Pixel probe of step2 put the Spotlight pill at about y=980-1032, x=30-470.
send("/mouse/click", {"x": 200, "y": 1006, "button": 1})
time.sleep(0.5)
shot("c241-step4-infield-click.bmp")
send("/key/sendkey", {"key": "a"})
time.sleep(0.6)
shot("c241-step4-letter-a.bmp")
send("/key/sendkey", {"key": " "})
time.sleep(0.6)
shot("c241-step4-space.bmp")
send("/key/sendkey", {"fn_key": "Backspace"})
time.sleep(0.6)
shot("c241-step4-backspace.bmp")
(OUT / "step4-log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
print("step4 done", flush=True)

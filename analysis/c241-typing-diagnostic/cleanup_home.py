import json, subprocess, time, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
C241 = "FE:A9:BC:D7:A0:44"


def api(method, url, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def send(payload):
    raw = api("POST", BASE + "/", {"fun": "/key/sendkey", "data": {"id": C241, **payload}})
    body = json.loads(raw)
    print(json.dumps(body)[:300], flush=True)
    if body.get("data", {}).get("code") != 0:
        raise RuntimeError(raw.decode(errors="replace")[:300])


def shot(name):
    raw = api("GET", f"{BASE}/pic/screenshot?id={C241}&binary=true")
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


send({"fn_key": "Home"})
time.sleep(0.8)
send({"fn_key": "Home"})
time.sleep(0.6)
shot("c241-cleanup-final.bmp")
print("cleanup done", flush=True)

"""One swipe on F215 to see if any HID reaches the phone. Does not restart the kernel."""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
F215 = "3A:DC:15:FB:DD:EC"


def api(method, url, body=None, timeout=20):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def post(fun, payload):
    raw = api("POST", BASE + "/", {"fun": fun, "data": payload})
    return json.loads(raw)["data"]


def shot(name):
    raw = api("GET", f"{BASE}/pic/screenshot?id={F215}&binary=true")
    if not raw.startswith(b"BM"):
        raise RuntimeError(raw[:80])
    (OUT / name).write_bytes(raw)


def main():
    data = post("/input/acquire", {"id": F215, "lease_ms": 30000})
    if data.get("code") != 0:
        raise SystemExit(data)
    token = data["leases"][0]["token"]
    try:
        shot("probe-f215-before-swipe.bmp")
        swipe = post("/mouse/swipe", {"id": F215, "token": token, "direction": "left", "len": 0.75})
        time.sleep(1.0)
        shot("probe-f215-after-swipe.bmp")
        print(json.dumps({"code": swipe.get("code"), "message": swipe.get("message"), "results": swipe.get("results")}))
    finally:
        rel = post("/input/release", {"id": F215, "token": token})
        print("released", rel.get("code"), rel.get("message"))


if __name__ == "__main__":
    main()

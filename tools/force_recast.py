"""Force-recast one phone onto its iMouse receiver over USB-HID.

Opens Control Center, taps the Screen Mirroring tile, selects that phone's
receiver row, then dismisses to Home. Targets one device id only.

A tap on an already-checked row stops mirroring. If that happens, the same
select sequence runs once more from Home so the recast ends live.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TILE = (199, 432)
STOP_ROW = (250, 724)
PHONES = {
    # ponytail: vendor-absent grid. +63px per AirPlay name listed above these two.
    "C24C": {"id": "86:1D:4A:04:2F:F6", "name": "iMouse2-C24C", "row": (250, 472)},
    "C241": {"id": "FE:A9:BC:D7:A0:44", "name": "iMouse2-C241", "row": (250, 535)},
    "C214": {"id": "8A:23:B5:71:35:8D", "name": "iMouse2-C214", "row": (250, 598)},
    "724E": {"id": "3A:DC:15:FB:DD:EC", "name": "iMouse2-F215", "row": (250, 691)},
}
BY_ID = {v["id"].upper(): k for k, v in PHONES.items()}


def api_base(url):
    url = url.rstrip("/")
    return url if url.endswith("/api") else url + "/api"


def _request(base, method, path, body=None, timeout=20):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            code = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        code = exc.code
    parsed = json.loads(raw) if raw else {}
    data = parsed.get("data", parsed)
    if code != 200 or data.get("code") not in (0, None):
        raise RuntimeError(f"{method} {path} http={code} body={raw[:400]!r}")
    return data


def hid(base, fun, device_id, token, **payload):
    return _request(base, "POST", "/", {"fun": fun, "data": {"id": device_id, "token": token, **payload}})


def kernel_status(base):
    return _request(base, "GET", "/kernel/status", timeout=8)


def receiver(status, device_id):
    for row in status.get("receivers") or []:
        if row.get("deviceid", "").upper() == device_id.upper():
            return row
    raise RuntimeError(f"{device_id} missing from kernel status")


def _select(base, device_id, token, row, stop):
    hid(base, "/key/sendkey", device_id, token, fn_key="ControlBar")
    time.sleep(0.8)
    hid(base, "/mouse/click", device_id, token, x=TILE[0], y=TILE[1], button=1)
    time.sleep(0.8)
    if stop:
        hid(base, "/mouse/click", device_id, token, x=STOP_ROW[0], y=STOP_ROW[1], button=1)
        time.sleep(1.0)
        hid(base, "/mouse/click", device_id, token, x=TILE[0], y=TILE[1], button=1)
        time.sleep(0.8)
    hid(base, "/mouse/click", device_id, token, x=row[0], y=row[1], button=1)
    time.sleep(1.2)


def _home(base, device_id, token):
    hid(base, "/key/sendkey", device_id, token, fn_key="Home")
    time.sleep(0.5)
    hid(base, "/key/sendkey", device_id, token, fn_key="Home")
    time.sleep(0.8)


def _wait_live(base, device_id, seconds=12):
    deadline = time.time() + seconds
    last = receiver(kernel_status(base), device_id)
    while time.time() < deadline:
        time.sleep(0.5)
        nxt = receiver(kernel_status(base), device_id)
        if nxt.get("live") and nxt["frames"] > last["frames"]:
            return last, nxt
        last = nxt
    raise RuntimeError(f"stream not live or frames stalled: { {k: last.get(k) for k in ('live', 'frames', 'receiver_state')} }")


def recast(device_id, url="http://127.0.0.1:9913", stop=False):
    """Re-select this phone's mapped receiver. Returns the live/frames check."""
    phone = BY_ID.get(device_id.upper())
    if phone is None:
        raise ValueError(f"unmapped device id {device_id}")
    spec = PHONES[phone]
    if "row" not in spec:
        raise ValueError(f"{phone} receiver {spec['name']} has no measured picker row")
    base = api_base(url)
    lease = _request(base, "POST", "/", {"fun": "/input/acquire", "data": {"id": device_id, "lease_ms": 90000}})
    token = lease["leases"][0]["token"]
    reselected = False
    try:
        before = receiver(kernel_status(base), device_id)
        _home(base, device_id, token)
        _select(base, device_id, token, spec["row"], stop)
        _home(base, device_id, token)
        # ponytail: checked-row tap stops the cast; one more select from Home restores it
        if before.get("live") and not receiver(kernel_status(base), device_id).get("live"):
            reselected = True
            _select(base, device_id, token, spec["row"], stop=False)
            _home(base, device_id, token)
        sample, after = _wait_live(base, device_id)
    finally:
        _request(base, "POST", "/", {"fun": "/input/release", "data": {"id": device_id, "token": token}})
    return {
        "phone": phone,
        "device_id": spec["id"],
        "receiver": spec["name"],
        "row": list(spec["row"]),
        "stop": stop,
        "reselected": reselected,
        "live": after.get("live"),
        "receiver_state": after.get("receiver_state"),
        "frames": [sample["frames"], after["frames"]],
        "frame_delta": after["frames"] - sample["frames"],
        "ok": True,
    }


def resolve(phone, device_id):
    if phone and device_id and PHONES[phone]["id"].upper() != device_id.upper():
        raise SystemExit(f"{phone} is {PHONES[phone]['id']}, not {device_id}")
    if phone:
        return PHONES[phone]["id"]
    if device_id and device_id.upper() in BY_ID:
        return PHONES[BY_ID[device_id.upper()]]["id"]
    raise SystemExit("pass --phone C24C|C241 or a mapped --id")


def main(argv=None):
    p = argparse.ArgumentParser(description="Force-recast one phone onto its iMouse receiver.")
    p.add_argument("--phone", choices=sorted(PHONES))
    p.add_argument("--id")
    p.add_argument("--url", default="http://127.0.0.1:9913")
    p.add_argument("--stop", action="store_true", help="tap Stop Mirroring, reopen the picker, then select")
    args = p.parse_args(argv)
    json.dump(recast(resolve(args.phone, args.id), url=args.url, stop=args.stop), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, urllib.error.URLError, TimeoutError, KeyError) as exc:
        sys.stderr.write(f"{exc}\n")
        raise SystemExit(1)

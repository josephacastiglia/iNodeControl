"""Signal one phone so the operator can match it to its slot. Other phones are not addressed."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

HOLD_S = 1.5
HOME_GAP_S = 0.5
LEASE_MS = 15000


def api_base(url: str) -> str:
    url = url.rstrip("/")
    return url if url.endswith("/api") else url + "/api"


def request(base: str, method: str, path: str, body: dict | None = None, timeout: float = 20) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw, code = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        raw, code = exc.read(), exc.code
    parsed = json.loads(raw) if raw else {}
    payload = parsed.get("data", parsed)
    if code != 200:
        raise RuntimeError(f"{method} {path} http={code} body={raw[:300]!r}")
    return payload


def post(base: str, fun: str, payload: dict) -> dict:
    return request(base, "POST", "/", {"fun": fun, "data": payload})


def _fold(value) -> str:
    return str(value or "").casefold()


def matches(query: str, device: dict, receiver: dict | None) -> bool:
    q = query.casefold()
    fields = [device.get("pid"), device.get("name"), device.get("deviceid"), device.get("uid")]
    if receiver:
        fields.append(receiver.get("name"))
    for field in fields:
        text = _fold(field)
        if text == q or text.endswith("-" + q) or text.endswith(" " + q):
            return True
    return False


def resolve(query: str, devices: list[dict], receivers: list[dict]) -> dict:
    by_id = {row.get("deviceid"): row for row in receivers}
    hits = []
    for device in devices:
        receiver = by_id.get(device.get("deviceid"))
        if matches(query, device, receiver):
            hits.append((device, receiver or {}))
    if len(hits) != 1:
        known = ", ".join(sorted({str(d.get("pid") or d.get("name")) for d in devices}))
        raise SystemExit(f"expected one phone for {query!r}, found {len(hits)} ({known})")
    device, receiver = hits[0]
    device_id = device.get("deviceid")
    if not device_id or "," in str(device_id):
        raise SystemExit(f"refusing multi-target id {device_id!r}")
    return {
        "query": query,
        "board": device.get("pid") or query,
        "name": device.get("name") or receiver.get("name") or query,
        "device_id": device_id,
        "receiver": receiver.get("name"),
    }


def acquire(base: str, device_id: str) -> str:
    deadline = time.monotonic() + 12
    last = ""
    while True:
        status = request(base, "GET", "/input/status", timeout=5)
        row = next((p for p in status.get("phones") or [] if p.get("id") == device_id), None)
        if row and row.get("stopped"):
            raise RuntimeError(f"{device_id} is stopped; not resuming over an operator stop")
        got = post(base, "/input/acquire", {"id": device_id, "lease_ms": LEASE_MS})
        if got.get("code") == 0 and got.get("leases"):
            token = got["leases"][0].get("token")
            if got["leases"][0].get("id") != device_id or not token:
                raise RuntimeError(f"acquire returned an unexpected lease: {got}")
            return token
        last = got.get("message") or str(got)
        if time.monotonic() >= deadline:
            raise RuntimeError(f"lease busy, not stealing it: {last}")
        print(f"waiting for {device_id} lease ({last})", file=sys.stderr)
        time.sleep(0.4)


def send_key(base: str, device_id: str, token: str, fn_key: str) -> None:
    got = post(base, "/key/sendkey", {"id": device_id, "token": token, "fn_key": fn_key})
    if got.get("code") != 0:
        raise RuntimeError(f"{fn_key} failed: {got}")


def signal(query: str, url: str) -> dict:
    base = api_base(url)
    devices = request(base, "GET", "/device/get", timeout=8).get("list") or []
    status = request(base, "GET", "/kernel/status", timeout=8)
    phone = resolve(query, devices, status.get("receivers") or [])
    token = acquire(base, phone["device_id"])
    try:
        send_key(base, phone["device_id"], token, "ControlBar")
        time.sleep(HOLD_S)
        send_key(base, phone["device_id"], token, "Home")
        time.sleep(HOME_GAP_S)
        send_key(base, phone["device_id"], token, "Home")
    finally:
        released = post(base, "/input/release", {"id": phone["device_id"], "token": token})
        if released.get("code") != 0:
            raise RuntimeError(f"release failed: {released}")
    return phone


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flash Control Center on one phone, then return Home.")
    parser.add_argument("--phone", required=True, help="board or name, e.g. C241 or Phone5")
    parser.add_argument("--url", default="http://127.0.0.1:9913/api")
    args = parser.parse_args(argv)
    phone = signal(args.phone, args.url)
    print(f"[IDENTIFY] Visually signaled {phone['board']} ({phone['name']}). Slot identified.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"identify failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

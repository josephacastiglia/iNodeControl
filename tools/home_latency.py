"""Timestamp Home: API completion vs first visual change. One phone ID per trial."""
from __future__ import annotations
import json, time, urllib.request
from pathlib import Path

PHONES = [
    ("C241", "FE:A9:BC:D7:A0:44"),
    ("C24C", "86:1D:4A:04:2F:F6"),
]
BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parents[1] / "analysis" / "home-latency"


def api(method, url, body=None, timeout=40):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    return time.perf_counter() - t0, ctype, raw


def status():
    _, _, raw = api("GET", BASE + "/kernel/status")
    return json.loads(raw)["data"]


def device(phone_id):
    _, _, raw = api("GET", BASE + "/device/get")
    for row in json.loads(raw)["data"]["list"]:
        if row["deviceid"] == phone_id:
            return row
    raise SystemExit("missing " + phone_id)


def send(phone_id, fun, data):
    payload = {"fun": fun, "data": {"id": phone_id, **data}}
    elapsed, _, raw = api("POST", BASE + "/", payload)
    j = json.loads(raw)
    if j.get("status") != 200 or j["data"].get("code") != 0:
        raise RuntimeError(raw.decode())
    return elapsed


def shot(phone_id):
    elapsed, ctype, raw = api("GET", f"{BASE}/pic/screenshot?id={phone_id}&binary=true", timeout=8)
    if raw[:2] != b"BM":
        raise RuntimeError(ctype + raw[:80].decode("utf-8", "replace"))
    return elapsed, raw


def mad(a, b):
    pa, pb = a[54:], b[54:]
    n = min(len(pa), len(pb))
    step = 24
    total = count = 0
    for i in range(0, n, step):
        total += abs(pa[i] - pb[i])
        count += 1
    return total / count if count else 0


def trial(tag, phone_id, n):
    OUT.mkdir(parents=True, exist_ok=True)
    send(phone_id, "/key/sendkey", {"fn_key": "Home"})
    time.sleep(0.8)
    send(phone_id, "/mouse/click", {"x": 250, "y": 900, "button": 1})
    time.sleep(1.0)
    _, spotlight = shot(phone_id)
    (OUT / f"{tag}-{n}-spotlight.bmp").write_bytes(spotlight)
    t_send = time.perf_counter()
    api_s = send(phone_id, "/key/sendkey", {"fn_key": "Home"})
    t_api = time.perf_counter()
    visual_ms = None
    polls = []
    deadline = t_send + 2.5
    last = spotlight
    while time.perf_counter() < deadline:
        fetch_s, frame = shot(phone_id)
        now = time.perf_counter()
        d = mad(spotlight, frame)
        polls.append({"ms_from_send": round((now - t_send) * 1000, 1), "fetch_ms": round(fetch_s * 1000, 1), "mad": round(d, 2)})
        last = frame
        if visual_ms is None and d >= 18:
            visual_ms = (now - t_send) * 1000
            (OUT / f"{tag}-{n}-visual-home.bmp").write_bytes(frame)
            break
    else:
        (OUT / f"{tag}-{n}-timeout.bmp").write_bytes(last)
    st = status()
    rec = next(r for r in st["receivers"] if r["deviceid"] == phone_id)
    return {
        "phone": tag,
        "id": phone_id,
        "api_ms": round(api_s * 1000, 1),
        "api_return_ms": round((t_api - t_send) * 1000, 1),
        "visual_home_ms": None if visual_ms is None else round(visual_ms, 1),
        "video_after_api_ms": None if visual_ms is None else round(visual_ms - (t_api - t_send) * 1000, 1),
        "polls": polls,
        "live": rec["live"],
        "frames": rec["frames"],
    }


def main():
    results = []
    for tag, phone_id in PHONES:
        row = device(phone_id)
        if not row.get("state"):
            raise SystemExit(f"{tag} not live")
        print(tag, row.get("pid"), row.get("receiver_name"), "live")
        for n in range(3):
            r = trial(tag, phone_id, n)
            results.append(r)
            print(json.dumps({k: r[k] for k in r if k != "polls"}))
            time.sleep(0.4)
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("wrote", OUT / "results.json")


if __name__ == "__main__":
    main()

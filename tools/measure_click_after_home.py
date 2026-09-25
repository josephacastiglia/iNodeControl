"""Compare Search click after Home vs without Home; origin vs far point."""
from __future__ import annotations
import json, time, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parents[1] / "analysis" / "click-after-home-20260915"
PHONES = [("C24C", "86:1D:4A:04:2F:F6"), ("C241", "FE:A9:BC:D7:A0:44")]


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


def send(pid, fun, **data):
    elapsed, _, raw = api("POST", BASE + "/", {"fun": fun, "data": {"id": pid, **data}})
    j = json.loads(raw)
    if j.get("status") != 200 or j["data"].get("code") != 0:
        raise RuntimeError(raw.decode())
    return elapsed


def shot(pid):
    elapsed, ctype, raw = api("GET", f"{BASE}/pic/screenshot?id={pid}&binary=true", timeout=8)
    if raw[:2] != b"BM":
        raise RuntimeError("not bmp")
    return raw


def recs():
    st = status()
    return {r["name"]: {"frames": r["frames"], "restarts": r["receiver_restarts"], "live": r["live"]} for r in st["receivers"]}


def click(pid, x, y):
    return send(pid, "/mouse/click", x=x, y=y, button=1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    before = recs()
    for tag, pid in PHONES:
        other = next(p for t, p in PHONES if p != pid)
        send(pid, "/key/sendkey", fn_key="Home")
        time.sleep(0.8)
        t = send(pid, "/key/sendkey", fn_key="Home")
        rows.append({"phone": tag, "kind": "home-only", "api_ms": round(t * 1000, 1)})

        time.sleep(0.5)
        t = click(pid, 20, 20)
        rows.append({"phone": tag, "kind": "home-then-origin-click", "api_ms": round(t * 1000, 1)})
        print(rows[-1])

        send(pid, "/key/sendkey", fn_key="Home")
        time.sleep(0.8)
        t = click(pid, 250, 900)
        time.sleep(0.5)
        img = shot(pid)
        (OUT / f"{tag}-home-then-search.bmp").write_bytes(img)
        rows.append({"phone": tag, "kind": "home-then-search", "api_ms": round(t * 1000, 1), "shot": f"{tag}-home-then-search.bmp"})
        print(rows[-1])

        t = click(pid, 250, 900)
        time.sleep(0.4)
        img = shot(pid)
        (OUT / f"{tag}-search-again.bmp").write_bytes(img)
        rows.append({"phone": tag, "kind": "search-again-no-home", "api_ms": round(t * 1000, 1)})
        print(rows[-1])

        t = click(pid, 80, 140)
        rows.append({"phone": tag, "kind": "move-to-facetime-no-home", "api_ms": round(t * 1000, 1)})
        print(rows[-1])
        send(pid, "/key/sendkey", fn_key="Home")
        time.sleep(0.5)
        other_shot = shot(other)
        (OUT / f"{tag}-other-after.bmp").write_bytes(other_shot)

    after = recs()
    out = {"before": before, "after": after, "trials": rows}
    (OUT / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

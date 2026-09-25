"""Gate 4 targeting baseline. C24C then C241. Single-id API. No retries."""
from __future__ import annotations
import json, time, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:9913/api"
OUT = Path(__file__).resolve().parent
PHONES = [("C24C", "86:1D:4A:04:2F:F6"), ("C241", "FE:A9:BC:D7:A0:44")]
LOCS = [(80, 140), (400, 200), (120, 500), (360, 760)]


def api(method, url, body=None, timeout=20):
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


def send(pid, fun, **data):
    elapsed, raw = api("POST", BASE + "/", {"fun": fun, "data": {"id": pid, **data}})
    j = json.loads(raw)
    if j.get("status") != 200 or j["data"].get("code") != 0:
        raise RuntimeError(raw.decode(errors="replace")[:500])
    return elapsed


def shot(pid):
    elapsed, raw = api("GET", f"{BASE}/pic/screenshot?id={pid}&binary=true", timeout=8)
    if raw[:2] != b"BM":
        raise RuntimeError("not bmp: " + raw[:80].decode(errors="replace"))
    return elapsed, raw


def save(name, raw):
    (OUT / name).write_bytes(raw)
    return name


def recs():
    return {
        r["deviceid"]: {
            "name": r["name"], "live": r["live"], "frames": r["frames"],
            "restarts": r["receiver_restarts"], "state": r["receiver_state"],
            "pid": r["receiver_pid"],
        }
        for r in status()["receivers"]
    }


def main():
    rows = []
    start = recs()
    if not all(start[pid]["live"] for _, pid in PHONES):
        raise SystemExit("both phones must be live")
    for tag, pid in PHONES:
        send(pid, "/key/sendkey", fn_key="Home")
        time.sleep(0.8)
    for tag, pid in PHONES:
        ms, raw = shot(pid)
        save(f"pre-{tag.lower()}-home.bmp", raw)
        rows.append({"phone": tag, "kind": "pre-home", "shot_ms": round(ms * 1000, 1)})
        print(rows[-1], flush=True)

    for tag, pid in PHONES:
        other = next(p for t, p in PHONES if p != pid)
        otag = "C241" if tag == "C24C" else "C24C"
        if tag == "C241":
            send(other, "/key/sendkey", fn_key="Home")
            time.sleep(0.7)
            _, raw = shot(other)
            save("pre-c241-series-c24c-home.bmp", raw)
        for n in range(1, 6):
            home_s = send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.7)
            t0 = time.perf_counter()
            click_s = send(pid, "/mouse/click", x=250, y=900, button=1)
            time.sleep(0.6)
            t_shot, raw = shot(pid)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            target = save(f"{tag.lower()}-cycle{n}-search.bmp", raw)
            iso_s, oraw = shot(other)
            other_name = save(f"{otag.lower()}-iso-during-{tag.lower()}-cycle{n}.bmp", oraw)
            row = {
                "phone": tag, "kind": "cycle", "n": n,
                "target": [250, 900],
                "expected": "Spotlight within 5s",
                "home_ms": round(home_s * 1000, 1),
                "click_ms": round(click_s * 1000, 1),
                "target_shot_ms": round(t_shot * 1000, 1),
                "isolation_shot_ms": round(iso_s * 1000, 1),
                "effect_ms": round(elapsed_ms, 1),
                "within_5s": elapsed_ms <= 5000,
                "target_bmp": target, "other_bmp": other_name,
            }
            rows.append(row)
            print(row, flush=True)
            send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.4)

        for i, (x, y) in enumerate(LOCS):
            move_s = send(pid, "/mouse/move", x=x, y=y)
            time.sleep(0.35)
            _, mraw = shot(pid)
            save(f"{tag.lower()}-loc{i}-after-move.bmp", mraw)
            home_s = send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.7)
            t0 = time.perf_counter()
            click_s = send(pid, "/mouse/click", x=250, y=900, button=1)
            time.sleep(0.6)
            t_shot, raw = shot(pid)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            target = save(f"{tag.lower()}-loc{i}-search.bmp", raw)
            iso_s, oraw = shot(other)
            other_name = save(f"{otag.lower()}-iso-during-{tag.lower()}-loc{i}.bmp", oraw)
            row = {
                "phone": tag, "kind": "from-location", "n": i, "from": [x, y],
                "target": [250, 900],
                "expected": "Spotlight within 5s",
                "move_ms": round(move_s * 1000, 1),
                "home_ms": round(home_s * 1000, 1),
                "click_ms": round(click_s * 1000, 1),
                "target_shot_ms": round(t_shot * 1000, 1),
                "isolation_shot_ms": round(iso_s * 1000, 1),
                "effect_ms": round(elapsed_ms, 1),
                "within_5s": elapsed_ms <= 5000,
                "target_bmp": target, "other_bmp": other_name,
                "move_bmp": f"{tag.lower()}-loc{i}-after-move.bmp",
            }
            rows.append(row)
            print(row, flush=True)
            send(pid, "/key/sendkey", fn_key="Home")
            time.sleep(0.4)

        send(pid, "/key/sendkey", fn_key="Home")
        time.sleep(0.6)
        _, before = shot(pid)
        save(f"{tag.lower()}-pre-swipe.bmp", before)
        t0 = time.perf_counter()
        left_s = send(pid, "/mouse/swipe", direction="left", len=0.75, duration=400)
        time.sleep(0.7)
        _, lraw = shot(pid)
        left_ms = (time.perf_counter() - t0) * 1000
        save(f"{tag.lower()}-swipe-left.bmp", lraw)
        iso_s, oraw = shot(other)
        save(f"{otag.lower()}-iso-during-{tag.lower()}-swipe-left.bmp", oraw)
        t1 = time.perf_counter()
        right_s = send(pid, "/mouse/swipe", direction="right", len=0.75, duration=400)
        time.sleep(0.5)
        home_s = send(pid, "/key/sendkey", fn_key="Home")
        time.sleep(0.6)
        _, rraw = shot(pid)
        right_ms = (time.perf_counter() - t1) * 1000
        save(f"{tag.lower()}-swipe-right-home.bmp", rraw)
        iso2, oraw2 = shot(other)
        save(f"{otag.lower()}-iso-during-{tag.lower()}-swipe-right.bmp", oraw2)
        send(pid, "/mouse/up", button=1)
        row = {
            "phone": tag, "kind": "swipe",
            "expected_left": "Home page 2 within 5s",
            "expected_right_home": "Home page 1 within 5s",
            "left_ms": round(left_s * 1000, 1),
            "right_ms": round(right_s * 1000, 1),
            "home_ms": round(home_s * 1000, 1),
            "left_effect_ms": round(left_ms, 1),
            "right_effect_ms": round(right_ms, 1),
            "left_within_5s": left_ms <= 5000,
            "right_within_5s": right_ms <= 5000,
            "left_bmp": f"{tag.lower()}-swipe-left.bmp",
            "right_bmp": f"{tag.lower()}-swipe-right-home.bmp",
            "other_left_bmp": f"{otag.lower()}-iso-during-{tag.lower()}-swipe-left.bmp",
            "other_right_bmp": f"{otag.lower()}-iso-during-{tag.lower()}-swipe-right.bmp",
            "isolation_left_shot_ms": round(iso_s * 1000, 1),
            "isolation_right_shot_ms": round(iso2 * 1000, 1),
        }
        rows.append(row)
        print(row, flush=True)

    end = recs()
    out = {"start": start, "end": end, "rows": rows}
    (OUT / "timings.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote timings", flush=True)


if __name__ == "__main__":
    main()

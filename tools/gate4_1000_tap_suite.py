"""Gate 4 1,000-tap suite. One scored Search click per trial. No retries.

C24C and C241, 500 each, four setup categories. The scored tap is always
Search at (250, 900). A miss stays a miss.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PHONES = (("C24C", "86:1D:4A:04:2F:F6"), ("C241", "FE:A9:BC:D7:A0:44"))
LOCS = ((80, 140), (400, 200), (120, 500), (360, 760))
CATS = ("home_search", "off_location", "app_switch", "swipe")
TARGET = (250, 900)
EXPECTED = "Spotlight: wallpaper dims and search field focused within 5s"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "gate4-1000-tap"
# ponytail: 500x1080 24-bit BMP, stride 1500. Recalibrate if the mirror size changes.
W, H, STRIDE = 500, 1080, 1500
ISO_MAX = 8.0  # home noise <2; a real page change is 45+


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def plan(n: int) -> list[dict]:
    if n < 2 or n % 2:
        raise SystemExit("total-taps must be even so both phones get the same count")
    rows = []
    for i in range(n // 2):
        cat = CATS[i % 4]
        loc = LOCS[(i // 4) % 4]
        for tag, pid in PHONES:
            rows.append({
                "n": len(rows),
                "phone": tag,
                "id": pid,
                "category": cat,
                "from": [loc[0], loc[1]] if cat == "off_location" else None,
                "target": [TARGET[0], TARGET[1]],
                "expected": EXPECTED,
            })
    return rows


def api(base: str, method: str, url: str, body: dict | None = None, timeout: float = 25):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return (time.perf_counter() - t0) * 1000, raw


def post(base: str, fun: str, payload: dict, timeout: float = 25) -> dict:
    _, raw = api(base, "POST", base + "/", {"fun": fun, "data": payload}, timeout)
    body = json.loads(raw)
    return body.get("data") or body


def kernel(base: str) -> dict:
    _, raw = api(base, "GET", base + "/kernel/status", timeout=5)
    return json.loads(raw)["data"]


def phones_status(base: str) -> dict[str, dict]:
    data = post(base, "/input/status", {})
    return {p["id"]: p for p in data.get("phones") or []}


def shot(base: str, pid: str) -> bytes:
    _, raw = api(base, "GET", f"{base}/pic/screenshot?id={pid}&binary=true", timeout=8)
    if not raw.startswith(b"BM") or len(raw) < 54 + H * STRIDE:
        raise RuntimeError("not a 500x1080 bmp")
    return raw


def band_mean(raw: bytes, y0: int, y1: int) -> float:
    pix = raw[54:]
    total = count = 0
    for y in range(y0, y1, 4):
        row = (H - 1 - y) * STRIDE
        for x in range(0, W, 8):
            i = row + x * 3
            total += pix[i] + pix[i + 1] + pix[i + 2]
            count += 3
    return total / count if count else 0.0


def mad(a: bytes, b: bytes) -> float:
    pa, pb = a[54:], b[54:]
    n = min(len(pa), len(pb))
    total = count = 0
    for i in range(0, n, 24):
        total += abs(pa[i] - pb[i])
        count += 1
    return round(total / count, 2) if count else 0.0


def classify(before: bytes, after: bytes) -> dict:
    """Spotlight dims the wallpaper and lights the bottom search field."""
    d = mad(before, after)
    mid_drop = band_mean(before, 400, 700) - band_mean(after, 400, 700)
    field = band_mean(after, 970, 1030) - band_mean(after, 400, 700)
    hit = d >= 20 and mid_drop >= 30 and field >= 25
    return {
        "mad": d,
        "mid_drop": round(mid_drop, 1),
        "field_delta": round(field, 1),
        "hit": hit,
        "wrong_target": d >= 20 and not hit,
    }


def pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    i = min(len(s) - 1, max(0, round((p / 100) * (len(s) - 1))))
    return round(s[i], 1)


def write_status(doc: dict) -> None:
    path = OUT / "status.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def done_ns() -> set[int]:
    path = OUT / "results.jsonl"
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.add(json.loads(line)["n"])
    return out


def load_rows() -> list[dict]:
    path = OUT / "results.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def other_of(pid: str) -> tuple[str, str]:
    return next((t, p) for t, p in PHONES if p != pid)


def take_lease(base: str, ids: list[str]) -> dict[str, str]:
    st = phones_status(base)
    blocked = [i for i in ids if st.get(i, {}).get("owned") or st.get(i, {}).get("stopped")]
    if blocked:
        active = [i for i in blocked if st.get(i, {}).get("active")]
        if active:
            raise SystemExit("input active, not taking lease: " + ",".join(active))
        post(base, "/input/stop", {"id": ",".join(blocked)})
        time.sleep(0.4)
        st = phones_status(base)
        gens = {i: st[i].get("generation", 0) for i in blocked if i in st}
        resumed = post(base, "/input/resume", {"id": ",".join(blocked), "expected_generations": gens})
        if resumed.get("code") not in (0, None):
            raise SystemExit("resume failed: " + str(resumed))
    acq = post(base, "/input/acquire", {"id": ",".join(ids), "lease_ms": 120000})
    tokens = {row["id"]: row["token"] for row in acq.get("leases") or []}
    if acq.get("code") != 0 or set(tokens) != set(ids):
        raise SystemExit("acquire failed: " + str(acq.get("message") or acq))
    return tokens


def renew(base: str, ids: list[str], tokens: dict[str, str]) -> None:
    st = phones_status(base)
    if any(st.get(i, {}).get("lease_remaining_ms", 0) < 25000 for i in ids):
        got = post(base, "/input/renew", {"id": ",".join(ids), "tokens": tokens})
        if got.get("code") != 0:
            raise RuntimeError("renew failed: " + str(got))


def send_timed(base: str, pid: str, token: str, fun: str, **data) -> dict:
    t0 = time.perf_counter()
    got = post(base, fun, {"id": pid, "token": token, **data}, timeout=25)
    got["rtt_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    if got.get("code") != 0:
        raise RuntimeError(f"{fun} {got.get('code')} {got.get('message')}")
    return got


def stuck(base: str, ids: list[str]) -> dict:
    st = phones_status(base)
    bad = []
    for i in ids:
        row = st.get(i) or {}
        if row.get("release_failed") or row.get("releasing") or row.get("active"):
            bad.append({"id": i, **{k: row.get(k) for k in ("active", "releasing", "release_failed", "message")}})
    return {"stuck": bool(bad), "detail": bad}


def setup(base: str, spec: dict, token: str) -> dict:
    pid = spec["id"]
    cat = spec["category"]
    extra: dict = {}
    if cat == "off_location":
        x, y = spec["from"]
        extra["move"] = send_timed(base, pid, token, "/mouse/move", x=x, y=y)
        time.sleep(0.25)
    elif cat == "app_switch":
        extra["app_switch"] = send_timed(base, pid, token, "/key/sendkey", fn_key="AppSwitch")
        time.sleep(0.7)
    elif cat == "swipe":
        extra["swipe_left"] = send_timed(base, pid, token, "/mouse/swipe", direction="left", len=0.75, duration=400)
        time.sleep(0.45)
        extra["swipe_right"] = send_timed(base, pid, token, "/mouse/swipe", direction="right", len=0.75, duration=400)
        time.sleep(0.35)
    extra["home"] = send_timed(base, pid, token, "/key/sendkey", fn_key="Home")
    time.sleep(0.55)
    return extra


def watch_click(base: str, pid: str, token: str, before: bytes) -> dict:
    box: dict = {}

    def run() -> None:
        t0 = time.perf_counter()
        try:
            box["click"] = post(base, "/mouse/click", {
                "id": pid, "token": token, "x": TARGET[0], "y": TARGET[1], "button": 1,
            }, timeout=25)
        except Exception as ex:
            box["error"] = str(ex)
        box["rtt_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    t0 = time.perf_counter()
    threading.Thread(target=run, daemon=True).start()
    last = before
    seen = None
    polls = 0
    while time.perf_counter() - t0 < 5.0:
        frame = shot(base, pid)
        polls += 1
        last = frame
        verdict = classify(before, frame)
        if verdict["hit"]:
            seen = (round((time.perf_counter() - t0) * 1000, 1), verdict, frame)
            break
        time.sleep(0.2)
    deadline = time.perf_counter() + 20
    while "rtt_ms" not in box and time.perf_counter() < deadline:
        time.sleep(0.05)
    effect_ms = seen[0] if seen else None
    verdict = seen[1] if seen else classify(before, last)
    bounced = False
    if verdict["hit"]:
        time.sleep(0.35)
        later = shot(base, pid)
        bounced = mad(before, later) < 12
        last = later
    return {
        "dispatch_ms": box.get("rtt_ms"),
        "click_code": (box.get("click") or {}).get("code"),
        "click_error": box.get("error"),
        "effect_ms": effect_ms,
        "within_5s": bool(verdict["hit"] and effect_ms is not None and effect_ms <= 5000),
        "verdict": verdict,
        "polls": polls,
        "frame": last,
        "double_click": bounced,
        "clicks_sent": 1,
    }


HOME_REF: dict[str, bytes] = {}


def not_in_spotlight(frame: bytes, home_ref: bytes | None = None) -> bool:
    field_delta = band_mean(frame, 970, 1030) - band_mean(frame, 400, 700)
    if home_ref is None:
        return field_delta < 25
    mid_drop = band_mean(home_ref, 400, 700) - band_mean(frame, 400, 700)
    return field_delta < 25 or mid_drop < 20


def settled(base: str, pid: str, budget: float = 2.5, home_ref: bytes | None = None) -> bytes:
    # Wait until other is out of Spotlight (field_delta < 25 or mid_drop < 20) and motion settles.
    ref = home_ref or HOME_REF.get(pid)
    prev = shot(base, pid)
    deadline = time.perf_counter() + budget
    while time.perf_counter() < deadline:
        time.sleep(0.25)
        frame = shot(base, pid)
        if not_in_spotlight(frame, ref) and mad(prev, frame) < 3:
            HOME_REF[pid] = frame
            return frame
        prev = frame
    return prev




def trial(base: str, spec: dict, token: str, ids: list[str]) -> dict:
    otag, oid = other_of(spec["id"])
    row = {
        "n": spec["n"], "at": utc(), "phone": spec["phone"], "id": spec["id"],
        "other": otag, "category": spec["category"], "from": spec["from"],
        "target": spec["target"], "expected": spec["expected"],
        "clicks_sent": 0, "pass": False,
    }
    other_before = settled(base, oid, home_ref=HOME_REF.get(oid))
    prep = setup(base, spec, token)
    row["setup_ms"] = {k: v.get("rtt_ms") for k, v in prep.items()}
    before = shot(base, spec["id"])
    HOME_REF[spec["id"]] = before
    watched = watch_click(base, spec["id"], token, before)
    row["clicks_sent"] = watched["clicks_sent"]
    other_after = shot(base, oid)
    iso = mad(other_before, other_after)
    hold = stuck(base, ids)
    hit = watched["within_5s"] and not watched["verdict"]["wrong_target"]
    row.update({
        "dispatch_ms": watched["dispatch_ms"],
        "click_code": watched["click_code"],
        "click_error": watched["click_error"],
        "effect_ms": watched["effect_ms"] if hit else 5000.0,
        "effect_ms_raw": watched["effect_ms"],
        "within_5s": hit,
        "mad": watched["verdict"]["mad"],
        "mid_drop": watched["verdict"]["mid_drop"],
        "field_delta": watched["verdict"]["field_delta"],
        "wrong_target": watched["verdict"]["wrong_target"],
        "isolation_mad": iso,
        "isolated": iso < ISO_MAX,
        "stuck": hold["stuck"],
        "stuck_detail": hold["detail"],
        "double_click": watched["double_click"],
        "polls": watched["polls"],
    })
    row["pass"] = bool(hit and row["isolated"] and not row["stuck"] and not row["double_click"] and row["click_code"] == 0)
    row["target_hit"] = bool(hit and row["click_code"] == 0 and not row["double_click"])
    if not row["pass"]:
        shots = OUT / "shots"
        shots.mkdir(exist_ok=True)
        (shots / f"{spec['n']:04d}-{spec['phone']}-after.bmp").write_bytes(watched["frame"])
        if not row["isolated"]:
            (shots / f"{spec['n']:04d}-{otag}-other.bmp").write_bytes(other_after)
    try:
        send_timed(base, spec["id"], token, "/key/sendkey", fn_key="Home")
        settled(base, spec["id"], home_ref=before)
    except Exception as ex:
        row["recover_error"] = str(ex)
    return row


def summarize(rows: list[dict], args, block: int, state: str) -> dict:
    by_phone: dict[str, dict] = {}
    by_cat: dict[str, dict] = {}
    for row in rows:
        bucket = by_phone.setdefault(row["phone"], {"n": 0, "hit": 0, "pass": 0})
        bucket["n"] += 1
        bucket["hit"] += int(bool(row.get("target_hit")))
        bucket["pass"] += int(bool(row.get("pass")))
        cat = by_cat.setdefault(row["category"], {"n": 0, "hit": 0})
        cat["n"] += 1
        cat["hit"] += int(bool(row.get("target_hit")))
    n = len(rows)
    hits = sum(1 for r in rows if r.get("target_hit"))
    iso_ok = sum(1 for r in rows if r.get("isolated"))
    lat = [r["effect_ms"] for r in rows if r.get("effect_ms") is not None]
    blocks = args.total_taps // args.block_size
    return {
        "model": "openai-codex/gpt-6-sol",
        "updated": utc(),
        "state": state,
        "url": args.url,
        "total_taps": args.total_taps,
        "block_size": args.block_size,
        "current_block": block,
        "completed": n,
        "target_hits": hits,
        "passed": sum(1 for r in rows if r.get("pass")),
        "failed": n - hits,
        "accuracy_rate": round(hits / n, 4) if n else None,
        "latency_p50_ms": pct(lat, 50),
        "latency_p95_ms": pct(lat, 95),
        "isolation_score": round(iso_ok / n, 4) if n else None,
        "stuck_events": sum(1 for r in rows if r.get("stuck")),
        "double_clicks": sum(1 for r in rows if r.get("double_click")),
        "unintended_phone_actions": sum(1 for r in rows if r.get("isolated") is False),
        "per_phone": by_phone,
        "per_category": by_cat,
        "remaining_blocks": list(range(block + 1, blocks + 1)) if state != "blocked" else list(range(block, blocks + 1)),
        "remaining_taps": max(0, args.total_taps - n),
        "note": "Timeouts count as 5000 ms. A failed tap is never retried. Mirror-to-all is off: every command uses one device id.",
    }


def run_block(args, block: int) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows_plan = plan(args.total_taps)
    start = (block - 1) * args.block_size
    chunk = rows_plan[start:start + args.block_size]
    if not chunk:
        raise SystemExit(f"block {block} is past {args.total_taps} taps")
    ks = kernel(args.url)
    live = {r["deviceid"]: r for r in ks.get("receivers") or []}
    for _, pid in PHONES:
        if not live.get(pid, {}).get("live"):
            raise SystemExit(pid + " is not live; kernel left running")
    ids = [pid for _, pid in PHONES]
    tokens = take_lease(args.url, ids)
    seen = done_ns()
    log = OUT / "results.jsonl"
    try:
        for spec in chunk:
            if spec["n"] in seen:
                continue
            renew(args.url, ids, tokens)
            try:
                row = trial(args.url, spec, tokens[spec["id"]], ids)
            except Exception as ex:
                row = {**spec, "at": utc(), "pass": False, "target_hit": False, "error": str(ex), "effect_ms": 5000.0}
            with log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
            all_rows = load_rows()
            blocked = row.get("stuck") or row.get("double_click")
            write_status(summarize(all_rows, args, block, "blocked" if blocked else "running"))
            print(
                f"n={row.get('n')} {row.get('phone')} {row.get('category')} "
                f"hit={row.get('target_hit')} pass={row.get('pass')} "
                f"effect={row.get('effect_ms_raw')} iso={row.get('isolation_mad')}",
                flush=True,
            )
            if blocked:
                print("blocking event; stopping block", flush=True)
                return 2
        write_status(summarize(load_rows(), args, block, "block-complete"))
    finally:
        try:
            post(args.url, "/input/release", {"id": ",".join(ids), "tokens": tokens})
        except Exception as ex:
            print("release failed", ex, flush=True)
    return 0


def self_check() -> None:
    rows = plan(1000)
    assert len(rows) == 1000
    assert sum(r["phone"] == "C24C" for r in rows) == 500
    assert sum(r["phone"] == "C241" for r in rows) == 500
    assert all(sum(r["category"] == c and r["phone"] == p for r in rows) == 125 for c in CATS for p in ("C24C", "C241"))
    home = (OUT / "probe" / "c24c-home.bmp").read_bytes()
    after = (OUT / "probe" / "c24c-after.bmp").read_bytes()
    same = classify(home, home)
    spot = classify(home, after)
    assert not same["hit"] and same["mad"] == 0
    assert spot["hit"] and not spot["wrong_target"], spot
    assert not_in_spotlight(home, home) and not not_in_spotlight(after, home)
    assert pct([10, 20, 30], 50) == 20
    print("self-check ok", spot)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--total-taps", type=int, default=1000)
    p.add_argument("--block-size", type=int, default=100)
    p.add_argument("--url", default="http://127.0.0.1:9913/api")
    p.add_argument("--block", type=int, default=1)
    p.add_argument("--self-check", action="store_true")
    args = p.parse_args()
    if args.self_check:
        self_check()
        return 0
    if args.block_size < 1 or args.total_taps % args.block_size:
        raise SystemExit("block-size must divide total-taps")
    return run_block(args, args.block)


if __name__ == "__main__":
    raise SystemExit(main())

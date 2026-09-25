"""Gate 7 live video frame accounting.

Polls each live receiver's /pic/screenshot?binary=true, hashes the BMP, and
reads kernel status `frames` as the sequence counter. Screenshot responses
carry no sequence id. Read-only: does not send input or restart anything.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import statistics
import struct
import threading
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "gate7-video-accounting" / "report.json"
CEILING_FPS = 30.0
FREEZE_MS = 2000.0
BUCKETS = (16, 33, 50, 100, 250, 500, 1000, 2000)


def split_url(url: str) -> tuple[str, int, str]:
    parts = urllib.parse.urlsplit(url if "://" in url else "http://" + url)
    return parts.hostname or "127.0.0.1", parts.port or 80, (parts.path or "/api").rstrip("/")


def get(conn: http.client.HTTPConnection, path: str) -> tuple[int, bytes]:
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    return resp.status, body


def status_snapshot(host: str, port: int, base: str) -> dict:
    conn = http.client.HTTPConnection(host, port, timeout=5)
    try:
        code, body = get(conn, base + "/kernel/status")
    finally:
        conn.close()
    if code != 200:
        raise RuntimeError(f"kernel status HTTP {code}")
    data = json.loads(body)["data"]
    if "receivers" not in data:
        raise RuntimeError("kernel status has no receivers")
    return data


def gap_stats(gaps: list[float]) -> dict:
    if not gaps:
        return {"min": None, "median": None, "max": None, "over_2s": 0}
    return {
        "min": round(min(gaps), 3),
        "median": round(statistics.median(gaps), 3),
        "max": round(max(gaps), 3),
        "over_2s": sum(g > FREEZE_MS for g in gaps),
    }


def histogram(gaps: list[float]) -> dict:
    labels = [f"<{n}" for n in BUCKETS] + [f">={BUCKETS[-1]}"]
    counts = [0] * len(labels)
    for gap in gaps:
        for i, edge in enumerate(BUCKETS):
            if gap < edge:
                counts[i] += 1
                break
        else:
            counts[-1] += 1
    return dict(zip(labels, counts))


def flat_spans(points: list[tuple[float, int]]) -> list[dict]:
    spans = []
    if len(points) < 2:
        return spans
    start_t, start_n = points[0]
    prev_t = start_t
    for t, n in points[1:]:
        if n != start_n:
            dt = (prev_t - start_t) * 1000
            if dt > FREEZE_MS:
                spans.append({"t0": round(start_t, 3), "t1": round(prev_t, 3), "ms": round(dt, 1)})
            start_t, start_n = t, n
        prev_t = t
    dt = (prev_t - start_t) * 1000
    if dt > FREEZE_MS:
        spans.append({"t0": round(start_t, 3), "t1": round(prev_t, 3), "ms": round(dt, 1)})
    return spans


def summarize(samples: int, gaps: list[float], lead_ms: float, trail_ms: float,
              unique: int, duration: float, sequence_delta: int | None,
              sequence_window: float) -> dict:
    raw_fps = samples / duration if duration else 0.0
    unique_fps = unique / duration if duration else 0.0
    stats = gap_stats(gaps)
    seq_fps = None
    if sequence_delta is not None and sequence_window > 0:
        seq_fps = sequence_delta / sequence_window
    expected = None
    if sequence_delta is not None:
        expected = min(sequence_delta, CEILING_FPS * duration)
    freeze_ok = samples > 0 and stats["over_2s"] == 0 and lead_ms <= FREEZE_MS and trail_ms <= FREEZE_MS
    return {
        "frames_received": samples,
        "raw_received_fps": round(raw_fps, 3),
        "unique_frames": unique,
        "unique_fps": round(unique_fps, 3),
        "uniqueness_pct": round(100.0 * unique / samples, 3) if samples else 0.0,
        "identical_frames": samples - unique,
        "gap_ms": {"min": stats["min"], "median": stats["median"], "max": stats["max"]},
        "gap_histogram": histogram(gaps),
        "gaps_over_2s": stats["over_2s"],
        "lead_ms": round(lead_ms, 3),
        "trail_ms": round(trail_ms, 3),
        "freeze_ok": freeze_ok,
        "ceiling_fps": CEILING_FPS,
        "delivery_ratio": round(min(unique_fps, CEILING_FPS) / CEILING_FPS, 4),
        "sequence_frames": sequence_delta,
        "sequence_fps": round(seq_fps, 3) if seq_fps is not None else None,
        "sequence_delivery_ratio": round(min(seq_fps, CEILING_FPS) / CEILING_FPS, 4) if seq_fps is not None else None,
        "expected_frames": round(expected, 3) if expected is not None else None,
        "unique_vs_expected": round(unique / expected, 4) if expected else None,
    }


def self_check() -> None:
    stats = gap_stats([100.0, 100.0, 2300.0])
    assert stats == {"min": 100.0, "median": 100.0, "max": 2300.0, "over_2s": 1}
    assert flat_spans([(0.0, 1), (1.0, 1), (3.5, 1), (3.6, 2)]) == [{"t0": 0.0, "t1": 3.5, "ms": 3500.0}]
    row = summarize(4, [100.0, 100.0, 50.0], 20.0, 30.0, 2, 1.0, 30, 1.0)
    assert row["frames_received"] == 4
    assert row["unique_frames"] == 2 and row["identical_frames"] == 2
    assert row["uniqueness_pct"] == 50.0
    assert row["raw_received_fps"] == 4.0 and row["unique_fps"] == 2.0
    assert row["delivery_ratio"] == round(2 / 30, 4)
    assert row["freeze_ok"] is True and row["sequence_frames"] == 30
    assert summarize(1, [], 2500.0, 10.0, 1, 3.0, 0, 3.0)["freeze_ok"] is False
    assert summarize(0, [], 30000.0, 0.0, 0, 30.0, 0, 30.0)["freeze_ok"] is False


def poll_phone(host: str, port: int, path: str, t0: float, deadline: float, slot: dict) -> None:
    conn = http.client.HTTPConnection(host, port, timeout=3)
    gaps: list[float] = []
    over: list[dict] = []
    changes: list[dict] = []
    seen: set[str] = set()
    samples = errors = 0
    width = height = None
    prev_t = None
    first_t = last_t = None
    try:
        while time.perf_counter() < deadline:
            try:
                code, body = get(conn, path)
            except Exception:
                errors += 1
                try:
                    conn.close()
                except Exception:
                    pass
                conn = http.client.HTTPConnection(host, port, timeout=3)
                time.sleep(0.02)
                continue
            now = time.perf_counter()
            if code != 200 or not body.startswith(b"BM") or len(body) < 54:
                errors += 1
                continue
            digest = hashlib.sha256(body).hexdigest()
            if width is None:
                width, height = struct.unpack_from("<ii", body, 18)
                height = abs(height)
            if prev_t is None:
                first_t = now
            else:
                gap = (now - prev_t) * 1000
                gaps.append(gap)
                if gap > FREEZE_MS:
                    over.append({"t": round(now - t0, 3), "ms": round(gap, 1)})
            samples += 1
            if digest not in seen:
                seen.add(digest)
                changes.append({"t": round(now - t0, 3), "hash": digest})
            prev_t = last_t = now
    finally:
        conn.close()
    end = min(time.perf_counter(), deadline)
    lead = ((first_t - t0) * 1000) if first_t is not None else (deadline - t0) * 1000
    trail = max(0.0, (end - last_t) * 1000) if last_t is not None else 0.0
    if lead > FREEZE_MS:
        over.insert(0, {"t": round((first_t or deadline) - t0, 3), "ms": round(lead, 1), "lead": True})
    if trail > FREEZE_MS:
        over.append({"t": round(end - t0, 3), "ms": round(trail, 1), "trail": True})
    slot.update(samples=samples, errors=errors, gaps=gaps, over=over, changes=changes,
                unique=len(seen), lead_ms=lead, trail_ms=trail, width=width, height=height)


def poll_status(host: str, port: int, base: str, ids: list[str], t0: float, deadline: float,
                series: list[dict], stop: threading.Event) -> None:
    conn = http.client.HTTPConnection(host, port, timeout=3)
    try:
        while not stop.is_set() and time.perf_counter() < deadline:
            try:
                code, body = get(conn, base + "/kernel/status")
                if code == 200:
                    data = json.loads(body)["data"]
                    frames = {r["deviceid"]: r.get("frames") for r in data.get("receivers", []) if r["deviceid"] in ids}
                    series.append({"t": round(time.perf_counter() - t0, 3), "frames": frames})
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = http.client.HTTPConnection(host, port, timeout=3)
            stop.wait(0.1)
    finally:
        conn.close()


def main() -> int:
    self_check()
    parser = argparse.ArgumentParser(description="Gate 7 live video frame accounting")
    parser.add_argument("--duration-seconds", type=float, default=30)
    parser.add_argument("--url", default="http://127.0.0.1:9913/api")
    args = parser.parse_args()
    if args.duration_seconds <= 0:
        raise SystemExit("duration must be > 0")
    host, port, base = split_url(args.url)
    before = status_snapshot(host, port, base)
    live = [r for r in before["receivers"] if r.get("live")]
    if not live:
        raise SystemExit("no live receivers")
    ids = [r["deviceid"] for r in live]
    t0 = time.perf_counter()
    deadline = t0 + args.duration_seconds
    slots = {i: {} for i in ids}
    series: list[dict] = []
    stop = threading.Event()
    threads = [threading.Thread(target=poll_status, args=(host, port, base, ids, t0, deadline, series, stop), daemon=True)]
    for rec in live:
        path = f"{base}/pic/screenshot?id={urllib.parse.quote(rec['deviceid'], safe='')}&binary=true"
        threads.append(threading.Thread(target=poll_phone, args=(host, port, path, t0, deadline, slots[rec["deviceid"]]), daemon=True))
    for thread in threads:
        thread.start()
    for thread in threads[1:]:
        thread.join()
    stop.set()
    threads[0].join(timeout=2)
    t1 = time.perf_counter()
    after = status_snapshot(host, port, base)
    after_by_id = {r["deviceid"]: r for r in after.get("receivers", [])}
    window = deadline - t0
    phones = []
    for rec in live:
        slot = slots[rec["deviceid"]]
        end = after_by_id.get(rec["deviceid"], {})
        start_n = rec.get("frames")
        end_n = end.get("frames")
        delta = None if start_n is None or end_n is None or end_n < start_n else end_n - start_n
        points = [(0.0, start_n)] if start_n is not None else []
        for row in series:
            n = row["frames"].get(rec["deviceid"])
            if n is not None:
                points.append((row["t"], n))
        if end_n is not None:
            points.append((round(t1 - t0, 3), end_n))
        row = summarize(slot.get("samples", 0), slot.get("gaps", []), slot.get("lead_ms", window * 1000),
                        slot.get("trail_ms", 0.0), slot.get("unique", 0), window, delta, t1 - t0)
        row.update({
            "deviceid": rec["deviceid"],
            "name": rec.get("name"),
            "alias": str(rec.get("name", "")).removeprefix("iMouse2-") or rec["deviceid"],
            "width": slot.get("width"),
            "height": slot.get("height"),
            "errors": slot.get("errors", 0),
            "receiver_restarts": end.get("receiver_restarts", rec.get("receiver_restarts")),
            "sequence_stalls": flat_spans(points),
            "gaps_over_2s_events": slot.get("over", []),
            "changes": slot.get("changes", []),
        })
        row["freeze_ok"] = row["freeze_ok"] and not row["sequence_stalls"]
        phones.append(row)
        print(f"{row['alias']} recv={row['frames_received']} raw_fps={row['raw_received_fps']} "
              f"unique={row['unique_frames']} uniq_fps={row['unique_fps']} uniq%={row['uniqueness_pct']} "
              f"gap={row['gap_ms']['min']}/{row['gap_ms']['median']}/{row['gap_ms']['max']} "
              f"seq_fps={row['sequence_fps']} delivery={row['delivery_ratio']} freeze_ok={row['freeze_ok']}")
    report = {
        "url": args.url,
        "duration_s": round(window, 3),
        "sequence_window_s": round(t1 - t0, 3),
        "ceiling_fps": CEILING_FPS,
        "freeze_limit_ms": FREEZE_MS,
        "phones_live": len(phones),
        "freeze_ok": all(p["freeze_ok"] for p in phones),
        "definitions": {
            "frames_received": "successful screenshot polls; each poll is the kernel's latest BMP",
            "unique_frames": "distinct SHA256 of those BMPs; a repeated image counts once",
            "gap_ms": "inter-arrival of successful polls, t_i - t_{i-1}, milliseconds",
            "delivery_ratio": "min(unique_fps, 30) / 30",
            "sequence_frames": "kernel status frames delta; increments on every pipe write, including identical pixels",
            "unique_vs_expected": "unique hashes / min(sequence_frames, 30 * duration)",
        },
        "limits": "Kernel frame store keeps the latest BMP only, so it cannot accumulate a display backlog. "
                  "This samples the kernel, not the console present path. A still screen correctly yields a low uniqueness ratio.",
        "phones": phones,
        "sequence_samples": series,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {OUT} freeze_ok={report['freeze_ok']}")
    return 0 if report["freeze_ok"] and len(phones) >= 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())

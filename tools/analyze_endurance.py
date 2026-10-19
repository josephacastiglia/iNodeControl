"""Read-only Gate 10 dashboard from telemetry.jsonl. Writes DASHBOARD.md and dashboard.html. Does not touch the soak."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "analysis" / "gate10-endurance-20260916"
PHONES = ["C24C", "C241", "C214", "724E", "Phone 5"]
WINDOW_S = 600
RECENT_S = 1800
FREEZE_S = 2.0
FLAT_MB_H = 5.0  # |slope| under this is settled; upgrade if a leak budget is set
MB = 1024 * 1024


def parse_at(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def phone_label(rec: dict) -> str:
    if rec.get("deviceid") == "*" or str(rec.get("name", "")).endswith("Phone5"):
        return "Phone 5"
    return str(rec.get("name") or rec.get("deviceid") or "?").rsplit("-", 1)[-1]


def target_label(target: str | None) -> str:
    return "Phone 5" if target in ("*", "Phone 5", "Phone5") else str(target or "?")


def slope_mb_h(ts: list[float], vals: list[float]) -> float | None:
    n = len(ts)
    if n < 2 or len(vals) != n:
        return None
    mx = sum(ts) / n
    my = sum(vals) / n
    den = sum((t - mx) ** 2 for t in ts)
    if den == 0:
        return 0.0
    return sum((t - mx) * (v - my) for t, v in zip(ts, vals)) / den / MB * 3600


def median(vals: list[float]) -> float | None:
    return statistics.median(vals) if vals else None


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_rows(path: Path) -> tuple[list[dict], int]:
    rows: list[dict] = []
    bad = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    bad += 1
                    continue
                rows.append(row)
            except json.JSONDecodeError:
                bad += 1
    return rows, bad


def split_sessions(rows: list[dict]) -> list[list[dict]]:
    sessions: list[list[dict]] = []
    cur: list[dict] = []
    prev_el = None
    prev_pid = None
    prev_console = None
    for row in rows:
        if row.get("kind") != "sample":
            if cur:
                cur.append(row)
            continue
        el, pid, console = row.get("elapsed_s"), row.get("kernel_pid"), row.get("console_pid")
        reset = prev_el is not None and el is not None and el + 1 < prev_el
        if cur and (reset or (prev_pid and pid and pid != prev_pid) or (prev_console and console and console != prev_console)):
            sessions.append(cur)
            cur = []
        cur.append(row)
        prev_el, prev_pid, prev_console = el, pid, console
    if cur:
        sessions.append(cur)
    return sessions


def pick_live(sessions: list[list[dict]], status: dict) -> list[dict]:
    expected = status.get("expected") or {}
    want_k = expected.get("kernel_pid") or status.get("kernel_pid")
    want_c = expected.get("console_pid") or status.get("console_pid")
    for session in reversed(sessions):
        sample = next(row for row in session if row.get("kind") == "sample")
        if (not want_k or sample.get("kernel_pid") == want_k) and (not want_c or sample.get("console_pid") == want_c):
            return session
    raise ValueError("no telemetry session matches the fleet recorded in status")


def _blank() -> dict:
    return {"n": 0, "click_ok": 0, "click_rtt": [], "home_ok": 0, "home_n": 0}


def analyze_phones(samples: list[dict]) -> list[dict]:
    series: dict[str, list[tuple[float, dict]]] = {}
    for row in samples:
        t = parse_at(row["at"])
        for rec in row.get("receivers") or []:
            series.setdefault(phone_label(rec), []).append((t, rec))
    labels = PHONES + [name for name in series if name not in PHONES]
    out = []
    for label in labels:
        pts = series.get(label) or []
        if not pts:
            continue
        fps: list[float] = []
        freezes = 0
        freeze_s = 0.0
        resets = 0
        restarts = 0
        unavailable = 0
        unavailable_s = 0.0
        pids: list[int] = []
        frames: list[tuple[float, int, int | None]] = []
        for i, (t, rec) in enumerate(pts):
            fr = rec.get("frames")
            if fr is not None:
                frames.append((t, fr, rec.get("receiver_pid")))
            restarts = max(restarts, int(rec.get("receiver_restarts") or 0))
            if rec.get("receiver_pid"):
                pids.append(int(rec["receiver_pid"]))
            if i == 0:
                continue
            prev_t, prev = pts[i - 1]
            dt = t - prev_t
            if dt <= 0:
                continue
            if rec.get("live") is not True or prev.get("live") is not True:
                unavailable += 1
                unavailable_s += dt
                continue
            if prev.get("receiver_pid") != rec.get("receiver_pid"):
                resets += 1
                continue
            delta = rec.get("frame_delta")
            if delta is None and fr is not None and prev.get("frames") is not None:
                delta = fr - prev["frames"]
            if delta is None or dt <= 0:
                continue
            if delta < 0:
                resets += 1
                continue
            if delta == 0 and dt > FREEZE_S:
                freezes += 1
                freeze_s += dt
                continue
            fps.append(delta / dt)
        gained = sum(max(0, frames[i][1] - frames[i - 1][1]) for i in range(1, len(frames)) if frames[i][2] == frames[i - 1][2])
        span = (frames[-1][0] - frames[0][0]) if len(frames) >= 2 else 0.0
        cur = None
        if frames:
            latest = frames
            for i in range(len(frames) - 1, 0, -1):
                if frames[i - 1][2] != frames[-1][2]:
                    latest = frames[i:]
                    break
            start = latest[0]
            last_t = frames[-1][0]
            for item in latest:
                if item[0] <= last_t - 60:
                    start = item
            if frames[-1][0] > start[0] and frames[-1][1] >= start[1]:
                cur = (frames[-1][1] - start[1]) / (frames[-1][0] - start[0])
        out.append({
            "label": label,
            "received": gained,
            "counter": frames[-1][1] if frames else None,
            "avg": (gained / span) if span else None,
            "cur": cur,
            "min": min(fps) if fps else None,
            "max": max(fps) if fps else None,
            "restarts": max(restarts, sum(a != b for a, b in zip(pids, pids[1:]))),
            "resets": resets,
            "freezes": freezes,
            "freeze_s": freeze_s,
            "unavailable_intervals": unavailable,
            "unavailable_s": unavailable_s,
            "pid": pids[-1] if pids else None,
            "state": pts[-1][1].get("receiver_state"),
            "live": pts[-1][1].get("live"),
        })
    return out


def _proc_vals(points: list[dict], pid: int, key: str, t0: float) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for point in points:
        hit = next((row for row in point["procs"] if row.get("pid") == pid and row.get(key) is not None), None)
        if hit:
            xs.append(point["t"] - t0)
            ys.append(hit[key])
    return xs, ys


def analyze_memory(samples: list[dict]) -> dict:
    points = []
    for row in samples:
        procs = [p for p in (row.get("processes") or []) if p.get("working_set") is not None]
        points.append({
            "t": parse_at(row["at"]),
            "procs": procs,
            "ws": sum(p.get("working_set") or 0 for p in procs),
            "pm": sum(p.get("private_bytes") or 0 for p in procs),
        })
    if not points:
        return {"procs": [], "total": {}}
    t0 = points[0]["t"]
    last = points[-1]["t"]
    win = [p for p in points if p["t"] >= last - WINDOW_S] or [points[-1]]
    recent = [p for p in points if p["t"] >= last - RECENT_S]
    pid_phone = {}
    for rec in samples[-1].get("receivers") or []:
        if rec.get("receiver_pid"):
            pid_phone[int(rec["receiver_pid"])] = phone_label(rec)
    proc_rows = []
    for proc in points[-1]["procs"]:
        pid = int(proc["pid"])
        xs, ws = _proc_vals(points, pid, "working_set", t0)
        px, pm = _proc_vals(points, pid, "private_bytes", t0)
        win_ws, win_pm = [], []
        for point in win:
            hit = next((row for row in point["procs"] if row.get("pid") == pid), None)
            if not hit:
                continue
            if hit.get("working_set") is not None:
                win_ws.append(hit["working_set"])
            if hit.get("private_bytes") is not None:
                win_pm.append(hit["private_bytes"])
        proc_rows.append({
            "role": proc.get("role"),
            "name": proc.get("name"),
            "pid": pid,
            "phone": pid_phone.get(pid, ""),
            "alive": proc.get("alive"),
            "ws": proc.get("working_set"),
            "pm": proc.get("private_bytes"),
            "ws_med": median(win_ws),
            "ws_peak": max(win_ws) if win_ws else None,
            "pm_med": median(win_pm),
            "pm_peak": max(win_pm) if win_pm else None,
            "slope_ws": slope_mb_h(xs, ws),
            "slope_pm": slope_mb_h(px, pm),
        })
    role_order = {"kernel": 0, "console": 1, "receiver": 2}
    phone_order = {name: i for i, name in enumerate(PHONES)}
    proc_rows.sort(key=lambda row: (role_order.get(row["role"], 9), phone_order.get(row["phone"], 9), row["pid"]))
    xs = [p["t"] - t0 for p in points]
    rx = [p["t"] - recent[0]["t"] for p in recent]
    total = {
        "ws": points[-1]["ws"],
        "pm": points[-1]["pm"],
        "ws0": points[0]["ws"],
        "pm0": points[0]["pm"],
        "ws_mid": points[len(points) // 2]["ws"],
        "pm_mid": points[len(points) // 2]["pm"],
        "ws_med": median([p["ws"] for p in win]),
        "ws_peak": max(p["ws"] for p in win),
        "pm_med": median([p["pm"] for p in win]),
        "pm_peak": max(p["pm"] for p in win),
        "slope_ws": slope_mb_h(xs, [p["ws"] for p in points]),
        "slope_pm": slope_mb_h(xs, [p["pm"] for p in points]),
        "slope_ws_30m": slope_mb_h(rx, [p["ws"] for p in recent]) if len(recent) >= 2 else None,
        "slope_pm_30m": slope_mb_h(rx, [p["pm"] for p in recent]) if len(recent) >= 2 else None,
        "n": len(points),
        "win_n": len(win),
        "span_s": last - t0,
    }
    return {"procs": proc_rows, "total": total}


def mentions_stuck(row: dict) -> bool:
    for key, value in row.items():
        if "stuck" in str(key).lower() and bool(value):
            return True
        if isinstance(value, dict) and mentions_stuck(value):
            return True
        if isinstance(value, list) and any(mentions_stuck(item) for item in value if isinstance(item, dict)):
            return True
        if key in ("error", "message") and isinstance(value, str):
            text = re.sub(r"(?i)\b(?:no|not|zero|0)\s+stuck\b|\bstuck\s*[:=]\s*(?:false|0)\b", "", value)
            if re.search(r"(?i)\bstuck\b", text):
                return True
    return False


def analyze_interactions(session: list[dict], samples: list[dict]) -> dict:
    ix = [row for row in session if row.get("kind") == "interaction"]
    per: dict[str, dict] = {name: _blank() for name in PHONES}
    stuck = 0
    for row in ix:
        bucket = per.setdefault(target_label(row.get("target")), _blank())
        bucket["n"] += 1
        if row.get("click_rtt_ms") is not None:
            bucket["click_rtt"].append(row["click_rtt_ms"])
        if row.get("spotlight_open") is True:
            bucket["click_ok"] += 1
        results = row.get("group_home_results") or []
        if results:
            id_to_label = {}
            for sample in reversed(samples):
                for rec in sample.get("receivers") or []:
                    id_to_label.setdefault(rec.get("deviceid"), phone_label(rec))
                if id_to_label:
                    break
            for item in results:
                home = per.setdefault(id_to_label.get(item.get("id"), item.get("id") or "?"), _blank())
                home["home_n"] += 1
                if item.get("code") == 0:
                    home["home_ok"] += 1
        elif row.get("group_home_code") is not None:
            bucket["home_n"] += 1
            if row.get("group_home_code") == 0:
                bucket["home_ok"] += 1
        release = row.get("release")
        release_code = release.get("code") if isinstance(release, dict) else None
        if mentions_stuck(row) or release_code not in (None, 0):
            stuck += 1
    reached = [row for row in ix if row.get("group_home_code") is not None]
    dispatched = [row for row in ix if row.get("click_rtt_ms") is not None]
    return {
        "n": len(ix),
        "failed": sum(row.get("ok") is not True for row in ix),
        "release_unverified": sum((row.get("ok") is True or row.get("acquire_code") == 0 or row.get("click_rtt_ms") is not None)
                                  and (not isinstance(row.get("release"), dict) or row["release"].get("code") is None) for row in ix),
        "per": per,
        "stuck": stuck,
        "click_ok": sum(1 for row in ix if row.get("spotlight_open") is True),
        "click_dispatched": len(dispatched),
        "click_p50": median([row["click_rtt_ms"] for row in dispatched]),
        "home_ok": sum(1 for row in reached if row.get("group_home_code") == 0),
        "home_n": len(reached),
        "errors": Counter(row.get("error") or ("ok" if row.get("ok") is True else "interaction failed or unverified") for row in ix),
        "acquire": Counter(row.get("acquire_code") for row in ix),
    }


def evaluate_health(samples, phones, memory, ix, bad=0):
    """Observed conditions only. Never turn a clean subset into Gate 10 acceptance."""
    failures = []
    incomplete = []
    if bad:
        failures.append(f"{bad} malformed telemetry rows")
    if ix.get("failed", 0):
        failures.append(f"{ix['failed']}/{ix['n']} interactions failed or unverified")
    if ix.get("stuck", 0):
        failures.append(f"{ix['stuck']} stuck-input or release failures")
    for phone in phones:
        if phone.get("restarts", 0):
            failures.append(f"{phone['label']}: {phone['restarts']} receiver restarts")
        if phone.get("freezes", 0):
            failures.append(f"{phone['label']}: {phone['freezes']} sampled live no-frame gaps")
        if phone.get("unavailable_intervals", 0) or phone.get("live") is False:
            failures.append(f"{phone['label']}: video unavailable")
    if any(row.get("alive") is False for row in memory.get("procs", [])) or any(proc.get("alive") is False for row in samples for proc in row.get("processes", [])):
        failures.append("recorded process is not alive")
    if any(row.get("fleet_match") is False for row in samples):
        failures.append("fleet identity changed or mismatched")
    if len(samples) < 2:
        incomplete.append("fewer than two telemetry samples")
    if not phones:
        incomplete.append("no receiver observations")
    if not memory.get("procs"):
        incomplete.append("no process observations")
    if not ix.get("n"):
        incomplete.append("no interaction attempts")
    if ix.get("release_unverified"):
        incomplete.append(f"{ix['release_unverified']} attempted-input releases unverified")
    return {"status": "failed" if failures else ("incomplete" if incomplete else "no_observed_failures"),
            "failures": failures, "incomplete": incomplete, "gate10_acceptance": False,
            "scope": "observed sample conditions; duration, planned workloads and memory budgets require separate acceptance"}


def fmt_mb(n: float | None) -> str:
    return "n/a" if n is None else f"{n / MB:.1f}"


def fmt_fps(n: float | None) -> str:
    return "n/a" if n is None else f"{n:.2f}"


def fmt_slope(n: float | None) -> str:
    return "n/a" if n is None else f"{n:+.1f}"


def fmt_num(n: float | None) -> str:
    return "n/a" if n is None else f"{int(n):,}"


def pct(num: int, den: int) -> str:
    return "n/a" if not den else f"{100 * num / den:.0f}% ({num}/{den})"


def hms(seconds: float | None) -> str:
    total = int(seconds or 0)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def drift_word(slope: float | None) -> str:
    if slope is None:
        return "n/a"
    if abs(slope) < FLAT_MB_H:
        return "FLAT"
    return "RISING" if slope > 0 else "FALLING"


def table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def render(status: dict, live: list[dict], phones: list[dict], memory: dict, ix: dict, parsed: int, bad: int, prior: list[list[dict]]) -> str:
    samples = [row for row in live if row.get("kind") == "sample"]
    last = samples[-1]
    first = samples[0]
    elapsed = last.get("elapsed_s") or 0
    duration = status.get("duration_s")
    remaining = None if not duration else max(0, duration - elapsed)
    total = memory["total"]
    restarts = sum(phone["restarts"] for phone in phones)
    freezes = sum(phone["freezes"] for phone in phones)
    ws_word = drift_word(total.get("slope_ws"))
    pm_word = drift_word(total.get("slope_pm"))
    dead = [row for row in memory["procs"] if row.get("alive") is False]
    health = evaluate_health(samples, phones, memory, ix, bad)
    gates = [
        ["receiver restarts", str(restarts), "NONE RECORDED" if restarts == 0 else "FAIL"],
        ["live no-frame gaps >2s", str(freezes), "NONE RECORDED" if freezes == 0 else "FAIL"],
        ["stuck keys/buttons", str(ix["stuck"]), "NONE RECORDED" if ix["stuck"] == 0 else "FAIL"],
        ["processes alive", "yes" if not dead and memory["procs"] else (",".join(str(row["pid"]) for row in dead) or "not observed"), "FAIL" if dead else ("OBSERVED" if memory["procs"] else "NOT OBSERVED")],
        ["failed interactions", f"{ix.get('failed', 0)}/{ix['n']}", "FAIL" if ix.get("failed") else ("NONE RECORDED" if ix["n"] else "NOT OBSERVED")],
        ["memory drift", f"WS {fmt_slope(total.get('slope_ws'))} MB/h, private {fmt_slope(total.get('slope_pm'))} MB/h", f"{ws_word}/{pm_word}"],
    ]
    phone_rows = []
    for phone in phones:
        phone_rows.append([
            phone["label"],
            fmt_num(phone["received"]),
            fmt_num(phone["counter"]),
            fmt_fps(phone["avg"]),
            fmt_fps(phone["cur"]),
            fmt_fps(phone["min"]),
            fmt_fps(phone["max"]),
            str(phone["restarts"]),
            str(phone["freezes"]),
            str(phone["state"] or "n/a"),
            "yes" if phone["live"] else "no",
            str(phone["pid"] or "n/a"),
        ])
    mem_rows = []
    for row in memory["procs"]:
        who = row["role"] if not row["phone"] else f"{row['role']} {row['phone']}"
        mem_rows.append([
            who,
            str(row["pid"]),
            row.get("name") or "",
            fmt_mb(row["ws"]),
            fmt_mb(row["pm"]),
            fmt_mb(row["ws_med"]),
            fmt_mb(row["ws_peak"]),
            fmt_mb(row["pm_med"]),
            fmt_mb(row["pm_peak"]),
            fmt_slope(row["slope_ws"]),
            fmt_slope(row["slope_pm"]),
        ])
    mem_rows.append([
        "aggregate",
        "-",
        f"{total.get('n', 0)} samples",
        fmt_mb(total.get("ws")),
        fmt_mb(total.get("pm")),
        fmt_mb(total.get("ws_med")),
        fmt_mb(total.get("ws_peak")),
        fmt_mb(total.get("pm_med")),
        fmt_mb(total.get("pm_peak")),
        fmt_slope(total.get("slope_ws")),
        fmt_slope(total.get("slope_pm")),
    ])
    ix_rows = []
    for name in PHONES:
        bucket = ix["per"].get(name) or _blank()
        rtt = median(bucket["click_rtt"])
        ix_rows.append([
            name,
            str(bucket["n"]),
            pct(bucket["click_ok"], bucket["n"]),
            "n/a" if rtt is None else f"{rtt:.0f}",
            pct(bucket["home_ok"], bucket["home_n"]),
        ])
    prior_bits = []
    for session in prior:
        sample = next(row for row in session if row.get("kind") == "sample")
        n_ix = sum(1 for row in session if row.get("kind") == "interaction")
        n_sample = sum(1 for row in session if row.get("kind") == "sample")
        prior_bits.append(f"kernel {sample.get('kernel_pid')} ({n_sample} samples, {n_ix} interactions)")
    errors = ", ".join(f"{count}x {err}" for err, count in ix["errors"].most_common(3))
    acquires = ", ".join(f"{code}:{count}" for code, count in ix["acquire"].most_common())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Gate 10 endurance dashboard",
        "",
        f"Generated {now}. Saved telemetry analysis; soak was not touched.",
        f"Observed health: **{health['status']}**. This is not Gate 10 release acceptance.",
        f"Issues: {'; '.join(health['failures'] + health['incomplete']) or 'none in these checks'}",
        "",
        f"- As of: {last.get('at')} (elapsed {hms(elapsed)}, remaining {hms(remaining) if remaining is not None else 'n/a'})",
        f"- Started: {status.get('started_at') or first.get('at')}",
        f"- Recorded running state: {status.get('running')} (not a live process check)",
        f"- Fleet: kernel {last.get('kernel_pid')} / console {last.get('console_pid')} / match {last.get('fleet_match')}",
        f"- Rows: {parsed} parsed ({bad} incomplete), live samples {len(samples)}, live interactions {ix['n']}",
        f"- Prior sessions excluded: {', '.join(prior_bits) if prior_bits else 'none'}",
        "",
        "## Recorded conditions",
        "",
        table(["check", "value", "result"], gates),
        "",
        f"FLAT labels |slope| < {FLAT_MB_H:.0f} MB/h; it is not a predeclared acceptance budget. Full-session slope includes warm-up. Last 30m WS {fmt_slope(total.get('slope_ws_30m'))} MB/h, private {fmt_slope(total.get('slope_pm_30m'))} MB/h.",
        "",
        "## Phones",
        "",
        table(
            ["phone", "received", "counter", "avg fps", "fps 60s", "min fps", "max fps", "restarts", "freezes", "state", "live", "pid"],
            phone_rows,
        ),
        "",
        "Received is counter progress within unchanged receiver identities. FPS excludes restart boundaries. No-frame gaps are sampled while marked live; unavailable video is counted separately. These counters do not measure the console's displayed frames.",
        "",
        "## Memory",
        "",
        f"10-minute window: {total.get('win_n', 0)} samples. Aggregate WS {fmt_mb(total.get('ws0'))} -> {fmt_mb(total.get('ws_mid'))} -> {fmt_mb(total.get('ws'))} MB. Private {fmt_mb(total.get('pm0'))} -> {fmt_mb(total.get('pm_mid'))} -> {fmt_mb(total.get('pm'))} MB.",
        "",
        table(
            ["process", "pid", "name", "ws MB", "private MB", "10m ws med", "10m ws peak", "10m priv med", "10m priv peak", "ws MB/h", "priv MB/h"],
            mem_rows,
        ),
        "",
        "## Interactions",
        "",
        f"- Executed: {ix['n']}",
        f"- Search click success: {pct(ix['click_ok'], ix['n'])}",
        f"- Dispatch latency p50: {('n/a' if ix['click_p50'] is None else format(ix['click_p50'], '.0f') + ' ms')} ({ix['click_dispatched']} dispatched)",
        f"- Group Home response: {pct(ix['home_ok'], ix['home_n']) if ix['home_n'] else 'n/a (0 dispatched)'}",
        f"- Stuck keys/buttons: {ix['stuck']}",
        f"- Acquire codes: {acquires or 'n/a'}",
        f"- Errors: {errors or 'none'}",
        "",
        table(["phone", "attempts", "search success", "dispatch p50 ms", "group home"], ix_rows),
        "",
    ]
    return "\n".join(lines) + "\n"


def _check() -> None:
    assert abs((slope_mb_h([0.0, 3600.0], [0.0, float(MB)]) or 0) - 1) < 1e-9
    sessions = split_sessions([
        {"kind": "sample", "elapsed_s": 15, "kernel_pid": 1},
        {"kind": "interaction", "target": "C24C"},
        {"kind": "sample", "elapsed_s": 0, "kernel_pid": 2},
    ])
    assert len(sessions) == 2 and sessions[0][1]["kind"] == "interaction"
    assert target_label("*") == "Phone 5"
    assert drift_word(0.4) == "FLAT" and drift_word(9) == "RISING"
    page = render_html(
        {"duration_s": 100},
        [{"kind": "sample", "elapsed_s": 40, "at": "t<x>"}],
        [{"label": "C24C", "received": 3, "cur": 1.0, "avg": 2.0, "state": "ok", "restarts": 0, "freezes": 0}],
        {"total": {"slope_ws": 0.1, "slope_pm": 9}, "procs": []},
        {"stuck": 0},
    )
    assert 'content="10"' in page and "width:40.0%" in page
    assert "t&lt;x&gt;" in page and "FLAT/RISING" in page


def render_html(status: dict, live: list[dict], phones: list[dict], memory: dict, ix: dict, health=None) -> str:
    esc = html.escape
    samples = [row for row in live if row.get("kind") == "sample"]
    last = samples[-1]
    elapsed = float(last.get("elapsed_s") or 0)
    duration = float(status.get("duration_s") or 0)
    remaining = None if not duration else max(0.0, duration - elapsed)
    done = 0.0 if not duration else min(100.0, max(0.0, 100.0 * elapsed / duration))
    total = memory["total"]
    restarts = sum(phone["restarts"] for phone in phones)
    freezes = sum(phone["freezes"] for phone in phones)
    stuck = int(ix["stuck"])
    health = health or evaluate_health(samples, phones, memory, ix)
    ws_word = drift_word(total.get("slope_ws"))
    pm_word = drift_word(total.get("slope_pm"))
    mem_word = ws_word if ws_word == pm_word else f"{ws_word}/{pm_word}"
    phone_rows = "\n".join(
        "<tr><td>{}</td><td class=\"num\">{}</td><td class=\"num\">{}</td><td class=\"num\">{}</td><td>{}</td></tr>".format(
            esc(str(phone["label"])),
            fmt_num(phone["received"]),
            fmt_fps(phone["cur"]),
            fmt_fps(phone["avg"]),
            esc(str(phone["state"] or "n/a")),
        )
        for phone in phones
    )
    mem_rows = []
    for row in memory["procs"]:
        who = str(row.get("role") or "process").capitalize()
        if row.get("phone"):
            who = f"{who} {row['phone']}"
        mem_rows.append(
            "<tr><td>{}</td><td class=\"num\">{}</td><td class=\"num\">{}</td><td class=\"num\">{}</td><td class=\"num\">{}</td></tr>".format(
                esc(who),
                fmt_mb(row["ws"]),
                fmt_mb(row["pm"]),
                fmt_mb(row["ws_med"]),
                fmt_mb(row["pm_med"]),
            )
        )
    css = """
:root { color-scheme: dark; --bg:#0e1116; --card:#171c24; --line:#2a3340; --text:#e7edf4; --muted:#8b98a8; --ok:#3dd68c; --bad:#ff6b6b; --warn:#f0b429; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.45 "Segoe UI", system-ui, sans-serif; }
main { max-width:1080px; margin:0 auto; padding:28px 20px 40px; display:grid; gap:16px; }
h1 { margin:0; font-size:1.45rem; letter-spacing:-.02em; }
h2 { margin:0 0 12px; font-size:.95rem; }
.sub { color:var(--muted); margin:6px 0 0; }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; }
.stats, .gates { display:grid; gap:12px; }
.stats { grid-template-columns:repeat(3,1fr); margin-top:16px; }
.gates { grid-template-columns:repeat(4,1fr); }
.stat b, .gate b { display:block; font-size:1.55rem; font-variant-numeric:tabular-nums; font-weight:650; }
.stat span, .gate span, th { color:var(--muted); font-size:.72rem; letter-spacing:.06em; text-transform:uppercase; }
.track { height:10px; margin-top:16px; background:#0b0e13; border-radius:99px; overflow:hidden; }
.fill { height:100%; width:WIDTH_PCT%; background:#4c8dff; }
.ok { color:var(--ok); } .bad { color:var(--bad); } .warn { color:var(--warn); }
table { width:100%; border-collapse:collapse; }
th, td { padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
tr:last-child td { border-bottom:0; }
@media (max-width:720px) { .stats, .gates { grid-template-columns:1fr 1fr; } }
""".replace("WIDTH_PCT", f"{done:.1f}")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>Endurance telemetry report</title>
<style>{css}</style>
</head>
<body>
<main>
<section class="card">
<h1>Endurance telemetry report</h1>
<p class="sub">Saved observations as of {esc(str(last.get("at") or ""))} · {esc(health['status'])} · not Gate 10 release acceptance</p>
<p>{esc('; '.join(health['failures'] + health['incomplete']) or 'No failures observed in these checks.')}</p>
<div class="stats">
<div class="stat"><span>Elapsed Time</span><b>{hms(elapsed)}</b></div>
<div class="stat"><span>Remaining Time</span><b>{"n/a" if remaining is None else hms(remaining)}</b></div>
<div class="stat"><span>Progress</span><b>{done:.0f}%</b></div>
</div>
<div class="track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{done:.0f}" aria-label="Soak progress"><div class="fill"></div></div>
</section>
<section class="card">
<h2>Recorded conditions</h2>
<div class="gates">
<div class="gate"><span>Restarts</span><b class="{"ok" if restarts == 0 else "bad"}">{restarts}</b></div>
<div class="gate"><span>Freezes</span><b class="{"ok" if freezes == 0 else "bad"}">{freezes}</b></div>
<div class="gate"><span>Stuck Keys</span><b class="{"ok" if stuck == 0 else "bad"}">{stuck}</b></div>
<div class="gate"><span>Memory</span><b class="{"ok" if mem_word == "FLAT" else "warn"}">{esc(mem_word)}</b></div>
</div>
</section>
<section class="card">
<h2>Live Phone Streams</h2>
<table>
<thead><tr><th>Phone</th><th class="num">Received</th><th class="num">Current FPS</th><th class="num">Average FPS</th><th>State</th></tr></thead>
<tbody>
{phone_rows}
</tbody>
</table>
</section>
<section class="card">
<h2>Memory Tracking</h2>
<table>
<thead><tr><th>Process</th><th class="num">Working Set MB</th><th class="num">Private Bytes MB</th><th class="num">10m WS med</th><th class="num">10m priv med</th></tr></thead>
<tbody>
{chr(10).join(mem_rows)}
</tbody>
</table>
</section>
</main>
</body>
</html>
"""

def main(argv=None) -> int:
    _check()
    parser = argparse.ArgumentParser(description="Gate 10 endurance dashboard")
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    parser.add_argument("--out", help="separate report directory; source records are never rewritten")
    parser.add_argument("--self-check", action="store_true", help="run synthetic checks only")
    args = parser.parse_args(argv)
    if args.self_check:
        print("self-check ok")
        return 0
    source_dir = Path(args.dir)
    out_dir = Path(args.out) if args.out else source_dir
    rows, bad = load_rows(source_dir / "telemetry.jsonl")
    status = load_json(source_dir / "status.json")
    sessions = split_sessions(rows)
    if not sessions:
        print("no sample rows", file=sys.stderr)
        return 1
    try:
        live = pick_live(sessions, status)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    samples = [row for row in live if row.get("kind") == "sample"]
    if not samples:
        print("live session has no samples", file=sys.stderr)
        return 1
    phones = analyze_phones(samples)
    memory = analyze_memory(samples)
    ix = analyze_interactions(live, samples)
    health = evaluate_health(samples, phones, memory, ix, bad)
    out_dir.mkdir(parents=True, exist_ok=True)
    text = render(status, live, phones, memory, ix, len(rows), bad, [s for s in sessions if s is not live])
    dest = out_dir / "DASHBOARD.md"
    tmp = dest.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, dest)
    page = render_html(status, live, phones, memory, ix, health)
    html_dest = out_dir / "dashboard.html"
    html_tmp = html_dest.with_suffix(".html.tmp")
    html_tmp.write_text(page, encoding="utf-8")
    os.replace(html_tmp, html_dest)
    analysis = {"health": health, "samples": len(samples), "sessions": len(sessions),
                "phones": phones, "memory": memory, "interactions": ix, "malformed_rows": bad}
    json_tmp = out_dir / "analysis.json.tmp"
    json_tmp.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    os.replace(json_tmp, out_dir / "analysis.json")
    print(text, end="")
    print(f"Observed health: {health['status']}; Gate 10 acceptance is not established")
    return 1 if health["status"] == "failed" else (2 if health["status"] == "incomplete" else 0)


if __name__ == "__main__":
    sys.exit(main())

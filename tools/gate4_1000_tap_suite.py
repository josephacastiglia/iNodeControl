"""Gate 4 targeting suite, version 2.

Written against the Gate 4 criterion in FINISH-CRITERIA.md and the gaps left by the
25 Sep two-phone run (tools/gate4_1000_tap_suite.py):

- Varied tap positions. v1 aimed every one of its 1,000 taps at Search (250, 900).
  v2 taps a per-phone table of targets spread across the screen, each with an
  expected visible effect recorded in a calibration pass and signed off by a
  person before any scored run.
- Varied distances. v1's "off_location" moved the pointer and then pressed Home,
  and Home marks the pointer state unknown, so the scored click always began with
  a corner reset: every v1 tap travelled corner -> (250, 900). v2's long_move
  category moves to the start point AFTER Home, so the click travels from there.
- Recovery from interruption. v2's after_interruption category stops input on the
  target phone, resumes it, takes a fresh lease, checks the old token is refused,
  and only then taps.
- Every board/phone pair. Any number of phones from a config file; every other
  enabled phone is checked for isolation on every trial.
- The isolation race. v1 photographed the non-target phone 350 ms after dismissing
  its previous trial, while it was often still animating, and 18 trials were
  falsely flagged. v2 returns each target phone to its Home screen and waits until
  it is still there before the next trial starts, and refuses to take a baseline
  from a phone that is not demonstrably settled.
- Provenance. The code that produced the v1 results no longer exists (the file was
  edited two minutes after its audit was written). Every v2 result carries this
  file's SHA-256, and each run writes a manifest of exactly what ran.

No retries: a missed tap stays missed. Suspected unintended actions, stuck inputs,
possible double-clicks and failed recoveries stop the run for a person to review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
# Hashed with line endings folded to LF. With core.autocrlf a Windows checkout rewrites this file
# as CRLF, which would otherwise give the same commit a different hash on every machine. Folded,
# it equals the hash of the committed blob:  git show <commit>:tools/gate4_v2/gate4_suite.py | sha256sum
HARNESS_SHA256 = hashlib.sha256(HERE.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

CATEGORIES = ("after_home", "long_move", "after_app_switch", "after_swipe", "after_interruption")
EFFECT_TIMEOUT_S = 5.0          # criterion: the effect must appear within five seconds
GRID = 10                        # compare every 10th pixel in both directions
STATUS_BAR_PX = 60               # masked: the clock and indicators change on their own
SETTLE_BUDGET_S = 8.0            # how long a phone may take to come to rest on Home
STILL = 2.0                      # consecutive-frame distance under which a screen counts as still
# Test-only: speeds every wait up against tools/gate4_v2/mock_kernel.py. A run refuses to
# start with any other value unless the kernel reports itself as the mock.
TIME_SCALE = float(os.environ.get("GATE4_TIME_SCALE", "1"))
START_POINTS = ((40, 120), (460, 120), (40, 980), (460, 980), (250, 120), (250, 980), (40, 540), (460, 540))


def nap(seconds: float) -> None:
    time.sleep(seconds * TIME_SCALE)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ frames

def grid(raw: bytes) -> tuple[int, int, list[int]]:
    """Luminance samples of a BMP on a coarse grid, status bar masked."""
    if raw[:2] != b"BM":
        raise ValueError("not a BMP")
    offset = int.from_bytes(raw[10:14], "little")
    width = int.from_bytes(raw[18:22], "little", signed=True)
    height = int.from_bytes(raw[22:26], "little", signed=True)
    bpp = int.from_bytes(raw[28:30], "little")
    if bpp not in (24, 32) or width <= 0 or height == 0:
        raise ValueError(f"unsupported BMP {width}x{height}x{bpp}")
    bottom_up, h = height > 0, abs(height)
    step = bpp // 8
    stride = (width * step + 3) & ~3
    if offset + stride * h > len(raw):
        raise ValueError("truncated BMP")
    out = []
    for y in range(STATUS_BAR_PX + GRID // 2, h, GRID):
        row = offset + ((h - 1 - y) if bottom_up else y) * stride
        for x in range(GRID // 2, width, GRID):
            i = row + x * step
            out.append((raw[i + 2] * 299 + raw[i + 1] * 587 + raw[i] * 114) // 1000)
    return width, h, out


def distance(a: list[int], b: list[int]) -> float:
    """Mean absolute luminance difference, 0-255. Different shapes are infinitely far apart."""
    if len(a) != len(b) or not a:
        return float("inf")
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


# ------------------------------------------------------------------ kernel

class Kernel:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def _req(self, method: str, url: str, body: dict | None = None, timeout: float = 25) -> bytes:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()

    def post(self, fun: str, data: dict, timeout: float = 25) -> dict:
        body = json.loads(self._req("POST", self.url + "/", {"fun": fun, "data": data}, timeout))
        return body.get("data") or body

    def status(self) -> dict:
        return json.loads(self._req("GET", self.url + "/kernel/status", timeout=5))["data"]

    def input_status(self) -> dict[str, dict]:
        return {p["id"]: p for p in self.post("/input/status", {}).get("phones") or []}

    def shot(self, pid: str) -> bytes:
        return self._req("GET", f"{self.url}/pic/screenshot?id={urllib.parse.quote(pid)}&binary=true", timeout=8)

    def send(self, pid: str, token: str, fun: str, **data) -> dict:
        t0 = time.perf_counter()
        got = self.post(fun, {"id": pid, "token": token, **data})
        got["rtt_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if not command_ok(got):
            raise RuntimeError(f"{fun} -> code {got.get('code')}: {got.get('message')}")
        return got

    def acquire(self, ids: list[str], lease_ms: int = 120000) -> dict[str, str]:
        got = self.post("/input/acquire", {"id": ",".join(ids), "lease_ms": lease_ms})
        leases = got.get("leases") or []
        tokens = {row["id"]: row["token"] for row in leases
                  if row.get("id") in ids and isinstance(row.get("token"), str) and row["token"]}
        if got.get("code") != 0 or set(tokens) != set(ids) or len(leases) != len(ids):
            if tokens:
                self.release(tokens)
            raise RuntimeError("acquire failed: " + str(got.get("message") or got))
        return tokens

    def release(self, tokens: dict[str, str]) -> None:
        if not tokens:
            return
        got = self.post("/input/release", {"id": ",".join(tokens), "tokens": tokens})
        if not command_ok(got):
            raise RuntimeError("release unconfirmed: " + str(got))


def command_ok(reply: dict) -> bool:
    return reply.get("code") == 0 and all(r.get("code") == 0 for r in reply.get("results") or [])


# ------------------------------------------------------------------ config

def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    phones = [p for p in cfg["phones"] if p.get("enabled")]
    if not phones:
        raise SystemExit("config enables no phones")
    tags = [p["tag"] for p in phones]
    if len(set(tags)) != len(tags) or len({p["id"] for p in phones}) != len(phones):
        raise SystemExit("phone tags and ids must be unique")
    for p in phones:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", p["tag"]):
            raise SystemExit("phone tags must be simple names, not paths")
        problems = check_targets(p)
        if problems:
            raise SystemExit(f"{p['tag']}: " + "; ".join(problems))
    cfg["_enabled"] = phones
    cfg["_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return cfg


def check_targets(phone: dict) -> list[str]:
    """The criterion asks for varied positions. Enforce a real spread, not one easy target."""
    t = phone.get("targets") or []
    problems = []
    if len(t) < 6:
        problems.append(f"needs at least 6 targets, has {len(t)}")
    if len({x["name"] for x in t}) != len(t):
        problems.append("target names must be unique")
    for x in t:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", x["name"]):
            problems.append("target names must be simple names, not paths")
        if not (0 <= x["x"] < 500 and STATUS_BAR_PX <= x["y"] < 1080):
            problems.append(f"{x['name']} at ({x['x']},{x['y']}) is off-screen or under the status bar")
    cols = {min(3, x["x"] * 4 // 500) for x in t}
    rows = {min(4, (x["y"] - STATUS_BAR_PX) * 5 // (1080 - STATUS_BAR_PX)) for x in t}
    if len(cols) < 3:
        problems.append("targets must span at least 3 of 4 columns")
    if len(rows) < 3:
        problems.append("targets must span at least 3 of 5 rows")
    return problems


# ------------------------------------------------------------------ plan

def plan(cfg: dict, total: int, seed: int) -> list[dict]:
    """Balanced across phones, and within each phone across every target x category pair.
    Phones alternate, so each phone rests while another is tested."""
    phones = cfg["_enabled"]
    if total <= 0 or not phones:
        raise SystemExit("a positive trial count and enabled phones are required")
    if total % len(phones):
        raise SystemExit(f"total {total} must divide evenly across {len(phones)} phones")
    per_phone = total // len(phones)
    cats = [c for c in CATEGORIES if c not in set(cfg.get("skip_categories") or [])]
    if not cats:
        raise SystemExit("at least one setup category is required")
    queues = []
    for p in phones:
        combos = [(t, c) for t in p["targets"] for c in cats]
        if per_phone % len(combos):
            raise SystemExit(f"{p['tag']}: {per_phone} taps do not divide over {len(combos)} target x category pairs")
        q = combos * (per_phone // len(combos))
        random.Random(f"{seed}:{p['tag']}").shuffle(q)
        queues.append((p, q))
    rows = []
    for i in range(per_phone):
        for p, q in queues:
            target, cat = q[i]
            rows.append({"n": len(rows), "phone": p["tag"], "id": p["id"], "profile": p.get("profile", "default"),
                         "category": cat, "target": target["name"], "x": target["x"], "y": target["y"]})
    return rows


def far_start(x: int, y: int) -> tuple[int, int]:
    return max(START_POINTS, key=lambda s: (s[0] - x) ** 2 + (s[1] - y) ** 2)


# ------------------------------------------------------------------ calibration

def calibration_path(out: Path) -> Path:
    return out / "calibration.json"


def load_calibration(out: Path, cfg: dict) -> dict:
    path = calibration_path(out)
    if not path.exists():
        raise SystemExit(f"no calibration at {path}; run --calibrate first")
    cal = json.loads(path.read_text(encoding="utf-8"))
    if cal.get("config_sha256") != cfg["_sha256"]:
        raise SystemExit("calibration was made for a different config; recalibrate")
    if not cal.get("reviewed") or not cal.get("reviewed_by"):
        raise SystemExit("calibration not signed off: check every reference frame, then set reviewed=true and reviewed_by")
    for tag, phone in cal["phones"].items():
        bad = [n for n, ref in phone["targets"].items() if not ref.get("valid")]
        if bad:
            raise SystemExit(f"{tag}: invalid references {bad}: {phone.get('warnings')}. Fix the targets and recalibrate")
        for name, ref in [("home", phone["home"])] + list(phone["targets"].items()):
            f = out / ref["file"]
            if not f.resolve().is_relative_to(out.resolve()):
                raise SystemExit("calibration reference escapes its output directory")
            if sha256_file(f) != ref["sha256"]:
                raise SystemExit(f"reference {f} changed since calibration")
            width, height, ref["grid"] = grid(f.read_bytes())
            if (width, height) != (500, 1080):
                raise SystemExit("calibration requires 500x1080 frames")
            if name != "home" and (not math.isfinite(ref["threshold"]) or ref["threshold"] <= 0):
                raise SystemExit("calibration thresholds must be finite and positive")
        names = list(phone["targets"])
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                d = distance(phone["targets"][a]["grid"], phone["targets"][b]["grid"])
                if d < 2 * max(phone["targets"][a]["threshold"], phone["targets"][b]["threshold"]):
                    raise SystemExit(f"{tag}: {a} and {b} produce screens too alike to tell apart ({d:.1f}); choose distinct targets")
    return cal


def wait_still(k: Kernel, pid: str, budget: float, runs: int = 4, away_from: list[int] | None = None,
               min_away: float = 15.0) -> tuple[bool, bytes]:
    """At rest means `runs` consecutive unchanged frames, about a second.

    One unchanged pair is not enough: a transition can hold a frame for a moment, and an AirPlay
    mirror can freeze mid-animation. With `away_from`, the screen must also differ from that
    picture (a tap's result must not be mistaken for the Home screen it started from)."""
    prev = k.shot(pid)
    pg = grid(prev)[2]
    calm = 0
    deadline = time.perf_counter() + budget * TIME_SCALE
    while time.perf_counter() < deadline:
        nap(0.25)
        cur = k.shot(pid)
        cg = grid(cur)[2]
        moved_away = away_from is None or distance(cg, away_from) > min_away
        calm = calm + 1 if distance(pg, cg) < STILL and moved_away else 0
        if calm >= runs:
            return True, cur
        prev, pg = cur, cg
    return False, prev


def back_home(k: Kernel, pid: str, home: list[int], thr: float, budget: float = SETTLE_BUDGET_S) -> bool:
    t0 = time.perf_counter()
    prev = grid(k.shot(pid))[2]
    while time.perf_counter() - t0 < budget * TIME_SCALE:
        nap(0.2)
        cur = grid(k.shot(pid))[2]
        if distance(cur, home) <= thr and distance(prev, cur) < STILL:
            return True
        prev = cur
    return False


def calibrate(k: Kernel, cfg: dict, out: Path) -> None:
    """Record what each target should look like after a tap. A person must check these."""
    phones = cfg["_enabled"]
    if calibration_path(out).exists() or (out / "refs").exists():
        raise SystemExit("calibration evidence already exists; use a new output folder")
    preflight(k, cfg)
    refs = out / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    ids = [p["id"] for p in phones]
    tokens = k.acquire(ids)
    result = {"made": utc(), "harness_sha256": HARNESS_SHA256, "config_sha256": cfg["_sha256"],
              "reviewed": False, "reviewed_by": "", "phones": {}}
    try:
        for p in phones:
            pid, tag = p["id"], p["tag"]
            k.send(pid, tokens[pid], "/key/sendkey", fn_key="Home")
            ok, home = wait_still(k, pid, SETTLE_BUDGET_S)
            if not ok:
                raise SystemExit(f"{tag}: Home never came to rest")
            samples = [grid(home)[2]]
            for _ in range(5):
                nap(0.4)
                samples.append(grid(k.shot(pid))[2])
            noise = max(distance(samples[i], samples[i + 1]) for i in range(len(samples) - 1))
            hf = refs / f"{tag}-home.bmp"
            hf.write_bytes(home)
            entry = {"home": {"file": str(hf.relative_to(out)), "sha256": sha256_file(hf)},
                     "home_noise": round(noise, 3), "targets": {}}
            home_thr = max(4.0, 3 * noise + 1.0)
            for t in p["targets"]:
                k.send(pid, tokens[pid], "/key/sendkey", fn_key="Home")
                if not back_home(k, pid, samples[0], home_thr):
                    raise SystemExit(f"{tag}: did not return to Home before calibrating {t['name']}")
                k.send(pid, tokens[pid], "/mouse/click", x=t["x"], y=t["y"], button=1)
                ok, a = wait_still(k, pid, SETTLE_BUDGET_S, away_from=samples[0])
                nap(1.0)
                b = k.shot(pid)
                stab = distance(grid(a)[2], grid(b)[2])
                from_home = distance(grid(a)[2], samples[0])
                tf = refs / f"{tag}-{t['name']}.bmp"
                tf.write_bytes(a)
                entry["targets"][t["name"]] = {"file": str(tf.relative_to(out)), "sha256": sha256_file(tf),
                                               "x": t["x"], "y": t["y"], "stability": round(stab, 3),
                                               "distance_from_home": round(from_home, 2), "came_to_rest": ok}
                print(f"{tag} {t['name']}: stability {stab:.2f}, distance from Home {from_home:.1f}"
                      + ("" if ok else "  (did not come to rest)"), flush=True)
            k.send(pid, tokens[pid], "/key/sendkey", fn_key="Home")
            wait_still(k, pid, SETTLE_BUDGET_S)
            result["phones"][tag] = entry
    finally:
        k.release(tokens)
    thresholds(result)
    calibration_path(out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote {calibration_path(out)}. Open every refs/*.bmp and confirm it shows the intended screen;"
          " then set reviewed=true and reviewed_by in calibration.json.", flush=True)


def thresholds(cal: dict) -> None:
    """Derived from measured noise, so a phone with a busier Home screen gets a looser bound."""
    for phone in cal["phones"].values():
        phone["home_threshold"] = round(max(4.0, 3 * phone["home_noise"] + 1.0), 2)
        phone["isolation_threshold"] = phone["home_threshold"]
        for ref in phone["targets"].values():
            ref["threshold"] = round(max(6.0, 3 * ref["stability"] + 2.0), 2)
        warn = []
        for a, ref in phone["targets"].items():
            ref["valid"] = ref["distance_from_home"] >= 15 and ref["came_to_rest"]
            if ref["distance_from_home"] < 15:
                warn.append(f"{a}: the tap produced no visible change from Home")
            if not ref["came_to_rest"]:
                warn.append(f"{a}: the result never came to rest (dynamic content, or still animating)")
        phone["warnings"] = warn


# ------------------------------------------------------------------ verdicts

def classify(frame: list[int], tag: str, intended: str, cal: dict) -> dict:
    phone = cal["phones"][tag]
    d_home = distance(frame, phone["home"]["grid"])
    dists = {name: distance(frame, ref["grid"]) for name, ref in phone["targets"].items()}
    d_t = dists[intended]
    others = [v for name, v in dists.items() if name != intended]
    nearest = min(dists, key=dists.get)
    at_home = d_home <= phone["home_threshold"]
    matches = (not at_home and d_t <= phone["targets"][intended]["threshold"]
               and d_t < 0.6 * min(others + [d_home]))
    wrong = (not matches and not at_home and nearest != intended
             and dists[nearest] <= phone["targets"][nearest]["threshold"])
    return {"d_target": round(d_t, 2), "d_home": round(d_home, 2), "nearest": nearest,
            "d_nearest_other": round(min(others), 2) if others else None,
            "hit": matches, "at_home": at_home, "wrong_target": wrong,
            "unknown_screen": not matches and not at_home and not wrong}


def settle_home(k: Kernel, pid: str, tag: str, cal: dict, budget: float = SETTLE_BUDGET_S) -> tuple[bool, list[int], float]:
    """True only once the phone shows its Home screen and has stopped moving."""
    home, thr = cal["phones"][tag]["home"]["grid"], cal["phones"][tag]["home_threshold"]
    t0 = time.perf_counter()
    prev = grid(k.shot(pid))[2]
    while time.perf_counter() - t0 < budget * TIME_SCALE:
        nap(0.2)
        cur = grid(k.shot(pid))[2]
        if distance(cur, home) <= thr and distance(prev, cur) < STILL:
            return True, cur, round((time.perf_counter() - t0) * 1000)
        prev = cur
    return False, prev, round((time.perf_counter() - t0) * 1000)


# ------------------------------------------------------------------ one trial

def setup(k: Kernel, spec: dict, tokens: dict[str, str], cal: dict) -> dict:
    pid, tag, cat = spec["id"], spec["phone"], spec["category"]
    rec: dict = {"actions": {}, "setup_ok": True, "notes": []}
    act = rec["actions"]

    def send(name, fun, **data):
        act[name] = k.send(pid, tokens[pid], fun, **data)["rtt_ms"]

    if cat == "after_app_switch":
        send("app_switch", "/key/sendkey", fn_key="AppSwitch")
        nap(0.9)
        if classify(grid(k.shot(pid))[2], tag, spec["target"], cal)["at_home"]:
            rec["setup_ok"] = False
            rec["notes"].append("App Switcher did not appear")
    elif cat == "after_swipe":
        send("swipe_left", "/mouse/swipe", direction="left", len=0.75, duration=400)
        nap(0.6)
        if classify(grid(k.shot(pid))[2], tag, spec["target"], cal)["at_home"]:
            rec["setup_ok"] = False
            rec["notes"].append("swipe left did not change the page")
        send("swipe_right", "/mouse/swipe", direction="right", len=0.75, duration=400)
        nap(0.5)

    send("home", "/key/sendkey", fn_key="Home")
    ok, _, ms = settle_home(k, pid, tag, cal)
    rec["home_settle_ms"] = ms
    if not ok:
        raise BlockingEvent("target phone did not settle on Home before the tap")

    if cat in ("long_move", "after_interruption"):
        # After Home, so the click really travels from here instead of from a corner reset.
        sx, sy = far_start(spec["x"], spec["y"])
        send("move_to_start", "/mouse/move", x=sx, y=sy)
        rec["start"] = [sx, sy]
        rec["move_px"] = round(((sx - spec["x"]) ** 2 + (sy - spec["y"]) ** 2) ** 0.5)
        nap(0.25)

    if cat == "after_interruption":
        old = tokens[pid]
        stop = k.post("/input/stop", {"id": pid})
        st = k.input_status().get(pid, {})
        if stop.get("code") != 0 or not st.get("stopped"):
            raise BlockingEvent(f"stop did not take effect: {stop}")
        resumed = k.post("/input/resume", {"id": pid, "expected_generations": {pid: st.get("generation", 0)}})
        if resumed.get("code") != 0:
            raise BlockingEvent(f"resume failed: {resumed}")
        tokens[pid] = k.acquire([pid])[pid]
        refused = k.post("/mouse/move", {"id": pid, "token": old, "x": sx, "y": sy}).get("code") == 33
        rec["old_token_refused"] = refused
        if not refused:
            raise BlockingEvent("a revoked token was still accepted")
        act["interruption"] = "stop, resume, new lease"
    return rec


class BlockingEvent(Exception):
    """Stops the run for a person to review. Never converted into a pass."""


def watch_tap(k: Kernel, spec: dict, token: str, cal: dict) -> dict:
    pid, tag = spec["id"], spec["phone"]
    box: dict = {}

    def click() -> None:
        t0 = time.perf_counter()
        try:
            box["reply"] = k.post("/mouse/click", {"id": pid, "token": token, "x": spec["x"], "y": spec["y"], "button": 1})
        except Exception as ex:
            box["error"] = str(ex)
        box["rtt_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    t0 = time.perf_counter()
    threading.Thread(target=click, daemon=True).start()
    seen, last, polls = None, None, 0
    while time.perf_counter() - t0 < EFFECT_TIMEOUT_S * TIME_SCALE:
        raw = k.shot(pid)
        polls += 1
        v = classify(grid(raw)[2], tag, spec["target"], cal)
        last = (raw, v)
        if v["hit"]:
            seen = round((time.perf_counter() - t0) * 1000, 1)
            break
        nap(0.15)
    end = time.perf_counter() + 20
    while "rtt_ms" not in box and time.perf_counter() < end:
        time.sleep(0.01)
    if box.get("error") or not command_ok(box.get("reply") or {}):
        raise BlockingEvent("tap failed or its outcome is unknown; no follow-up input: " + str(box))
    raw, v = last
    post_change = False
    if seen is not None:
        # A second click would carry on into the app. The screen must hold the intended result.
        nap(0.6)
        raw = k.shot(pid)
        later = classify(grid(raw)[2], tag, spec["target"], cal)
        post_change = later["d_target"] > 1.5 * cal["phones"][tag]["targets"][spec["target"]]["threshold"]
    else:
        ok, raw = wait_still(k, pid, 2.0)
        v = classify(grid(raw)[2], tag, spec["target"], cal)
    return {"dispatch_ms": box.get("rtt_ms"), "click_code": (box.get("reply") or {}).get("code"),
            "click_error": box.get("error"), "effect_ms": seen, "verdict": v, "polls": polls,
            "post_hit_change": post_change, "frame": raw}


def stuck(k: Kernel, ids: list[str]) -> list[dict]:
    st = k.input_status()
    return [{"id": i, **{f: st.get(i, {}).get(f) for f in ("active", "releasing", "release_failed", "message")}}
            for i in ids if any(st.get(i, {}).get(f) is not False for f in ("active", "releasing", "release_failed"))]


def trial(k: Kernel, spec: dict, tokens: dict[str, str], cal: dict, cfg: dict, shots: Path, run_id: str) -> dict:
    pid, tag = spec["id"], spec["phone"]
    others = [p for p in cfg["_enabled"] if p["id"] != pid]
    row = {"run_id": run_id, "harness_sha256": HARNESS_SHA256[:16], "at": utc(), **spec,
           "clicks_sent": 0, "pass": False}

    # Isolation baselines, taken only from phones demonstrably at rest on Home.
    baselines, unsettled = {}, []
    for o in others:
        ok, g, _ = settle_home(k, o["id"], o["tag"], cal)
        if ok:
            baselines[o["tag"]] = g
        else:
            unsettled.append(o["tag"])
    if unsettled:
        raise BlockingEvent("could not take an isolation baseline: not settled on Home: " + ",".join(unsettled))

    row.update(setup(k, spec, tokens, cal))
    watched = watch_tap(k, spec, tokens[pid], cal)
    row["clicks_sent"] = 1

    iso = []
    for o in others:
        d = distance(baselines[o["tag"]], grid(k.shot(o["id"]))[2])
        thr = cal["phones"][o["tag"]]["isolation_threshold"]
        iso.append({"phone": o["tag"], "distance": round(d, 2), "threshold": thr, "isolated": d <= thr})
    v = watched["verdict"]
    hit = bool(v["hit"] and watched["effect_ms"] is not None and watched["effect_ms"] <= EFFECT_TIMEOUT_S * 1000 * TIME_SCALE)
    row.update({
        "dispatch_ms": watched["dispatch_ms"], "click_code": watched["click_code"], "click_error": watched["click_error"],
        "effect_ms": watched["effect_ms"], "within_5s": hit, "verdict": v,
        "wrong_target": v["wrong_target"], "unknown_screen": v["unknown_screen"],
        "post_hit_change": watched["post_hit_change"], "isolation": iso,
        "isolated": all(i["isolated"] for i in iso), "polls": watched["polls"],
    })
    row["stuck_detail"] = stuck(k, [p["id"] for p in cfg["_enabled"]])
    row["stuck"] = bool(row["stuck_detail"])
    row["target_hit"] = bool(hit and row["click_code"] == 0 and not row["post_hit_change"])
    row["pass"] = bool(row["target_hit"] and row["setup_ok"] and row["isolated"] and not row["stuck"])

    if not row["pass"]:
        shots.mkdir(parents=True, exist_ok=True)
        (shots / f"{spec['n']:05d}-{tag}-{spec['target']}-after.bmp").write_bytes(watched["frame"])
        for i, o in zip(iso, others):
            if not i["isolated"]:
                (shots / f"{spec['n']:05d}-{o['tag']}-other.bmp").write_bytes(k.shot(o["id"]))

    if blocking_reason(row):
        row["recover_ok"] = None
        return row

    # Back to Home only after a result that allows further input.
    k.send(pid, tokens[pid], "/key/sendkey", fn_key="Home")
    ok, _, ms = settle_home(k, pid, tag, cal)
    row["recover_ms"] = ms
    row["recover_ok"] = ok
    return row


def blocking_reason(row: dict) -> str | None:
    if row.get("error"):
        return "input or observation failed: " + row["error"]
    if row.get("stuck"):
        return "stuck input"
    if row.get("post_hit_change"):
        return "screen changed after the hit (possible double-click)"
    if row.get("isolated") is False:
        return "possible unintended action on another phone"
    if row.get("recover_ok") is False:
        return "phone did not return to Home"
    if row.get("blocking"):
        return row["blocking"]
    return None


# ------------------------------------------------------------------ run

def preflight(k: Kernel, cfg: dict) -> dict:
    ks = k.status()
    live = {r.get("deviceid"): r for r in ks.get("receivers") or []}
    st = k.input_status()
    report = []
    for p in cfg["_enabled"]:
        r = live.get(p["id"]) or {}
        problems = []
        if not r.get("live"):
            problems.append("not mirroring")
        expected_name = p.get("receiver_name")
        if expected_name and r.get("name") != expected_name:
            problems.append(f"receiver is {r.get('name')!r}, expected {expected_name!r}")
        s = st.get(p["id"], {})
        if any(s.get(field) is not False for field in ("owned", "active", "stopped", "releasing", "release_failed")):
            problems.append("input ownership/recovery is not explicitly idle and ready")
        report.append({"phone": p["tag"], "id": p["id"], "receiver": r.get("name"), "problems": problems})
    bad = [r for r in report if r["problems"]]
    if bad:
        raise SystemExit("preflight failed: " + json.dumps(bad))
    if ks.get("input_leases_required") is not True:
        raise SystemExit("kernel does not enforce input leases; refusing")
    if TIME_SCALE != 1 and not ks.get("mock"):
        raise SystemExit("GATE4_TIME_SCALE is for the mock kernel only; refusing to drive real phones with it")
    return {"kernel": {k2: ks.get(k2) for k2 in ("input_protocol", "input_leases_required", "allowed")}, "phones": report}


def pct(vals: list[float], p: float):
    if not vals:
        return None
    s = sorted(vals)
    return round(s[min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))], 1)


def summarize(rows: list[dict], total: int, state: str, reason: str | None) -> dict:
    def bucket(key):
        out: dict = {}
        for r in rows:
            b = out.setdefault(str(r.get(key)), {"n": 0, "hit": 0, "pass": 0, "setup_failed": 0})
            b["n"] += 1
            b["hit"] += int(bool(r.get("target_hit")))
            b["pass"] += int(bool(r.get("pass")))
            b["setup_failed"] += int(r.get("setup_ok") is False)
        return out
    lat = [r["effect_ms"] if r.get("target_hit") else EFFECT_TIMEOUT_S * 1000 * TIME_SCALE for r in rows]
    n = len(rows)
    hits = sum(1 for r in rows if r.get("target_hit"))
    return {
        "updated": utc(), "state": state, "stopped_because": reason,
        "harness_sha256": HARNESS_SHA256, "planned": total, "completed": n,
        "target_hits": hits, "misses": n - hits, "passed": sum(1 for r in rows if r.get("pass")),
        "accuracy": round(hits / n, 4) if n else None,
        "criterion_995_of_1000": (sum(bool(r.get("pass")) for r in rows) >= 995)
            if n == total == 1000 and state == "complete" and not reason else None,
        "release_acceptance": False,
        "effect_ms_p50": pct(lat, 50), "effect_ms_p95": pct(lat, 95),
        "unintended_phone_actions": sum(1 for r in rows if r.get("isolated") is False),
        "stuck_events": sum(1 for r in rows if r.get("stuck")),
        "possible_double_clicks": sum(1 for r in rows if r.get("post_hit_change")),
        "wrong_target": sum(1 for r in rows if r.get("wrong_target")),
        "per_phone": bucket("phone"), "per_profile": bucket("profile"),
        "per_category": bucket("category"), "per_target": bucket("target"),
        "note": "Misses count as 5000 ms in latency. No tap is retried. Trials whose setup did not produce its"
                " intended condition are counted under setup_failed and must not be credited to that category.",
    }


def run(args, cfg: dict) -> int:
    out = Path(args.out)
    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise SystemExit("run-id must be a simple name, not a path")
    rdir = out / "runs" / run_id
    if rdir.exists():
        raise SystemExit("run evidence already exists; use a new run-id (automatic resume is disabled)")
    rows_plan = plan(cfg, args.total, args.seed)
    cal = load_calibration(out, cfg)
    k = Kernel(args.url)
    pre = preflight(k, cfg)
    rdir.mkdir(parents=True, exist_ok=False)
    manifest = {"run_id": run_id, "started": utc(), "harness": str(HERE.name), "harness_sha256": HARNESS_SHA256,
                "config": cfg["phones"], "config_sha256": cfg["_sha256"], "calibration_sha256":
                sha256_file(calibration_path(out)), "reviewed_by": cal["reviewed_by"], "total": args.total,
                "seed": args.seed, "url": args.url, "python": sys.version, "time_scale": TIME_SCALE, "preflight": pre}
    (rdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log, ids = rdir / "results.jsonl", [p["id"] for p in cfg["_enabled"]]
    rows, tokens, reason = [], {}, None
    release = {"confirmed": False, "attempted": False}
    with log.open("x", encoding="utf-8") as fh:
        try:
            tokens = k.acquire(ids)
            for spec in rows_plan:
                try:
                    st = k.input_status()
                    if any(i not in st for i in ids):
                        raise BlockingEvent("input status is incomplete")
                    if any(st[i].get("lease_remaining_ms", 0) < 25000 for i in ids):
                        got = k.post("/input/renew", {"id": ",".join(ids), "tokens": tokens})
                        if got.get("code") != 0:
                            raise BlockingEvent("renew failed: " + str(got))
                    row = trial(k, spec, tokens, cal, cfg, rdir / "shots", run_id)
                except Exception as ex:
                    row = {"run_id": run_id, "harness_sha256": HARNESS_SHA256[:16], "at": utc(), **spec,
                           "pass": False, "target_hit": False, "error": str(ex), "outcome": "unconfirmed"}
                rows.append(row)
                fh.write(json.dumps(row) + "\n"); fh.flush()
                print(f"n={row['n']} {row['phone']} {row['category']} hit={row.get('target_hit')} pass={row.get('pass')}", flush=True)
                reason = blocking_reason(row)
                state = "stopped" if reason else "running"
                (rdir / "status.json").write_text(json.dumps(summarize(rows, args.total, state, reason), indent=2), encoding="utf-8")
                if reason:
                    break
        except (KeyboardInterrupt, SystemExit):
            reason = "run interrupted before completion"
            raise
        except Exception as ex:
            reason = str(ex)
        finally:
            if tokens:
                release["attempted"] = True
                try:
                    k.release(tokens)
                    release["confirmed"] = True
                except Exception as ex:
                    release["error"] = str(ex)
                    reason = reason or "release unconfirmed: " + str(ex)
            else:
                reason = reason or "no lease acquired"
            status = summarize(rows, args.total, "stopped" if reason else "complete", reason)
            status["release"] = release
            (rdir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return 2 if reason else 0


def self_check() -> None:
    """Offline checks of the pieces that do not need a kernel."""
    def bmp(fill) -> bytes:
        # Rows are uniform here, so build each one at once; fill(x, y) is sampled at x = 0.
        w, h = 500, 1080
        px = b"".join(bytes((fill(0, y),) * 3) * w for y in range(h - 1, -1, -1))
        hdr = b"BM" + (54 + len(px)).to_bytes(4, "little") + b"\0\0\0\0" + (54).to_bytes(4, "little")
        info = (40).to_bytes(4, "little") + w.to_bytes(4, "little") + h.to_bytes(4, "little", signed=True) \
            + (1).to_bytes(2, "little") + (24).to_bytes(2, "little") + bytes(24)
        return hdr + info + bytes(px)
    a = grid(bmp(lambda x, y: 100))[2]
    b = grid(bmp(lambda x, y: 100 if y < 40 else 100))[2]
    c = grid(bmp(lambda x, y: 100 if y >= STATUS_BAR_PX else 250))[2]
    assert distance(a, b) == 0 and distance(a, c) == 0, "status bar must be masked"
    assert distance(a, grid(bmp(lambda x, y: 110))[2]) == 10
    good = {"tag": "T", "targets": [{"name": f"t{i}", "x": x, "y": y} for i, (x, y) in
                                     enumerate([(60, 150), (190, 150), (310, 400), (440, 400), (60, 700), (250, 1000)])]}
    assert check_targets(good) == [], check_targets(good)
    one = {"tag": "T", "targets": [{"name": f"t{i}", "x": 250, "y": 900} for i in range(6)]}
    assert check_targets(one), "one repeated target must be refused"
    cfg = {"_enabled": [dict(good, id="A", tag="A"), dict(good, id="B", tag="B")]}
    rows = plan(cfg, 2 * 6 * len(CATEGORIES) * 2, 7)
    assert [r["phone"] for r in rows[:4]] == ["A", "B", "A", "B"], "phones must alternate"
    for tag in ("A", "B"):
        pairs = {}
        for r in rows:
            if r["phone"] == tag:
                pairs[(r["target"], r["category"])] = pairs.get((r["target"], r["category"]), 0) + 1
        assert set(pairs.values()) == {2} and len(pairs) == 6 * len(CATEGORIES), "every target x category pair equally"
    assert plan(cfg, len(rows), 7) == rows and plan(cfg, len(rows), 8) != rows, "plan must be seeded and deterministic"
    assert far_start(60, 150) == (460, 980)
    print("self-check ok; harness sha256", HARNESS_SHA256)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=False, help="phones and targets (see targets.example.json)")
    ap.add_argument("--out", default="analysis/gate4-current", help="calibration, references and runs go here")
    ap.add_argument("--url", default="http://127.0.0.1:9913/api")
    ap.add_argument("--total", "--total-taps", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261001)
    ap.add_argument("--run-id")
    ap.add_argument("--calibrate", action="store_true", help="record reference frames (drives the phones)")
    ap.add_argument("--plan", action="store_true", help="print the plan and exit; sends nothing")
    ap.add_argument("--live", action="store_true", help="required for anything that drives a phone")
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()
    if args.self_check:
        self_check()
        return 0
    if not args.config:
        ap.error("--config is required")
    cfg = load_config(Path(args.config))
    if args.plan:
        rows = plan(cfg, args.total, args.seed)
        for r in rows[:20]:
            print(json.dumps(r))
        print(f"... {len(rows)} trials over {len(cfg['_enabled'])} phone(s)")
        return 0
    if not args.live:
        raise SystemExit("refusing to drive phones without --live")
    if args.calibrate:
        calibrate(Kernel(args.url), cfg, Path(args.out))
        return 0
    return run(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())

"""A stand-in for the iMouse 2.0 kernel and its phones, for testing gate4_suite.py offline.

It follows the real kernel where the harness depends on it (src/iMouse.Kernel, InputSessions.cs
and InputRouter.cs at ee445d7):

- per-phone leases; commands need the phone's current token;
- /input/stop revokes the token and bumps the generation; /input/resume needs the matching
  generation and leaves old tokens invalid;
- Home and AppSwitch mark the pointer position unknown, so the next move or click starts
  with a corner reset. That is the behaviour which made every v1 "off_location" tap begin
  from a corner.

Phones are simulated as screens that change after realistic delays, with encoder-style noise
and a status bar that changes every frame. Faults can be injected to check that the harness
notices them. Reports itself as {"mock": true} so the harness allows GATE4_TIME_SCALE.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

OFFLINE = {}


def offline_request(client, method, url, body=None, timeout=25):
    mock = OFFLINE.get(client.url)
    if mock is None or not url.startswith(client.url + "/"):
        raise AssertionError("offline tests refuse any unregistered service: " + url)
    route = url[len(client.url):]
    with mock.lock:
        if method == "POST":
            return json.dumps({"data": mock.dispatch_post(body["fun"], body.get("data") or {})}).encode()
        if route == "/kernel/status":
            return json.dumps({"data": mock.kernel_status()}).encode()
        if route.startswith("/pic/screenshot?"):
            pid = parse_qs(urlparse(route).query)["id"][0]
            return mock.phones[pid].frame(time.monotonic(), mock.rng)
        raise AssertionError("unexpected offline route: " + route)


W, H = 500, 1080


def _bmp(row_values: list[int]) -> bytes:
    px = b"".join(bytes((v, v, v)) * W for v in reversed(row_values))
    hdr = b"BM" + (54 + len(px)).to_bytes(4, "little") + b"\0\0\0\0" + (54).to_bytes(4, "little")
    info = (40).to_bytes(4, "little") + W.to_bytes(4, "little") + H.to_bytes(4, "little", signed=True) \
        + (1).to_bytes(2, "little") + (24).to_bytes(2, "little") + bytes(24)
    return hdr + info + px


def _pattern(screen: str) -> list[int]:
    """A distinct, row-uniform picture per screen."""
    if screen == "home":
        return [60 + 50 * ((y // 54) % 2) + (y * 7) % 13 for y in range(H)]
    if screen == "page2":
        return [70 + 60 * ((y // 90) % 2) for y in range(H)]
    if screen == "switcher":
        return [25 + 40 * ((y // 160) % 2) for y in range(H)]
    if screen.startswith("app:"):
        i = int(screen.split(":")[1])
        return [30 + 160 * ((y // (18 + 11 * i)) % 2) + (i * 23) % 40 for y in range(H)]
    if screen.startswith("inner:"):
        return [200 - 30 * ((y // 40) % 2) for y in range(H)]
    raise ValueError(screen)


class Phone:
    def __init__(self, tag: str, pid: str, targets: list[dict]):
        self.tag, self.id, self.targets = tag, pid, targets
        self.screen = "home"
        self.pending: list[tuple[float, str]] = []   # (when, screen)
        self.leaving: tuple[float, str] | None = None  # (until, dimmed screen shown while animating)
        self.known = False
        self.token: str | None = None
        self.stopped = False
        self.generation = 0
        self.deadline = 0.0

    def tick(self, now: float) -> None:
        due = [p for p in self.pending if p[0] <= now]
        for p in due:
            self.screen = p[1]
            self.pending.remove(p)
        if self.leaving and self.leaving[0] <= now:
            self.leaving = None

    def frame(self, now: float, rng: random.Random) -> bytes:
        self.tick(now)
        if self.leaving:
            rows = [int(v * 0.6) for v in _pattern(self.leaving[1])]   # mid-animation: neither screen
        else:
            rows = list(_pattern(self.screen))
        for y in range(60):
            rows[y] = rng.randrange(256)                                 # the clock: always changing
        for _ in range(12):
            y = rng.randrange(60, H)
            rows[y] = max(0, min(255, rows[y] + rng.choice((-1, 1))))    # encoder noise
        return _bmp(rows)


class MockKernel:
    def __init__(self, phones: list[dict], *, scale: float = 1.0, appswitch_works: bool = True,
                 open_ms: int = 350, dismiss_ms: int = 400, crosstalk: tuple[str, str] | None = None,
                 miss_every: int = 0, double_on: set[int] | None = None, seed: int = 1):
        self.phones = {p["id"]: Phone(p["tag"], p["id"], p["targets"]) for p in phones}
        self.scale, self.appswitch_works = scale, appswitch_works
        self.open_ms, self.dismiss_ms = open_ms, dismiss_ms
        self.crosstalk, self.miss_every, self.double_on = crosstalk, miss_every, double_on or set()
        self.clicks = 0
        self.log: list[dict] = []
        self.lock = threading.Lock()
        self.rng = random.Random(seed)
        self.server: ThreadingHTTPServer | None = None

    # -- helpers
    def _later(self, ms: float) -> float:
        return time.monotonic() + ms / 1000 * self.scale

    def _go(self, phone: Phone, screen: str, ms: float, dim_from_current: bool = False) -> None:
        if dim_from_current and phone.screen != "home":
            phone.leaving = (self._later(ms), phone.screen)
        phone.pending = [(self._later(ms), screen)]

    # -- leases (InputSessions)
    def _acquire(self, d: dict) -> dict:
        ids = d["id"].split(",")
        ps = [self.phones[i] for i in ids]
        if any(p.token or p.stopped for p in ps):
            return {"code": 409, "message": "A target is owned, stopped, or recovering. No leases acquired."}
        ms = int(d.get("lease_ms", 30000))
        for p in ps:
            p.token, p.deadline = uuid.uuid4().hex, time.monotonic() + ms / 1000
        return {"code": 0, "leases": [{"id": p.id, "token": p.token, "lease_ms": ms} for p in ps]}

    def _close(self, d: dict, stop: bool) -> dict:
        for i in d["id"].split(","):
            p = self.phones[i]
            p.token, p.generation = None, p.generation + 1
            p.stopped |= stop
        return {"code": 0, "message": "Input released; previous tokens revoked."}

    def _resume(self, d: dict) -> dict:
        ids = d["id"].split(",")
        exp = d.get("expected_generations") or {}
        if any(exp.get(i) != self.phones[i].generation for i in ids):
            return {"code": 409, "message": "Generation changed; inspect status again."}
        for i in ids:
            self.phones[i].stopped = False
        return {"code": 0, "message": "Input ready for a new lease. Old tokens remain invalid."}

    def _status(self) -> dict:
        now = time.monotonic()
        return {"code": 0, "protocol": 1, "phones": [
            {"id": p.id, "owned": p.token is not None, "active": False, "stopped": p.stopped, "releasing": False,
             "release_failed": False, "message": "", "generation": p.generation,
             "lease_remaining_ms": max(0, int((p.deadline - now) * 1000)) if p.token else 0}
            for p in self.phones.values()]}

    # -- input (InputRouter)
    def _input(self, fun: str, d: dict) -> dict:
        p = self.phones[d["id"]]
        token = d.get("token") or (d.get("tokens") or {}).get(p.id)
        if p.stopped or not p.token or token != p.token:
            return {"code": 33, "message": "A valid per-phone input lease is required."}
        p.tick(time.monotonic())
        entry = {"t": time.monotonic(), "phone": p.tag, "fun": fun, "data": {k: v for k, v in d.items() if k not in ("token", "tokens")},
                 "reset": False}
        if fun in ("/mouse/move", "/mouse/click"):
            if not p.known:
                entry["reset"] = True                                   # corner reset before moving
                p.known = True
        if fun == "/key/sendkey":
            key = d.get("fn_key")
            if key == "Home":
                p.known = False
                if p.screen != "home" or p.pending:
                    self._go(p, "home", self.dismiss_ms, dim_from_current=True)
            elif key == "AppSwitch":
                p.known = False
                if self.appswitch_works:
                    self._go(p, "switcher", 300)
        elif fun == "/mouse/swipe":
            if p.screen == "home" and d.get("direction") == "left":
                self._go(p, "page2", 300)
            elif p.screen == "page2" and d.get("direction") == "right":
                self._go(p, "home", 300)
        elif fun == "/mouse/click":
            self.clicks += 1
            missed = self.miss_every and self.clicks % self.miss_every == 0
            if p.screen == "home" and not p.pending and not missed:
                hit = [i for i, t in enumerate(p.targets) if abs(t["x"] - d["x"]) <= 30 and abs(t["y"] - d["y"]) <= 30]
                if hit:
                    self._go(p, f"app:{hit[0]}", self.open_ms)
                    if self.clicks in self.double_on:
                        p.pending.append((self._later(self.open_ms + 300), "inner:0"))
                    if self.crosstalk and self.crosstalk[0] == p.tag:
                        victim = next(q for q in self.phones.values() if q.tag == self.crosstalk[1])
                        self._go(victim, f"app:{hit[0]}", self.open_ms)
            entry["missed"] = bool(missed)
        self.log.append(entry)
        return {"code": 0, "results": [{"id": p.id, "code": 0, "message": "ok"}]}

    def start_offline(self):
        self.offline_url = "mock://" + uuid.uuid4().hex + "/api"
        OFFLINE[self.offline_url] = self
        return self.offline_url

    def kernel_status(self):
        return {"code": 0, "input_protocol": 1, "input_leases_required": True, "mock": True,
                "allowed": list(self.phones),
                "receivers": [{"deviceid": p.id, "name": f"iMouse2-{p.tag}", "live": True,
                               "frames": 1, "receiver_state": "mirroring"} for p in self.phones.values()]}

    def dispatch_post(self, fun, data):
        if fun == "/input/acquire": return self._acquire(data)
        if fun == "/input/renew": return {"code": 0}
        if fun == "/input/release": return self._close(data, stop=False)
        if fun == "/input/stop": return self._close(data, stop=True)
        if fun == "/input/resume": return self._resume(data)
        if fun == "/input/status": return self._status()
        return self._input(fun, data)

    # -- HTTP
    def start(self) -> str:
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, body: bytes, ctype: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                u = urlparse(self.path)
                with mock.lock:
                    if u.path == "/api/kernel/status":
                        data = mock.kernel_status()
                        return self._send(json.dumps({"status": 200, "data": data}).encode(), "application/json")
                    if u.path == "/api/pic/screenshot":
                        pid = parse_qs(u.query)["id"][0]
                        return self._send(mock.phones[pid].frame(time.monotonic(), mock.rng), "image/bmp")
                self.send_error(404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fun, d = body["fun"], body.get("data") or {}
                with mock.lock:
                    data = mock.dispatch_post(fun, d)
                self._send(json.dumps({"status": 200, "message": "ok", "data": data}).encode(), "application/json")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.server.server_address[1]}/api"

    def stop(self) -> None:
        OFFLINE.pop(getattr(self, "offline_url", None), None)
        if self.server:
            self.server.shutdown()

"""One fresh-note trial on C24C. Note prep uses the release kernel API; the text does not.

Operator has already made a physical Home gesture. Sequence (same coordinates and waits as
fka_activate_trial.py, except the send):
  reset, move to Notes, down, 0.95 s, up, 1.0 s, frame, click New Note, 3.0 s, frame,
  arm B: one body click; arm A: no click (the shared 1.5 s is the matched wait),
  /input/release and confirm C24C is unowned,
  1.5 s, frame,
  one UIA call: set "Hi there", confirm the box, InvokePattern on Send text,
  wait for the activity line or 4.0 s, frame,
  UIA disconnect, connect, re-select C24C, then poll until C24C is unowned (3.0 s).
The runner's lease is gone before the button, so candidate-5's InputLeaseClient can acquire
C24C. That client keeps the lease (it renews). The trial does not finish until disconnect
has released it. C241 is never addressed.

  python fka_console_ab_runner.py frame TAG
  python fka_console_ab_runner.py trial TAG A|B --candidate-pid PID
  python fka_console_ab_runner.py --self-check
"""
import io, json, os, re, subprocess, sys, time, urllib.request

API = "http://127.0.0.1:9913/api/"
C24C, C241 = "86:1D:4A:04:2F:F6", "FE:A9:BC:D7:A0:44"
TEXT = "Hi there"
NOTES_ICON, NEW_NOTE = (192, 250), (212, 396)
BODY_CLICK = (250, 520)
SEND_WAIT = 4.0
OUT = os.environ.get("FKA_AB_OUT", r"C:/Users/joey_/Desktop/Claude Code/iMouseXP-2.0-evidence-archive/20261001-typing-mode-ab")
UIA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "console_uia.ps1")


class Http:
    def get(self, p):
        with urllib.request.urlopen(API + p, timeout=5) as r: return r.read()
    def post(self, fun, data):
        body = json.dumps({"fun": fun, "data": data})
        with urllib.request.urlopen(urllib.request.Request(API, body.encode(), {"Content-Type": "application/json"}), timeout=15) as r:
            res = json.loads(r.read())
        return body, res.get("data", res)
    def sleep(self, s): time.sleep(s)
    def save_frame(self, raw, tag):
        from PIL import Image
        img = Image.open(io.BytesIO(raw)); img.load(); img.save(os.path.join(OUT, tag + ".png"))


def phones(io_):
    return {p["id"]: p for p in json.loads(io_.get("input/status"))["data"]["phones"]}


def held(ins):
    return any(v["owned"] or v["stopped"] or v["active"] for v in ins.values())


def send_ok(line):
    return f"Send text: {len(TEXT)} characters in 1 chunk(s)" in line


class Uia:
    """Live candidate-5. keeps_lease: SequenceAsync retains the token until disconnect."""
    keeps_lease = True
    def __init__(self, pid):
        self.pid = str(int(pid))
    def _run(self, action, text=None, previous=None, timeout=None):
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", UIA,
               "-ProcessId", self.pid, "-Action", action]
        if text is not None: cmd += ["-Text", text]
        if previous is not None: cmd += ["-Previous", previous]
        if timeout is not None: cmd += ["-TimeoutSec", str(timeout)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0: raise RuntimeError(out.strip() or f"uia {action} failed")
        return out
    def activity(self):
        m = re.search(r"event=\[(.*)\]", self._run("log"), re.S)
        return m.group(1) if m else ""
    def send(self, text):
        out = self._run("send", text=text)
        m = re.search(r"value=\[(.*)\] length=", out)
        if not m: raise RuntimeError("no Send text box readback")
        im = re.search(r"invoked_ms=(\d+)", out)
        pressed = im and "pressed 'Send text'" in out
        return m.group(1), (int(im.group(1)) if pressed else None)
    def wait_send(self, timeout, previous):
        m = re.search(r"event=\[(.*)\]", self._run("wait", previous=previous, timeout=timeout), re.S)
        return m.group(1) if m else ""
    def release_lease(self):
        if "released" not in self._run("release-lease"): raise RuntimeError("candidate-5 did not disconnect")


def run(mode, tag, arm=None, io_=None, console=None, note=print):
    io_ = io_ or Http()
    def frame(t):
        io_.save_frame(io_.get("pic/screenshot?id=" + C24C + "&binary=true"), t); note(f"frame saved {t}.png")
    if mode == "frame": frame(tag); return 0
    if arm not in ("A", "B"): raise SystemExit("arm must be A or B")
    if console is None: raise SystemExit("trial needs a candidate console")
    st = json.loads(io_.get("kernel/status"))["data"]; r = {x["name"]: x for x in st["receivers"]}
    ins = phones(io_)
    note(f"[{tag}] arm {arm} preflight: C24C rx {r['iMouse2-C24C']['receiver_pid']} live={r['iMouse2-C24C']['live']}; "
         + "; ".join(f"{k[-5:]} owned={v['owned']} stopped={v['stopped']} gen={v['generation']}" for k, v in ins.items()))
    if not r["iMouse2-C24C"]["live"] or held(ins):
        note(f"[{tag}] REFUSED: C24C not live, or a phone is held; nothing sent"); return 2
    frame(f"{tag}-0-home")
    _, acq = io_.post("/input/acquire", {"id": C24C, "lease_ms": "60000"})
    if acq.get("code") != 0: note(f"[{tag}] REFUSED acquire {acq}"); return 2
    lease = acq["leases"][0]
    if lease.get("id") != C24C or not lease.get("token"):
        if lease.get("token"): io_.post("/input/release", {"id": lease.get("id") or C24C, "token": lease["token"]})
        note(f"[{tag}] REFUSED acquire lease {lease}"); return 2
    tok = lease["token"]
    released = False
    def cmd(fun, **kw):
        d = {"id": C24C, "token": tok}; d.update({k: str(v) for k, v in kw.items()})
        body, res = io_.post(fun, d)
        note(f"[{tag}] {fun} {json.dumps({k: v for k, v in d.items() if k not in ('id', 'token')})} -> code {res.get('code')}")
        if res.get("code") != 0: raise RuntimeError(f"{fun} failed: {res}")
        return body
    def release():
        _, rel = io_.post("/input/release", {"id": C24C, "token": tok})
        note(f"[{tag}] release code {rel.get('code')}")
        return rel.get("code")
    def console_clear():
        console.release_lease()
        waited = 0.0
        while True:
            ins = phones(io_)
            if ins[C241]["owned"] or ins[C241]["active"]:
                note(f"[{tag}] REFUSED: C241 held after console release"); return False
            if not ins[C24C]["owned"]:
                note(f"[{tag}] console release: C24C owned=False after {waited:.1f}s"); return True
            if waited >= 3.0:
                note(f"[{tag}] REFUSED: C24C still owned 3.0s after console release"); return False
            io_.sleep(0.2); waited += 0.2
    pressed = cleared = False
    def drop_console():
        nonlocal cleared
        if not pressed or cleared: return True
        cleared = True
        try: return console_clear()
        except Exception as e: note(f"[{tag}] console release failed: {e}"); return False
    try:
        cmd("/mouse/reset"); cmd("/mouse/move", x=NOTES_ICON[0], y=NOTES_ICON[1]); cmd("/mouse/down", button=1)
        io_.sleep(0.95); cmd("/mouse/up", button=1)
        io_.sleep(1.0); frame(f"{tag}-1-quickaction")
        cmd("/mouse/click", x=NEW_NOTE[0], y=NEW_NOTE[1])
        io_.sleep(3.0); frame(f"{tag}-2-fresh-note")
        if arm == "B": cmd("/mouse/click", x=BODY_CLICK[0], y=BODY_CLICK[1])
        else: note(f"[{tag}] arm A: no click; matched wait is the shared 1.5s after release")
        code = release()
        t_release = time.time()
        ins = phones(io_)
        note(f"[{tag}] after release: C24C owned={ins[C24C]['owned']} active={ins[C24C]['active']}; C241 owned={ins[C241]['owned']}")
        if code != 0 or held(ins):
            note(f"[{tag}] REFUSED: lease not clear (release code {code}); Send text not pressed"); return 2
        released = True
        io_.sleep(1.5); frame(f"{tag}-2b-before-send")
        previous = console.activity()
        got, invoke_ms = console.send(TEXT)
        note(f"[{tag}] box readback {got!r} bytes {got.encode().hex(' ')}")
        if got != TEXT or invoke_ms is None:
            note(f"[{tag}] REFUSED: box is not {TEXT!r}; Send text not pressed"); return 2
        pressed = True
        note(f"[{tag}] release-to-send {invoke_ms - int(t_release * 1000)} ms")
        note(f"[{tag}] invoked Send text on candidate-5")
        event = console.wait_send(SEND_WAIT, previous)
        note(f"[{tag}] activity: {event}")
        note(f"[{tag}] SUBMITTED via Send text button: {TEXT.encode().hex(' ')} ({TEXT!r}). "
             "A completion line means the console finished the send, not that iOS inserted the text")
        frame(f"{tag}-3-after-send")
        ins = phones(io_)
        note(f"[{tag}] after send: C24C owned={ins[C24C]['owned']} gen={ins[C24C]['generation']}; C241 owned={ins[C241]['owned']}")
        rc = 0
        if ins[C241]["owned"] or ins[C241]["active"]:
            note(f"[{tag}] C241 is held; this script never addresses it"); rc = 4
        elif ins[C24C]["owned"] and not console.keeps_lease:
            note(f"[{tag}] C24C still owned after send"); rc = 4
        elif ins[C24C]["owned"]:
            note(f"[{tag}] C24C owned after send by candidate-5 (it keeps the lease); runner token was released before the button")
        else:
            note(f"[{tag}] C24C unowned after send")
        if rc == 0 and (not send_ok(event) or event == previous):
            note(f"[{tag}] Send text did not report completion"); rc = 3
        if not drop_console(): return 4
        return rc
    finally:
        if not released:
            try: release()
            except Exception as e: note(f"[{tag}] release failed: {e}")
        if not drop_console(): note(f"[{tag}] console lease still held after the trial")


class Fake:
    """Records every call. Tracks lease ownership so a missed release is visible."""
    def __init__(self, held=None, fail_on=None, sticky=False):
        self.calls, self.frames, self.slept = [], [], 0.0
        self.owned = dict(held or {})
        self.fail_on, self.sticky, self.token = fail_on, sticky, "t"
    def get(self, p):
        self.calls.append(("GET", p, None))
        if p == "kernel/status":
            return json.dumps({"data": {"receivers": [{"name": "iMouse2-C24C", "receiver_pid": 1, "live": True},
                                                      {"name": "iMouse2-C241", "receiver_pid": 2, "live": True}]}}).encode()
        if p == "input/status":
            return json.dumps({"data": {"phones": [dict(id=i, owned=self.owned.get(i, False), stopped=False, active=False, generation=0)
                                                   for i in (C24C, C241)]}}).encode()
        if p.startswith("pic/screenshot"): return b"BMP"
        raise AssertionError("unexpected GET " + p)
    def post(self, fun, data):
        self.calls.append(("POST", fun, dict(data)))
        if fun == self.fail_on: return "{}", {"code": 3}
        if fun == "/input/acquire":
            self.owned[data["id"]] = True
            return json.dumps({"fun": fun, "data": data}), {"code": 0, "leases": [{"id": data["id"], "token": self.token}]}
        if fun == "/input/release":
            if not self.sticky: self.owned[data["id"]] = False
            return json.dumps({"fun": fun, "data": data}), {"code": 0}
        return json.dumps({"fun": fun, "data": data}), {"code": 0}
    def sleep(self, s): self.slept += s
    def save_frame(self, raw, tag): self.frames.append(tag)


class FakeConsole:
    keeps_lease = False
    def __init__(self, io, readback=None, steal=False):
        self.io, self.readback, self.steal = io, TEXT if readback is None else readback, steal
        self.pressed = False
    def activity(self):
        self.io.calls.append(("UIA", "activity", None))
        return "" if not self.pressed else f"12:00:00  Send text: {len(TEXT)} characters in 1 chunk(s)"
    def send(self, text):
        self.io.calls.append(("UIA", "send", text))
        if self.readback != text: return self.readback, None
        self.pressed = True
        if self.steal: self.io.owned[C24C] = True
        return self.readback, int(time.time() * 1000)
    def wait_send(self, timeout, previous):
        self.io.calls.append(("UIA", "wait", timeout))
        return self.activity() if self.pressed else previous
    def release_lease(self):
        self.io.calls.append(("UIA", "release-lease", None))
        self.io.owned[C24C] = False


def _code(text):
    return "\n".join(ln.split("#", 1)[0] for ln in text.splitlines())

def _fn(script, name):
    i = script.find(f"function {name}")
    if i < 0: return ""
    ends = [x for x in (script.find("\nfunction ", i + 1), script.find("\nswitch ", i + 1)) if x > 0]
    return _code(script[i:min(ends)] if ends else script[i:])

def _block(script, action):
    key = f"\n  '{action}'"
    i = script.find(key)
    if i < 0: return ""
    j = script.find("\n  '", i + len(key))
    return _code(script[i:j if j > 0 else None])

def reconnect_outcome(script):
    """Connect selects the first online phone. That is C241 unless release-lease Selects C24C."""
    block = _block(script, "release-lease")
    select = _fn(script, "Select-C24C")
    i = block.find("Invoke-Id 'ConnectButton'")
    picked = block.find("Select-C24C", i + 1) if i >= 0 else -1
    asserted = block.find("Assert-SelectedC24C", picked + 1) if picked >= 0 else -1
    match = _fn(script, "Is-C24CLabel") if "Is-C24CLabel" in select else select
    if i >= 0 and picked > i and asserted > picked and ".Select()" in select and "C24C" in match and "2F:F6" in match:
        return "C24C", []
    if i < 0: raise AssertionError("release-lease does not connect")
    return "C241", [C241]

def self_check():
    quiet = lambda s: None
    def trial(arm, tag, **kw):
        f = Fake(**{k: kw[k] for k in ("held", "fail_on", "sticky") if k in kw})
        c = FakeConsole(f, readback=kw.get("readback"), steal=kw.get("steal", False))
        if kw.get("keeps"): c.keeps_lease = True
        return f, c, run("trial", tag, arm, f, c, quiet)
    a, ca, ra = trial("A", "A1")
    b, cb, rb = trial("B", "B1")
    assert ra == 0 and rb == 0
    posts = lambda f: [(c[1], {k: v for k, v in c[2].items() if k != "token"}) for c in f.calls if c[0] == "POST"]
    pa, pb = posts(a), posts(b)
    # 1. Only C24C is posted to. C241 appears in status reads only.
    assert all(d.get("id") == C24C for _, d in pa + pb) and not any(d.get("id") == C241 for _, d in pa + pb)
    # 2. The runner never sends a key. One UIA send carries Hi there and the button.
    for f, c in ((a, ca), (b, cb)):
        assert not [x for x in f.calls if x[0] == "POST" and str(x[1]).startswith("/key/")]
        assert [x[1:] for x in f.calls if x[0] == "UIA" and x[1] == "send"] == [("send", TEXT)]
        assert c.pressed
    assert TEXT.encode().hex() == "4869207468657265"
    # 3. Arms differ by exactly one body click, after New Note.
    extra = [x for x in pb if x not in pa or pb.count(x) > pa.count(x)]
    assert extra == [("/mouse/click", {"id": C24C, "x": str(BODY_CLICK[0]), "y": str(BODY_CLICK[1])})], extra
    assert [x for x in pb if x != extra[0]] == pa
    # 4. Same waits, same frames. Release is verified unowned before the box is set.
    assert a.slept == b.slept == 0.95 + 1.0 + 3.0 + 1.5
    assert [f[3:] for f in a.frames] == [f[3:] for f in b.frames] == [
        "0-home", "1-quickaction", "2-fresh-note", "2b-before-send", "3-after-send"]
    for f in (a, b):
        seq = [(c[0], c[1]) for c in f.calls]
        rel = seq.index(("POST", "/input/release"))
        assert seq[rel + 1] == ("GET", "input/status")
        assert seq.index(("UIA", "send")) > rel + 1
        assert seq.index(("UIA", "release-lease")) > seq.index(("UIA", "send"))
        assert not f.owned[C24C] and not f.owned.get(C241)
        assert ("UIA", "wait", SEND_WAIT) in [(c[0], c[1], c[2]) for c in f.calls if c[0] == "UIA"]
    # 5. A held phone sends nothing.
    for who in ({C24C: True}, {C241: True}):
        f, c, rc = trial("A", "R", held=who)
        assert rc == 2 and not [x for x in f.calls if x[0] in ("POST", "UIA")]
    # 6. A mid-trial mouse failure still releases, and the button is never pressed.
    f = Fake(fail_on="/mouse/up"); c = FakeConsole(f)
    try: run("trial", "F", "B", f, c, quiet); raise AssertionError("expected failure")
    except RuntimeError: pass
    assert [x[1] for x in f.calls if x[0] == "POST"][-1] == "/input/release"
    assert not [x for x in f.calls if x[0] == "UIA"] and "/key/sendkey" not in [x[1] for x in f.calls]
    # 7. Release that leaves the phone owned does not press Send text.
    f, c, rc = trial("A", "S", sticky=True)
    assert rc == 2 and not [x for x in f.calls if x[0] == "UIA"]
    # 8. A wrong box readback does not press.
    f, c, rc = trial("A", "W", readback="Hithere")
    assert rc == 2 and not c.pressed and [x[1] for x in f.calls if x[0] == "UIA"] == ["activity", "send"]
    # 9. After send, an unexpected owner (this console does not keep a lease) is not ignored.
    f, c, rc = trial("B", "O", steal=True)
    assert rc == 4 and "3-after-send" in f.frames[-1] and not f.owned[C24C]
    # 10. A console that keeps its lease through the send still leaves C24C unowned before return.
    notes = []
    f = Fake(); c = FakeConsole(f, steal=True); c.keeps_lease = True
    assert run("trial", "K", "A", f, c, notes.append) == 0 and not f.owned[C24C]
    assert any(re.fullmatch(r"\[K\] release-to-send -?\d+ ms", s) for s in notes)
    assert ("UIA", "release-lease", None) in [(x[0], x[1], x[2]) for x in f.calls if x[0] == "UIA"]
    # 11. Trial 2 is not refused by trial 1's retained lease.
    shared = Fake()
    c1 = FakeConsole(shared, steal=True); c1.keeps_lease = True
    assert run("trial", "A1", "A", shared, c1, quiet) == 0 and not shared.owned[C24C]
    c2 = FakeConsole(shared, steal=True); c2.keeps_lease = True
    assert run("trial", "B1", "B", shared, c2, quiet) == 0 and not shared.owned[C24C]
    acq = [i for i, c in enumerate(shared.calls) if c[0] == "POST" and c[1] == "/input/acquire"]
    rels = [i for i, c in enumerate(shared.calls) if c[0] == "UIA" and c[1] == "release-lease"]
    assert len(acq) == 2 and len(rels) == 2 and rels[0] < acq[1]
    class Boom(FakeConsole):
        def wait_send(self, timeout, previous):
            raise RuntimeError("wait failed")
    f = Fake(); c = Boom(f, steal=True); c.keeps_lease = True
    try: run("trial", "X", "A", f, c, quiet); raise AssertionError("expected wait failure")
    except RuntimeError as e:
        assert "wait failed" in str(e)
    assert not f.owned[C24C] and ("UIA", "release-lease", None) in [(x[0], x[1], x[2]) for x in f.calls if x[0] == "UIA"]
    # 12. Reconnect auto-selects C241. UIA Selects C24C; a C241 lease is refused and never posted.
    script = open(UIA, encoding="utf-8").read()
    assert reconnect_outcome(script) == ("C24C", [])
    assert reconnect_outcome(script.replace(".Select()", ".Nope()")) == ("C241", [C241])
    class Reconnect(FakeConsole):
        def __init__(self, io, src):
            super().__init__(io); self.src, self.selected = src, None
        def release_lease(self):
            super().release_lease()
            self.selected, leases = reconnect_outcome(self.src)
            for phone in leases: self.io.owned[phone] = True
            if self.selected != "C24C": raise RuntimeError(f"selected phone is {self.selected}, not C24C")
    class LeasesC241(FakeConsole):
        def release_lease(self):
            super().release_lease(); self.io.owned[C241] = True
    f = Fake(); c = Reconnect(f, script)
    assert run("trial", "Q", "A", f, c, quiet) == 0 and c.selected == "C24C" and not f.owned.get(C241)
    assert not any(d.get("id") == C241 for _, d in posts(f))
    f = Fake(); c = LeasesC241(f)
    assert run("trial", "Z", "A", f, c, quiet) == 4 and f.owned[C241]
    assert not any(d.get("id") == C241 for _, d in posts(f))
    print("self-check: 12 checks passed (mock transport; nothing sent)")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]: self_check(); sys.exit(0)
    args, pid = [], None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--candidate-pid": pid = sys.argv[i + 1]; i += 2
        else: args.append(sys.argv[i]); i += 1
    if not args or args[0] not in ("frame", "trial"): raise SystemExit("usage: frame TAG | trial TAG A|B --candidate-pid PID")
    if args[0] == "trial" and not pid: raise SystemExit("trial requires --candidate-pid PID")
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "run.txt"), "a", encoding="utf-8")
    def note(s):
        t = time.time(); line = time.strftime("%H:%M:%S", time.localtime(t)) + ".%03d " % (int(t * 1000) % 1000) + s
        print(line, flush=True); log.write(line + "\n"); log.flush()
    sys.exit(run(args[0], args[1], args[2] if len(args) > 2 else None, console=Uia(pid) if pid else None, note=note))

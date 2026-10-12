"""One fresh-note trial on C24C through the release kernel API, FKA On (lease held for the trial only).
Extends the 27 Sep fka_trial.py (evidence archive 20260927-fka-comparison) by one condition; every other
step, coordinate and wait is that script's.

Operator has already made a physical Home gesture. Sequence:
reset, move to Notes icon, down, 0.95 s, up (long press), 1.0 s, frame, click New Note, 3.0 s, frame,
  arm A: wait 1.5 s, frame                      (no input)
  arm B: click once inside the empty note body, wait 1.5 s, frame
/key/sendkey key="Hi there", 4.0 s, frame, release.
Both arms send the same text and nothing else: no software Home, no fn_key, no space on its own.

  python fka_activate_trial.py frame TAG
  python fka_activate_trial.py trial TAG A|B
  python fka_activate_trial.py --self-check        (mock transport; sends nothing)
"""
import io, json, os, sys, time, urllib.request

API = "http://127.0.0.1:9913/api/"
C24C, C241 = "86:1D:4A:04:2F:F6", "FE:A9:BC:D7:A0:44"
TEXT = "Hi there"
NOTES_ICON, NEW_NOTE = (192, 250), (212, 396)      # 27 Sep positions; Notes still at (192, 255) on 1 Oct
BODY_CLICK = (250, 520)                            # inside the empty text view, clear of title line and toolbar
OUT = os.environ.get("FKA_AB_OUT", r"C:/Users/joey_/Desktop/Claude Code/iMouseXP-2.0-evidence-archive/20261001-typing-mode-ab")


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


def run(mode, tag, arm=None, io_=None, note=print):
    io_ = io_ or Http()
    def frame(t):
        io_.save_frame(io_.get("pic/screenshot?id=" + C24C + "&binary=true"), t); note(f"frame saved {t}.png")
    if mode == "frame": frame(tag); return 0
    if arm not in ("A", "B"): raise SystemExit("arm must be A or B")
    st = json.loads(io_.get("kernel/status"))["data"]; r = {x["name"]: x for x in st["receivers"]}
    ins = {p["id"]: p for p in json.loads(io_.get("input/status"))["data"]["phones"]}
    note(f"[{tag}] arm {arm} preflight: C24C rx {r['iMouse2-C24C']['receiver_pid']} live={r['iMouse2-C24C']['live']}; "
         + "; ".join(f"{k[-5:]} owned={v['owned']} stopped={v['stopped']} gen={v['generation']}" for k, v in ins.items()))
    # Refuse if C24C is not free, or if any controller holds any phone (27 Sep ON4: the installed console held C24C).
    if not r["iMouse2-C24C"]["live"] or any(v["owned"] or v["stopped"] or v["active"] for v in ins.values()):
        note(f"[{tag}] REFUSED: C24C not live, or a phone is held; nothing sent"); return 2
    frame(f"{tag}-0-home")
    _, acq = io_.post("/input/acquire", {"id": C24C, "lease_ms": "60000"})
    if acq.get("code") != 0: note(f"[{tag}] REFUSED acquire {acq}"); return 2
    tok = acq["leases"][0]["token"]
    def cmd(fun, **kw):
        d = {"id": C24C, "token": tok}; d.update({k: str(v) for k, v in kw.items()})
        body, res = io_.post(fun, d)
        note(f"[{tag}] {fun} {json.dumps({k: v for k, v in d.items() if k not in ('id', 'token')})} -> code {res.get('code')}")
        if res.get("code") != 0: raise RuntimeError(f"{fun} failed: {res}")
        return body
    try:
        cmd("/mouse/reset"); cmd("/mouse/move", x=NOTES_ICON[0], y=NOTES_ICON[1]); cmd("/mouse/down", button=1)
        io_.sleep(0.95); cmd("/mouse/up", button=1)
        io_.sleep(1.0); frame(f"{tag}-1-quickaction")
        cmd("/mouse/click", x=NEW_NOTE[0], y=NEW_NOTE[1])
        io_.sleep(3.0); frame(f"{tag}-2-fresh-note")
        if arm == "B": cmd("/mouse/click", x=BODY_CLICK[0], y=BODY_CLICK[1])
        io_.sleep(1.5); frame(f"{tag}-2b-before-send")
        body = cmd("/key/sendkey", key=TEXT)
        sent = json.loads(body)["data"]["key"]
        note(f"[{tag}] SUBMITTED key bytes: {sent.encode().hex(' ')} ({sent!r}). Code 0 means HID writes completed, not insertion")
        io_.sleep(4.0); frame(f"{tag}-3-after-send")
    finally:
        _, rel = io_.post("/input/release", {"id": C24C, "token": tok}); note(f"[{tag}] release code {rel.get('code')}")
        ins = {p["id"]: p for p in json.loads(io_.get("input/status"))["data"]["phones"]}
        note(f"[{tag}] after: C24C owned={ins[C24C]['owned']} gen={ins[C24C]['generation']}; C241 owned={ins[C241]['owned']}")
    return 0


class Fake:
    """Records every call. Answers like the release kernel for the endpoints this script uses."""
    def __init__(self, held=None, fail_on=None):
        self.calls, self.frames, self.slept, self.held, self.fail_on = [], [], 0.0, held or {}, fail_on
    def get(self, p):
        self.calls.append(("GET", p, None))
        if p == "kernel/status":
            return json.dumps({"data": {"receivers": [{"name": "iMouse2-C24C", "receiver_pid": 1, "live": True},
                                                      {"name": "iMouse2-C241", "receiver_pid": 2, "live": True}]}}).encode()
        if p == "input/status":
            return json.dumps({"data": {"phones": [dict(id=i, owned=self.held.get(i, False), stopped=False, active=False, generation=0)
                                                   for i in (C24C, C241)]}}).encode()
        if p.startswith("pic/screenshot"): return b"BMP"
        raise AssertionError("unexpected GET " + p)
    def post(self, fun, data):
        self.calls.append(("POST", fun, dict(data)))
        if fun == self.fail_on: return "{}", {"code": 3}
        res = {"code": 0, "leases": [{"id": C24C, "token": "t"}]} if fun == "/input/acquire" else {"code": 0}
        return json.dumps({"fun": fun, "data": data}), res
    def sleep(self, s): self.slept += s
    def save_frame(self, raw, tag): self.frames.append(tag)


def self_check():
    quiet = lambda s: None
    a, b = Fake(), Fake()
    assert run("trial", "A1", "A", a, quiet) == 0 and run("trial", "B1", "B", b, quiet) == 0
    posts = lambda f: [(c[1], {k: v for k, v in c[2].items() if k != "token"}) for c in f.calls if c[0] == "POST"]
    pa, pb = posts(a), posts(b)
    # 1. Only C24C is ever addressed.
    assert all(d.get("id") == C24C for _, d in pa + pb) and C241 not in json.dumps(pa + pb)
    # 2. Identical text, sent once per trial, and no other key of any kind.
    for p in (pa, pb):
        keys = [d for f, d in p if f.startswith("/key/")]
        assert keys == [{"id": C24C, "key": TEXT}], keys
    assert TEXT.encode().hex() == "4869207468657265"
    # 3. The arms differ by exactly one body click, inserted after the New Note click.
    extra = [x for x in pb if x not in pa or pb.count(x) > pa.count(x)]
    assert extra == [("/mouse/click", {"id": C24C, "x": str(BODY_CLICK[0]), "y": str(BODY_CLICK[1])})], extra
    assert [x for x in pb if x != extra[0]] == pa
    # 4. Same waits and the same frames in both arms.
    assert a.slept == b.slept and [f[3:] for f in a.frames] == [f[3:] for f in b.frames]
    # 5. Refuses when any phone is held, including C241 or C24C by the installed console; sends nothing.
    for held in ({C24C: True}, {C241: True}):
        f = Fake(held=held); assert run("trial", "R", "A", f, quiet) == 2 and not [c for c in f.calls if c[0] == "POST"]
    # 6. A failure mid-trial still releases the lease, and the text is never sent after it.
    f = Fake(fail_on="/mouse/up")
    try: run("trial", "F", "B", f, quiet); raise AssertionError("expected failure")
    except RuntimeError: pass
    funs = [c[1] for c in f.calls if c[0] == "POST"]
    assert funs[-1] == "/input/release" and "/key/sendkey" not in funs
    print("self-check: 6 checks passed (mock transport; nothing sent)")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-check"]: self_check(); sys.exit(0)
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, "run.txt"), "a", encoding="utf-8")
    def note(s):
        t = time.time(); line = time.strftime("%H:%M:%S", time.localtime(t)) + ".%03d " % (int(t * 1000) % 1000) + s
        print(line, flush=True); log.write(line + "\n"); log.flush()
    sys.exit(run(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None, note=note))

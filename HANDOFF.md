# iMouse 2.0 — context handoff

Written 10 September 2026. Everything below was measured on this machine against the real
rack, not inferred. Where a number appears, it came from a run recorded in `qa/`.

---

## What this project is

A Windows replacement console for **iMouse XP International Edition**, the vendor software
that drives a rack of iPhones ("phone farm"). The 2.0 console shows a live view of one
phone large, every other phone as a small tile beside it, and lets one phone's clicks and
drags be mirrored to all the others.

Two deliverables exist:

| | what it is | status |
|---|---|---|
| `release/iMouse2/iMouse2.exe` | the real app — .NET 8 WPF | **current**, this is the one being developed |
| `console/index.html` | a browser console built earlier in the project | works, no longer the focus |

---

## The one thing to understand first: two independent channels

This explains most of the project's surprises, and it is the thing to hold onto.

```
CONTROL   PC ──USB──> WCH HID board ──Lightning──> iPhone
VIDEO     iPhone ──Wi-Fi──> AirPlay ──> PC
```

They are **completely separate paths**. Either can fail while the other works perfectly:

- A phone can show a flawless live picture and ignore every tap (board unbound, or the
  pointer stuck — see below).
- A phone can accept every tap and show nothing (not mirroring).

So the console always reports control status and video status **separately** per phone.
Any bug report of the form "phone X isn't working" must be split along this line first.

Full detail, with measurements, is in **`analysis/HARDWARE.md`** — read that before
touching anything timing- or protocol-related. It is the most valuable file in the repo.

---

## Architecture

`src/iMouse.Console/` — about 3,600 lines, no third-party packages.

| file | what lives there |
|---|---|
| `MainWindow.xaml.cs` (2316) | everything: frame pumps, gestures, mirroring, binding, wall, tests |
| `MainWindow.xaml` (344) | layout — master top-left, action strip, wall, status bar, drawer |
| `ApiClient.cs` (291) | `Device`, `Board`, HTTP client, `CoordinateMapper`, `FrameBuffer` |
| `LiveFrame.cs` (302) | BMP decode + row-flip + downscale, `RateMeter`, `JitterMeter`, `FrameRegion` |
| `SelfTests.cs` (319) | mock HTTP transport (`TestHandler`) + the pure-logic checks |
| `PhoneWall.cs` (95) | `Thumb` — one wall tile's view model |
| `Theme.cs` (62) | light/night palette swap |

`MainWindow.xaml.cs` is sectioned by `// ---- name ----` comments: shell, live view,
pointer input, control-board binding, master/mirror, the wall.

### How a frame reaches the screen

```
poll /pic/screenshot?binary=true  (raw BMP, ~2 ms)
  └─ SameAsPrevious? → discard, poll again          most polls land here
  └─ LiveFrame.Prepare  on a worker thread          row-flip, optional downscale
      └─ Dispatcher.BeginInvoke(Render)             present now, not on the next tick
          └─ WriteableBitmap.WritePixels            one copy, no allocation
```

Two rules this path enforces, both learned the hard way:

1. **Never derive the poll interval from measured frame gaps.** It feeds back on itself:
   one missed frame widens the gap → longer sleep → more misses. Measured decaying from
   23 fps to 16.5.
2. **Never present on `CompositionTarget.Rendering`.** It fires on WPF's schedule, so a
   frame arriving just after a tick waits up to 28 ms. Posting at `Render` priority on
   arrival took present-interval spread from 9.5 ms to 0.5 ms.

### How an input reaches the phone

Every input endpoint accepts a **comma-separated id list**, so mirroring to N phones is
one request, not N. `InputTargetIds()` returns `master,follower1,follower2…`; `Followers()`
excludes phones that are offline, have no working board, or have a different screen size
(an identical coordinate on a different-sized screen is not the same place).

A drag is a real `/mouse/down` → streamed `/mouse/move` → `/mouse/up`, run on the thread
pool. It is **not** replayed as a canned swipe.

---

## Measured facts that constrain every design decision

All measured on this rack, console closed unless stated.

### Raw BMP beats JPEG by 20×

| | requests/sec | latency p50 |
|---|---|---|
| `binary=true` (raw BMP, 1.6 MB) | 84 | **2.0 ms** |
| `+ jpg=true` (96 KB) | **21 — a hard cap** | **40.5 ms** |

The kernel re-encodes for JPEG. On loopback it is strictly worse, thumbnails included.

### Phones are independent — there is no shared bottleneck

- Two phones polled concurrently, flat out: 83 and 85 req/s, p50 3 ms — same as either alone.
- Ten concurrent pollers: 512 req/s total, p50 3 ms.
- Streaming `/mouse/move` while polling frames: **98.8** req/s vs 78.7 with no input at all.

An earlier belief recorded in this project — that wall thumbnails "starved" the master,
30 fps falling to 19.8 — **was wrong**. That measurement was reading the source rate.
A clean 3-run A/B proved the wall is free:

```
wall off       master 17.7 fps   p50 31.9 ms   tiles  0.0 fps
wall at 30fps  master 17.6 fps   p50 32.3 ms   tiles 11.8 fps
```

### The board *walks* the pointer: ~0.6 ms per pixel

| jump | latency | | jump | latency |
|---|---|---|---|---|
| 2 px | 1.0 ms | | 400 px | 250 ms |
| 100 px | 78 ms | | 1000 px | **592 ms** |

Identical for one phone or ten — the board walks every phone in an id list in parallel.

Consequences:
- **A move's latency is meaningless without its distance.** A p50 of 3.7 ms with a max of
  264 ms looks like jitter; it is the distance distribution.
- **Coalescing a drag is free.** Sending only the newest position skips no pixels — the
  board traverses the path either way. Verified: the same stroke as 14 steps, 7 steps and
  2 jumps produced identical results on both phones.
- **A full-height swipe is slow by construction** (~580 ms), and iOS may read it as a drag
  rather than a flick. Prefer the short axis.

### The source rate is content-dependent and differs per phone

Under continuous motion, polled flat out, **console closed**:

| phone | new frames/sec |
|---|---|
| 192.168.4.68 | 28.9 |
| 192.168.4.27 | **4.5** |

Two identical iPhone XRs, same iOS build. The second one's AirPlay stream is genuinely
~5× slower, and it is just as slow when it is the only phone being polled. **This is not
fixable in software** — it is that phone's Wi-Fi link. The vendor's own software hits the
same wall. Each tile therefore shows its own live fps, so a slow phone reads as a slow
phone and not a slow app.

---

## Traps that cost real time — do not re-enter them

### Never compare screenshots byte-for-byte

A mirrored screen never repeats exactly — the clock, the AirPlay encoder and wallpaper
parallax all move. An MD5 comparison reports "reacted" for an **untouched** phone as
reliably as for a tapped one. This produced a wrong conclusion once in this project.

Use **mean absolute pixel difference against an idle control**. Idle measures ~0.02;
a real reaction measures 20–160.

### Normalise phone state before comparing

Phones drift onto different home pages, and **the two XRs in this rack have entirely
different home screens and wallpapers** — the same coordinate is Clock on one and
Reminders on the other. Two Home presses (first leaves the app, second returns to page
one) before any measurement. Even then, one coordinate is only a fair probe if both
phones have the same icon there.

### Never probe with a state-dependent gesture

Watching for a home-page flip or an app to open is unreliable: a phone already on its
last page, or an edge gesture iOS declines, is indistinguishable from mirroring having
dropped that phone. Probe instead with:

- **what was sent** — assert the delivered coordinate and the id list directly, or
- **where the pointer ended up** — mean pixel difference in a small box around the
  stroke's final coordinate. Measured 1.4–9.8 against an idle floor of 0.02. A whole-frame
  diff cannot see a pointer dot a few pixels across; this is why auto-bind uses a box.

### A phone can silently stop accepting taps

Measured: a phone took `/mouse/move` normally — the pointer visibly followed — but **every
`/mouse/click` did nothing**, on its own and mirrored alike. `/mouse/up` did not fix it, so
it is the pointer's own state, not a stuck button. Hardware keys kept working throughout,
so the phone looks perfectly healthy. **`/mouse/reset` clears it, permanently.**

The console now resets the pointer across the whole target set whenever the mirror set
changes. If a phone ever appears to be "skipped by mirroring", try Reset first.

### Measurement hygiene

- A **still screen produces almost no new frames**, so benchmarking one measures nothing.
  Drive continuous motion. That is what `--wall-test` does.
- `gdigrab` captures whichever window is on top — one run read 0.1 fps because the vendor
  console was covering the app.
- A 30 Hz sampler cannot resolve a 30 Hz stream (~90% ceiling).
- This display is at 150% DPI.

---

## Testing

Five modes, all writing JSON/PNG into `qa/` beside the executable:

| mode | what it does | needs the rack? |
|---|---|---|
| `--self-test` | **75 checks** — pure logic over a mock HTTP transport | no |
| `--ui-test` | **76 checks** — drives real handlers against mock devices, renders the UI | no |
| `--smoke-test` | connects to the live service read-only | yes |
| `--fps-test` | master frame rate, jitter, GC cost | yes |
| `--wall-test` | master + tiles under continuous motion, tile geometry stability | yes |
| `--mirror-test` | end-to-end mirrored tap and stroke, with pixel-difference proof | yes |

`--ui-test` is the valuable one. `TestHandler` in `SelfTests.cs` serves a five-device
fixture (TEST:01…05) with deliberate variety: offline, no board, and one phone at a
different screen size so mirroring exclusion can be asserted.

The gesture stages take a plain `Point` rather than a mouse event — `BeginGesture`,
`TrackGesture`, `EndGestureAsync` — specifically so tests can drive the exact path a real
press follows. Synthesising WPF mouse events is not practical.

### Build and deploy

```bash
dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o release/iMouse2-net
```

Then copy five files (`iMouse2.exe`, `.dll`, `.deps.json`, `.runtimeconfig.json`, `.pdb`)
from `release/iMouse2-net/` to `release/iMouse2/` and relaunch. Build to the staging
folder, test there, deploy only when green — the app locks its own files while running.

The .NET 8 SDK is at `C:\Program Files\dotnet\dotnet.exe`.

---

## Current state — all verified 10 Sep 2026

- **75 self-tests, 76 UI checks passing.**
- Live view at source parity; frame pacing steady at ~32 ms p50.
- Wall tiles at 11–18 fps each, costing the master nothing.
- Allocation **488 MB/s → 2.9 MB/s**; gen-2 collections **496 per 8 s → 0–1**. (Every
  1.6 MB frame was a Large Object Heap allocation; the pump polls far more often than the
  source produces frames, so nearly all of them were discarded immediately. Fixed by
  reusing buffers — `FrameBuffer` / `ScreenshotIntoAsync`.)
- Tile geometry stable: one distinct width, one distinct position over a 10 s run.
- Mirrored tap and mirrored stroke both verified reaching both phones.
- **Long press added 13 Sep 2026.** A stationary press held ≥250 ms promotes into the existing
  down/move/up drag loop (`HoldWatchAsync`), so the phone's button is down while the mouse is
  held and up on release; hold-then-move becomes a drag. 7 new UI checks (83 total). Verified
  on the rack: `/mouse/down`, hold 1.5 s, `/mouse/up` on the Tinder icon of iPhone XR 2F:F6
  produced the iOS icon context menu (mean pixel diff 51 mid-hold, persisting after release,
  cleared by Home). **The first attempt did nothing (diff 0.14) because the phone was in the
  stuck-click state; `/mouse/reset` fixed it** - the same trap as taps, so Reset first if a
  hold does nothing.

### Features working

Live master view · click to tap · drag to swipe (real down/move/up) · hold ≥250 ms to
long-press (button down while held, up on release; hold-then-move drags, matching the vendor
console) · hover moves the
phone's own pointer · master/mirror mode over multi-id requests · select-all · board
binding and **auto-bind** (identifies a board by moving its pointer and watching which
screen reacts — 10.56/3.94 signal vs 0.00 for wrong boards) · Reset and Home strip ·
light/night themes · size sliders for master and tiles · per-tile fps readout.

### Rig state right now

Both phones report `state: 0` (**not mirroring**) and the board list is **empty**.
`IMService.exe` is running but `IMConsole.exe` is not. Earlier today, with IMConsole
running, both phones were `state: 1` and 19 boards were listed. **Start the vendor console
first** to bring the rack back up before testing.

---

## Open items

**Stale docs.** `README.md` and `TESTING.md` describe an app from several iterations ago —
"1, 2, or 5 frames per second", "40 checks", "17 interaction checks", an older UI. They
are misleading as written. Worth a rewrite; deliberately not done unasked.

**Unanswered questions** put to the user and never resolved:
- Whether to add the rest of the vendor's vertical strip (Restart, Lock, Ctrl Bar, KB,
  Cast, App, IME, Disc). Currently only Reset and Home.
- Whether the device-list checkbox reads clearly as "select mirror followers".

**Unverified:**
- Whether **Reset** actually corrects a *drifted* pointer. Confirmed only that it clears
  the stuck-click state and returns code 0 everywhere.
- Whether the wall holds up with a real rack of 10+. Only two phones were ever attached.
  The aggregate floor (`period = max(tilePeriod, tiles × 12 ms)`) is untested at scale.

**Blocking full independence from `IMService.exe`:** the vendor HID report format. The
descriptor is vendor-defined and the 9-byte layout is opaque. Decoding it needs a USB
capture (USBPcap/Wireshark) of known actions. Re-implementing the AirPlay receiver would
also be required. Neither blocks console work — the documented API covers video and every
input.

**Minor:** the search box has no placeholder; the group filter is `Visibility="Collapsed"`.

---

## Handling notes

- **`C:\iMouseXP\IMService.json` contains the user's account password** as trivially
  reversible hex obfuscation — recoverable from that file alone. Do not print it, do not
  carry the scheme forward, keep `build/` excluded by `.gitignore`.
- **Do not minimise or resize the vendor console during screen-capture tests.** Doing so
  repeatedly left it rendering black and unable to recover; it needed restarting. The
  kernel was untouched, but avoid the situation.
- This project is **not a git repository**.
- Never point the app's write paths at `release/iMouse2/` while it is running.

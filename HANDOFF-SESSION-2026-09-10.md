# iMouse 2.0 — session handoff, 2026-09-10

Gesture mirroring, wall-thumbnail performance, and the hardware characteristics uncovered
while fixing them.

> **Scope note.** This records one working session (2026-09-10). The repository has moved
> on since — see the root `HANDOFF.md` (2026-09-13) and later notes for anything after this
> date. Everything below was measured on the live rack on the day; where a number appears,
> it was measured, not estimated.

---

## 1. The rack as it stood

Two iPhone XRs, both mirroring, both bound to control boards:

| device id | ip | board uid | mirror geometry | iOS |
|---|---|---|---|---|
| `FE:A9:BC:D7:A0:44` | 192.168.4.68 | `C241BFBD` | 500 × 1080 | 18.7.10 |
| `8A:23:B5:71:35:8D` | 192.168.4.27 | `C214BEBD` | 500 × 1080 | 18.7.10 |

Vendor kernel on `127.0.0.1:9911`. 19 boards enumerated, 14 with a phone attached
(`state: 2`).

Two independent channels, and either can fail alone:

- **control** — PC → USB → WCH HID board → Lightning → iPhone
- **video** — iPhone → Wi-Fi → AirPlay → PC

---

## 2. Three problems solved, in order

### 2.1 "Mirroring actions (clicks and drags) isn't working as intended"

Four distinct causes. The first three were in the gesture handler; the fourth was the real
one, and it was not in the software at all.

**(a) A stroke leaving the picture froze mid-way.** `MapPreview` returns null the instant
the cursor leaves the phone bitmap, and that test sat *before* the drag block in
`Preview_Move`. A swipe running past the edge stopped at the last inside point. Worse: a
fast flick that left the picture before crossing the 4 px drag threshold started no drag
**and** then fell through to a tap path that also rejected the point — so the whole gesture
sent nothing at all.

Fix: `CoordinateMapper.MapClamped` (pulls an outside point to the nearest edge) plus
`MapPreviewClamped`, and `Preview_Move` restructured so an in-progress gesture is handled
*first*, using the clamping mapper.

**(b) A tap landed where the button came up, not where it went down.** A few pixels of
drift moved the tap, and a release a hair outside the picture sent nothing. Fixed to use
the press point recorded in `_gesture`.

**(c) Hover tracking addressed only the master.** Followers' pointers sat wherever they had
been left, so the phones were not in the same state when the click arrived.
`PumpPointerAsync` now addresses `InputTargetIds()`.

**(d) The real cause — a phone can silently stop accepting taps.** The follower took
`/mouse/move` normally (the pointer visibly followed) but **every** `/mouse/click` did
nothing — and it failed identically when addressed on its own, so mirroring was never at
fault.

Mean absolute pixel difference, whole frame, 0–255. An untouched phone reads ~0.02:

| action | master | stuck follower |
|---|---|---|
| idle, no input | 0.03 | 0.03 |
| click, that phone alone | 0.02 | **0.09** |
| click, both in one request | 162.66 | **0.03** |
| click after `/mouse/reset` | — | **141.96** |
| `/key/sendkey Home` while stuck | — | 142.15 |

Three things follow:

- `/mouse/up` did **not** clear it — so it is the pointer's own state, not a button left
  down by an interrupted drag.
- Hardware keys keep working while the pointer is stuck. The board and cable are fine; a
  phone in this state looks alive in every other way.
- `/mouse/reset` clears it and it **stays** cleared.

To an operator this reads exactly like "mirroring is broken": the master obeys and one
phone in the rack quietly does nothing.

**Fix:** `ResetJoinedPointers()`, called at the end of `UpdateControls()`, sends
`/mouse/reset` to the whole target set whenever the mirror set changes — a phone ticked,
unticked, or made master. One request at those moments, nothing while working. The manual
**Reset** button remains for a phone that drifts mid-session.

### 2.2 "A lot of lag … the visual display is very lagged behind for the smaller phones"

Three causes, two severe.

**(a) The wall was 1 fps by construction.** One loop walked the phones in turn, fetched each
as JPEG, then slept a full second. Both halves were expensive:

| | requests/sec | latency p50 | bytes |
|---|---|---|---|
| raw BMP, flat out | 84 | 12.7 ms | 1.6 MB |
| raw BMP, paced at 50 ms | 20 | **2.0 ms** | 1.6 MB |
| JPEG, flat out | **21 (hard cap)** | **40.5 ms** | 96 KB |

JPEG makes the kernel re-encode: twenty times the latency, and a cap of ~21 requests a
second per stream. The wall was paying that for pictures it then shrank to thumbnails.
Walking phones in turn also means the last tile in a rack of ten waits for the other nine.

Phones are independent — there is no shared bottleneck to design around:

- two phones' raw frames polled concurrently and flat out: 83 and 85 req/s, p50 3 ms each —
  the same as either alone
- ten concurrent pollers: 512 req/s total, p50 3 ms, worst p95 142 ms

Fix: raw frames, **one independent pump per phone** (`TilePumpAsync`), shrunk to tile size
on a worker thread by whole-block averaging (`LiveFrame.Prepare(span, maxHeight)` →
`Reduce`), duplicate frames skipped entirely, a `SemaphoreSlim(3)` bounding in-flight
fetches, and an aggregate floor (`period = max(_tilePeriodMs, tiles * 12)`) so a large rack
degrades gracefully instead of saturating the link.

**(b) 488 MB/s allocated, 496 gen-2 collections every 8 seconds.** This was the master's
"slight" lag. Every screenshot is ~1.6 MB — over the 85 KB threshold at which .NET puts an
array on the Large Object Heap — and the pump polls far more often than the source produces
frames, so nearly every allocation was a large object discarded microseconds later.

Measured inside the running app, one phone on screen, one tile on the wall:

| | before | after |
|---|---|---|
| allocated | 488 MB/s | **2.9 MB/s** |
| gen-2 collections / 8 s | 496 | **1** |
| GC pause / 8 s | 96.9 ms | 8.5 ms |

Roughly sixty full collections per second — exactly the periodic hitching the frame
pipeline exists to avoid. Fix: `FrameBuffer` + `ApiClient.ScreenshotIntoAsync`, one reusable
buffer per pump (ping-ponged so the previous frame survives for the dedupe compare), read
with `HttpCompletionOption.ResponseHeadersRead` so `HttpClient` does not buffer into an
array of its own.

**(c) The wall stood aside while you dragged** — exactly when you need to watch it, since
that is when the mirrored phones should be moving. The justification in the code was a
misreading: it claimed tiles starved the master from 30 fps to 19.8, but ~20 fps *was* the
source rate that day.

A/B, three runs each, proves the wall is free:

```
wall off        master 17.7 fps   p50 31.9 ms   tiles  0.0 fps
wall at 30 fps  master 17.6 fps   p50 32.3 ms   tiles 11.8 fps
```

**The part that is not fixable in software.** Driving the same mirrored swipe and polling
flat out with the console closed entirely:

| phone | new fps, both polled | new fps, polled alone |
|---|---|---|
| 192.168.4.68 | 27.5 | 28.9 |
| 192.168.4.27 | 5.8 | **4.5** |

Two identical iPhone XRs, same iOS build, same rack. The second one's AirPlay stream
produces about a fifth of the frames, and it is just as slow when it is the only phone being
polled — so it is that phone's own Wi-Fi link, not contention and not the console. Any
console, the vendor's included, is bounded by this. Hence the per-tile rate readout: a phone
whose mirror is slow should look slow, not make the app look slow.

### 2.3 "The small phone display is jittering in a weird way (just visual)"

Caused by the rate readout added in 2.2. Measured from the user's 13.4 s screen recording,
all 401 frames, by detecting the tile's green selection border:

```
tile border width:  178 px  (184 frames)
                    132 px  (167 frames)
                    177, 168, 167, 131 px
spread: 131 → 178 px — a 47 px jump, 14 times in 13.4 seconds
```

A tile sized itself to its contents, and the rate text changes width as the number changes
(`""` → `"21 fps"` → `"20.7 fps"`). Every time a phone's rate moved, the tile grew or shrank
and the whole wall reflowed.

Three changes:

1. **A tile is a fixed box.** `MainWindow.TileWidth` = tile height × the phone's screen
   aspect (taken from a live device, default 500/1080). Nothing about a tile's geometry may
   depend on its own content.
2. **The rate is overlaid on the picture**, bottom-right, inside the fixed-size border. An
   overlay cannot affect layout.
3. **The rate reads as a whole number** and updates only on a change of ≥1 fps.

Verified in the running app — the same measurement, taken from the live layout, sampled
every 50 ms for 10 s while a phone streamed at 18.5 fps:

```
distinct tile widths:     [67]
distinct tile positions:  [0]
```

Side effect: since tiles no longer stretch to fit captions, the caption shows
`Thumb.ShortName` — the part after the `·`, e.g. `35:8D` rather than `iPhone XR · 35:8D`,
which is the half that distinguishes phones. Full name and status on hover (`Thumb.Detail`).

---

## 3. Hardware characteristics worth carrying forward

### 3.1 A pointer move costs ~0.6 ms per pixel travelled

The board does not teleport the cursor, it walks it — and it walks every phone in an id list
in parallel, so mirroring a move to ten phones costs the same as moving one.

| jump | one phone | both phones |
|---|---|---|
| 2 px | 1.0 ms | 1.0 ms |
| 10 px | 4.3 ms | 4.3 ms |
| 50 px | 35 ms | 28 ms |
| 100 px | 78 ms | 77 ms |
| 200 px | 133 ms | 136 ms |
| 400 px | 250 ms | 242 ms |
| 700 px | 422 ms | 421 ms |
| 1000 px | 592 ms | 594 ms |

Consequences:

- **A move's latency says nothing on its own.** A benchmark that nudges the pointer a few
  pixels reports 1–4 ms; the same call across the screen reports 600 ms. An early
  measurement here reported p50 3.7 ms with a max of 264 ms and looked like jitter — it was
  the distance distribution.
- **Coalescing a drag is free.** Sending only the newest position skips no pixels; the board
  traverses the path either way. Verified: the same stroke sent as 14 small steps, 7 steps,
  and 2 large jumps produced identical reactions on both phones (26.2 and 22.9).
- **A full-height swipe is slow by construction.** 1080 px ≈ 580 ms of travel, which iOS
  reads as a slow drag rather than a flick, so velocity-dependent gestures may not fire.
  Prefer the short axis.
- **Hover tracking is not free** — following the mouse commands the same walk.

### 3.2 Screenshot traffic does not slow input

Latency of `/mouse/move` to both phones, with small jumps so distance is not a factor:

| conditions | p50 | p95 | max |
|---|---|---|---|
| nothing else running | 11.7 ms | 25.0 ms | 25.0 ms |
| one phone polled flat out | 1.0 ms | 28.6 ms | 29.2 ms |
| both phones polled flat out | 0.5 ms | 23.4 ms | 36.1 ms |
| both polled at a paced 33 ms | 3.4 ms | 27.9 ms | 36.8 ms |

There is therefore no reason for the wall to stand aside while the operator drags.

---

## 4. How to measure whether a gesture landed

Hard-won, and easy to get wrong:

- **Never compare screenshots byte for byte.** A mirrored screen never repeats exactly — the
  clock, the AirPlay encoder and wallpaper parallax all move. An MD5 comparison reports
  "reacted" for an untouched phone just as reliably as for a tapped one. An earlier
  diagnostic in this project drew a wrong conclusion that way. Use **mean absolute pixel
  difference against an idle control** (~0.02 on this rack).
- **Do not watch for an app to open or a home page to flip.** Both are state-dependent: a
  phone already on its last page, or an edge gesture iOS declines to recognise, is
  indistinguishable from mirroring having dropped that phone. This made the swipe probe fail
  perhaps half the time while the app was working correctly.
- **Two probes that are state-independent:**
  1. **What was sent** — assert the delivered coordinate and the id list directly.
  2. **Where the pointer ended up** — mean pixel difference in a small box around the
     stroke's final coordinate. Measured 1.4–9.8 against an idle floor of 0.02. A
     whole-frame diff cannot see this (the dot is a few pixels across), which is the same
     reason auto-bind uses a box.
- **Normalise before comparing coordinates.** Two phones in the same rack may have entirely
  different home screens and wallpapers. One coordinate is a fair target for two phones only
  after two Home presses (first leaves the app, second returns to page one) — and even then,
  only if both have the same icon at that spot. On this rack, `(0.845, 0.232)` is Clock on
  one phone and Reminders on the other.
- **Benchmark with the screen in motion.** A still screen produces almost no new frames, so
  every rate looks the same and the numbers say nothing about what swiping feels like.
- Other traps hit earlier in the project: `gdigrab` captures whichever window is on top;
  a 30 Hz sampler cannot resolve a 30 Hz stream (~90 % ceiling); the display is 150 % DPI.

---

## 5. Code map — what changed

| file | change |
|---|---|
| `src/iMouse.Console/ApiClient.cs` | `FrameBuffer`; `ScreenshotIntoAsync`; `IsImage(ReadOnlySpan<byte>)`; `CoordinateMapper.MapClamped`; equality guard on `Device.BoardState` |
| `src/iMouse.Console/LiveFrame.cs` | `Prepare(ReadOnlySpan<byte>, int maxHeight)` + `Reduce` (whole-block averaging); span `SameAsPrevious`, `LooksLikeBmp` |
| `src/iMouse.Console/MainWindow.xaml.cs` | gesture stages split into point-taking `BeginGesture` / `TrackGesture` / `EndGestureAsync`; `MapPreviewClamped`; `ResetJoinedPointers`; `TilePumpAsync` replacing `WallPumpAsync`; pooled master pump; `TileWidth`; input paths moved off the dispatcher; `RunWallAsync`; extended `RunMirrorAsync` |
| `src/iMouse.Console/MainWindow.xaml` | tile template: fixed-size `StackPanel`/`Border`, rate overlaid, `ShortName` caption; wall rate options now frame rates |
| `src/iMouse.Console/PhoneWall.cs` | `Thumb.Fps` / `RateText` / `RateVisibility` / `ShortName` / `Detail`; reference-equality guard on `Image` |
| `src/iMouse.Console/SelfTests.cs` | clamped-mapper, buffer-reuse and reduction tests |
| `src/iMouse.Console/App.xaml.cs` | `--mirror-test`, `--wall-test`, `--tile-ms=N` |
| `analysis/HARDWARE.md` | all of section 3 and 4 above |

### Notable design points

- **Gesture stages take a plain `Point`, not a mouse event.** Synthesising WPF mouse events
  is not practical, and this path is where the mirroring bugs lived — so the handlers are
  thin wrappers and the tests drive the real code.
- **Input paths run off the UI thread.** `DragLoopAsync` and `PumpPointerAsync` are started
  with `Task.Run` and use `ConfigureAwait(false)`; target id lists are computed on the UI
  thread first (`InputTargetIds()` reads the selection and tick boxes and must not be
  touched from a worker). `LogAsync` marshals back. Note `Task.Yield()` is **not** enough —
  it posts back to the dispatcher it was called on.
- **Tile bitmaps are written in place.** `Thumb.Image` is assigned once; after that the same
  `WriteableBitmap` is mutated, so a new frame costs no binding work.
- **Reduction is by whole integer factors.** Asking for more than half the source height
  leaves the frame at full size rather than scaling slightly — correct, if not obvious, and
  it means a very large tile setting passes the full frame through.

---

## 6. Build, test, deploy

```bash
"C:/Program Files/dotnet/dotnet.exe" build "src/iMouse.Console/iMouse.Console.csproj" -c Release -o "release/iMouse2-net" --nologo
```

Test modes — each writes JSON under `release/iMouse2-net/qa/`, and a failure writes
`<mode>-test-failure.txt` beside the exe:

| command | what it does | last result |
|---|---|---|
| `iMouse2.exe --self-test` | 75 pure unit checks against a mock transport | 75 passed |
| `iMouse2.exe --ui-test` | 76 UI checks on a fake device fixture; renders `ui-preview.png` | 76 passed |
| `iMouse2.exe --smoke-test` | connects to the live service, one frame | ok |
| `iMouse2.exe --fps-test` | live master frame rate, pacing, GC | see §2.2 |
| `iMouse2.exe --wall-test [--tile-ms=N]` | master + tiles under continuous mirrored motion, plus live tile geometry | see below |
| `iMouse2.exe --mirror-test` | drives the real gesture handlers against the rack | see below |

Deploy (stops the running app, copies five files, relaunches):

```bash
powershell -NoProfile -Command "Stop-Process -Name iMouse2 -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 700; Copy-Item 'release\iMouse2-net\iMouse2.exe','release\iMouse2-net\iMouse2.dll','release\iMouse2-net\iMouse2.deps.json','release\iMouse2-net\iMouse2.runtimeconfig.json','release\iMouse2-net\iMouse2.pdb' -Destination 'release\iMouse2\' -Force; Start-Process -FilePath 'release\iMouse2\iMouse2.exe' -WorkingDirectory (Resolve-Path 'release\iMouse2')"
```

### Final verification on the rack

`--wall-test`:

```
distinctTileWidths     [67]        distinctTileLefts  [0]
tileFpsEach            18.5        masterFps          19.4
masterPresentP50Ms     32.2        allocatedMbPerSec  3.2      gen2  0
```

`--mirror-test`, three consecutive runs:

```
control [A0:44 0.02  35:8D 0.02]   tap [A0:44 85.13  35:8D 110.64]
stroke: clamped=True allPhones=True   pointer arrived [A0:44 9.77  35:8D 3.82]

control [A0:44 0.03  35:8D 0.02]   tap [A0:44 85.19  35:8D 110.67]
stroke: clamped=True allPhones=True   pointer arrived [A0:44 9.74  35:8D 8.57]

control [A0:44 0.02  35:8D 0.02]   tap [A0:44 85.20  35:8D 110.62]
stroke: clamped=True allPhones=True   pointer arrived [A0:44 1.42  35:8D 3.98]
```

---

## 7. Corrections made to earlier project beliefs

Recorded because each one had been written down as fact and was wrong:

1. **"Polling wall tiles starved the master — 30 fps fell to 19.8."** That was the source
   rate, not contention. Concurrent polling does not degrade either phone, and an A/B shows
   the wall costs the master nothing.
2. **"Screenshots and input contend."** They do not, in either direction.
3. **"Byte-identical screenshots mean nothing happened."** The opposite: a *changed*
   screenshot means nothing on its own, because an untouched mirror never repeats.
4. **The `/mouse/move` p50 of 3.7 ms with a 264 ms max was not jitter** — it was distance.

---

## 8. Open items

- **The `/mouse/reset` root cause is unexplained.** `/mouse/up` did not clear it, so it is
  not a button left down by an interrupted drag. Auto-reset on mirror-set change papers over
  it; what puts a phone into that state is unknown.
- **192.168.4.27's mirror runs at ~4.5 fps under motion** versus 28.9 for its twin. Worth
  checking that phone's Wi-Fi band, signal and distance from the AP. Not a software problem.
- **Mixed-aspect racks.** `TileWidth` samples the first online device's geometry; a rack
  mixing phone models will letterbox the odd ones out. Fine for an all-XR rack.
- **The reduction cliff.** A tile height above ~270 asks for more than half the source
  height, so the frame passes through at full size. Harmless at the default (118),
  documented in `LiveFrame.Prepare`.
- **The vendor HID report format** is still opaque — a USB capture would be needed. It, plus
  re-implementing the AirPlay receiver, is all that stands between this console and full
  independence from `IMService.exe`.
- Unanswered questions from earlier: whether to add the rest of the original's vertical strip
  (Restart, Lock, Ctrl Bar, KB, Cast, App, IME, Disc); whether the device-list checkbox reads
  clearly as "select mirror followers"; the search box has no placeholder and the group
  filter is `Visibility="Collapsed"`.

---

## 9. Security note

`C:\iMouseXP\IMService.json` contains the account credential as trivially reversible hex
obfuscation. Do not print or distribute it, and keep `build/` excluded by `.gitignore`.

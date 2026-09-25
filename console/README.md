# iMouse 2.0 console

A working replacement for the iMouse XP console window: live phone screen, click
to tap, drag to swipe, navigation and typing. Runs in your browser with nothing
to install.

## Start it

Double-click **`Start iMouse 2.0.cmd`**, or run:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File "console\serve.ps1"
```

It opens `http://127.0.0.1:8777/`. Leave the black window open while you use the
console; closing it stops the host. iMouse XP and the phones keep running either
way — this console only reads from and sends commands to the existing kernel.

The original `IMConsole.exe` window does **not** need to be open. The kernel
(`IMService.exe`) runs as an automatic Windows service and is what actually
drives the boards and the mirroring.

## What works

| | Status |
| --- | --- |
| Live screen | 30 fps at about 6 ms latency |
| Tap, drag-to-swipe, scroll wheel | Working, verified on hardware |
| Home, App switcher, Control centre, Back | Working |
| Directional swipes | Working |
| Typing (box, or your own keyboard) | ASCII |
| Start / stop mirroring | Working |
| Reset pointer, restart board | Working |
| Save screenshot | Working |

## Look and feel

The native console is plain white by default - white surfaces, hairline rules, one
restrained accent - with a **Night** button in the top right that flips the whole window
to a dark palette. The choice is remembered in `data/settings.json`.

Two decisions worth recording:

- **Every themed colour is a keyed brush, referenced with `DynamicResource`.** A
  `StaticResource` is resolved once when the window loads, so anything styled that way
  would stay stuck in the old palette when the toggle is pressed. That includes the styles
  inside `App.xaml` itself, which is the easy half to miss.
- **Night is not light inverted.** Dark surfaces need a dimmer accent and a lower-contrast
  muted tone, or the window glares. The palettes are listed side by side in `Theme.cs`.

"Ready" and "selected" are deliberately different colours. Green means the phone is
working; blue means it is the one you are pointing at. They were previously the same
accent, which made a working phone and a chosen phone look identical at a glance - the
opposite of useful when scanning a rack.

Combo boxes, scrollbars and buttons carry their own minimal templates. The stock WPF
chrome ignores the palette entirely and looks obviously wrong the moment night mode is on.

## The wall: master plus every other phone at once

The centre panel is a large master view with a live tile for every other phone beside it,
so a rack can be watched in one screen. Drag the splitter between them to enlarge the
master; the tile size dropdown (Small / Medium / Large) sets how many fit per row.

- **Tap coordinates do not change with size.** Mapping is computed from the view's actual
  dimensions and the letterbox, so the same point on the phone is the same image pixel at
  any master size. Four self-tests pin this: identical results at 1x, 2x and 4x, with and
  without letterboxing.
- **Click a tile to promote that phone to master.** The quickest way to inspect one phone
  that looks out of step, without hunting for it in the device list.
- **A tile bordered in green is following the master.** Dimmed tiles are not mirroring or
  have no working board, so a phone that has silently dropped out is visible at a glance -
  which is the entire point of watching ten at once.

### Why the tiles refresh about once a second

One round-robin loop serves the whole wall rather than a pump per phone, and a full pass is
spread over roughly a second however many phones there are. Tiles only need to answer "is
this phone keeping up", which one frame per second does.

Polling them harder is not free and the cost lands on the master: with a single tile
running flat out, the master fell from 30 fps to 19.8. Each tile also makes the service
encode a JPEG, so what is being bounded is the service's encode load, not just this app's
bandwidth. The wall also stands aside entirely while a drag is in progress, so an active
gesture always has the link to itself.

Measured with the wall running and the master phone in motion: **30.2 fps average, 29.9
worst, p95 present interval 40 ms, zero long intervals** - no worse than with no wall at
all, and slightly better paced than before.

## Master mode (one phone drives the rest)

Tick **"Mirror this phone's actions to the checked phones"** in the Controls panel. The
phone you have selected is the master - the one on screen, the one your mouse acts on -
and every checked phone repeats what it does: taps, drags, swipes, navigation buttons and
typing.

**Follow: same model, online** checks every other phone that is mirroring, has a working
board, and has the same screen geometry as the master, which is the usual setup for a rack
of identical handsets.

### One request, not one per phone

Every input endpoint accepts a comma-separated id list, so a mirrored gesture is a single
round trip regardless of how many phones are following. Ten phones cost the same as one,
and they receive the event as close to simultaneously as the service can dispatch it. A
mirrored drag holds `/mouse/down` on the whole set, streams `/mouse/move` to the whole set,
and releases them together.

Casting is deliberately *not* collapsed this way - each phone negotiates its own AirPlay
session, so Start casting still issues one request per phone.

### Why followers must match the master's screen size

Only phones with the same mirror geometry are included. Identical screens make the
coordinates identical, which is exactly what makes the mimicry accurate. A phone with a
different screen size would need its coordinates rescaled, and on a different layout a
rescaled tap lands on whatever happens to occupy that fraction of the screen - a plausible
looking action in the wrong place.

So mismatched phones are excluded and **named in the panel**, in amber, along with any
checked phone that is offline or has no working board. Silently dropping a follower is the
worst possible behaviour here: the operator believes ten phones are in lockstep when only
nine are.

### Verified on hardware

A mirrored press-move-release addressed to two phones in one request: both performed the
drag, whole gesture 693 ms. Covered by eight interaction checks, including that mirrored
input is a single request, that the master is named first, that a differently sized phone
is excluded, that an offline follower never joins the set, and that exclusions are surfaced
rather than dropped.

## Dragging

Drag is a live gesture, not a replayed one. On press the console holds `/mouse/down` on
the phone and streams `/mouse/move` for the whole gesture, releasing with `/mouse/up`, so
content follows the cursor exactly as it does under a finger.

It did not always work that way. The first version recorded where the drag started,
sent nothing at all while the mouse moved, and fired a single canned `/mouse/swipe` on
release. The phone therefore sat motionless under the cursor and then jumped when the
button came up - which feels like the picture is stuck or lagging, even though the video
is running at full rate. It is worth separating the two symptoms: a slow *picture* is a
frame-rate problem, whereas a picture that is fine until you drag is an input problem.

Details that matter in the implementation:

- The gesture runs as one sequential task, so press, moves and release are strictly
  ordered and the last queued position is always delivered before the button lifts. A
  fire-and-forget scheme can release at a stale coordinate.
- The newest pending position wins; intermediate ones are dropped rather than queued, so
  the phone tracks the mouse instead of replaying a backlog.
- `/mouse/up` is sent from a `finally` block, and with a non-cancellable token. If a move
  fails mid-gesture the button must still come up, or the phone is left with a stuck press
  and every later tap lands inside a drag.
- Losing mouse capture counts as a release, for the same reason.
- A press that never moves is still a single atomic `/mouse/click`; the drag path engages
  only past a small movement threshold.

## Native app render path

Smoothness is measured, not asserted. `iMouse2.exe --fps-test` runs the real pipeline for
eight seconds against the live service while the phone is scrolling:

| | Average | Worst | Present-interval p95 |
| --- | --- | --- | --- |
| Before this work | 26.9 fps | 26.1 fps | — |
| **Now** | **30.2 fps** | **29.9 fps** | 44.5 ms |

The source delivers ~30 fps under motion, so the console now takes essentially every frame
it produces. On-screen capture (ffmpeg gdigrab, byte-exact `mpdecimate`) puts the app at
27.0 fps against the vendor console's 24.6 measured through the same pipeline.

Watch `presentIntervalP95Ms` and `longIntervals` in `qa/fps.json` rather than the average:
judder is uneven delivery, and an average is blind to it. A 7/60/7/60 ms stream and a
steady 33 ms stream report the same fps.

Five defects were behind the original stutter, each found by measurement:

- **Poll interval carried the wrong units.** `PreviewRate` in XAML has `SelectedIndex="3"`,
  whose `Tag` is `33` - a *frame period*. WPF raises `SelectionChanged` during
  `InitializeComponent`, before the constructor body, so `Rate_Changed` assigned that 33 to
  `_pollInterval`, a *poll spacing*, and the `= 5` field initializer was dead code. The loop
  then re-fetched immediately (always a duplicate) and slept 33 ms, giving 37 ms
  detect-to-detect = 26.7 fps against a 30 fps source. The handler now derives both values
  from the Tag, so firing during init is correct rather than something to suppress.
- **Presenting on the compositor's schedule instead of on arrival.**
  `CompositionTarget.Rendering` fires on WPF's own cadence (~83/s, gaps of 7/14/28 ms), so a
  frame landing just after a tick waits up to 28 ms. That turns an even 33 ms arrival stream
  into a 31/47 ms limp. Posting `Dispatcher.BeginInvoke(DispatcherPriority.Render, ...)` when
  the frame arrives cut present-interval standard deviation from 9.5 ms to 0.5 ms and long
  gaps from 58 per 8 s to zero. The `Rendering` hook stays attached as a backstop.
- **Self-reinforcing pacing.** Sleep was derived from measured gaps between frames, so one
  missed frame widened the gap, lengthened the sleep, and missed more. Measured decay:
  23 fps to 16.5 fps over eight seconds. Pacing is now fixed, never derived from observation.
- **Transient errors treated as outages.** Roughly 1-3% of screenshot requests fail even on a
  healthy phone; each triggered a 700 ms stall. Short runs now retry immediately.
- **High-quality resampling every frame.** The 500x1080 mirror draws into about a fifth of
  that area and WPF's default filter is the expensive one, on the render thread. Bilinear,
  with no visible loss at this scale.

Also: decode off the UI thread, pooled frame buffers, and the Windows timer resolution
raised to 1 ms while running (the default ~15.6 ms granularity turns a 6 ms sleep into
~15 ms and caps the view near 20 fps on its own).

One thing that was investigated and is **not** a problem: frames being written and then
discarded by WPF. Instrumenting the hand-off directly showed 0-1 drops per 8 seconds. The
apparent loss was mistimed frames being scored as duplicates by a 30 Hz sampler, not lost
ones.

Three measurement traps, all of which produced confidently wrong numbers before being
caught: a static phone screen barely changes, so counts must be taken under motion; desktop
capture silently measures whichever window is on top, so the app under test must be verified
frontmost; and a 30 Hz sampler cannot resolve a 30 Hz stream - its ceiling is about 90% even
with zero loss, so capture above 60 fps when comparing.

## Measured on this machine

Frame latency, iPhone XR at 500 x 1080:

| Path | Latency | Rate |
| --- | --- | --- |
| Raw frames, straight from the kernel | 6 ms | 30 fps (capped; 75 fps uncapped) |
| JPEG, straight from the kernel | 41 ms | 24 fps |
| Raw, through the proxy | 472 ms | 2 fps |
| JPEG, through the proxy | 78 ms | 12 fps |

Two consequences are baked into the design:

- **Raw beats JPEG.** JPEG makes the kernel re-encode every frame. Raw is an
  uncompressed copy of the frame the decoder already holds, so it is roughly
  seven times faster despite being sixteen times larger. Over loopback, size
  does not matter and encode time does.
- **Frames skip the proxy.** They load straight from `127.0.0.1:9911` as images,
  which browsers allow across origins. Only JSON and commands go through the
  proxy, because the kernel sends no CORS headers and a browser cannot otherwise
  read its responses.

## The two channels

The left panel shows two separate badges per phone, because control and video
are genuinely independent:

- **Control** — the USB path: PC to control board to phone. Green once a phone is
  attached to its board.
- **Mirroring** — the Wi-Fi path: phone casting to this PC over AirPlay.

Either can fail alone. A phone can show a perfect picture and ignore every tap,
or be fully controllable with no picture at all. The original console showed one
combined status, which is why that failure was hard to see. Full detail is in
[`../analysis/HARDWARE.md`](../analysis/HARDWARE.md).

## Tap coordinates

Confirmed by testing on hardware: taps use **mirror image pixels** (the
`imgw` x `imgh` geometry, 500 x 1080 here), not iOS logical points. The selector
in the toolbar is left in place in case a differently configured phone disagrees;
if taps land offset, try switching it before changing anything else.

## If something does not work

- **No phones listed.** The kernel is not running. Start iMouse XP once; its
  service is set to start automatically thereafter.
- **"Not mirroring".** On the phone, open Control Centre, Screen Mirroring, and
  pick your `iMouseXP-*` receiver. Or press Start casting.
- **Picture but taps do nothing.** The control channel or the phone's own
  accessibility settings. Check the Control badge first; if it is green, the
  phone needs: AssistiveTouch on, Full Keyboard Access on, and trackpad tracking
  speed at maximum. The full list is in `../analysis/HARDWARE.md`.
- **Port already in use.** `serve.ps1 -Port 8778`.

## Files

- `index.html` — the console. Self-contained; no build step and no dependencies.
- `serve.ps1` — the local host and API proxy. Windows PowerShell 5.1, no admin.
- `Start iMouse 2.0.cmd` — launcher that handles the quoting.

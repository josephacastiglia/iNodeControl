# Hardware analysis — control boards and signal path

Evidence gathered September 7, 2026 against the live running system, with one iPhone XR
mirroring. Discovery was read-only: HTTP GETs to the local service, Windows PnP/HID metadata
queries, process/socket enumeration, and config file reads. No report was written directly to
any board and no service state was changed.

Two later steps did send input to the connected iPhone XR, through the documented API, to
settle questions that could not be answered by observation: pointer moves during coordinate
probing, and one tap plus one Home press to confirm the coordinate space. The tap opened the
Clock app and Home returned the phone to its home screen, leaving it as found.

## Headline finding: there are two independent channels, not one

The single most important structural fact for 2.0 is that **control and video travel over
completely separate paths**, and a board can be fully healthy on one while the other is dead.

| | Control (input) | Video (screen) |
| --- | --- | --- |
| Path | PC -> USB -> control board -> Lightning -> iPhone | iPhone -> Wi-Fi -> PC |
| Transport | USB HID vendor-defined reports | AirPlay mirroring over TCP |
| Owner process | `IMService.exe` | `AirplayMirroring.exe` |
| Discovery | Windows USB enumeration | `mDNSResponder.exe` (Bonjour) |
| Reported by | `/api/config/usb/get` (`state`) | `/api/device/get` (`state`, `air_handle`) |
| Fails independently | Board unplugged / phone cable out | Phone off Wi-Fi / mirroring stopped |

This is exactly what the first 2.0 build got wrong. It treated "device online" as one flag.
Live data proves they diverge: **13 boards currently report a phone attached over USB, but
only 1 phone is mirroring.** A phone can be fully controllable with no picture, or visible
with no control. The 2.0 UI must show both states per slot.

## The control boards

19 boards are present, each enumerating as a USB HID device under `VID_720A` with a
**unique PID that acts as its address**.

| Property | Value |
| --- | --- |
| Vendor ID | `720A` (all boards) |
| Product ID | Unique per board — this is the addressing key |
| Manufacturer string | `wch.cn` (Jiangsu Qinheng / WCH) |
| Product string | 老猫子虚拟设备 — "Old Cat virtual device" |
| `bcdDevice` | `0x0100` (1.00) on all 19 |
| HID usage page | `0xFF00` — vendor-defined, not a standard mouse/keyboard page |
| HID usage | `0x00` |
| Output report | **9 bytes** (1 report ID + 8 payload) — PC to board |
| Input report | **17 bytes** (1 report ID + 16 payload) — board to PC |
| Feature reports | none |

Each board appears twice in Windows: once as `USB\VID_720A&PID_xxxx` ("USB Input Device")
and once as `HID\VID_720A&PID_xxxx` ("HID-compliant vendor-defined device").

An 8-byte payload is the size of a standard HID keyboard report, which is consistent with
these being HID bridges: the PC hands the board an input event, the board re-emits it to the
iPhone as a hardware keyboard/mouse. That is the mechanism by which iOS accepts the input at
all — to the phone it looks like a physical accessory, which is why the documented setup
requires the iOS accessibility / AssistiveTouch pointer options.

The vendor-defined usage page means the report layout is proprietary and is **not** derivable
from the descriptor. Confirming the exact byte format needs a USB capture (see next steps).

## Board addressing and identity

- `pid` — 4 hex chars, unique per board, factory-programmed. The address.
- `uid` — 8 hex chars, **always `pid` plus a 4-char suffix**. This is the ID the software
  binds phones to. Observed suffixes here: `BEBD`, `BFBD`, `C4BD` (batch/revision markers).
- `ver` / `uver` — **unreliable in this build.** For boards with no phone attached it reads
  `c.n`; for boards with a phone it reads the `uid` suffix bytes rendered as characters
  (literal `\u00BE.\u00BD` text, which displays as the mojibake seen in the console). The
  service emits these as literal escape text rather than real JSON escapes. Vendor docs show
  a clean `4.4` for this field, so this is a service-side encoding defect, not a property of
  your boards. **2.0 must not parse or display this field as a version.**

## Board state values

Confirmed against the vendor callback docs (`usb_change`, `code: 12` = "There are hardware
and mobile phone connections"):

| `state` | Meaning | Count now |
| --- | --- | --- |
| 1 | Board enumerated on the PC, **no phone attached** | 6 |
| 2 | Board enumerated **and phone attached** over USB | 13 |

Note this says nothing about whether the phone is mirroring — that is the separate channel.

## Physical topology

Boards hang off three 7-port USB hubs (`VID_1A40&PID_0201`, Terminus-class), themselves
chained upstream. 19 of 21 slots are populated.

| Hub | Populated ports | Board PIDs by port |
| --- | --- | --- |
| Hub #0009 | 7 / 7 | 1:`E414` 2:`3523` 3:`C415` 4:`764E` 5:`374C` 6:`3848` 7:`D446` |
| Hub #0010 | 6 / 7 (port 4 empty) | 1:`C24C` 2:`C241` 3:`C214` 5:`724E` 6:`F215` 7:`9515` |
| Hub #0011 | 6 / 7 (port 5 empty) | 1:`7949` 2:`704E` 3:`694E` 4:`1248` 6:`1814` 7:`D142` |

Hub plus port is a stable physical location. **2.0 should surface this as the rack slot
label**, since PIDs are opaque and a failed board is otherwise impossible to find by hand.
The original software does not expose it.

## The mirroring path, as currently running

Verified live for the connected iPhone XR:

- `mDNSResponder.exe` advertises the PC as AirPlay receiver **`iMouseXP-5429`** (UDP 5353).
- The phone at `192.168.4.68` connects to the PC at `192.168.4.29`.
- `AirplayMirroring.exe` (PID 36096) listens on **TCP 17000** and holds three established
  sockets to the phone (two on 17000, one on 10986).
- The device record's `air_pid` field is literally that process ID, and `air_handle` is its
  session handle — so `air_pid` is the live proof that mirroring is up for that phone.

Listening surface owned by the stack: `9911` (HTTP + WebSocket API, `IMService`), `3362`
(UDP, `IMService`), `17000` and `47010` (`AirplayMirroring`), `5356` and `18082`
(`mDNSResponder`).

## Binding: how a phone is tied to a board

`DeviceList.json` is the persistence layer. Each phone record carries both its network
identity and its board identity in one row:

- Phone side: `deviceid`, `mac`, `ip`, `device_name`, `model`, `version`, `user_name`
- Board side: `vid`, `pid`, `uid`
- Geometry: `width`/`height` = **414x896** (iOS logical points), `imgw`/`imgh` = **500x1080**
  (mirror stream pixels), plus `rotate`

Those two geometries are not the same space. **Confirmed by hardware test on 7 September 2026:
`/mouse/click` takes coordinates in mirror image pixels (`imgw` x `imgh`), not iOS points.** A tap
sent at 442,245 in the 500 x 1080 image space landed exactly on the intended app icon and opened it.
Assuming the logical 414 x 896 point space instead would put every tap in the wrong place.

`/mouse/move` uses the **same absolute image-pixel space** (confirmed 8 September 2026: a move to
380,880 put the pointer at 377,875 in the captured frame). An earlier probe wrongly concluded the
pointer was not carried in the AirPlay stream at all. It is - as a small, low-contrast grey dot that
a naive frame diff misses. The correction matters, because it means a console can drive the phone's
own pointer for hover-sensitive interfaces, not only send taps.

`location` is empty and `location_crc` is `B0DBD800`, which is byte-identical to the value in
the vendor's own documentation examples. Per the vendor API notes, mouse parameters are stored
as CRC values with "universal library matching for same-model devices" — so this rig is running
on a **shared library calibration profile, not a per-device measurement**. That is a supported
configuration, not an error, but it is the first thing to check if taps land offset. A
device-specific calibration is captured through `/device/collection/mouse` and persisted with
`/device/collection/mouse/save`.

## Answering the setup-order question directly

The order described is correct and is enforced by the hardware:

1. Board plugged into the PC — it enumerates as `USB\VID_720A&PID_xxxx`, `state` becomes 1.
2. Phone cabled to the board — `state` becomes 2. Control is now possible.
3. Phone joins the same LAN and starts screen mirroring to `iMouseXP-5429` — an
   `AirplayMirroring` session opens on TCP 17000 and the phone appears in `/device/get`
   with a live `air_pid`.
4. The phone's record is bound to that board's `uid` and persisted.

Steps 2 and 3 are independent. Nothing in step 3 verifies step 2, which is why the original
console can show a picture from a phone it cannot actually click.

## Vendor confirmation of the above

The official product page and setup guide corroborate the live findings:

- **"One piece of this hardware corresponds to one mobile phone."** This confirms the
  one-board-one-phone model, and therefore that a board's unique PID is effectively the
  phone's control address.
- Board variants exist for **Lightning and USB-C**, and the board reaches the PC through an
  **OTG cable**. The vendor warns the board "is only compatible with the included Lightning
  cable or USB-C cable" — so cable substitution is a real failure mode to surface in 2.0.
- Supported range is **iPhone 6s and above, iOS 15 and above**. No jailbreak, no app on the
  phone — consistent with the HID-accessory mechanism found above.
- The documented connection order is board-to-PC first, then phone-to-board, matching the
  observed `state` 1 then 2 transition exactly.

### iOS-side prerequisites the phone must satisfy

These are on the phone, not the PC, and none of them are visible over the API — which is why
a phone can mirror perfectly and still ignore every input:

- Accessibility - Touch - **AssistiveTouch ON**, tracking sensitivity max
- Accessibility - Keyboards - **Full Keyboard Access ON**, auto-hide 1s
- General - Trackpad & Mouse - **tracking speed max** (this menu only appears while the board
  is attached, which itself is a useful diagnostic)
- Display & Brightness - **Auto-Lock Never**, view Standard
- Both orientations locked, StandBy disabled
- Control Center - Screen Mirroring to the receiver name (`iMouseXP-5429` on this PC)

The vendor's own troubleshooting entry for input non-responsiveness is exactly this list.
**2.0 should ship this as an on-screen checklist per phone**, because it is the single
largest source of "the slot looks fine but nothing happens".

## A second, different API exists — do not confuse them

`doc.some3c.com/iphone-farm-setup/api-documentation` documents a related product on
**HTTP port 9912** with WebSocket at `ws://host:9911/clinet`. The installed system here is the
**XP** edition, which serves both HTTP and WebSocket on **9911** (verified: `IMService.exe`
owns the 9911 listener). Build 2.0 against the `xp-api-documentation` set only. The two share
concepts and much naming but are not interchangeable.

Relevant XP endpoints confirmed present in the docs for hardware work:

| Endpoint | Purpose |
| --- | --- |
| `/config/usb/get` | Enumerate boards and their attach state |
| `/device/usb/restart` | Reset a board without touching the service |
| `/device/collection/mouse`, `/device/collection/mouse/save` | Pointer calibration capture and persist |
| `/mouse/reset` | Recover pointer state |
| `/device/airplay/connect`, `/disconnect`, `/connect/all` | Drive the mirroring channel independently |

That `airplay/connect` group is the direct lever for the video channel, and confirms 2.0 can
manage the two channels separately rather than hoping they come up together.

## Live video is available through the documented API

The earlier open question - whether a replacement console could show live video or only
still screenshots - is settled. `/pic/screenshot?binary=true` returns the frame the decoder
already holds, with no re-encode:

| Request | Latency | Payload |
| --- | --- | --- |
| `binary=true` (raw BMP) | **2 ms** | 1,620,054 bytes = 500 x 1080 x 3 + 54-byte header |
| `binary=true&jpg=true` | 41 ms | ~96 KB |
| default (base64 BMP in JSON) | 26 ms | ~2.3 MB |

Polling the raw form sustains 75 fps, well above the 30 fps the AirPlay stream itself
produces, so a console can display the mirror with no added latency. Measured end to end in
the browser console: **30 fps at 6 ms**. Reimplementing an AirPlay receiver is therefore not
required for a live view - only for full independence from `IMService.exe`.

## A phone can silently stop accepting taps until its pointer is reset

Measured on the rack on 2026-09-10, with two iPhone XRs bound to boards `C241BFBD` and
`C214BEBD`. The second phone reached a state where it took `/mouse/move` normally — the
pointer visibly followed — but **every** `/mouse/click` did nothing at all. This was not a
mirroring fault: it failed identically when the phone was addressed on its own.

Mean absolute pixel difference between before/after screenshots, whole frame, 0-255 scale.
An untouched phone measures about 0.02, so anything under ~1 is "nothing happened":

| action | master | stuck follower |
|---|---|---|
| idle, no input | 0.03 | 0.03 |
| `/mouse/click` addressed to that phone alone | 0.02 | **0.09** |
| `/mouse/click` addressed to both in one request | 162.66 | **0.03** |
| `/mouse/click` after `/mouse/reset` | — | **141.96** |
| `/key/sendkey Home` while stuck | — | 142.15 |

Three things follow from this:

- `/mouse/up` did **not** clear it, so it is the pointer's own state rather than a button
  left down by an interrupted drag.
- Hardware keys keep working while the pointer is stuck, so the board and the cable are
  fine — only the pointer path is affected. A phone in this state looks alive in every
  other way.
- `/mouse/reset` clears it, and it stays cleared: repeated mirrored clicks landed on both
  phones afterwards with no further resets.

To an operator this reads exactly like "mirroring is broken" — the master obeys and one
phone in the rack quietly does nothing. The console therefore sends `/mouse/reset` to the
whole target set whenever the mirror set changes (a phone ticked, unticked, or made
master), which costs one request at those moments and nothing while working. The manual
Reset button remains, for a phone that drifts mid-session.

**Measuring reactions:** do not compare screenshots byte for byte. A mirrored screen never
repeats exactly — the clock, the AirPlay encoder and wallpaper parallax all move — so an
MD5 comparison reports "reacted" for an untouched phone just as reliably as for a tapped
one. An earlier diagnostic run in this project drew a wrong conclusion that way. Mean pixel
difference against an idle control separates them cleanly.

**Normalise before comparing:** phones drift onto different home pages, and two iPhones in
the same rack may have entirely different home screens and wallpapers. One coordinate is
only a fair target for two phones after two Home presses (the first leaves the app, the
second returns to page one) — and even then, only if the two phones have the same icon at
that spot.

## Frame delivery: what the service can do, and what each phone can do

Measured 2026-09-10 with the console closed, so the only traffic was the measuring script.

**Format matters enormously.** `binary=true` returns a raw bottom-up BMP; adding `jpg=true`
makes the kernel re-encode:

| | requests/sec | latency p50 | bytes |
|---|---|---|---|
| raw BMP, flat out | 84 | 12.7 ms | 1.6 MB |
| raw BMP, paced at 50 ms | 20 | **2.0 ms** | 1.6 MB |
| JPEG, flat out | **21 (a hard cap)** | **40.5 ms** | 96 KB |

JPEG costs twenty times the latency and caps a stream at about 21 requests a second. It is
the right choice only on a link where 1.6 MB a frame is unaffordable. On loopback it is
strictly worse, including for thumbnails.

**Phones are independent; there is no shared bottleneck to design around.**

- Polling two phones' raw frames concurrently and flat out: 83 and 85 requests/sec, p50
  3 ms each — the same as either one alone.
- Ten concurrent pollers: 512 requests/sec total, p50 3 ms, worst p95 142 ms.
- Streaming `/mouse/move` to both phones while polling frames: 98.8 requests/sec, versus
  78.7 with no input traffic at all. Input did not interfere in the slightest.

This retires an earlier belief recorded in this project — that polling wall thumbnails
"starved" the master, 30 fps falling to 19.8. That measurement was reading the source rate,
not contention. See below.

**The source rate is content-dependent, and differs per phone.** A still screen produces
almost no new frames, so benchmarking one measures nothing. Under continuous motion (a
mirrored swipe driven throughout), polled flat out:

| phone | new frames/sec, both polled | new frames/sec, polled alone |
|---|---|---|
| 192.168.4.68 | 27.5 | 28.9 |
| 192.168.4.27 | 5.8 | **4.5** |

Two identical iPhone XRs, same iOS build, same rack. The second one's mirror produces
about a fifth of the frames — and it is just as slow when it is the only phone being
polled, so this is that phone's own AirPlay/Wi-Fi link, not contention, not the console.
Any console, including the vendor's, is bounded by this. It is worth showing per-phone, so
a slow phone does not read as a slow app.

## The console's own frame cost

Every screenshot is about 1.6 MB, over the 85 KB threshold at which .NET puts an array on
the Large Object Heap. The frame pump polls far more often than the source produces frames
- most polls return a picture identical to the last - so nearly every allocation was a
large object discarded microseconds later.

Measured inside the running app, one phone on screen, one tile on the wall:

| | before | after reusing buffers |
|---|---|---|
| allocated | 488 MB/s | 2.9 MB/s |
| gen-2 collections in 8 s | 496 | 1 |
| GC pause in 8 s | 96.9 ms | 8.5 ms |

Roughly sixty full collections per second, which is exactly the periodic hitching the
frame pipeline is otherwise built to avoid. One buffer per pump, refilled in place, removes
essentially all of it.

## The board steps the pointer: a move costs about 0.6 ms per pixel

Measured 2026-09-10, console closed. Latency of one `/mouse/move`, by how far the pointer
had to travel to get there:

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

The board does not teleport the cursor, it walks it, at roughly 0.6 ms per pixel — and it
walks every phone in an id list in parallel, so mirroring a move to ten phones costs the
same as moving one.

Consequences that matter:

- **A move's latency says nothing on its own.** A benchmark that nudges the pointer a few
  pixels reports 1–4 ms; the same call across the screen reports 600 ms. An early
  measurement in this project reported a p50 of 3.7 ms with a max of 264 ms and looked like
  jitter — it was the distance distribution.
- **Coalescing a drag is free.** Sending the newest position instead of every intermediate
  one does not skip any pixels: the board traverses the path either way. Measured with the
  same stroke sent as 14 small steps, 7 steps, and 2 large jumps, both phones reacted
  identically every time (26.2 and 22.9 mean pixel change).
- **A full-height swipe is slow by construction.** 1080 px is about 580 ms of pointer
  travel, which iOS reads as a slow drag rather than a flick, so gestures that depend on
  velocity may not fire. Prefer the short axis.
- **Hover tracking is not free.** Following the mouse across the preview commands the same
  walk, so a fast sweep across a 1080-px-tall mirror is ~600 ms of board time. The console
  coalesces to the newest position for exactly this reason.

## Screenshot traffic does not slow input

The reverse direction was measured earlier; this is the one that decides how a drag feels.
Latency of `/mouse/move` addressed to both phones, with small jumps so distance is not a
factor:

| conditions | p50 | p95 | max |
|---|---|---|---|
| nothing else running | 11.7 ms | 25.0 ms | 25.0 ms |
| one phone polled flat out | 1.0 ms | 28.6 ms | 29.2 ms |
| both phones polled flat out | 0.5 ms | 23.4 ms | 36.1 ms |
| both polled at a paced 33 ms | 3.4 ms | 27.9 ms | 36.8 ms |

Input is unaffected. There is therefore no reason for the wall to stand aside while the
operator drags, and the console no longer does.

## Measuring whether a gesture landed

Do not watch for an app to open or a home page to flip. Both are state-dependent: a phone
already on its last page, or an edge gesture iOS declines to recognise, is indistinguishable
from mirroring having dropped that phone. Two probes that are not state-dependent:

- **What was sent.** Assert the delivered coordinate and the id list directly.
- **Where the pointer ended up.** Mean pixel difference in a small box around the stroke's
  final coordinate, which is where each phone's pointer must now be. Measured across three
  runs: 1.4–9.8 against an idle noise floor of 0.02. A whole-frame diff cannot see this —
  the dot is a few pixels across — which is the same reason auto-bind uses a box.

## Security note

`C:\iMouseXP\IMService.json` stores the account login under `user.password` as a short hex
string. It is a trivially reversible byte obfuscation, not a hash or real encryption — the
plaintext is recoverable from that file alone. Flagging it because 2.0 will read this file:
do not carry this scheme forward, and treat the existing `build/` copy as containing a live
credential (`.gitignore` already excludes it — keep it that way).

## What is still unknown

- **The vendor HID report format.** The descriptor is vendor-defined, so the 8-byte command
  layout is opaque. This is the one gap that blocks talking to boards directly. It does not
  block building a console: the documented API covers live video and every input.
- LED colour meaning on the boards. The photos show green / blue / red per slot, and the live
  split is 13 attached vs 6 unattached, which is suggestive — but there is no evidence tying a
  specific colour to a specific state, so this is untested.
- Board model number and firmware source. `wch.cn` plus a custom VID narrows it to a
  WCH-microcontroller HID bridge, and the vendor product page lists no model number or
  chipset. The exact part is not established from software or vendor docs alone.
- Which iOS accessibility prerequisites are actually satisfied on each of the 13 attached
  phones. Not queryable — needs a per-phone input test.

## Recommended next step

Two options, depending on how far 2.0 should go:

- **Stay on the documented API** (lower risk, no capture needed). 2.0 talks to `IMService`
  on 9911 and keeps the existing engine driving the boards. Everything above is already
  enough to build a correct two-channel status model, slot labels, and coordinate mapping.
- **Drive the boards directly** (full independence from `IMService`). This requires decoding
  the 8-byte report format via a USB capture — running the original software while capturing
  a few known actions (Home, single tap, swipe) and diffing the reports. Needs USBPcap or
  Wireshark installed, and one board that can be safely exercised.

The first is the better basis for the 2.0 build, with the capture run as a parallel
investigation so the console is not blocked on protocol work.

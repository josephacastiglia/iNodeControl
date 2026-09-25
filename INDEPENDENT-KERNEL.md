# Independent kernel test build — 14 September 2026

Direct HID input is implemented and working on the authorized iPhone XR ending
**2F:F6**, board **C24C**. The independent UxPlay receiver receives live
500×1080 BMP video from that phone through port 9913 when that phone is
casting to `iMouse2-C24C`. This is a single-phone prototype, not a finished
daily replacement for IMService.

## Build and start

The latest tested outputs are:

- `release/iMouse2-kernel-verified/iMouse2.Kernel.exe`
- `release/iMouse2-independent/iMouse2.exe`
- `tools/airplay/uxplay/build-imouse/uxplay.exe`

Use `Start Independent Kernel.ps1` after closing the previous test kernel.
It starts the receiver as `iMouse2-C24C`, restricts direct HID input to C24C,
and restricts the AirPlay client to the test phone ID. The HTTP address is
`http://127.0.0.1:9913`. The launcher does not stop vendor services or alter the
firewall. Use only one controller for input to the test phone.

The separate console build has its own preferences and is preset to 9913.
The existing vendor-backed console and copied installation remain available.

## What was validated

- Real direct HID reset, approximate absolute move, click, 900 ms long press,
  Home, Control Centre, and primitive drag on C24C.
- Home Screen page changed during the primitive drag; context menu appeared
  during long press. Screenshots and report captures are in `analysis/`.
- 18 kernel checks: captured packet encoding, request bounds, target restriction,
  held-button movement, failure cleanup, BMP layout, named-pipe frame receipt,
  identical frames, and clearing a stopped stream. Mock transport sends no HID.
- 75 console self-checks and 100 console UI checks passed; UI checks used mocks
  and reported zero real phone input commands.
- Native console fix: identical successfully fetched frames refresh the input
  freshness timestamp, so an unchanged Home Screen does not expire after 10 seconds.

## AirPlay implementation

Source is FDH2/UxPlay master archive downloaded 14 September 2026, identifying
itself as 1.74. Build uses portable MSYS2 UCRT64 and GStreamer under `tools/airplay`.
MSYS2 archive SHA-256 was checked against its official release metadata.

The local modification in `renderers/imouse_frame_pipe.h` attaches an appsink,
converts to 500×1080 BGR, and writes bottom-up 24-bit BMP frames to a local named
pipe. Buffers are reused. The C# kernel validates the layout, keeps two reusable
buffers, serves the latest BMP at `/api/pic/screenshot?id=...&binary=true`, and
reports the phone online only once a frame is present. No JPEG or vendor video
forwarder is used. A zero-length frame marks session stop; pipe loss also clears
the frame. A static but connected frame remains valid.

The bridge has been tested with synthetic BMPs through the named pipe and with
live iPhone→UxPlay decode→pipe→HTTP video on 14 September. Portrait
is the current prototype scope; rotation and multiple receiver sessions need
additional work. A separate receiver process/pipe per phone is the intended
extension, not concurrent clients sharing one frame.

UxPlay is GPL-3.0-or-later; its license and source, including the local changes,
are retained. Preserve corresponding source and notices when distributing it.
Upstream: https://github.com/FDH2/UxPlay

## Session 14 Sep ~01:25 (verified vs remaining)

Inspected before replacing anything: old kernel
`release/iMouse2-kernel-airplay/iMouse2.Kernel.exe` PID 33712 on 9913, UxPlay
PID 2732, live frames already past 2200, phone `86:1D:4A:04:2F:F6` bound to
**C24C / C24CBFBD** (not 724E). Vendor `IMService` and `AirplayMirroring`
were left running. The vendor-backed console `release/iMouse2-net/iMouse2.exe`
was also left running; do not drive 2F:F6 from that window.

Replaced only the test kernel and its UxPlay child, then started
`release/iMouse2-kernel-verified/iMouse2.Kernel.exe` via
`Start Independent Kernel.ps1` (kernel PID 38720, UxPlay PID 38772).
Input remains restricted to C24C. Restarting the receiver dropped the AirPlay
session, as expected. Status after restart: `live:false`, frames 0, API code 25
asking to select `iMouse2-C24C`. Vendor 9911 had no BMP for this phone either.

**Code changes in this session (kernel only):**

- `/mouse/click` and `/mouse/down` / canned `/mouse/swipe` now send a
  zero-motion mouse report and wait 120 ms before the button goes down, so the
  pointer can finish walking. Click hold is 80 ms. This is a settle, not a
  double-click.
- ASCII space is USB usage 44 (same as the vendor capture). Hold is 90 ms with
  a 35 ms gap after each key-up.

**Automated checks this session:** 25 kernel checks (settle, space, LivePid,
bounded UxPlay restart). Console 76 self-checks and 100 UI checks (mocks).

**After recast** (client 192.168.4.28 / 2F:F6, live frames again):

| Action | Result | Evidence |
|---|---|---|
| Reset | Pointer to top-left | `analysis/live-reset.bmp` |
| Home | Left Control Centre to Home Screen | `analysis/live-home.bmp` |
| Single Search click (250,900) | Spotlight opened on the **first** click | `analysis/live-click-search.bmp` |
| Long press VLC (423,756, 900 ms) | App context menu | `analysis/live-longpress.bmp` |
| Canned swipe left | Home Screen page changed | `analysis/live-swipe.bmp` |
| Independent GUI on 9913 | Live master, Control ready, Mirroring, Cast iMouse2-C24C, Mirror-to-all off | `analysis/live-gui-console.png` |
| ASCII in Notes | `A B` then `A B Test 123!` with visible spaces | `analysis/live-notes-space.bmp`, `live-notes-space-2.bmp` |

Spotlight still shows `Test123!` with no space (`live-ascii.bmp`). That is Spotlight eating space, not a missing HID packet — Notes received the same usage 44 as a real space. Maps sheet was dismissed on the phone; Home returned to the first Home Screen (`live-home-after-notes.bmp`).

The kernel that served those Notes shots later exited after the frame pipe hit EOF. Combined verified build is now running (`iMouse2.Kernel` 39096, UxPlay 32960, console 16672): pipe-EOF reconnect, live `receiver_pid`, and bounded automatic UxPlay restart (5 tries, 2 s). Video is `live:false` until 2F:F6 recasts to `iMouse2-C24C`.

## Remaining live work

1. Automatic UxPlay restart is in the combined verified build (5 recoveries,
   2 s delay). Console shows **Receiver restarting**, then the recast prompt
   if there is still no frame. iPhone recast remains manual.
2. Completed: automatic UxPlay restart on C24C. Write-up
   `analysis/UXPLAY-AUTORESTART-TEST.md`. Kernel 39096 and console 16672
   unchanged; UxPlay 32960 → 13412; recast restored video and Search clicks.
   Recast after a helper crash is still a manual iPhone step.
3. Completed: 45 min C24C stability (16/16 cycles). Report
   `analysis/stability-c24c/REPORT.md`. Ready for a *controlled* two-phone
   test (second calibration + second receiver), not rack-wide enablement.

## Rebuild and checks

```powershell
dotnet build src/iMouse.Kernel/iMouse.Kernel.csproj -c Release -o release/iMouse2-kernel-verified
release/iMouse2-kernel-verified/iMouse2.Kernel.exe --self-test
dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o release/iMouse2-independent
release/iMouse2-independent/iMouse2.exe --self-test
release/iMouse2-independent/iMouse2.exe --ui-test
```

`tools/airplay/build-receiver.sh` rebuilds the modified receiver using the
portable MSYS2 bash. Build output and runtime DLLs currently stay in the project;
the portable dependencies are large and this is not a minimal installer.

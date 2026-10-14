# HID protocol — WCH boards (VID 720A)

**14 October 2026 update:** static analysis of the original vendor DLL now
identifies the separate Fn field, the shortcut Tab prelude, movement reply
handlers and an unvalidated alternate absolute mode. Read
[the vendor protocol report](vendor-protocol-rea-20261014/REPORT.md).
Those findings extend the historical capture below; they do not establish new
phone-side acceptance. The saved-byte decoder is `tools/vendor_hid_decode.py`.

Captured 13 Sep 2026 23:43:51–23:45:42 local, Windows USB ETW (`tools/hid-capture.ps1`),
19 boards present, IMService still running. File: `analysis/hid-captures/vid720a-20260913-234351`.

## What is solid

Every board is the same USB 1.1 HID gadget:

| | Address | Type | Max packet |
|---|---|---|---|
| Default | `0x00` | control | 64 |
| Host → board | `0x03` interrupt OUT | 8 bytes |
| Board → host | `0x83` interrupt IN | 16 bytes |

That matches the earlier HID-API sizes: a 9-byte output report is 1 report ID + 8 USB bytes;
a 17-byte input report is 1 report ID + 16 USB bytes. Report ID is added by `hidclass`,
not sent as an extra USB packet.

During the gesture window the trace has **3577** completed 8-byte OUTs and **3567**
completed 16-byte INs, paired almost 1:1 per second. So each command is likely one
8-byte OUT, and the board answers with a 16-byte status on IN. Idle boards did not
stream IN reports — traffic only appeared while the console was driving a phone
(first burst 23:44:32, ~40 s after capture start).

bcdUSB `0x0110`, bcdDevice `0x0100`, unique PID per board (the address).

## HID class view (14 Sep 2026)

All 19 boards opened with `FILE_SHARE_READ|WRITE` while IMService was still holding them.

| | Value |
|---|---|
| Usage page | `0xFF00` (vendor) |
| Usage | `0x0000` |
| Output report | **9 bytes** at the HID API (report ID 0 + 8 data) |
| Input report | **17 bytes** (report ID 0 + 16 data) |
| Feature | none |
| Output fields | one vendor field, **8 bits × 8** — unstructured blob, not a standard mouse |

USB config matches: HID 1.10, two interrupt endpoints (IN 16, OUT 8), report descriptor length 34 bytes. The 34-byte descriptor itself is not in the ETW log and the HID `GET_REPORT_DESCRIPTOR` ioctl returned `ERROR_INVALID_FUNCTION`.

## Previous payload gap (resolved for mouse and basic keyboard on C24C)

The 8 data bytes have no HID-level field names. ETW `FullDataBusTrace` logged URB **headers** only (`fid_URB_TransferBuffer` is a kernel pointer; UCX event 27 is 172 bytes with no payload appended). `tracerpt` XML cannot recover them.

On 14 September the outgoing buffers were recovered by observing `WriteFile`
inside the running IMService process with Frida. This observes existing calls;
the hook does not replace buffers, returns, or license behavior. No second USB
ETW capture and no random command guesses were needed.

User-approved target: `86:1D:4A:04:2F:F6`, current board **C24C**, UID
`C24CBFBD`. The old copied device file incorrectly maps this phone to 724E.
Use `analysis/single-phone-config/devices.json`, which records the live binding.
No direct output was sent to the other 18 boards.

## Observed packet map

The following are **eight data bytes**, excluding the initial HID report ID 0.
Transport is overlapped `WriteFile` on a shared read/write HID handle. Vendor
calls return `ERROR_IO_PENDING` (997), as expected for overlapped writes.
`HidD_SetOutputReport` was hooked too but was not used by the observed actions.
Our transport awaits completion of each write.

| Byte | A1 mouse report | A2 keyboard report |
|---|---|---|
| 0 | A1 | A2 |
| 1 | button state: 00 released, 01 left held | USB keyboard modifiers: 02 left Shift, 08 left GUI |
| 2 | signed 8-bit relative X displacement | USB keyboard usage, e.g. 04 A, 2B Tab, 2C Space |
| 3 | signed 8-bit relative Y displacement | zero in captures |
| 4–6 | zero in captures; other meanings unverified | zero in captures |
| 7 | zero in mouse captures; meaning unverified | 02 is the vendor Fn field (14 Oct static confirmation); values other than 00/02 remain unknown |

| Operation | Observed/replayed data |
|---|---|
| Right by one unit | `A1 00 01 00 00 00 00 00` |
| Down by one unit | `A1 00 00 01 00 00 00 00` |
| Left down | `A1 01 00 00 00 00 00 00` |
| Left up | `A1 00 00 00 00 00 00 00` |
| Click | down, ~70–80 ms, up |
| Long press | down, ~900 ms, up; visually verified on VLC context menu |
| Corner reset | release buttons/keys, then `A1 00 81 81 00 00 00 00` four times |
| Home | keyboard release, `A2 00 2B 00 00 00 00 00`, release, `A2 08 0B 00 00 00 00 00`, release |
| ControlBar | Tab then release; `A2 00 00 00 00 00 00 02`; `A2 00 06 00 00 00 00 02`; release |
| AppSwitch | same prefix as ControlBar, then `A2 00 52 00 00 00 00 02`; release |

There is no observed absolute-pixel movement packet. The vendor emits many
small relative steps. For example, a requested (100,200)→(300,400) move emitted
39 reports of `A1 00 01 01 00 00 00 00`. iOS acceleration and pointer settings
are part of this conversion; an absolute 16-bit X/Y guess would have been wrong.

The prototype calibration uses a corner origin near (14,14) and approximately
5.12 horizontal / 5.09 vertical image pixels per unit. It is specific to this
phone's present settings and portrait 500×1080 stream. Verified target points
include Search near (250,900) and VLC near (423,756). This is approximate
calibration, not universal pixel-perfect positioning. Changing pointer speed,
screen scaling, orientation, or another controller's pointer position requires
reset/recalibration. The software refuses boards without explicit enablement
and a calibration entry.

## Direct validation and evidence

- `hid-observation-20260914.jsonl` / `hid-command-markers.jsonl`: mouse reports.
- `hid-keys-20260914.jsonl` / `hid-key-markers.jsonl`: keyboard sequences.
- `direct-reset.bmp`, `direct-search-move.bmp`, `direct-click.bmp`,
  `direct-home.bmp`: our direct HID replay and vendor video used for observation.
- `kernel-api-click.bmp`, `kernel-position.bmp`, `kernel-longpress.bmp`,
  `kernel-drag.bmp`: actual 9913/9914 kernel input, also observed through vendor video.
- `kernel-api-ascii.bmp` / `live-ascii.bmp`: letters, numbers and `!` reach
  Spotlight; a requested space is not kept there (Spotlight consumes it).
- `live-notes-space.bmp` / `live-notes-space-2.bmp`: the same HID space
  (usage 44) is a visible space in Notes (`A B Test 123!`).

Drag primitives were visually verified by moving from one Home Screen page
to the next. The first canned swipe did not change pages; a subsequent primitive
drag with an 80 ms contact-settle interval did. That interval has been added to
the canned swipe implementation; the amended canned route has not yet been
live-retested.

IMService remained running for video and shared handles. Direct tests invoked
our kernel or HID replay process for input, not the vendor HTTP input endpoint.
A full test with IMService stopped remains outstanding. Raw restart, firmware,
right/middle buttons, scrolling, and other report fields have not been decoded.
Unsupported functions continue to return a failure instead of claiming success.

## Capture note

### 14 October 2026: incoming reports, C24C only

Two short read-only captures alongside the installed release's lease-controlled
reset and small moves produced 23 A1 movement signals and two AF status reports.
All were 17-byte Windows input reports including report ID zero. A1's leading
fields were consistent with the commanded relative deltas; no command sequence
number or iOS-completion indication was established. AF appeared during both
successful checks and must not be classified as an error without more evidence.
No A0/A5/A6 response was observed in this small sample.

In these 23 A1 samples, payload byte 4 matched `(0x80 + byte1 + byte2 + byte3)
modulo 256`; this remains an observation, not an enforced checksum. Trailing
bytes varied. Report timing/counts cannot establish USB round-trip latency,
one response per write or accurate phone positioning. No typing was performed.

The combined candidate source now offers optional `--hid-replies-pid` diagnostics
for enabled input boards. It defaults off and never waits for a reply before a
write. Status exposes bounded observations rather than acknowledgements. The
final complete kernel has only offline validation; installed software and the
prior packaged candidate are unchanged. See
`hid-input-replies-20261014/REPORT.md` for provenance, raw capture locations,
restoration and limitations. Earlier observations above retain their original
dates/scopes; this addendum does not retroactively validate them.

### Earlier capture environment

USBPcap was not used. This PC is Windows 11 25H2 + Secure Boot; USBPcap’s installer
still advertises Windows 7/8/10. Windows USB ETW is enough for topology and sizes.
It is not enough, via `tracerpt` XML, for the report layout.

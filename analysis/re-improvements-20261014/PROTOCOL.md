# Control and reply follow-up

14 October 2026. Static vendor analysis and offline candidate work only. The
installed release and all phones were untouched during this session.

## What the additional analysis established

The same MouseKeyItem.dll SHA-256 recorded on 14 October was used. Five more
functions were decompiled; four concern movement/buttons and one was an
unrelated destructor. Thirteen cited instruction sequences were independently
checked by `verify_vendor_followup.py`, which never executes the DLL.

- A5 identifier replies and A0/A1 movement replies signal the **same event**
  at context offset 0x20d. No sequence identifier was found. Treating this event
  as a matching command acknowledgement would be unsound.
- AF sets offset 0x1f9 to 10. The relative reset loop passes that value to Sleep.
  AF also sets two other fields; A6 sets one of those fields. Their physical
  meaning remains unknown. Two AF reports appeared during successful C24C
  checks in the previous session, so AF is not classified as a command failure.
- Our existing reset already waits 10 ms between its corner reports. There is
  no evidence for changing ordinary movement pacing or adding an ACK wait.
  Late/missing/identifier/status replies remain observations, never retries,
  automatic Resume, or proof that iOS acted.
- `HT_SetIOSVer` sets a host context field and returns without sending a board
  command. That flag is not a hardware capability negotiation.
- In that alternate mode, both LeftDown and LeftUp send A0 with cached
  coordinates. A full absolute-mode implementation needs mode-aware buttons,
  cleanup and orientation. Replacing only the movement encoder is insufficient.

The first new REA batch failed its private snapshot ACL inside the sandbox.
The successful permission-reviewed retry returned all five functions and
closed normally. Raw decompilation remains ignored and is archived locally;
only the curated findings and short instruction checks are versioned.

## Candidate changes

### Navigation without the wrapper's Tab

The existing `command-h` and `command-wake` Home alternatives are reused.
`--home-sequence fn-h` adds a directly encoded Fn+H alternative. The new
`--navigation-sequence direct-fn` sends Fn+Up for App Switcher and Fn+C for
Control Centre without the Tab prelude. These are explicit test settings:
defaults remain `vendor`, and there is no automatic shortcut fallback.

Apple documents those Fn shortcuts under Full Keyboard Access on iPhone and
allows reassignment. Its Command-Tab documentation is for an external keyboard
on iPad, so that shortcut was not substituted on iPhone. Sources:
[iPhone keyboard controls](https://support.apple.com/en-kw/guide/iphone/ipha4375873f/ios),
[switching apps](https://support.apple.com/en-euro/118408).

This is evidence for candidate choices, not physical validation. App Switcher
previously failed with FKA Off; support in that condition remains unestablished.
The console now explains the limitation and points to physical app switching.
The kernel reports its selected sequences and explicitly says phone settings
are not detected. Diagnostic export retains that configuration and bounded
reply counters, without raw payloads or identifier bytes.

### Absolute movement capability probe

`--absolute-probe-pid C24C` requires exactly one enabled board, with reply
observation enabled. The existing lease-protected `/mouse/move` and
`/mouse/reset` paths then send zero-button A0 coordinate reports. The normal
image bounds apply; the static vendor mapping uses 32767 times coordinate
divided by the corresponding image size, with truncation.

Clicks, button down/up, swipes and keyboard input are refused before opening
transport. The probe never sends a button-down report. Stop cancels its write,
releases keys and closes transport; it does not resend the A0 position or
switch to a relative report. This avoids replaying a move of unknown outcome.
Normal relative input and cleanup remain unchanged when the flag is absent.

The probe is **not absolute-positioning product support**. No A0 report has
been sent live. A normal lease must first be free, and a coordinated candidate
window is required. If the move is unsupported or visibly wrong, stop after the
first failure; do not try clicks, raw commands, firmware writes or blind retries.

## Validation and limits

- Kernel Release build: zero warnings/errors, **290 offline self-tests passed**.
- Console Release build: zero warnings/errors, **411 headless tests passed**.
- Tests cover exact Fn reports, no Tab in direct variants, ownership, command
  serialization, Stop during Fn prefix/chord, A0 bounds, refused activation,
  no cross-board dispatch, and no A0 replay on failure/cancellation.
- Full suites initially hit sandbox restrictions on temporary named pipes and
  atomic file replacement. Permission-reviewed reruns passed; those failures
  were not attributed to product behavior.
- No UI suite or real console/phone acceptance was run. Physical navigation,
  typing-field preservation, FKA mode compatibility, A0 support and targeting
  remain pending. The missing-space investigation remains deferred.

See the separate negative-control record and package report for guard-removal
checks and exact packaged hashes. Test counts are offline checks, not gate passes.

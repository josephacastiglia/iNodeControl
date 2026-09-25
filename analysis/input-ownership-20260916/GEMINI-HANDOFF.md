# Handoff: close Priority 2 live, then build Priority 1 (guided phone identification)

Work in `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0`. Read `REPORT.md`, `API.md`,
`walkthrough.md` (in Downloads, or ask for it), `../PHONE-FARM-CORE-REVIEW.md` §1 and §4,
and `../../FINISH-CRITERIA.md` gates 2, 3 and 4 before starting.

## Where things stand on 17 September 2026

Priority 2 (one controller per phone, reliable Stop) is **implemented and offline-verified**:
kernel 70/70, console self-test 112/112, UI test 109/109, staged dll SHA256
`89B8A2841AE0DB1BF96F39AD31B3D9351A6FF880722866D57D6C9FA711C95491`. All six review
amendments were confirmed in code by a second reviewer.

It has now also been **run live once**. The ownership kernel is running on 9913 with the
daily launcher's arguments (`--data-dir analysis\two-phone-config --input-pid C24C,C241
--receivers ... --receiver ... --receiver-runtime ...`), the staged console is connected to
it, and `GET /api/input/status` showed phone `FE:A9:BC:D7:A0:44` (board C241) `owned: true`
with a live lease acquired from a console click. That proves acquisition on hardware. It does
not yet prove Stop latency, release on a disconnected phone, or Resume against a real
generation, which is Part A.

The desktop shortcut still launches the two-phone pair (`release/iMouse2-two-phone-candidate`
+ `release/iMouse2-kernel-two-phone`). Do not change it until Part A passes.

Note for anyone running the pair by hand: after switching the console to 9913 the phones
must be recast from the vendor receiver `iMouseXP-5429` to `iMouse2-C24C` / `iMouse2-C241`
in Control Center, or you get control with no picture.

## Part A: close Priority 2 with a live acceptance run (with the user present)

Run on C24C and C241 only. Record each item with before/after frames or the Activity log,
under `analysis/input-ownership-live-YYYYMMDD/`. Pass/fail is per item.

| # | Test | Pass condition |
|---|---|---|
| A1 | Tap, drag, long press, Home on each phone through the ownership console | Feels identical to the two-phone build; one `/input/acquire` per phone per session, no re-acquire per gesture (check kernel log) |
| A2 | Stop mid-drag (press, move, press Stop while held) | Phone releases the button; measure console-click-to-release from the kernel log; no `/mouse/up` sent by the console after `/input/stop`; no error in Activity |
| A3 | Stop, then try to tap | Refused with the stopped message; zero input requests reach the kernel |
| A4 | Resume, then tap | Works; the kernel log shows a fresh token, not the revoked one |
| A5 | Stop with video offline (stop casting first) | Stop button still enabled and still releases the board |
| A6 | Unplug C241's cable during a held press, press Stop | Kernel reports `release_failed` or releases cleanly; console shows it honestly; Resume is blocked until it clears |
| A7 | Idle for 40 s with a phone selected | Lease renewed, no pause, no notice (renewal is every 10 s on a 30 s lease) |
| A8 | Selection change C24C to C241 mid-session | Old lease released, new one acquired, no stray input on the old phone |
| A9 | Disconnect from Settings | `GET /api/input/status` shows both phones `owned: false` |
| A10 | Leave the console idle 10 minutes with normal Wi-Fi | Count how many times a transient hover-move failure paused a phone and demanded Resume. Report the number; this decides whether the pause-on-any-error policy is too aggressive |

Promotion rule: only if A1 through A9 pass and A10 is acceptable to the user, update
`Open iMouse 2.0.ps1` (`$consoleExe`, `$kernelExe`) to the ownership pair, record hashes in
a new `deploy-manifest.json`, and keep the previous pair untouched for rollback. Otherwise
write up the failures and stop.

## Part B: Priority 1, guided phone identification, plus atomic saved settings

Priority 4's atomic write is bundled here because identification saves configuration and
`DeviceStore.Save` (`src/iMouse.Kernel/DeviceStore.cs` line 54) still writes the live file
directly with `File.WriteAllText`.

### Goal, in the user's words
A setup flow that confirms the board, the physical phone, the receiver and the calibration,
then saves a friendly name. It exists because of the C241 confusion: nobody could tell which
physical phone a board drove without guessing.

### What already exists, reuse it
- **Identity proof**: the console's Auto-bind (`MainWindow.xaml.cs` around line 1126)
  nudges one board's pointer and measures which phone's screen reacted with
  `FrameRegion.MeanDifference` in a small box around the expected pointer position
  (measured on this rack: about 10 for the right phone, 0.00 for wrong ones). That is the
  mechanism. Wrap it in a flow; do not invent a new one.
- **Stored identity**: `analysis/two-phone-config/devices.json` (phone id, name, board
  vid/pid/uid, geometry), `receivers.json` (DeviceId, BoardPid, receiver Name, Pipe, Port,
  Mac), `pointer-calibration.json` (Pid, origin, pixels per unit). Three files that must
  agree; today nothing checks that they do except `ReceiverFleet.Validate` at startup.
- **Ownership**: identification sends input, so it must acquire a lease like any other
  input, and an operator Stop must abort it. `API.md` is the contract.

### Build this
1. **Identify flow** (console, new drawer page or dialog): Board detected → Physical phone
   identified (pointer nudge, operator confirms "yes, that one moved") → Binding confirmed
   → Receiver matched (the receivers.json entry for that board; show its name so the user
   can pick it in Control Center) → Live video → Calibration verified (one diagonal move,
   box diff at the expected end point) → Name it. One board at a time, other phones untouched.
2. **Friendly name** tied to phone id + board uid + receiver name, shown everywhere the
   phone appears (list, header, tiles, Stop tooltip), with the board suffix beside it.
3. **Broken binding is flagged**: a board that disappears, a phone that reappears on a
   different board, a receiver whose DeviceId no longer matches, or geometry that changed
   shows a visible state (Recalibration required, Binding changed, Board missing) and
   input is refused for that phone until re-identified. No silent redirect, ever.
4. **Atomic configuration**: one writer; write to a temp file, fsync, rename over the live
   file, keep one `.bak`; on load, if the live file is unparseable fall back to `.bak` and
   say so. Add a profile version and last-verified timestamp to each record. Changing a
   binding or geometry invalidates that phone's calibration and remembered pointer state.
5. **Tests**, offline, in the existing suites: identify picks the reacting phone and never
   the non-reacting one; a mismatched binding cannot reach Ready; interrupted save leaves
   a valid old or new file (kill mid-write in the test); concurrent save does not lose an
   update; Stop during identification aborts it and releases the lease; names survive a
   reload.

### Acceptance (from FINISH-CRITERIA gate 3 and the review)
Deliberately mismatched binding cannot become Ready. Names persist after restart.
Identifying one phone leaves the others untouched. A changed or missing binding is clearly
flagged. Interrupted saving leaves a valid file. Concurrent updates are not lost.

### Constraints, unchanged
Keep legacy pacing; do not enable `--precise-movement`; do not run either rejected kernel.
Stage to a new directory; do not overwrite the validated pair or the shortcut. No live
hardware needed for the implementation; after mocks pass, write a short live plan for C24C
and C241 and report readiness. Do not stop vendor services or touch other phones. No
unrelated visual redesign. Record hashes and results.

## After this
Priority 3 (per-phone health with the right recovery step) follows naturally from the flag
states built here. Priority 6 (verify outcomes: did Search actually open) can reuse the
same box-diff measurement. Versioned workflows stay last.

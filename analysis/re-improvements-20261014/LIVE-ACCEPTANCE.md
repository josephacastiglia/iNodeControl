# Bounded C24C acceptance procedure

Prepared offline, 14 October 2026. **Not yet authorized or run.** The active
development goal does not itself schedule a kernel/mirroring interruption.

## First window: navigation and passive replies

Use the new package and its separate C24C-only navigation profile. Confirm
exact hashes, intended endpoint, current C24C identity, fresh mirroring and free
ownership; coordinate with any other controller. Close only an idle installed
console. Snapshot installed binaries/configuration/settings and launch commands
before a graceful, verified release-kernel stop. Never force-kill on timeout.

The operator needs to be available to reconnect mirroring and prepare a
disposable note. This window uses APIs; it needs no PC mouse/keyboard control.
No input to C241. Keep FKA and all phone settings unchanged. Typing and the
missing-space investigation remain deferred; the operator supplies baseline
note text manually if a text-preservation check is possible.

1. Start the verified C24C-only candidate with `command-h`, `direct-fn`, and
   reply observation. Ask the operator to recast C24C. Record the actual FKA
   state without changing it. API success alone never counts as visible success.
2. Test Home from an active disposable note, a benign Settings page, and after
   60 seconds idle. Three attempts per situation, with operator preparation
   between attempts. Require visible Home and unchanged note text. Stop the
   sequence at its first failure. Do not add a Tab or retry automatically.
3. Test App Switcher and Control Centre in that recorded setting, with three
   independent preparations each. Require the intended visible panel and no
   text mutation. A failure is recorded as compatibility failure, not silently
   retried with another shortcut. FKA-Off remains unclaimed if not tested.
4. Record bounded reply observations during the existing relative movement
   and Stop checks. Check that silence, AF, or an identifier does not cause
   a replay, pause or pacing change. Do not derive action completion from counts.
5. Release C24C, stop only verified candidate processes, restore the original
   launch sequence and confirm both phones mirror again. Verify unchanged
   installed hashes and operator-settings content. If restoration is incomplete,
   report immediately and prioritize it over further testing.

Budget: approximately 15–20 minutes of checks plus recasting/restoration. Past
receiver discovery has taken up to 31 minutes. The operator may end the window
at any point; leave enough time for restoration. These API checks do not replace
later real-console button acceptance.

## Separate optional window: A0 capability, moves only

Do not combine this silently with the first window. The absolute profile
requires a separate kernel startup and a further explicitly coordinated swap.
It blocks all clicks, swipes and keyboard commands, including navigation.

On a harmless static Home screen, capture a baseline and make one leased move
to the image centre. Capture the pointer and reply telemetry. If it fails or the
pointer goes somewhere unexpected, stop; no additional A0 commands or fallback.
If centre placement is plausible, compare a small predefined set of interior
targets, once each, with measured image coordinates and known orientation.
Release, Stop/Resume and reacquisition must not replay moves. Restore release.

This can establish preliminary support only. Full absolute controls would need
separate button/drag/cleanup and orientation implementation and validation.
No firmware changes or unsupported mode-negotiation commands are permitted.

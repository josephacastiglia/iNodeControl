# C24C navigation window — 14 October 2026

**Partial result; candidate not promoted.** Home from Settings passed once.
Direct Fn+Up did not open App Switcher with FKA On. The sequence stopped at that
first physical failure, with no fallback or automatic retry.

## Authorization and tested build

The operator explicitly approved a temporary C24C-only kernel swap and mirroring
interruption, was present for recasting, and required unchanged FKA, no C241
input and restoration of the installed release. Typing and A0 probing were
excluded. No PC desktop automation ran. See `authorization.txt`.

The kernel used source `373dd58a6d5c1c541984e9b4ac8b76c9ed3e53e4`, DLL SHA-256
`572252ef7b30783a2d03612fb105099255f95f42b21e46f9b9a39e799e218e2c`,
with `command-h`, `direct-fn`, passive C24C reply observation and no absolute
probe. It was PID 9040, receiver 35328, with isolated C24C-only configuration.
The candidate console was not launched. FKA On and the original appearance
settings were visually verified; no phone setting was changed.

## Results

Times below are New York (UTC minus four); JSON timestamps are 15 October UTC.

| Check | Result | Evidence / limit |
|---|---|---|
| Initial video readiness | Tool refusal; no input | Retained frame showed the mirroring chooser. After the operator returned to FKA Settings, new frames arrived and the page then became quiet. |
| First Home preparation, 22:03:17 | No command sent | The reviewed BMP hash changed because the clock advanced. The tool released its acquired lease. This is not a failed/retried phone command. |
| Home from Settings, 22:03:47 | Preliminary pass, 1 attempt | API 305.8 ms; new frames show Home. The note/idle/repeat cases are untested; this does not close the Home requirement. |
| App Switcher from Home, 22:04:16 | Failed, 1 attempt | API 245.3 ms; new video shows Home with an FKA focus outline, not app cards. The later frame still shows Home. API completion is not physical success. |
| Passive reply monitor | No replies observed | Two transport connections, zero incoming reports; navigation only. No pacing or ACK conclusion follows. |
| Remaining cases | Not run | Stopped at the first navigation failure: no Control Centre, further Home cases, text, movement, Stop or absolute test. |

Each action used a fresh C24C lease and released it. `candidate-end-input.json`
shows free, inactive, not stopped, with generation 3 (including the no-command
baseline attempt). No C241 command was issued. FKA was not toggled, and no
shortcut fallback or additional phone input was used to investigate the failure.

Raw capture/results are in `../re-improvements-20261014/live-navigation/`.
`acceptance-review.json` records the human/visual verdict separately from the
runner's unscored API outcomes. `app-switcher-late.bmp` records the delayed result.
`fka-candidate.bmp` is a retained **mirroring chooser** despite its filename;
only `fka-original.bmp` and `fka-return.bmp` are verified FKA page captures.

## Test-tool correction

The old five-second freshness check wrongly rejected a connected static Settings
page and could also reject the planned 60-second idle preparation. The tool now
accepts an explicitly reviewed baseline BMP hash as an alternative; the captured
baseline must match it exactly before dispatch. Normal execution still requires
fresh video. Both paths require the same process, frame session, binding, lease
and connected pipe, and new receiver frames within five seconds after the one
command. No new frames means unscored evidence and cleanup, never an input retry.
A changing clock can invalidate the hash; the refusal above demonstrates that.

30 fake-API checks pass. Five in-memory guard-removal controls fail their intended
assertions, including the still-image hash and new-frame checks. Results are in
`runner-validation/`. Validation output now uses a new directory and computes
test counts instead of overwriting the earlier 26-test record. No product source
or candidate binary changed. These checks are not physical acceptance.

## Restoration

The candidate stopped gracefully at 22:05:06; its receiver and children exited.
The unchanged normal launcher restored release kernel 45284, receivers 35680
(C24C) / 33936 (C241), and installed console 3180. All 25 protected file hashes,
including operator settings, match the pre-window snapshot. No candidate was
installed or promoted. PIDs are historical and must be rechecked.

Both mirrors are confirmed live with advancing frames after operator recasting,
and both phones are unowned and inactive (`restoration-confirmed.json`). C241
was already offline before the interruption and is now mirroring as well.
Restoration is complete. No further input tests will run in this window.

## Next work

Investigate App Switcher offline before another coordinated test. The sent
sequence matches the documented vendor Fn field without its Tab prelude, but
this run does not establish whether focus activation, report timing or another
phone/board condition explains the failure. Do not add a Tab, blind retry or
claim FKA-On support from the byte-level tests. Home remains preliminary.

`RECAST-FOLLOWUP.md` records the user's original-app reconnect button and the
older local helper. Its fixed C24C row would target Bedroom TV in today's layout;
it was not run. Any replacement must verify the intended receiver by name and
must work with an appropriate observation method when mirroring is absent.

## Preservation

The source checkpoint and a verified local archive are preserved under
`../iMouseXP-2.0-evidence-archive/20261014-navigation-live`. It includes all raw
frames/results, launch and restoration evidence, the exact tested tool source,
and an active-branch Git bundle. See `archive-verification.json` for the final
count, bytes and manifest hash. This is local preservation, not an off-machine
backup. Nothing was pushed or promoted.

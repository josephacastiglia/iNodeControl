# iNodeControl continuation checkpoint — 14 October 2026

Continue in `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-combined-candidate`,
branch `local/combined-candidate-20261012`. The user requested continued progress;
typing/FKA remains deferred. Do not repeat completed suites without a relevant
change or unresolved concern. Nothing is pushed, installed or promoted.

## Latest completed work

- Incoming C24C replies validated through two pointer-only release-API captures:
  23 A1 and two AF reports. No iOS acknowledgement or timing guarantee inferred.
  New kernel source adds opt-in `--hid-replies-pid` counters/state and sanitized
  diagnostic export, default off. Final standalone kernel: 245 tests; helper:
  30 overlapping parser/monitor checks + six argument cases; Python: 23 export
  and three capture-guard tests. Read
  `analysis/hid-input-replies-20261014/REPORT.md`. The full new kernel was not
  started on hardware and the immutable package below is unchanged.
- Original vendor HID protocol investigated with REA/Ghidra, entirely offline.
  Read `analysis/vendor-protocol-rea-20261014/REPORT.md`: Fn field and Tab
  prelude resolved; incoming movement/identifier handlers identified; absolute
  mode unvalidated. Decoder: 13 tests, 221 saved output reports; DLL: 14 static
  evidence checks. No runtime source or packaged binary changed, no rack calls.
- Candidate isolation, actual connected-service hint and two-stream timing
  preflight: 89 runner, 20 diagnostics and 409 headless console checks pass.
  Five unsafe preflights fail on the old runner. Both UIA helper scripts parse;
  neither was executed. Read `analysis/gate6-preflight-20261013/REPORT.md`.
- This extends the existing runner. Normal Disconnect cleanup, failure records,
  process-lifetime guards and opt-in bounded response timing are retained.
- Earlier shutdown/recovery-specific tooling remains covered by its recorded
  41 recovery, 34 frame and 14 lifetime checks. The full kernel suite now has
  245 checks; the immutable packaged kernel retains its earlier 207-test record.

## One current review candidate

Package: `output/staging/combined-timing-20261013`.
Unused preparation: `output/candidate-runs/timing-20261013`.
Kernel SHA-256: `cd0f2129993f93158f7fcf183e590a9c1fe1be4c329de0903a2aef3de1dd7486`.
Console SHA-256: `ebf52cd77bc55e2a5ee4790ffdcd1c47d78783a9e6bf73a44d4500b6597eccc4`.
Package manifest: `9a2b786637f6f2ea262ee0d2a6c082508c0e6e66e67a0a06c070821bdba11b54`.

All 692 package entries verify. Both binaries pass no-window startup validation;
the final prepared-launcher and saved-profile checks pass. Settings are isolated,
explicitly addressed and hover-off. This kernel profile is C24C-only and therefore
cannot satisfy the Gate 6 runner's separate two-stream requirement. No normal
launch or live request ran. Older packages remain immutable historical evidence.
Read `analysis/combined-timing-package-20261013/REPORT.md` and its preparation
record before considering any startup.

## Next priorities

Continue offline correctness/measurement and release preparation where useful.
Reply observation can be enabled for explicitly allowed boards in a future
candidate validation window; do not infer completion, retry, change pacing or
auto-resume based on these uncorrelated reports. Rebuild/package deliberately
before that window; no release or launcher was changed by the reply work.
Do not produce another parallel timing or accuracy harness. Gate 6 still needs
reviewed correct-result evidence and true console-click-to-visible-response
measurement; UIA invocation and a later bitmap do not prove those requirements.
Actual console controls/cleanup, varied-target accuracy, receiver failure/recast,
full-rack mapping/scale, clean-PC loading and final endurance remain open.
`WORK-REMAINING.md`, `FINISH-CRITERIA.md` and `docs/CANDIDATE-ACCEPTANCE.md` retain
those limits. Home/typing/App Switcher defects are not closed by this package.

## Preservation and operating boundaries

Exact sources, test records, binaries, package and unused run are preserved under
`C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261013-timing-preflight-combined`.
Verify `archive-verification.json` in the combined-package record. This is a local
copy, not an off-machine backup. Never delete ignored evidence/worktrees or push
backup branches.

Latest live authority covered C24C-only board reply checks while leaving the
installed release unchanged. That bounded check is complete. C24C was released,
C241 received no input, and all four files protected by the capture retained
their hashes. The same release kernel, console and receivers stayed running.
See the dated run record; recheck before relying on old process/lease state.

No screen control, resumed typing/FKA experiments, C241 input, settings changes,
kernel/receiver restart or deployment is authorized by this note. Any required
physical interruption needs a coordinated window. Hash settings without
printing their contents. New raw reply evidence and exact helper binaries are
archived separately under `../iMouseXP-2.0-evidence-archive/20261014-hid-input-replies`;
verify its recorded checksums before removing any working evidence.

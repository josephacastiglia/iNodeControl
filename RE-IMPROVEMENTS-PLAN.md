# Reverse-engineering improvements: active implementation target

Started 14 October 2026 by explicit user request. Continue in
`iMouseXP-2.0-combined-candidate`, branch `local/combined-candidate-20261012`.
Starting revision: `735b3ad`. The installed release remains unchanged.

## Acceptance target

| Improvement | Starting evidence | Completion requirement |
| --- | --- | --- |
| Home without an inserted Tab | Vendor wrapper adds Tab; direct Command+H test variants already exist | Reuse the existing implementation, validate reliable navigation and unchanged field text, then integrate the supported behavior with clear compatibility handling |
| App Switcher compatibility | Fn is a separate field; FKA-Off failure is recorded | Determine a supported sequence or explicit compatibility limitation; demonstrate behavior in each claimed mode and make the console guidance usable |
| Movement reply/status handling | 23 A1 and two AF live reports; diagnostics implemented | Decode relevant vendor behavior, cover late/missing replies and cancellation, and validate any pacing change against accuracy and cleanup; never infer iOS success from uncorrelated replies |
| Absolute positioning | An A0 coordinate path exists in the host library | Determine protocol prerequisites and board support; implement only a supported, explicitly scoped mode and validate orientation, targets and recovery before making a product claim |
| Matching binaries and symbols | Installed DLL/PDB mismatch found; packaging hashes alone do not check pairing | Reject mismatched, corrupt or malformed symbol pairs before staging and during standalone verification; prove this with real builds and negative controls |

All five need evidence-based dispositions. An untested feature is pending, not
complete. Hardware limitations must be demonstrated and reported; a software
toggle alone does not satisfy functionality. Keep existing implementations and
harnesses; avoid creating another parallel input stack.

## Execution order

1. Finish the offline binary/symbol consistency check and integrate it into the
   existing package flow.
2. Trace the saved vendor reader, status and movement paths further; preserve
   exact evidence and distinguish host assumptions from board behavior.
3. Implement and test the justified control/protocol changes behind explicit
   candidate configuration, preserving ownership, Stop, release and isolation.
4. Produce one reproducible combined candidate and a concise physical acceptance
   procedure, including normal-console usability and cleanup.
5. Coordinate any required phone-setting changes or kernel/receiver interruption
   with the operator. Use C24C only for live input; do not promote or deploy.

## Working boundaries

Checkpoint: `combined-re-improvements-20261014` integrates the source at
`373dd58`. Its 698 entries verify; both exact managed pairs pass the new symbol
guard. The final kernel passes 290 mock checks and the console 411 headless
checks. The 74 packaging checks and five negative controls are separate evidence,
not physical acceptance. A fresh C24C-only isolated profile validates offline.

Home command-h/direct-Fn navigation and a separate move-only absolute probe are
prepared, not live-validated. Reply handling remains observation-only: the new
vendor trace showed identifier and movement signals share an event, so no ACK
wait or pacing change is justified. App Switcher FKA-Off support stays open.
Read `analysis/re-improvements-20261014/REPORT.md`, `PROTOCOL.md` and
`LIVE-ACCEPTANCE.md`. A coordinated navigation window was requested in chat;
do not treat an unanswered question as authorization. Physical acceptance remains
pending. `COMPLETION-AUDIT.md` in that record identifies the exact missing proof
and the coordinated window required to resume meaningful work.

Offline source work, tests, builds, local commits and preservation can continue
autonomously. No desktop control or speculative raw USB writes. All live input
must use the existing ownership/serialization/cancellation safeguards. C241 must
receive no input. Keep the installed release, launcher, settings and receivers
unchanged outside an explicitly coordinated temporary test window. Typing/FKA's
missing-space investigation remains deferred; compatibility work must not silently
reopen it or change phone settings.

The active goal is tracked in this Codex chat. Record meaningful checkpoints
here and in the dated evidence reports; do not mark the goal complete while
required validation remains.

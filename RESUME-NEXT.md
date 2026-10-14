# iNodeControl — continuation checkpoint, 13 October 2026

Work resumed at the operator's request. Fleet shutdown is repaired and packaged; later Gate 6 failure handling and console response timing preparation are verified offline. Do not repeat completed checks without a relevant change. Nothing is promoted, deployed or pushed.

## Current work

- Directory: `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-combined-candidate`.
- Branch: `local/combined-candidate-20261012`.
- Shutdown repair commit: `8cc4678`. Read `analysis/fleet-shutdown-20261013/RESUMED-REPORT.md`.
- Five targeted failures reproduced on the old source. Final results: 41 recovery, 207 kernel, 34 frame and 14 fake receiver-lifetime checks pass.
- Screenshot-client repair is still verified: 382 console, 44 preview, 22 wall checks and the recorded local transfer probe. See `analysis/screenshot-client-20261013/REPORT.md`.
- Latest tool repair: visual misses stop the Gate 6 runner, lease failures and cleanup are recorded, and evidence cannot overwrite earlier runs. All 35 regressions and its self-check pass. Read `analysis/gate6-failure-handling-20261013/REPORT.md`.
- Latest implementation: opt-in console response timeline, bounded diagnostic export and offline reader in the existing Gate 6 runner. Console 402, preview/timing 56 and runner 44 checks pass; shared cases overlap. Read `analysis/response-timing-20261013/REPORT.md`.
- Its exact standalone console is `analysis/response-timing-20261013/console-final/`, with source/build manifest. It is not yet in the combined package below. No live or UI-control test ran.
- Latest tooling: console-owned cleanup through normal Disconnect, including uncertain helper outcomes and process-lifetime checks; 65 runner checks pass. Read `analysis/gate6-console-cleanup-20261013/REPORT.md`. This is offline preparation, not validated desktop cleanup.
- Next useful offline work: explicit candidate-isolation/preflight checks, UIA preparation and reviewed correctness evidence for timing. Physical click-to-display timing is still not established by the opt-in bitmap timeline. Keep extending the existing runner rather than adding a parallel harness. No missing-space experiments should resume.

## One current candidate

Package: `output/staging/combined-shutdown-20261013`.
Unused run: `output/candidate-runs/shutdown-20261013`.
Kernel SHA-256: `cd0f2129993f93158f7fcf183e590a9c1fe1be4c329de0903a2aef3de1dd7486`.
Console SHA-256: `1eaaf9beb41987c21f70a1ab5f79529bb1eb5d5f0ce753a4aae3078221b9e554`.

All 689 package entries and source/runtime records verify. Both exact binaries validate saved C24C-only settings offline, and the strict prepared-launcher check passes. The profile is isolated, explicitly addressed and hover-off. Nothing was launched normally. Older packages are preserved and must not be mistaken for this one.

Read `analysis/combined-shutdown-package-20261013/REPORT.md`, `PROGRESS.md`, `WORK-REMAINING.md` and `docs/CANDIDATE-ACCEPTANCE.md` before choosing the next issue. No release gate was advanced by the offline checks. Remaining physical work includes actual console controls/cleanup/diagnostics, varied-target accuracy, receiver shutdown/recasting, latency/video under load, full-rack mapping/scale and endurance. Clean-PC/runtime release clearance remains open. Continue useful offline work where possible; do not repeat passed checks without a relevant change or unresolved concern.

## Preservation and boundaries

Exact repair records, builds, combined package and unused run are preserved under `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261013-shutdown-combined`; verify the receipt in the combined-package record. Earlier archives and the original draft are intact. These are local-disk copies, not off-machine backups.

No screen control, resumed typing/FKA work, C241 input, settings changes, kernel/receiver restart, deployment or promotion is authorized by this note. Coordinate any required physical window separately. No live rack status was requested during this resume; the last physical restoration record is historical. Recheck current state before authorized hardware work. Installed files and settings match the recorded baseline. Never delete worktrees/ignored evidence or push backup branches.

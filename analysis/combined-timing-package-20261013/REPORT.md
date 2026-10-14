# Combined timing candidate prepared offline

13 October 2026. This is a preserved review package, not an installed release.

## Result

The new package combines the last verified shutdown/recovery kernel with the
latest console: bounded image downloads, the opt-in response timeline and actual
connected-service tooltip/accessibility hint. Earlier input cleanup and candidate
settings isolation are included. The existing Gate 6 runner has explicit
candidate and workload preflight; it is a separate tool, not a second product.

| Item | Verified result |
|---|---|
| Package | `output/staging/combined-timing-20261013` |
| Inventory | 692 files; 186,057,041 bytes |
| Kernel DLL | `cd0f2129993f93158f7fcf183e590a9c1fe1be4c329de0903a2aef3de1dd7486` |
| Console DLL | `ebf52cd77bc55e2a5ee4790ffdcd1c47d78783a9e6bf73a44d4500b6597eccc4` |
| Package manifest | `9a2b786637f6f2ea262ee0d2a6c082508c0e6e66e67a0a06c070821bdba11b54` |
| Native preservation | All 610 receiver/runtime/source entries match the preceding package |
| Earlier package | `combined-shutdown-20261013` remains intact and verified |
| New console checks | 409 headless self-tests, zero build warnings/errors |
| Timing/diagnostics checks | 89 runner and 20 diagnostics tests; self-check and parse-only helpers pass |

The console manifest records the exact source including uncommitted work at
build time. Full source and binaries are retained in the package; historical
kernel/native validation is retained in their provenance. Tests from different
builds are not added together as a new physical acceptance total.

## Preparation

`output/candidate-runs/timing-20261013` is a new, unused C24C-only run. It uses
copied configuration, an explicit port-9913 endpoint, separate settings and hover
tracking Off. Both exact binaries passed their no-window `--validate-startup`
checks. The console validator ran from a separate byte-verified copy so its
report did not alter the strict prepared inventory. Final launcher `-CheckOnly`
passed. The timing runner's saved-profile validator also accepts these actual
files without inspecting a process or contacting a service.

No listener, receiver, application window or phone input started. C241 is absent
from this prepared kernel configuration. All 25 protected installed static files
and the source configuration still match their baseline hashes. The candidate
profile stayed unchanged through validation.

This is a smoke profile, **not the two-stream Gate 6 workload**. Later timing
work requires both declared streams, a verified exact candidate process and
coordinated setup. The saved-profile check cannot establish active connection,
physical identity or free ownership; it records those limits explicitly.

## Preservation and remaining acceptance

`archive_run.py` preserves the preflight sources/evidence, this package and its
unused preparation outside the worktree, verifies every copy and re-verifies the
relocated package. The resulting `archive-verification.json` records the exact
local commit, counts and checksums. This is another local-disk copy, not an
external backup.

No deployment, push, promotion or gate sign-off occurred. Physical console
controls/cleanup, true click-to-correct-display timing, varied targets, native
recovery/recasting, full-rack scale, final endurance and clean-PC/runtime release
clearance remain open. Home/App Switcher defects remain; typing is deferred.
No evidence from this offline package should replace those acceptance runs.

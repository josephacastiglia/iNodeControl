# Offline reliability run — 11 October 2026

Use this record to review completed tooling work and resume the remaining offline backlog. Diagnostics, build verification, endurance analysis, and soak safeguards are repaired and tested. The missing-space issue remains deferred. No physical release gate is signed off by this run.

## Completed work

The following results come from the recorded offline checks:

| Area | Result | Validation |
|---|---|---|
| Diagnostics | Partial exports survive unavailable components; explicit candidate settings take precedence; timing isn't guessed; managed console DLL identity is included; repeated exports don't overwrite | 18 tests pass |
| Build verification | Checks source bytes and all output files; detects changed assemblies, added inputs, and missing files; rejects unsafe paths | Nine tests pass |
| Endurance analysis | Failed interactions produce a failing status; receiver restarts aren't counted twice; unavailable video is separated from live no-frame gaps; console restarts split sessions | 15 tests pass |
| Soak safeguards | Explicit live targets required; occupied/paused/unknown phones refused; no automatic Resume; failed sends stop; failure evidence retained; old telemetry protected | 16 tests pass |
| Earlier timing repair | Bounded helper output/process waits and exact completion checks remain passing | 22 tests pass |

**Total: 80 passing offline tests, including 58 added in this run.** `VALIDATION.txt` preserves the final command outputs. Source changes are local and uncommitted; nothing is pushed, promoted, or deployed.

## Repeated scratch builds

The main checkout at `01fb669` builds with SDK `8.0.424`. Kernel and console each build twice with `--no-restore`, Release configuration, `-t:Rebuild`, and shared compilation disabled. Both passes have zero warnings and errors.

The comparison records cover the following files:

| Project | Source inputs | Output files | Second build comparison |
|---|---|---|---|
| Kernel | 19 | Six | Every byte matches |
| Console | 14 | Five | Every byte matches |

`kernel-build.json` and `console-build.json` record the inputs and output hashes. `build-a/` and `build-b/` hold the scratch outputs. No application binary is launched. This proves repeatability in this checkout and environment; it doesn't establish installed-release equivalence, cross-PC reproducibility, or dependency attestation.

The installed kernel DLL, console DLL, and UxPlay executable still match their recorded release hashes. Existing release folders, launchers, and phone settings aren't changed.

## Saved endurance evidence

The repaired analyzer reads the September telemetry into `endurance-reanalysis/`, leaving its source files unchanged. It finds two sessions. The selected resumed session has 1,272 samples and **64 failed or unverified interactions out of 64 attempts**. It reports `failed`, returns exit code one, and keeps `gate10_acceptance: false`.

The source checksums are preserved in `endurance-reanalysis/source-checksums.json`. Memory growth, earlier stream gaps, and complete 8-hour/24-hour acceptance remain open; this run doesn't fix or repeat those physical tests.

In that selected session, receiver private-memory slopes are about 18.3, 19.3, 18.5, 18.5, and 18.2 MB/hour. The aggregate is about 92.8 MB/hour, versus roughly flat kernel and console trends. The last 30-minute aggregate private-memory slope is about 56.9 MB/hour. These are process-level observations; they don't establish a leak mechanism or prove a resource budget violation after a declared warm-up.

A static review of `renderers/imouse_frame_pipe.h` finds that normal and error paths release pulled samples, mapped frames are unmapped, and one reusable BMP buffer grows only with larger frame dimensions. The inspected source doesn't demonstrate a continuous per-frame ownership leak. That isn't proof the receiver is leak-free or that the inspected native source exactly matches the installed binary. No speculative receiver patch or native rebuild was made.

## Test-isolation incident and restoration

One initial soak regression was insufficiently isolated. At 23:26 EDT on 11 October, it reached the old read-only sampler, enumerated host window/process metadata, and attempted a read-only kernel status request. Windows blocked the socket with error `10013`. The test didn't reach the interaction phase or send phone input.

That test appended one 509-byte sample to historical `telemetry.jsonl` and left its PID marker. Before repair, the original prefix matched the previously saved checksum and `status.json` was unchanged. The added row is preserved in `test-isolation-incident/added-test-sample.jsonl`. The historical telemetry was restored byte for byte to its original 7,560,461 bytes, and the test-owned PID marker was removed. Both source checksums match the pre-test record.

The repaired test boundaries replace network access, fleet binding, and host/UI sampling, and redirect default output to temporary workspace fixtures. The final 80-test run uses those repaired boundaries. No focus, mouse, keyboard, phone-setting, or receiver/kernel control action runs. The incident record is `test-isolation-incident/record.json`.

## Remaining work

Continue with the existing accuracy harness consolidation, offline display accounting, and recovery fault simulations. Physical targeting, navigation defects, rack expansion, receiver rediscovery, and final endurance runs require later coordinated validation. The deferred typing issue remains a known release gap.

For repeatable offline commands and changed CLI behavior, see [Verify tooling without operating the rack](../../tools/OFFLINE-VERIFICATION.md). Keep prior live evidence, unrelated working-tree changes, and the unpushed redaction backup intact.

## Local preservation

The run archive is `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261011-offline-backlog\`. It preserves the run records, both scratch builds, the recorded project sources, changed tooling and tests, progress documents, and the tracked diff. `SHA256SUMS.txt` lists the preserved files. This local archive isn't uploaded or a promoted release.

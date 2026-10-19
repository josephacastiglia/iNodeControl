# iNodeControl: remaining work

Updated 12 October 2026. The missing-space issue is **deferred**, not fixed. Work continues offline without screen control or phone input.

The two-phone system has working foundations: independent kernel and mirroring, selected-phone control, Stop, timeout recovery and isolated candidate settings. The full 19-phone release is not signed off. Gates 1–2 have scoped pass records; Gate 4's 1,000 taps passed only for two phones at one target.

| Area | What remains | Work available offline |
|---|---|---|
| Accurate control and identity | Identify 14 unbound boards; varied targets, interruption recovery and checks across the rack | Consolidate the existing Gate 4 harness and validate configuration checks |
| Everyday controls | Home inserts Tab; App Switcher with FKA Off; remaining console acceptance cases; deferred first-space loss | Source fixes and simulated input tests; physical behavior still needs later validation |
| Responsiveness | Correct console-action-to-visible-response timing, 100 observations per category/profile under load | Strengthen timing, correctness and failure handling in the existing runner |
| Video and recovery | Honest displayed-frame accounting, freezes, receiver failure/retry exhaustion and reliable recasting | Simulated faults and display/recovery logic tests |
| Rack scale and endurance | Validate 2 → 4 → 8 → 19 phones; investigate memory growth, interaction conflicts and freezes; final 8-hour/24-hour runs | Analyze existing logs and improve unattended-run preflight/reporting |
| Diagnostics and release | Reliable exports, build/source provenance, reproducible release, setup/update/recovery/rollback instructions | Mock collection and export tests, build manifests and packaging preparation |

## Current offline priority

1. **Completed:** repair the timing runner's unbounded console-helper wait and false completion check. All 22 offline regressions and its self-check pass. This is test-tool progress, not a Gate 6 pass.
2. **Completed offline:** diagnostics repairs and 18 tests; source/build verification and nine tests; two byte-identical scratch builds of each C# project.
3. **Completed offline:** endurance reporting and 15 tests; safer live-run opt-in, ownership checks, failure handling and 16 tests. The saved resumed block is correctly marked failed (64/64 input failures). Recorded memory growth is concentrated in receivers; its cause remains open.
4. **Completed offline:** reproduced the native receiver build (all 34 objects match; executable matches except timestamps/checksum) and fixed a proven leak in periodic report parsing. Eight native regression cases and eight tool tests pass; the patched scratch receiver builds. Full-rack memory improvement is still unverified. See `analysis/receiver-memory-20261012/REPORT.md` for synthetic video results and scope.
5. **Completed offline:** consolidated the accuracy harness and repaired receiver supervision. Fourteen accuracy scenarios, 17 evidence guards, 12 focused recovery checks and 70 kernel self-tests pass. The scratch kernel builds cleanly; full physical accuracy and recovery acceptance remain open. See `analysis/accuracy-recovery-20261012/REPORT.md`.
6. **Next:** strengthen frame freshness/display accounting and failure diagnostics with synthetic tests. Physical validation remains separate.

Offline work can prepare and repair these areas. Full-rack behavior, physical targeting, real display latency and final endurance acceptance still require later coordinated hardware runs. No desktop-control window, restart, deployment or promotion is authorized by this document.

The detailed requirements remain in [FINISH-CRITERIA.md](FINISH-CRITERIA.md); current evidence and history are in [PROGRESS.md](PROGRESS.md).

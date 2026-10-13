# Combined shutdown and image-download candidate

13 October 2026. Review-only assembly of already tested binaries; no desktop control, rack API call, listener, receiver, phone input or installed-release change. Nothing deployed or pushed.

## Package

`output/staging/combined-shutdown-20261013` contains **689 inventory files, 185,999,726 bytes**, plus `package.json`. The standalone package verifier and native runtime verifier pass. All **610 receiver/runtime/source entries** compared with `combined-recovery-20261013` are unchanged; that older package remains intact and passes verification.

| Component | SHA-256 |
|---|---|
| Package manifest | `74b04d5f41a59a734f141d1e0661694916c741ee7269f4620129f3ed0c57ccdd` |
| Kernel DLL | `cd0f2129993f93158f7fcf183e590a9c1fe1be4c329de0903a2aef3de1dd7486` |
| Console DLL | `1eaaf9beb41987c21f70a1ab5f79529bb1eb5d5f0ce753a4aae3078221b9e554` |

The kernel includes the fleet shutdown repair and all prior recovery work. Its evidence is in `analysis/fleet-shutdown-20261013/RESUMED-REPORT.md`: recovery 41, kernel 207, frame 34 and fake receiver-lifetime 14 checks pass. The console is the exact screenshot-client repair build from `analysis/screenshot-client-20261013/`: console 382, preview 44 and wall 22 checks, plus the recorded real loopback transfer probe. Those console suites were not rerun during file assembly. No new product compilation was performed by the packaging script.

Both component manifests and source snapshots are embedded, along with the native receiver/runtime and existing source/notice limitations. The launcher's error-reporting source remains inert text, not an installed or executable launcher. These checks establish package consistency, not combined physical acceptance or redistribution clearance.

## Offline preparation

`output/candidate-runs/shutdown-20261013` is a fresh unused preparation with only C24C's saved binding/calibration/receiver, an explicit port-9913 endpoint, isolated console settings and hover tracking off. C241 is absent. Validation copies stay separate from the pristine launch folder so generated reports do not invalidate its strict inventory.

Both exact binaries passed saved-configuration validation with no hardware, listener, receiver, connection or settings write. The final launcher `-CheckOnly` passed. See `preparation.json`, `run-inventory.json`, startup validation records and `console-final-check.txt` for the complete result. Installed static binaries, configuration, launcher and operator settings match the restoration baseline; active receiver logs are excluded from the static comparison.

An initial preparation command was accidentally issued while package assembly was still running. It refused at the first integrity check because `package.json` was not yet present. No run folder was created and no validation child or service started. `preparation-early-refusal.txt` records the orchestration error. The accepted preparation was issued after package assembly completed; no integrity check was bypassed and no partial run was reused.

## Preservation and next work

`archive_run.py` preserves the exact repair records/builds, new package, unused preparation, supporting source and focused commits under `iMouseXP-2.0-evidence-archive/20261013-shutdown-combined`. It verifies every copied hash, the relocated package and prepared inventory. `archive-verification.json` is the completed receipt; the script and intended path alone are not proof an archive exists. This is local-disk preservation, not an off-machine backup.

The next acceptance window must use this exact package or a subsequently verified replacement, not an older candidate with similar names. Physical shutdown/recasting, actual console controls/cleanup/diagnostics, varied-target accuracy, live latency/video, full-rack scale and endurance remain open. No new kernel swap, desktop-control window or C241 input is authorized here. Home and App Switcher limitations remain; typing/FKA work stays deferred. Do not rerun the completed missing-space experiments.

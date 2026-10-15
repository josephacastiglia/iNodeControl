# Integrated improvements checkpoint

14 October 2026. Source: `373dd58` on `local/combined-candidate-20261012`.
Goal active; physical completion is still pending. Nothing installed or pushed.

## Delivered

| Area | Implemented result | Remaining requirement |
|---|---|---|
| Home | Reused command-h/command-wake; added directly encoded Fn+H choice, no Tab in these candidate modes | Reliable visible navigation and unchanged field text on C24C, then actual console acceptance |
| App Switcher | Optional direct Fn+Up without Tab; Fn+C likewise; console explains the FKA limitation | Validate in each claimed phone mode; FKA-Off support remains unestablished |
| Board replies | Prior optional reader integrated; console diagnostic export now retains bounded observations and selected modes | Full candidate live observation; never treat an uncorrelated reply as action success |
| Absolute positions | One-board move-only A0 probe through normal leased/reset/move paths; activation refused | Demonstrate hardware support before implementing full absolute controls |
| Packaging | New stages and standalone verification reject mismatched DLL/PDB identities or contents | Completed within this new package; clean-PC/release acceptance remains separate |

Normal defaults remain unchanged. There is no automatic shortcut fallback,
movement retry, phone-setting change or A0 input in normal operation. The new
vendor trace does not justify changing movement pacing: identifier and movement
signals share an event, and AF's decoded reset delay is already used here.

## Exact combined package

`output/staging/combined-re-improvements-20261014`: **698 files, 186,167,075 bytes**.

- Kernel DLL SHA-256: `572252ef7b30783a2d03612fb105099255f95f42b21e46f9b9a39e799e218e2c`.
- Console DLL SHA-256: `609a95c946faed7d38d54fc8c040bfbb39c6df0948da5127c0cb5714d76e96ed`.
- Package manifest SHA-256: `7d8f145c1726326fa1cbd419195399e6dde8e97bd65535f1f3b452e482f9689d`.
- All 610 native receiver/runtime/source entries match the preceding package.
- Both managed symbol pairs pass identity and content-checksum validation.
- Embedded package and native-runtime verifiers pass independently.

The earlier immutable packages remain intact. The fresh run at
`output/candidate-runs/re-improvements-20261014` has C24C-only configuration,
explicit endpoint, isolated console data and hover tracking Off. Both exact
binaries pass no-window startup validation; launcher CheckOnly passes. A separate
absolute-probe argument profile also passes validation. Neither has been launched.
Fresh before/after hashes confirm preparation left protected installed files and
operator settings unchanged. No desktop control or rack API was used this session.

## Validation

- Release builds: zero warnings/errors.
- Exact final kernel: **290 mock self-tests**; exact console: **411 headless tests**.
- Packaging: 11 symbol, 32 managed-package, 22 native-package and nine manifest
  checks, **74 total**. Three new protections fail when symbol validation is disabled.
- Navigation/probe focused baseline: 33 checks. Reintroducing Tab and removing
  the probe activation guard each fail the intended assertion in isolated copies.
- Vendor follow-up: 13 fixed-offset instruction checks against the recorded DLL.

These counts overlap existing suites and are not additive release-gate passes.
Mock named-pipe and atomic-replacement tests needed permission-reviewed reruns
after sandbox access errors. Final tests passed. No UI suite was run.

## Continuation

The existing Gate 5 runner is now prepared for a single C24C navigation action
per invocation. It uses the current lease transport, verifies the exact candidate
and mapping, preserves failures, and requires explicit live execution. Its
default plan verified the unused run locally. All 26 fake-API tests pass, and
three removed-guard controls fail their assertions. Historical evidence is
unchanged. Read `NAVIGATION-RUNNER.md`; no new build or phone test ran for this
tooling follow-up.

`LIVE-ACCEPTANCE.md` defines the next coordinated C24C navigation window, using
APIs and unchanged FKA. The operator must be available for preparation and recasting.
The separate absolute test is not bundled into that permission request.
The missing-space investigation remains deferred. No feature is called physically
complete until its visible behavior is demonstrated on the exact candidate.

The raw vendor analysis, builds, negative controls, package and unused profile
are preserved by `archive_run.py` outside the worktree. Check
`archive-verification.json` before removing any local evidence. The archive is
on this PC, not an off-machine backup.

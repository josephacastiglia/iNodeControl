# Gate 6 failure handling — 13 October 2026

**Result:** offline runner repair, not product acceptance. The combined candidate and installed release are unchanged. No phone API, Windows UI helper, screen control, restart or phone input was used.

## Findings and repair

| Failure | Previous behavior | Current behavior |
|---|---|---|
| API succeeds, expected visual response is absent | Sent a Home dismissal and could continue later trials | Saves the miss, sends no dismissal, aborts before the next trial |
| Lease renewal fails | Exception escaped before a trial record was written | Saves an unsent failed trial with `failure_stage: renew`; attempts known-token release |
| Acquisition reply fails after one token was parsed | Acquisition was outside `finally`, leaving that token unreleased | Acquisition is covered by cleanup; only known tokens are released |
| Acquisition times out without a token | No durable cleanup outcome | Records unconfirmed acquisition and no known tokens; does not guess, retry or claim that no lease exists |
| Release fails | Console output only; original failure could be obscured | Preserves original abort plus separate cleanup error and remaining known phones; exits unsuccessfully |
| Run name reused or artifact escapes to a neighboring run | Could overwrite previous evidence | Refuses before reusing/creating an invalid output location or writing another run's files |

`run-state.json` holds status, phase, trial count and cleanup-failure state. `cleanup.json` records acquisition/release certainty and phone IDs, without lease tokens. Release is attempted before final evidence writes. A release acknowledgement is evidence from the API, not proof of the physical phone's state. Console-owned leases are explicitly recorded as unmanaged by this runner.

## Verification

- Base: `b1069f3` on `local/combined-candidate-20261012`.
- `before/` preserves the original runner and the initial ten new regression cases. All ten cases fail against the old runner (the log has eight assertion failures, including two subcases in one test, and three errors from missing records/uncaught renewal).
- The first repair passes 32 tests and the self-check.
- Three additional cases exercise normal acquire/renew/release, malformed-response parsing through the actual lease functions, and an operator interrupt.
- **Final:** 35 tests pass; the built-in self-check passes. `verification.json` records commands, exits and final source hashes. Exact source copies and logs are preserved here.
- New lifecycle tests forbid both transport and UI child creation, and assert neither boundary was called. Existing helper tests launch only harmless Python children for bounded pipe/exit checks.

Commands from the repository root:

```powershell
python analysis/gate6-release-validation-20260916/test_run_gate6.py -v
python analysis/gate6-release-validation-20260916/run_gate6.py --self-check
```

## Remaining scope

The runner still times API requests or UIA invocation to **kernel screenshot arrival**, not the actual console display. Search/Home classification is heuristic; App Switcher and Control Centre detect change without proving correctness. Console-owned lease cleanup, repeated UIA preparation and full live preflight remain incomplete. An uncertain acquire without a token needs ownership inspection/expiry; this repair does not bypass ownership. These limitations still prevent unattended Gate 6 acceptance.

The full release also needs current-build controls, varied-target accuracy and all bindings, physical recovery, actual display/video measurements, 4/8/19-phone scale, final 8-hour/24-hour endurance and clean-PC release checks. Typing/FKA work remains deferred by the operator.

## Preservation

Tracked changes are limited to this test runner, regressions, evidence and progress documents. Historical September evidence is preserved. The verified product package remains `output/staging/combined-shutdown-20261013`; no product rebuild or promotion was performed. `preservation.json` records static installed-file checks and the local archive receipt after they complete. Local archival is not off-machine backup.

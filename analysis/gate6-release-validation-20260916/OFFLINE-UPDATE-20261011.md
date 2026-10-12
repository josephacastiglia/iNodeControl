# Gate 6 helper deadline repair

11 October 2026. Offline test-tool work only; Gate 6 is not passed.

## Problem and change

The console helper read stdout synchronously before reaching `wait(timeout=20)`. If stdout never closed, the timeout never ran. Its completion check also accepted the substring `ok`, including a line saying `not ok`.

The existing runner now reads output through a background reader while the caller enforces one 20-second deadline across output and process exit. It preserves the invocation timestamp as soon as it arrives. Successful completion needs that timestamp, an exact `ok` line and exit code zero. Output is limited, and failed helpers are killed and reaped with bounded waits. Cleanup targets only the helper process, never the console, kernel or receivers.

An input already accepted by the console may continue after its helper exits. Timeout and incomplete output therefore stay unknown outcomes; they cannot trigger a retry or API fallback. Console-owned lease cleanup remains separate unfinished work. A reader whose pipe stays inherited elsewhere cannot extend the caller's wait; it remains a daemon until the pipe closes.

## Validation

| Check | Result |
|---|---|
| Open-stdout deadline regression, before repair | Failed: caller did not return within the test deadline |
| Exact completion regression, before repair | Failed: `not ok` counted as success |
| Complete offline regression suite, after repair | 22 passed, including 10 new helper tests |
| Existing built-in self-check | Passed |
| Real Python child with streamed timestamp | Timestamp observed before child exit |
| Real silent Python child | Timed out, killed, reaped and pipe closed |

The new tests also cover EOF with a hung process, nonzero exit despite `ok`, missing timestamp, excessive output, invalid timeout and cleanup failure. The existing 12 evidence-integrity regressions still pass. No PowerShell UI helper, screen control, phone API, kernel/receiver restart or operator-settings access was performed. Tests do not claim console presentation timing or physical input acceptance.

```powershell
python analysis/gate6-release-validation-20260916/test_run_gate6.py
python analysis/gate6-release-validation-20260916/run_gate6.py --self-check
```

Changes are uncommitted in `local/coordinator-work`, alongside the earlier runner repairs. Historical September run records are unchanged. The missing-space investigation is deferred at the operator's request.

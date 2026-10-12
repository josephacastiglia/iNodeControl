# Gate 6 timing tool — preparation, not acceptance

Updated 11 October 2026. The historical September files in this directory are unchanged. Current work extends `run_gate6.py`; it does not replace the old evidence or create a second harness.

## What the tool measures

| Field | Meaning |
|---|---|
| `first_visible_ms` | First changed frame arriving from the kernel screenshot endpoint |
| `first_correct_ms` | First changed frame matching the expected state according to the current heuristic classifier |
| `settled_ms` | Two successive small frame differences while the expected result remains visible; transition-only for unclassified categories |
| `dispatch_ms` | API request round-trip time; unset for UIA |
| `ui_invoke_elapsed_ms` | UIA helper time after invocation began; not kernel command completion |

UIA uses InvokePattern rather than a physical mouse click. Kernel screenshots do not establish when the console presents a frame. These measurements alone cannot pass Gate 6. Search/Home classification is heuristic; App Switcher/Control Centre currently have no correctness classifier.

## Repairs and validation

- Console rejection never falls back to direct API input. Search requires explicit `--api-only` before any live preflight.
- An unchanged target screen cannot prove that a command worked. Frames arriving after the observation deadline cannot count as hits.
- A stable wrong screen no longer ends polling before the correct result appears. Correctness-checked percentiles use the correct-result time, keeping first-change time separately.
- Failed commands remain failed even if the screen changes. Error rows and poll records are saved; the run stops before the next trial, and a failed measured action is not followed by a Home dismissal.
- Percentiles are separate for each phone and input route. Misses remain in the sample with the existing 5,000 ms penalty. Mixed-route/phone category percentiles are unset.
- UIA Home requires a prepared Search screen. It does not acquire an API lease to create that setup or count repeated Home-on-Home actions as successes.

The 10 October repair had seven regressions fail before it and 12 passing tests afterward. The 11 October extension adds 10 helper-lifecycle tests: two failed before the new repair, and **all 22 offline tests now pass**, along with the built-in self-check. Tests replace phone/action boundaries; two cases launch only harmless Python child processes to exercise real pipes. No phone input, live services, Windows UI helper or desktop automation is used.

The console helper now has one 20-second deadline covering streamed stdout and process exit, with bounded cleanup of that helper only. A hung pipe cannot bypass the deadline. Invocation time is retained before process completion. Success requires a timestamp, zero exit code and an exact `ok` line; `not ok` is rejected. Timeout or incomplete output is an unknown input outcome, never an instruction to retry or switch to the API. Terminating a helper does not cancel input already accepted by the console. See [OFFLINE-UPDATE-20261011.md](OFFLINE-UPDATE-20261011.md).

From the repository root:

```powershell
python analysis/gate6-release-validation-20260916/test_run_gate6.py
python analysis/gate6-release-validation-20260916/run_gate6.py --self-check
```

## Remaining work before live acceptance

1. Measure the console's actual presentation path and validate that the changed region represents the requested result. The current broad frame classifier is insufficient for general layouts, wallpapers and animations.
2. Prepare every UIA Home trial through the intended console workflow, without mixing in API input. At present, another Home trial stops unless Search is prepared again.
3. Complete and validate release/restoration for leases owned by the console, including uncertain helper outcomes. The helper's stdout and process waits are now bounded; this does not cancel an action already accepted by the console or release its lease.
4. Verify candidate identity, isolated settings, ownership, per-phone targeting and the required second streaming phone in a coordinated live window. The existing preflight checks target receiver frames, not all these conditions.
5. Run the written Gate 6 workload and sample count, keeping failures and measuring the correct response. No live run was performed on 10 October.

Known Home/typing defects still make unattended navigation unsuitable. On 11 October the operator deferred the missing-space investigation and requested offline work without screen control. Continue preparation for other gates while retaining that unresolved defect; this tool is not authorization to operate either phone or restart the rack.

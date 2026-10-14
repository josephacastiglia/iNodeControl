# Gate 6 timing tool — preparation, not acceptance

Updated 13 October 2026. The historical September files in this directory are unchanged. Current work extends `run_gate6.py`; it does not replace the old evidence or create a second harness.

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

The 13 October repair extends failure handling to **visual misses without transport errors**: these now stop the run, retain the missed sample and send no Home dismissal. A renewal failure is saved as an unsent trial. Acquisition is inside cleanup coverage, so tokens parsed before a malformed response are still released. `run-state.json` records completion/abort and phase; `cleanup.json` distinguishes confirmed release, unconfirmed release and unknown acquisition without storing tokens. That first repair covered API tokens only; console-owned cleanup is covered by the later extension below. New run directories cannot reuse earlier evidence, and output cannot escape into another run.

All **35 offline regressions** and the built-in self-check pass. Ten initial new cases fail against the preserved old runner; three additional checks cover normal completion, real partial-response parsing and operator interruption. See [the failure-handling report](../gate6-failure-handling-20261013/REPORT.md). No live workload or release gate was passed by this work.

From the repository root:

```powershell
python analysis/gate6-release-validation-20260916/test_run_gate6.py
python analysis/gate6-release-validation-20260916/run_gate6.py --self-check
```

## Console-owned cleanup, 13 October

UIA mode is for a dedicated candidate only: **it now disconnects that console after an attempted input**, whether the trial succeeds, misses, throws or is interrupted. It leaves the window open and disconnected; it does not reconnect or reopen the installed console. A failure before any UIA action is labelled `no_action_attempted`, which makes no claim about an existing lease.

The runner marks possible ownership before calling the helper, since a missing reply cannot show that nothing reached the console. Cleanup opens Settings and invokes Disconnect once, through the normal console path that cancels its queue and releases its own tokens. It waits for `Disconnected`, `Input released` and a disabled Disconnect button. It then reads `/api/input/status`: every planned target must explicitly be unowned, inactive, not releasing and without a release failure. Either source missing or uncertain makes cleanup fail; neither a free status alone nor successful helper dispatch is sufficient. No retry, forced release, Stop, Home, API input fallback or process kill is used for the console. Only a hung helper can be terminated.

Each helper checks the exact bound executable and creation FILETIME, plus the window's process identity. An explicitly supplied executable must match even for the old candidate-5 path. Selection and mirror guards still apply, including during cleanup; changed selection/identity or unavailable controls produce an unconfirmed record rather than an override. `manifest.json` records the bound process identity; `cleanup.json` keeps the disconnect and status observations separate. Original trial failures survive cleanup failures.

**65 offline regressions pass**, including 21 new checks. The first six new cases fail on the preserved old runner. Both generated helper scripts pass PowerShell parsing without execution. No UIA interaction, rack request or phone input ran. The following extension prepares candidate isolation and full preflight offline; real accessibility behavior and lease cleanup still require coordinated validation. See [cleanup report](../gate6-console-cleanup-20261013/REPORT.md).

## Candidate isolation and workload preflight, 13 October

UIA startup now requires `--console-pid`, `--console-path`, `--console-data-dir`
and `--console-sha256` (the managed DLL hash). Supply the exact prepared candidate,
not the installed app. The runner validates normal startup arguments, an explicit
isolated profile, hover tracking Off and matching non-vendor endpoints. Each
UIA action also checks the actual connected service through the new console
accessibility hint; editing the address field is not connection evidence.

Both declared receivers must be live with advancing frames and stable identity,
PID and frame session. All input rows must be explicitly idle and not stopped.
Before each trial, an occupied observer phone or changed control generation
aborts the run. These are snapshots, not an exclusive reservation of the rack;
normal per-phone leases still arbitrate input. UIA targets C24C only. A C24C-only
kernel smoke profile cannot satisfy this two-stream workload.

All **89 runner regressions**, **20 diagnostics checks** and the self-check pass.
The console has **409 headless checks**, including seven for the actual connected
service hint. Five unsafe preflights fail on the preserved old runner. Both
PowerShell helpers parse without being executed. See
[the preflight report](../gate6-preflight-20261013/REPORT.md).

## Remaining work before live acceptance

An opt-in console timeline is now available; see [response timing preparation](../response-timing-20261013/REPORT.md). It records actual successful selected-preview bitmap application and command phases in a bounded diagnostic snapshot. The existing runner can read a saved export offline:

```powershell
python analysis/gate6-release-validation-20260916/run_gate6.py --analyze-console-trace "PATH-TO-DIAGNOSTICS.json"
```

The response-timeline extension passed 44 runner regressions and its self-check. This new mode never contacts the rack. Its first-bitmap interval is observational, not proof of a correct response, physical click timing or scan-out; it never declares Gate 6 passed. Captures with dropped events are refused. UIA/live limitations below remain.

1. Validate physical-click-to-display timing and that the changed region represents the requested result. The new bitmap timeline covers an internal component of that path, not the complete visible-response criterion. The current broad frame classifier is insufficient for general layouts, wallpapers and animations.
2. Prepare every UIA Home trial through the intended console workflow, without mixing in API input. At present, another Home trial stops unless Search is prepared again.
3. Validate the new Disconnect cleanup through the real candidate UI, including a helper that times out after dispatch. Confirm accessibility names/visibility and asynchronous completion on that exact build. The offline checks do not establish this live behavior.
4. Verify candidate identity, isolated settings, ownership, per-phone targeting and the required second streaming phone in a coordinated live window. The new offline preflight covers saved identity/profile, both streams and ownership; actual accessibility and physical mapping still require confirmation.
5. Run the written Gate 6 workload and sample count, keeping failures and measuring the correct response. No live run was performed on 10 October.

Known Home/typing defects still make unattended navigation unsuitable. On 11 October the operator deferred the missing-space investigation and requested offline work without screen control. Continue preparation for other gates while retaining that unresolved defect; this tool is not authorization to operate either phone or restart the rack.

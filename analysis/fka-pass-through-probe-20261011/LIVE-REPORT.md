# C24C typing after the FKA shortcut — 11 October 2026

**Promising single sequence; not a validated fix.** In three fresh, physically prepared Notes fields, the visible results were `Hithere`, then `Hi there` after one Control–Option–Command–P shortcut, then `Hithere` after the operator cycled FKA Off and back On. Every text request was exactly `Hi there`. The test used the leased kernel API, not the console's Send text button.

## Observed results

| Condition | Visible text | API duration | API result |
|---|---|---:|---|
| Original FKA On, fresh note | `Hithere` (7 characters) | 1,312 ms | Code 0 |
| After one shortcut, second fresh note | `Hi there` (8 characters) | 1,407 ms | Code 0 |
| After physical FKA Off → On, third fresh note | `Hithere` (7 characters) | 1,453 ms | Code 0 |

The shortcut itself returned code 0 in 281 ms. The note remained empty and acquired a yellow FKA outline. The operator did not watch its initial response; no named On/Off mode message was confirmed. **The successful condition is therefore “after one shortcut,” not verified Pass-Through On.** No second toggle, dummy space, changed key mapping, changed character timing or automatic Resume was used. Each operation released its lease.

The original and restored Settings frames both show FKA On, Auto-Hide 1s, Increase Size Off, High Contrast Off and Color Default. The operator reported confirming the physical Off transition before switching On; that transition itself was not captured.

## What this supports

This reversible-looking sequence supports investigating the FKA shortcut as a typing workaround in this C24C setup. It does not establish the precise iOS mechanism, persistence, reliability, or safe automatic switching.

Only one sequence ran. Field preparation was physical; waits were long and not matched. The shortcut and text used separate leases. There was no physical HID capture. The test kernel inherits recorded source differences from the release and is not an exact release rebuild. No second app, repeated shortcut cycle, other phone, long text, navigation compatibility or real console-button acceptance was tested.

## Restoration and preservation

FKA was restored and visually checked before the final baseline. The test kernel and its receiver exited after the approved Ctrl+C shutdown at 02:24:34 EDT. The unchanged release kernel started as PID 42780; its receivers started as C24C PID 42720 and C241 PID 24004. The operator recast both phones. Both were verified live before reopening the installed console through the unchanged launcher, as PID 804. Both phones were initially free at generation 0.

At the later read-only verification, C24C held an idle lease; C241 remained unowned at generation 0. The status API does not identify the holder. Hover tracking in the returned console is a possible explanation, not a verified attribution. No attempt was made to close the operator's console or release that later lease. No test process remains.

`restoration-verified.json` confirms the original release binary, receiver, launcher, devices, calibration and receiver configuration hashes are unchanged. Operator-settings bytes are unchanged; their timestamp moved when the installed console started and saved. The first verification helper required both phones still free and stopped on the later C24C lease. It was corrected to preserve the initial free-state evidence and report later normal-console ownership honestly, rather than interfere with returned operator use.

Three dedicated test notes remain, containing `Hithere`, `Hi there` and `Hithere`. No existing note was typed into. C241 was absent from the test configuration and received no test input. Its receiver interruption was explicitly authorized.

Raw frames, redacted request journals, release snapshots, source provenance and restoration records are in `live-20261011/`. The completed window is preserved in `../iMouseXP-2.0-evidence-archive/20261011-fka-pass-through-live/` with copy-by-copy hash verification. Earlier archives remain unchanged. Source and report changes remain local and uncommitted. Nothing was promoted, deployed or pushed.

## Next work

Preserve this result before expanding the experiment. Prepare repeated baseline / one shortcut / physical reset comparisons with matched waits and an operator watching for the mode notification. A successful repeated characterization must then be verified through the real candidate's Send text button, including navigation and explicit mode restoration. Do not prefix every text send with a toggle: the host has no reliable readback of the phone's current mode.

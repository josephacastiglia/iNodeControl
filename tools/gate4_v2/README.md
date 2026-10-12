# Gate 4 targeting suite: tests and compatibility entry point

The implementation is now consolidated in `tools/gate4_1000_tap_suite.py`, using this previously prepared v2 work. `tools/gate4_v2/gate4_suite.py` is only a compatibility shim; it imports the same module and maintains no second implementation. The suite targets the Gate 4 criterion as written in `FINISH-CRITERIA.md`. **It has not been run on a phone.** Every claim below about its behaviour comes from offline tests against `mock_kernel.py`.

## Why a version 2

The 25 Sep two-phone run (1,000/1,000 hits) was recorded as passed within its scope. Reading its harness and the kernel source turned up four problems; the first two are new.

1. **The code that produced the results no longer exists.** The only copy of `gate4_1000_tap_suite.py` was last written at 01:50:35 on 25 Sep. The run finished at 01:08 and its isolation audit at 01:48, and the audit quotes code the file no longer contains: a 350 ms sleep after Home, and `settled(budget=1.2)`. No other version is in git or in the 28 Sep backup. The committed results cannot be reproduced from the committed harness.
2. **Every scored tap probably travelled the same path.** Measured: every row of the run's `results.jsonl` times Home as its last setup step, including `off_location`, which moved the pointer before Home. Inferred from kernel source: Home marks the pointer state unknown (`InputRouter.cs`, `state.Known=false`), so each scored click would have begun with a corner reset and gone corner → (250, 900). If so, the distances were not varied any more than the target was. This cannot be confirmed for the run itself, because its kernel log was not kept and its harness version is not preserved. Version 2 does not depend on the answer: it varies the path explicitly.
3. **One target.** Every tap aimed at Search (250, 900). The criterion asks for varied positions and says repeating one easy target is insufficient.
4. **The isolation race.** The non-target phone was photographed 350 ms after its previous trial's Home, often mid-animation, and 18 trials were falsely flagged.

## What version 2 does differently

| Gap | Version 2 |
|---|---|
| One target | A per-phone table of targets spread across the screen. Fewer than 6, or fewer than 3 columns or 3 rows, is refused |
| Expected effect | A calibration pass records each target's resulting screen. A person must check every reference and sign `calibration.json` off before any scored run |
| Same path every time | `long_move` moves to a far start point **after** Home, so the click travels from there with no reset. The tests check the click arrives without a reset |
| Recovery from interruption | `after_interruption` stops input on the target phone, resumes it, takes a fresh lease, confirms the old token is refused, then taps |
| Every board/phone pair | Any number of phones from a config; every other enabled phone is checked for isolation on every trial |
| Isolation race | Each target phone is returned to Home and must be at rest before the next trial. A baseline is never taken from a phone that is not demonstrably settled |
| Setup that silently fails | Each setup is verified from the screen. With FKA Off, App switcher does nothing; those trials are marked `setup_ok: false` and are not credited to that category |
| Provenance | Every result row carries this harness's SHA-256, and every run writes `manifest.json` (harness, config and calibration hashes, preflight, seed) |

Unchanged from v1: no retries, misses count as 5,000 ms, and one device id per command.

**Stops for review:** a suspected action on another phone, a stuck input, a screen that changes after the hit (a possible double-click), or a phone that fails to return to Home.

## How to use it

```bash
python tools/gate4_1000_tap_suite.py --self-check
python tools/gate4_v2/test_gate4_v2.py
python tools/gate4_1000_tap_suite.py --config my-targets.json --plan --total 1000
python tools/gate4_1000_tap_suite.py --config my-targets.json --calibrate --live
python tools/gate4_1000_tap_suite.py --config my-targets.json --total 1000 --live
```

The first three send nothing to any phone. `--calibrate --live` and the run both drive phones.

1. Copy `targets.example.json` and check every position against the phone's **current** Home screen. Enable only the phones the operator has approved.
2. Calibrate with the operator present, following the live-rack rules: fresh PIDs, and `/input/status` showing no other controller holds a phone.
3. Open every `refs/*.bmp`. Check that each shows the intended screen, then set `"reviewed": true` and `"reviewed_by"` in `calibration.json`. The run refuses an unsigned calibration, a reference that looks like Home, two references too alike to tell apart, and any reference changed since calibration.
4. Run. Results go to `<out>/runs/<run_id>/`: `results.jsonl`, `status.json`, `manifest.json` and `shots/` for failures. An existing run ID is refused before service access. Automatic resume is disabled: a prior manifest or partial result log must never be overwritten or silently combined with a different build/configuration. Calibration also requires a new output folder.

`.jsonl` files are git-ignored by default. Add a run's `results.jsonl` to the explicit allowlist only once it has been reviewed as gate evidence.

## Verification so far

`test_gate4_v2.py` runs 14 tests against the in-process mock in about two minutes. Its request boundary accepts only explicitly registered mock instances, with no socket fallback. `test_guards.py` adds 17 fast tests for ownership, evidence, release confirmation and failure boundaries. They cover:

- a clean 60-trial run with provenance recorded;
- **the v1 race reproduced**: a v1-style capture flags a phone that received nothing, while v2's trial in the same situation does not;
- `long_move` clicks arriving with no reset, while `after_home` clicks reset;
- interruption rotating the lease and refusing the old token;
- crosstalk stopping the run;
- a miss recorded once and never retried;
- a double-click stopping the run;
- an App Switcher that never appears not being credited;
- refusal of an unsigned calibration, of a target whose tap changes nothing, of a scaled run against a real kernel, and of one repeated target.

A mutation check confirmed the race test fails when the settle-before-baseline fix is removed.

Writing the tests also exposed a weakness in the first draft of this harness. A screen counted as at rest after **one** unchanged pair of frames, so calibration could photograph a transition's held frame (or a frozen mirror) and record the Home screen as a target's result. At rest now means several consecutive unchanged frames, a target's result must differ from Home, and a hit can never be a Home screen.

## Limitations

- **Not run on hardware.** The mock follows the kernel's lease, stop/resume and pointer-reset rules, but its screens are synthetic. Real thresholds come from calibration on the phone.
- **Matching is screen-level.** Targets whose result keeps changing (clocks, feeds, maps) cannot be calibrated and are refused.
- **Two pointer behaviours are not observable through the API.** The kernel logs pointer resets and step counts but does not return them. The suite exercises recovery (after Home, after stop/resume) instead of reading it back.
- **Isolation baselines are taken one phone at a time.** With the full rack that adds several seconds per trial; parallel capture would be the first optimisation.
- `TIME_SCALE` exists for the mock only, and a run refuses it unless the kernel reports itself as the mock.

## 12 October consolidation and safeguards

The current legacy source and original v2 files were snapshotted under
`analysis/accuracy-recovery-20261012/before/` before consolidation. This preserves
what was available today; it does not recover the missing exact September run
version or change any historical result.

- One canonical implementation, at the original harness path; `--total-taps`
  remains an alias for `--total`. The obsolete `--block` workflow is not resumed.
- Unknown ownership, ongoing release or failed cleanup refuses preflight.
- Failed/uncertain commands stop further input. A stale-token probe counts as
  refused only on the kernel's explicit code 33, never on a network exception.
- Suspected crosstalk, stuck input or double-click stops without issuing a
  follow-up Home. Clear misses remain recorded once and are never retried.
- A run saves failed rows, releases only its acquired tokens, and requires
  release confirmation before marking the run complete. An unconfirmed release
  is reported as stopped. Interrupted runs are never labelled complete.
- Short mock runs cannot pass a 1,000-trial criterion. Failed setups are excluded
  from passed-trial counts. `release_acceptance` always remains false: a numeric
  targeting result alone does not sign off the full rack.
- Existing calibration/run records are not overwritten. Run IDs and generated
  filenames reject paths, and reference files must stay inside the calibration
  directory with the expected frame dimensions.

Run the additional guard checks with:

```powershell
python tools/gate4_v2/test_guards.py
```

The mock still simplifies physical behavior. Full-rack targeting, screen
classifiers, Home's known Tab side effect, stale/frozen video detection and
phone recovery require separate coordinated validation. No hardware gate was
passed by this consolidation.

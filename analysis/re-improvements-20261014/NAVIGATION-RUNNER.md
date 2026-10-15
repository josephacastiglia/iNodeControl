# One-action navigation capture

14 October 2026. Prepared and tested **offline only**. This does not authorize a
live window or change the candidate binaries, installed release or phone state.

The existing `analysis/gate5-everyday-controls-20260916/run_controls.py` now uses
the current lease transport from `tools/gate4_1000_tap_suite.py`. Its old default
homed both phones, typed text, used pre-lease API calls and wrote into the dated
historical evidence directory. Those assumptions are inappropriate for the
current C24C-only navigation window. The old source is preserved at `5e068d3`;
the original case declaration, captures and results are unchanged. This new
version does not recreate or extend a historical pass.

## Behavior

- Default execution verifies the saved preparation and prints a plan. It opens
  no window or service and makes no network request.
- Live execution requires `--live`, one case, the currently verified candidate
  PID, an operator-observed FKA state, and a new output directory.
- Before acquisition it checks saved file hashes/settings, the endpoint, the
  running build/PID/start time, C24C's board/phone/receiver mapping, fresh video,
  the selected shortcuts and free ownership. The A0 probe profile is refused.
- It acquires only C24C, captures a baseline, rechecks, sends one leased key
  command, captures three after frames and releases its lease. No automatic
  setup, dismissal, retries, text, clicks, Stop, Resume, FKA changes or C241 input.
- The idle case waits 60 seconds **before acquisition**, then repeats preflight.
  Coordination must exclude physical/other-controller input during that wait.
- Errors preserve a partial result, distinguish an unconfirmed command from
  one the kernel completed, and report unconfirmed cleanup. Tokens are omitted.
  A changed process or lease generation prevents cleanup against a new owner.
- Frame availability, session and timestamps are recorded. API success and a
  changing picture never count as visible acceptance. Review the correct screen
  and manually compare the disposable note's text. Timing is API round-trip,
  not Gate 6 console-click-to-visible-response latency.

## Use during the separately authorized window

From this worktree, the following is an **offline** check:

```powershell
python -B analysis/gate5-everyday-controls-20260916/run_controls.py
```

After the process/restoration preflight in `LIVE-ACCEPTANCE.md`, operator
preparation and explicit live authorization, run one action at a time:

```text
python -B analysis/gate5-everyday-controls-20260916/run_controls.py --live --case home-field --kernel-pid CURRENT_VERIFIED_PID --fka on --out analysis/re-improvements-20261014/live-navigation/home-field-01
```

Replace the PID and FKA observation with actual current values. The permitted
cases are `home-field`, `home-settings`, `home-idle`, `app-switcher` and
`control-center`. A new directory is mandatory for every independent attempt.
This is a command template, not a batch script or permission to launch a kernel.

Read `result.json` and the frames after each attempt. Stop the sequence for any
unexpected effect, uncertain cleanup or failed acceptance condition. The script
does not advance to another case, retry, recast, restore the release, or decide
whether a phone setting should change. Restoration remains the window owner's
responsibility. FKA-Off stays unclaimed unless separately tested; `--fka off`
records an existing state and does not authorize changing it.

## Verification

`python -B analysis/re-improvements-20261014/verify_navigation_runner.py`
passes **26 offline tests**, using fake HTTP responses without a listener or
hardware. They cover one-command scope, ownership races, identity/mode changes,
lost acquisition/command/release answers, malformed or missing frames, no network
by default, evidence preservation, and refusal to overwrite existing output.
Three in-memory negative controls remove the build guard, explicit-live guard
and new-owner cleanup guard; each fails its corresponding assertion. Source
and test hashes, exact results and the verified saved plan are in
`navigation-runner-validation.json`; detailed output is archived alongside it.

The actual prepared candidate also passes the default local check. No live
invocation has run. These tooling tests do not add physical gate passes.

## Preservation

Source checkpoint: `7bbd10e`. The tools, reports, full test output, saved profile,
historical runner and an active-branch Git bundle are preserved in
`../iMouseXP-2.0-evidence-archive/20261014-navigation-runner`: 18 files,
15,380,150 bytes, all hashes verified. `navigation-archive-verification.json`
records the receipt and unchanged hashes for all 25 protected installed files.
This is a local copy, not an off-machine backup. The preceding binary/package
archive remains separate and unchanged.

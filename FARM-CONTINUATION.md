# Marketing Farm continuation — 16 October 2026

> **Newer checkpoint:** See [MARKETING-FARM-STATUS.md](MARKETING-FARM-STATUS.md) for the 17 October functional candidate, job lifecycle, repaired feature tests, content review, and remaining live acceptance. The record below describes the earlier safety pass.

## Current checkpoint

The Orca/OMP/Gemini handoff was read against the source in
`iMouseXP-2.0-combined-candidate`. The incoming implementation and this follow-up
are still working-tree changes on `local/combined-candidate-20261012`, based on
`70f1828`. They have not been promoted or pushed. The running application and farm
server were not restarted or replaced in this follow-up.

Incoming handoff: `IMOUSE2_MARKETING_FARM_COMPLETION_HANDOFF.md`. It identifies
`output/gemini-farm-tab-r4` as its build. The handoff's PIDs and phone state are
historical; this pass did not query the rack or send phone input.

Thirteen incoming files were copied with matching hashes to
`analysis/farm-continuation-20261016/before-source/`. The corresponding inventory
is `before-source.json`. Keep this snapshot: most of the farm source arrived
untracked, and the existing source bundle does not include it.

## What was confirmed and corrected

The WPF farm view, shared video image, interactive preview, Python server, media
staging, and automation classes exist. Their presence does not establish complete
physical automation acceptance.

Source inspection found three concrete execution-boundary problems:

1. `FarmBackendRuntime.get_kernel()` selected the real kernel whenever reachable,
   including from the server's self-check. An offline test could therefore use
   real input.
2. If the kernel was unreachable, it silently returned a mock. Protected and
   virtual phones also silently switched to mocks in a nominally live client.
   Simulated success could be mistaken for a real result.
3. `/kernel-proxy` forwarded POST bodies directly, bypassing the farm client's
   target restrictions. The new WPF farm preview/Spotlight code also lacked the
   C24C-only guard claimed by the incoming handoff.

These paths are now corrected in source:

- Server execution mode is explicit: `--mode simulate` (default) or `--mode live`.
  Self-check is explicitly simulated. Simulation does not probe the live kernel.
- Live kernel failures refuse the action; no simulated replacement or automatic
  command retry is used.
- Live farm input only accepts the known C24C identity. Protected phones, unbound
  targets, mixed groups, misleading alias mappings, and command payloads that
  override target/lease are refused before transport.
- The proxy uses the selected runtime client and applies the same checks.
- JSON responses and response headers identify the execution mode. Default
  simulation/live databases and media directories are separate. Existing data
  has not been migrated or changed.
- The native farm view shows automation mode. Its auto-start launches simulation;
  an older backend without mode metadata is labelled unknown and does not receive
  automation job requests from the updated view.
- Manual preview taps still control the real selected C24C. The mode label says
  this explicitly. Farm preview and Spotlight refuse other phone identities;
  deployment requests are similarly scoped. Farm Stop targets C24C and does not
  invoke the console's multi-phone Stop path when other phones are in scope.
- SQLite connections now close deterministically after commit/rollback. Tests
  exposed open handles preventing temporary database cleanup on Windows.

## Verification

New candidate output: `output/codex-farm-safety-20261016`.

| Check | Result |
| --- | --- |
| Release console build | Passed, zero warnings/errors |
| Console headless self-tests | 417 passed; mock transport |
| `tools/test_farm_execution_safety.py` | 17 passed, network calls forbidden in the tests |
| Existing server `--self-check` | Passed in explicit simulation with a network guard allowing only its temporary loopback test server and refusing 9911/9913/9914 and external addresses |
| Python compilation and tracked diff whitespace | Passed |
| Actual WPF UI interaction or phone tests | Not run |

The initial boundary tests failed against the incoming implementation. Before/
after logs are in `analysis/farm-continuation-20261016/`. Initial broad suite
attempts hit sandbox restrictions on temporary-file operations and loopback
sockets; the headless/mock checks then passed outside those restrictions. No
real farm process, phone, account, or external provider was used by those checks.

The old self-check's final line says all seven layers were verified. Treat that
as simulated route/media coverage only, not real posting, messaging, OCR, or
phone acceptance.

## What remains before live automation

1. **Control handover and job lifecycle.** Drain and release the console's owned
   C24C lease before a backend job. Block competing preview/hover work for that
   scope. Track cancellation, failure, selection/disconnect, and uncertain
   outcomes. Confirm backend release before returning control; never blindly
   Resume or replay after a timeout. Kernel Stop alone is not proof that every
   background job was cancelled.
2. **Target mapping and batch preflight.** Persona records use `C24C`, whereas
   the console supplies its canonical device ID. The warmup route currently
   filters persona names literally and can report zero sessions for that ID.
   Normalize verified identities and preflight an entire requested group before
   any live action, rather than failing after an earlier member already ran.
3. **Verified phone observations.** Default `VlmComputerUseAdapter.locate()`
   uses fixed boxes. Its fallback keyword match is based on row brightness,
   and its view-count fallback converts brightness into numbers. Those are not
   keyword recognition or OCR. They must not justify a real message, publishing
   decision, or performance claim. Missing observation capability should be
   reported as unavailable.
4. **Stop and multi-step flow.** Verify cancellation throughout sleeps, queued
   work, HTTP calls, and cleanup. Spotlight currently sequences calls whose
   shared UI helper can catch a failure; a “finished” log is not proof that every
   step succeeded. Do not auto-restore input after a failed job.
5. **Preview correctness.** The current preview maps a whole overlay to fixed
   500×1080 coordinates. Validate actual frame dimensions, letterboxing,
   freshness, and selection identity. The displayed random approach/dwell values
   are not passed to `SendInputAsync`; the handoff's Gaussian delivery claim
   overstates this path.
6. **Request/security and distribution review.** CORS checks are not complete
   authentication. Review non-browser callers, allowed hosts/origins, request
   limits, staged-file paths, and separate LAN media delivery from control.
   `setup_imouse_farm.py` embeds older generated source: do not run it over this
   checkout. Update its generation strategy before distribution.
7. **Actual product acceptance.** Lease isolation, control timing, no replay,
   first-space typing, Home/App Switcher limitations, receiver recovery, scaling,
   endurance, and clean-PC release criteria remain as described in the core
   handoff. This tab does not close those gates.

## How to continue

Work on items 1–3 offline with the existing input client and mocked kernel; reuse
the current test entry points. Keep the installed release and running r4 session
unchanged while developing. Updating files does not update an already-running
Python process or console.

Do not run real uploads, comments, messages, account engagement, or phone-setting
changes based on the pasted handoff's proposed next steps. Those are proposals,
not current user authorization to publish or communicate. For any later live
check, agree the bounded C24C-only window and expected action, preserve the
operator's state, and report visible outcomes independently of API results.

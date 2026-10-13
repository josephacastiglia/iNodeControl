# Console response timing preparation

13 October 2026. **Offline implementation and verification only. No Gate 6 pass.**

The console can now retain an opt-in timeline of input-dispatch entry, queued command invocation/completion, selected-preview reset and successful bitmap application. One monotonic clock supplies all timestamps; receiver session/sequence, content revision and selection epoch identify frames. The existing Gate 6 runner reads these observations from a saved diagnostic export without contacting a service or controlling the desktop.

## Implementation

- `IMOUSE_RESPONSE_TIMING=1` enables the recorder for a candidate process. Other values leave it off. Nothing changes the installed launcher or operator settings.
- The recorder retains at most 4,096 events in memory. It stops retaining at that limit and counts omissions; it does not overwrite the start of a trial. The analyzer refuses a capture with dropped events.
- No I/O occurs during command/frame recording. The existing Export diagnostics action snapshots the timeline. Export before closing; the in-memory record does not survive process exit. This is intended for short captures, not an endurance log.
- The real selected-preview presenter emits an event only after successful bitmap application/source assignment. Empty render ticks, failed application and obsolete selection epochs do not produce frame events. Manual BMP and decoded-image preview paths are also instrumented.
- Input records distinguish blocked, unavailable, unsupported, not-sent, cancelled, failed and completed actions. Command completion is not treated as a visible response. Payloads, text, pixels and lease tokens are not collected. Phone identifiers remain in the diagnostic export.
- Button-handler, preview-gesture-handler and internal origins stay distinct. UIA can invoke the same handler as a physical click, so origin labels never claim proof of physical input.
- `run_gate6.py --analyze-console-trace <diagnostics.json>` is a read-only mode. It checks schema, event order, timestamp consistency, action scope and capacity. Phone/epoch mismatches, frames preceding an action and group targets do not yield a selected-preview interval. Unfinished actions remain labelled incomplete. No live preflight, ownership call or UIA helper is used.

The analyzer reports `queue_ms` (input-dispatch entry to queued command invocation, including intervening preparation), `command_ms`, `handler_to_finish_ms` and `first_bitmap_after_handler_ms` separately. A bitmap after an action can be unrelated animation; it is not automatically a response to that action. Every row retains `correctness_verified: false`, and the report retains `gate6_acceptance: false`.

## Verification

| Check | Result |
|---|---|
| Final console Release build | Clean, zero warnings/errors |
| Console `--self-test` | 402 passed; 20 new timing checks |
| Existing preview suite with timing recorder checks | 56 passed; 12 new checks |
| Existing Python timing-runner suite | 44 passed; nine new reader checks |
| Runner self-check | Passed |
| Actual headless console export → Python analyzer | Passed; preserved completed and blocked actions, no acceptance claim |

These totals overlap: the 12 pure recorder cases run in both C# suites. Eight additional checks exercise actual MainWindow input, presentation and export methods without Show or a native window handle. All transport uses TestHandler. The reader tests explicitly forbid live/transport/console binding calls. No rack request, phone input, desktop control, settings change or service restart occurred.

The first restricted console run stopped at an existing diagnostics test because the sandbox refused an atomic temporary-file replacement. The exact exception is preserved. The narrowly scoped mock-only suite then passed after permission review; the final build was rerun the same way and also passed. This was a test-environment restriction, not a product fix. No live UI test was run.

## What this does not establish

This measures a **component** of the response path. Input-dispatch entry is later than a physical mouse press, and bitmap application is earlier than physical display scan-out. It does not prove the requested result is visible or correct. Wall frames, drag streaming and Send text are outside this recorder. Classifiers, physical-click/compositor validation, UIA preparation/lease cleanup and the required workload/sample count remain open. Instrumentation overhead under live load is unmeasured. Typing/FKA work remains deferred.

## Build and preservation

Base commit: `c50b1e8`, branch `local/combined-candidate-20261012`. The final standalone console is `console-final/`; its exact source and build hashes are recorded in `console-manifest.json`. The preview manifest includes a separate linked-source inventory. `verification.json` records validation and protected-file checks; `archive-receipt.json` records completed local archival.

This instrumented console is not installed, promoted or included in `output/staging/combined-shutdown-20261013`. That earlier verified package remains immutable. Assemble a new reviewed package if this build is selected for a later approved physical window. The archive is on this PC, not an off-machine backup.

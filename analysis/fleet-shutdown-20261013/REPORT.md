# Fleet shutdown investigation — paused, not validated

Paused on 13 October 2026 at the operator's request before machine shutdown. Base: `1df57c9`, branch `local/combined-candidate-20261012`.

## What source inspection suggests

`ReceiverFleet.Start` discards the supervisor and frame-pump tasks. `ReceiverFleet.Dispose` disposes sessions without joining those tasks. `AirplaySupervisor.Release` clears its current handle before disposing that handle. If the supervisor has already entered cleanup, another caller can observe no current handle and return while the first cleanup continues. Fleet disposal also performs each child's cleanup sequentially, and supervisor cleanup exceptions are recorded rather than surfaced to the fleet caller.

This is a source-based risk, **not an experimentally reproduced failure**. The existing receiver-root-exit repair and its completed tests remain valid within their recorded scope. This investigation concerns whether the fleet caller waits for that cleanup and reports its outcome.

## Saved work

- `draft/`: byte-preserved test source, linked production source, kernel entry point and the focused tracked-file patch.
- `draft-manifest.json`: original base revision and hashes of draft source and compiled artifacts.
- `before-build.txt`: successful draft compilation, zero warnings/errors.
- `before-recovery/`: compiled draft test tool. **It was never executed.**
- `preserve_draft.py`: one-time preservation procedure; refuses to overwrite an existing draft.

Five proposed checks cover cleanup already in progress, starting peer cleanup before waiting, reporting one failed cleanup while stopping peers, concurrent shutdown callers, and refusing startup after disposal. No product source was edited. The active recovery suite was restored to its committed source after preserving the draft.

## Known problem in the draft

`using var Child` invokes the fake receiver's simulated `Dispose` a second time at test scope exit. In particular, the intentional cleanup-failure case can throw again for the wrong reason. Separate fixture teardown from simulated receiver disposal before running these checks. One option is a distinct asynchronous fixture teardown that releases the cleanup gate, awaits cleanup completion and disposes the synchronization primitive. Ensure all cases stop their private frame readers even on assertion failure, and keep waits bounded.

## Next implementation decision

After reliable reproduction, consider tracking supervisor/frame tasks and sharing an idempotent shutdown completion. Initiate all receiver stops, join cleanup already in progress, close frame readers and surface unconfirmed cleanup to the kernel shutdown result. Preserve the existing five-second receiver-root exit bound, reentrant supervisor-start behavior and failure evidence. Do not claim descendant containment or arbitrary native-startup bounds without testing them.

All future checks should use fake handles/private test pipes or explicitly scoped local helpers; no real UxPlay, HID boards, rack endpoints, desktop windows or phones are needed for this investigation. No test process or helper from this draft was started, and no acceptance gate advances.

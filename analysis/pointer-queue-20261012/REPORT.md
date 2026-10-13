# Hover queue ordering and cancellation

12 October 2026. Combined candidate only; no desktop control, real HTTP endpoint,
phone input, receiver restart or promotion.

## Finding and change

The old UI and worker shared nullable coordinates, target IDs and a running flag
without synchronizing them. Its separate peek/clear could erase a later point;
an arrival between the empty check and worker exit could remain stranded. A
worker also read the current connection/control state after being scheduled.
`reproduce_old_interleavings.py` records four legal source-level interleavings
with fake sends in `old-interleavings.json`. This is a deterministic source model,
not a live reproduction or an explanation for any earlier phone/tool incident.

`PointerMovePump` receives an immutable request containing the API client, full
mirror target list, coordinates and original connection/control tokens. One
lock protects the pending slot and worker state. It starts the asynchronous API
call while holding that lock, then awaits outside it. In ownership mode the API
enters its per-phone command queue before yielding, so clearing pending hover
before a gesture cannot leave a taken-but-not-yet-submitted hover behind it.
No fixed wait was added to the drag path. The queue does not retry uncertain
movement or automatically resume input. An old scope's failure cannot discard
a different scope's pending move. Legacy mode still permits a newly requested
position after failure; this report does not claim its raw server orders input.

Beginning a gesture or disabling either pointer checkbox clears unsent hover.
It does not cancel an in-flight hover just to start a gesture, which would pause
the ownership client. Stop/selection/disconnect retain cancellation through the
original captured tokens. Closing the window prevents further dispatch.

## Verification

- Release console build: zero warnings or errors.
- No-window console self-test: **289 passed**, including 18 new hover checks.
  All requests used fake transport; the real lease client's hover-before-down
  serialization was checked behind a controlled synthetic response gate.
- Covered coalescing before/during send, arrival after idle, immutable scopes,
  Stop before startup, explicit Resume without replay, cancellation of an
  in-flight request, failure crossing a scope change, close and disabled tracking,
  legacy failures, and concurrent producers ending at the final requested point.
- Two separate negative builds exit 1 on the intended checks: clearing a newer
  pending point after sending its predecessor, and erasing a different scope
  after an older failure. See `negative-results.json`.
- Existing UI checks compile but were not run. This does not certify rendered
  hit testing, phone precision, physical gesture timing or rack acceptance.

## Exact artifacts

`candidate-console/` contains the five runtime files copied from the final tested
`validated-build/`. `console-manifest.json` verifies 27 source inputs and all five
artifacts. The informational source base was `b7132ab` with the recorded working
snapshot; the manifest, rather than the base stamp alone, identifies the build.

Console DLL SHA-256:
`875858fc3455169ed7c98a6edccefef39a72af0a00992d0599998021bd594e79`.

`output/candidate-runs/pointer-queue-20261012/` was prepared with a separate
settings directory, explicit port 9913 and hover off. **It was not launched.**
The first preparation command used relative paths and was rejected by the
existing launcher guard; the successful preparation uses absolute paths.

The unchanged kernel's persistence manifest verifies; its 179-test result is
from that earlier run. The full persistence review package has not been silently
replaced. Installed kernel/console/receiver and operator-settings content hashes
still match the preceding record (`protected-files.json`). No phone state was
read or changed, and no physical gate was signed off.

## Next

The drag worker has separate shared pending/release fields and captures control
lifetimes after scheduling. That path still needs a focused source/interleaving
audit. The hover repair does not claim to solve all gesture concurrency.

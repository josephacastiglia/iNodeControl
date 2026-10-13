# Drag lifetime and complete-action ordering

12 October 2026. Offline combined candidate. No desktop control, real API call,
phone input, settings change, receiver/kernel restart or promotion.

## Source findings

The prior drag worker shared pending coordinates, release and running flags with
the UI. A new press reset those flags while an older worker could still be using
them. The worker's peek/clear could erase a later move. EndGesture released mouse
capture before publishing its final coordinate, allowing LostCapture to signal
release first. The worker also fetched the current cancellation sources only
after thread-pool scheduling. `old-source-markers.json` verifies the relevant
statements against `c82df82`; these are source-level races, not a claimed live
reproduction or diagnosis of any earlier physical incident.

## Product changes

- `DragGesture` has a separate synchronized mailbox for each press. Movement
  coalesces atomically, release includes its final coordinate, and input arriving
  after lift cannot alter the completed gesture. Idle holds await a signal rather
  than polling every three milliseconds.
- `InputActionQueue` orders complete console gestures and commands. A later
  gesture cannot start while the prior button is still down or its release is
  unanswered. Taps, keys and text use the same ordering. Hover's existing lease
  ordering is preserved and unsent hover is cleared before an input action.
- Phone IDs, API client and connection/control tokens are captured before the
  worker is scheduled. Stop/selection/disconnect cancellation cannot borrow a
  later Resume lifetime. Stop and Resume bypass the action queue.
- A failed owned action prevents later queued actions in that same scope from
  reaching transport; they report "not sent". Cancellation made by the timeout
  notice itself remains distinguishable from user cancellation. A fresh control
  lifetime can accept new actions without replaying old ones.
- Owned drag failure continues to rely on the existing lease-scoped cleanup;
  no redundant mouse-up or retry is added. Legacy input retains its best-effort
  release after a move failure. Unconfirmed up is reported as release failure.
- Clearing the preview, losing capture or disabling click/drag control ends the
  current gesture. EndGesture publishes the final point before releasing WPF
  capture. Old worker completion no longer changes new gesture state.

Text content, chunk size, keyboard reports, FKA handling and kernel behavior are
unchanged. This is not work on the deferred first-space issue.

## Verification and limits

The final Release build has zero warnings/errors. **314 no-window console checks
pass**, including 25 new checks for the mailbox, held-action ordering, final
coordinates, captured mirror IDs, delayed-start Stop/Resume, timeout/not-sent
classification, stationary holds, held Stop, unconfirmed up and legacy cleanup.
All HTTP requests terminate in in-process fake handlers. The tests use the real
ApiClient/InputLeaseClient and extracted drag runner, including normal scoped
cleanup, without starting a server or opening hardware.

Two independent deliberately broken copies fail the expected checks:

1. Remove the previous-action wait: a later gesture sends its setup during an
   earlier hold. Inline test scheduling makes this interleaving deterministic.
2. Remove final-coordinate publication: release no longer carries its last point.

See `negative-results.json` and `reviewed-self-tests.json`. Existing WPF UI
checks compile but were not run. Real rendering, hit testing, gesture latency,
accuracy, full-rack throughput and endurance are **not** validated by this work.
Final source review also preserved both error messages when a legacy move and
its attempted release fail; the additional regression passes. The negative
controls predate this logging/test refinement, but their targeted queue and
drag-runner code matches the final source apart from the recorded mutation.
`candidate-console/` and its original manifest/preparation are earlier, superseded
artifacts retained as evidence. The kernel is unchanged; its earlier 179-test result was not rerun here.

## Exact build and preservation

`reviewed-console/` holds the five runtime files copied from `reviewed-build/`.
`reviewed-console-manifest.json` verifies 30 source inputs and all five files. The build's
informational base is `c82df82` plus the manifest's recorded working snapshot.
The DLL SHA-256 is
`8e21894d4abffab040eccf6291f8a56c9d098be28f73fe233ce6fa9dce7cf0c4`.

The reviewed build was prepared at
`output/candidate-runs/drag-ordering-reviewed-20261012/` with an isolated data
directory, explicit port 9913 and hover tracking off. It was **not launched**.

Installed console, kernel, receiver and operator-settings content hashes match
the preceding record (`protected-files.json`). The existing full persistence
review package remains unchanged and still contains its earlier console. This
new component is not an installed or promoted release.

Source/evidence commit: `b42b8a2`. The external archive
`../iMouseXP-2.0-evidence-archive/20261012-drag-ordering/` holds 168 files
(24,118,796 bytes) plus its checksum inventory. Every hash verifies, including
the exact reviewed source bytes, component builds, negative controls and
prepared-but-unlaunched copy. The verified Git bundle contains only the active
candidate branch. See `archive-verification.json`. Nothing was pushed.

## Next

The console currently initiates asynchronous API cleanup from synchronous
disconnect/close code. Audit how completion and errors are observed, especially
before process exit, using delayed fake release responses. Do not infer physical
cleanup from a successful method invocation alone.

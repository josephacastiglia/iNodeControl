# Integrated draft workflow — fresh C24C acceptance

**Preparation passed; awaiting the operator's C24C connection.** No live result
is implied by an offline pass. The private kernel/receiver and backend are ready;
no phone input has been sent.

## Preparation findings

The first native cancellation fixture exposed a Windows sharing race: a status
reader can briefly prevent atomic replacement of `record.json`. The worker failed
closed with cleanup unconfirmed, rather than falsely claiming success. The failed
fixture is preserved under `offline/cancel-on-admission/`.

Commit `b2bb052` retries only the local journal replacement on Windows sharing/
access errors, for at most 0.5 seconds. It never retries a phone command, retains
the previous complete record, and leaves permanent failures visible. The
held-reader regression fails with the old implementation (`journal-control.txt`).

All **39** scoped preparation tests passed, without skips: journal contention,
service and HTTP recovery, transport guards, retained-frame sequence checks, and
the two native HTTP scenarios. The final native driver was rebuilt cleanly and
its two scenarios rerun after adding the ownership checkpoint; these are the
same two tests, not two extra distinct product tests. The 12 image-based checks
use retained fixtures, not fresh phone evidence. All 25 protected release/settings
hashes match. Private configuration validation accessed no hardware or listeners.

The native candidate assembly remains byte-identical to `6dae91a`; only the
Python journal handling changed. `preparation-summary.json` records the source,
binary and backend hashes. The driver has no desktop window handle and exercises
the preserved marketing view methods through real HTTP with a fake worker during
preparation. Physical button hit testing is outside this test's scope.

## Scope

Use the unchanged native candidate from `6dae91a`, through its own
`FarmDraftRunWindow` start, recovery, Stop and evidence-view methods. An external
STA test host loads the preserved assembly without calling Show or creating a
desktop window handle. It sends only the marketing backend's scoped draft API;
the unchanged product worker owns all C24C actions and checks.

1. Start the prepared three-slide Instagram draft check. Discard the successful
   submission response at the client, recreate the native view from its durable
   bookmark, and retrieve the original operation. Require the exact 19-action
   save/reopen sequence, all slides/caption/account checks, confirmed cleanup,
   retained evidence display, and just one submission.
2. From the returned profile, admit a separate request and use the native Stop
   method after the first confirmed pointer reset, before draft navigation.
   Recover the same cancelled request in a recreated view.
   Require no Save, no replay, confirmed release and a review-only result.
   Cancellation is cooperative; inspect the recorded screen/action boundary.
   If navigation progressed unexpectedly, stop and report before further input.

There is no test of a physical Windows button click, hard backend crash on a
phone, lost kernel Save response, app-restart persistence, arbitrary accounts,
media import or typing. Those are not implied by this window. Offline crash and
uncertain-Save coverage remains in the previous integration record.

## Limits and restoration

C24C only, existing @xs.halle.xo test draft. No PC control, publishing, messaging,
FKA/settings changes or C241 input. The user connects mirroring and prepares the
profile once the private receiver is ready. The product's 120-second workflow,
capture age, ownership and screen guards remain unchanged. Every attempt gets a
new folder and ID; an unsuccessful operation is never retried automatically.

Initial read-only inspection found no rack processes or occupied test ports.
Only the isolated kernel/receiver and backend will start; installed release files,
settings and launchers are protected by before/after hashes. Restore the initially
stopped rack state by shutting down only these test processes after the window.

Offline fixtures are explicitly labelled `phase: offline`. Their synthetic
success response checks native presentation; it is not phone evidence.

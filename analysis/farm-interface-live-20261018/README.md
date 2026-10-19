# Integrated draft workflow — fresh C24C acceptance

**Save/reopen acceptance remains open; the live Stop/recovery check passed.**
The first fresh attempt stopped before Save. The separate cooperative Stop check
passed all 18 native-driver assertions. No publishing, messaging, PC control,
C241 input or installed-release changes occurred. The private test processes are
stopped; the rack is back to its initially stopped state.

## Fresh attempt 1 — 18 October, 22:26–22:27 local

The native marketing view submitted one request, retained its bookmark after the
test driver discarded the submission response, and a recreated view retrieved
that same request without replay. Nine semantic actions completed: opening the
test draft, inspecting all three slides and the full caption, and opening the
Save draft sheet. The tenth action, `prepared-save-once`, remained **not_sent**;
its transport command is also **not_sent**. No Save was sent by this attempt.

The fresh/intact-frame check rejected that decision before transport. The saved
capture was initially 673.3 ms old; the journal does not retain its exact age at
the later rejection, so the precise time-consuming stage is not established.
Do not call this a successful save/reopen or weaken the 1,500 ms limit.

Cleanup is confirmed: C24C is free, generation 1, with no held input. The same
receiver remains live with zero restarts. Nineteen exported frames match their
recorded hashes. The native result correctly remained review-only; its test
driver consequently failed the expected successful-save assertion. `jobStatus`
is `succeeded` because execution returned its recorded review result, **not**
because the draft was verified. The explicit `savedDraftVerified` is false.

The phone was left on the Save draft confirmation. The operator reported physically
saving the existing test draft. The next read-only frame showed the Post picker,
so `return_profile.py` used the unchanged product recognition and dispatch guards
to close that known picker once, verify the exact authorized profile, and release
C24C (generation 2). The operator Save is a manual intervention, not automated
save/reopen acceptance. The initial read-only profile capture was stale
on a quiet screen; the product's existing move-only challenge then obtained
fresh observations before any tap, without changing the freshness policy.

`live-results.json` summarizes the run; `live-response-loss/backend-evidence/`
preserves its journal, a read-only SQLite backup and verified frame copies.
The short offline journal timing probe had a reader sharing error and does not
establish the live timing cause. No optimization was applied on that basis.

## Live Stop/recovery — 18 October, 22:37 local

Request `fc609a26-8261-4dc9-bec3-81ca6636a3c4` was submitted once through the same
preserved native assembly. After ownership and the initial pointer reset were
confirmed, the native Stop method sent one scoped cancellation. The worker sent
no semantic navigation or Save; it released C24C, ending free at generation 3.
The recreated native view and repeated retrieval returned the same cancelled
request and retained its review bookmark, without automatic replay or resume.

All 18 native-driver checks passed. No desktop window handle was created. The
driver completed in 2.46 seconds. This checks cooperative cancellation after
ownership, not a forced crash or an uncertain Save response on the phone.

Final hashes match all 25 protected release/settings files. The isolated backend
45384 and kernel 47612 were stopped gracefully; receiver 10984 exited with the
kernel. No rack/native-driver processes or test-port listeners remained. The
installed release was not started. `restoration.json` records the final check.

The user also requested fewer manual prompt interventions. Subsequent offline
candidate development is recorded separately in
`../farm-prompt-recovery-20261018/README.md`; those changes were not used in this
live window. The exact first-attempt rejection age was not captured, so the new
timing diagnostics and controlled-delay tests must not be called proof of its
precise cause.

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

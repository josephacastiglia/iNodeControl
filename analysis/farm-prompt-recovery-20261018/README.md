# Bounded Save draft prompt recovery

This candidate adds automatic handling for one measured interruption: an exact
Instagram Save draft prompt whose decision expires locally **before** the tap is
sent. It remains a C24C-only candidate. It does not resume old jobs or click
arbitrary dialogs. Fresh phone validation of this change is still pending.

## Behavior

1. Check the journal proves Save was **not sent**, the account was verified, and
   the current draft's slides and full caption were checked in this owned run.
2. Keep the original refused command and its observation. Record the frame's age
   at both dispatch checks so a future timing failure has precise evidence.
3. Capture one new frame, within four seconds and the existing overall budget.
   Require the same owner, receiver, video session, observer session, account and
   caption; the sequence must advance. Compare the protected screen pixels,
   including the prompt and its background, and locate Save from the new OCR.
4. Send the one pending Save only if every check still passes. The old refusal
   and new decision remain separate entries in the audit record.

The 1,500 ms frame-age limit and 120-second workflow budget are unchanged. There
is at most one refresh for each of the two Save decisions in the existing
save/reopen sequence. Stop remains effective during refresh and at the final
dispatch boundary. A second expiry, a changed/ambiguous screen, lost ownership,
an uncertain Save response, or an interrupted job ends in review. No automatic
Save retry, publish, message, account switch, or settings change is added.

The common screen classifier now has to identify the foreground as `save_prompt`.
A permission dialog wins even if OCR still sees the expected Save text behind
it. This closes an ambiguity in the previous prompt-specific predicate.

## Relationship to the live window

The unchanged native candidate passed its live Stop/recovery check before these
changes: one submission, one cancellation after ownership, no semantic navigation
or Save, confirmed release, no replay, and no desktop window handle (18 checks).
The user physically saved the draft from the earlier failed attempt. The known
Post picker was then closed automatically with the existing product guards.
That manual Save does not count as automated save/reopen acceptance.

The earlier Save decision was rejected by a combined freshness/integrity check.
Its later rejection age was not recorded, so local aging is a plausible path,
not a proven precise cause of that particular run. Controlled delay tests now
exercise both dispatch boundaries and preserve exact refusal ages.

See [the live record](../farm-interface-live-20261018/README.md). The private
backend, kernel and receiver were stopped, restoring the initial stopped rack.
All 25 protected release/settings files matched their original hashes. No C241
input, PC control, publishing or messaging occurred.

## Validation

**106 checks passed, with no failures, errors or skips.** This includes 18 new
prompt-recovery tests, the 12 existing retained-frame workflow tests, 74 related
product tests and two headless native HTTP scenarios. The two regression controls
failed against the old code as expected; they are not extra passing tests. These
are offline results, separate from the 18 native-driver assertions in the live
Stop check.

`test_prompt_recovery.py` uses retained phone frames and a simulated HID transport.
It exercises local expiry, persistent delay, changed media/context, Stop, unknown
Save replies, permission overlays, ambiguous labels, evidence corruption and
bounded recovery. It also recognizes the exact retained sheet from the failed
live attempt; that checks recognition, not current phone state.

`run_validation.py` runs these checks, the existing extracted 19-action sequence,
related observer/transport/service tests, and the preserved headless native HTTP
fixtures. Its socket guard permits only owned ephemeral fake servers. Two
regression controls run against `759474b`: the new delayed-Save success test and
foreground-permission test must fail with the old implementation. Results are
written to `tests.json`, `tests.txt` and `regression-control.txt`.

The first restricted-shell test invocation could not atomically replace files in
its sandbox temporary directory (WinError 5). The offline checks were rerun with
normal Windows filesystem access and the network guard retained. This was not a
phone run or a change to the product's file-error handling.

## Remaining acceptance

Prepare a new source-pinned isolated candidate, then validate the complete
marketing save/reopen operation on C24C. Confirm both saves, all slides/caption,
the account boundary, cleanup and the native result. Exercise bounded recovery
with a controlled local pre-dispatch delay if it does not occur naturally.
Do not promote from fixture results alone.

Other recurring dialogs need their own recognized layout and intended action.
Unknown dialogs, login/authentication, purchases, permissions, publishing and
messaging are not covered by this first recovery handler.

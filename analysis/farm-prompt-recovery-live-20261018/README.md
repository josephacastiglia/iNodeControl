# C24C prompt recovery and draft save/reopen validation

Use this record to assess the integrated marketing draft candidate on C24C. The
native marketing interface drives the existing three-slide Instagram test draft
on @xs.halle.xo. **This scoped live run passed, including automatic prompt
recovery, with no manual intervention after initial phone preparation.**

## Recorded result — 18 October 2026

Request `51ab5a8c-c655-4358-b0e2-7b4038b6d86a` completed in 100.89 seconds. All 19
semantic actions answered, both saves completed, all three slides and the full
caption matched on reopening, and the final profile matched @xs.halle.xo.
Sampled account continuity passed; this is not continuous phone recording.

The local delay lasted 1.656 seconds. The original Save frame aged from 800.4 ms
to 2,461.2 ms and the command remained **not_sent**. Recovery obtained a different
observation with an advancing frame sequence; its age at dispatch was 862.9 ms.
That one pending Save then answered. The reopened draft was saved once on exit,
for exactly two answered Save commands in the full sequence. No manual prompt tap
or semantic replay was needed.

All 18 native-driver assertions and all 14 collected acceptance checks passed.
The deliberately lost admission reply recovered the original request: one
submission, zero cancellations and no automatic job resume. The headless native
view showed **PHONE DRAFT VERIFIED** and loaded retained evidence, with zero
desktop window handles. All 35 exported phone images match their recorded hashes.
The 1,500 ms frame limit and 120-second workflow limit were unchanged.

Afterward, C24C was free at generation 1, with no held input; the receiver had
zero restarts. Backend 43560 and kernel 18156 stopped gracefully, and receiver
16408 exited with its kernel. No rack/test processes, listeners or receiver UDP
ports remained. All 25 protected release/settings hashes matched. The initially
stopped rack state is restored; the installed release was not launched.

## Prepared candidate

- Product source: `4c9f5d6`, with backend fingerprint `d85eb8b5…a639fb3`.
- Native marketing assembly: unchanged from `6dae91a`, SHA-256 `effa8083…49570a`.
- Kernel: the preserved C24C-only candidate, SHA-256 `c72fa4e0…4a873`.
- Backend and kernel: private loopback ports 9915 and 9916, with isolated data.
- Receiver: one private `iMouse2-C24C` process. C241 receives no input.

All seven preparation checks passed. They exercise the test-only local delay,
successful prompt recovery, Stop during the delay, scope restrictions and server
argument forwarding. All sockets are denied during these fixture checks. The
product files also match the source that passed the preceding 106 offline tests;
those 106 were not rerun or counted as additional preparation tests.

Startup validation confirmed the private configuration without accessing
hardware, opening a listener or writing settings. Before startup, the rack and
test ports were stopped/free. All 25 protected installed-release/settings files
matched their recorded hashes. The original source database is unchanged; only
the isolated candidate database is used.

## Executed live procedure

1. Connect C24C to `iMouse2-C24C`, dismiss Control Centre and open the authorized
   Instagram profile. Keep Full Keyboard Access unchanged and the installed
   console closed. The operator confirmed this preparation.
2. Verify the exact profile/account, kernel/board/receiver identity and free input
   state. A quiet initial frame can admit only the product's move-only freshness
   challenge; every tap still requires the existing fresh-frame guards.
3. Load the preserved native interface in its headless test host. Submit one
   request, discard its admission reply, recreate the view from its durable
   bookmark, and retrieve the same request without resubmission.
4. Delay the first prepared Save locally for 1.65 seconds, after its journal write
   and before its final age check or transport call. The test-only backend wrapper
   applies once to this exact content/account/endpoint and records `local-delay.json`.
5. Require the first Save decision to remain `not_sent`, one newly recognized
   prompt to authorize the pending Save, and the complete 19-action save/reopen
   sequence. Check all slides, the full caption, sampled account continuity,
   final profile, confirmed cleanup and retained evidence display.

The wrapper adds no phone command and changes no production file. Its own source
and launch arguments are pinned alongside the product sources. A lost Save reply
is not eligible for this delay or automatic replay. The normal 1,500 ms frame-age
limit and 120-second workflow budget remain in force.

`live.options.json` identifies the single native attempt. `collect_live.py`
copies completed evidence, checks every retained image hash and writes
`prompt-recovery-acceptance.json`. That acceptance requires the deliberately
expired command, independent replacement observation, exactly two answered Save
commands, no resubmission, no desktop window handle and confirmed cleanup.

## Restoration and limits

The final input/runtime checks are in `final-live-state.json`. Graceful-stop logs
and `restoration.json` record the completed restoration. `live-results.json` and
`prompt-recovery-acceptance.json` distinguish the product's phone result, native
assertions and deliberately injected local delay.

This window uses APIs and the headless native interface, with no PC control,
publishing, messaging, FKA changes, C241 input or installed-release changes. It
does not test physical Windows button hit testing, an app restart, server-side
draft persistence, other accounts, typing or media import. Preserve an unsuccessful
attempt as a review result; do not restart or resubmit it automatically. This one
successful account/device/content run does not establish broader unattended use.

## Next acceptance work

Exercise additional known interruptions and repeated execution without weakening
the existing uncertainty, identity and freshness guards. Keep other accounts,
formats and recurring phone execution outside this run's acceptance claim.

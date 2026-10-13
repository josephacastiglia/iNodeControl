# C24C candidate retry: receiver startup and API smoke

13 October 2026. The operator explicitly authorized this second temporary
kernel swap and was available to recast. No desktop automation, typing, FKA
change or C241 input. Candidate console UI tests were not run.

## Candidate and scope

The exact guarded kernel (`e0f00fa8…92e16`) ran from
`output/candidate-runs/runtime-guard-20261013`, PID 19200. The repaired native
runtime and receiver came from `combined-runtime-guard-20261013`. Its one receiver
was PID 17164, bound only to C24C (`C24CBFBD`). The package and prepared-run hashes
were checked before startup. The existing release was idle and both phones were
unowned; its console closed normally and its kernel stopped gracefully.

The test kernel/receiver ran from approximately 04:56:03 to 05:05:01 UTC.
Startup passed without missing-plugin errors or automatic receiver restarts.
C24C recast and delivered 6,715 frames by the final pre-shutdown status, with
zero receiver restarts. This is a real receiver-startup result for
this package, not clean-PC, scale or endurance acceptance.

## Observed results

| Check | Result and limit |
|---|---|
| Receiver startup and identity | Passed; exact kernel hash, C24C-only mapping, live frames, zero restarts |
| Pointer movement | Upper (40,100) and lower (460,980) points visibly reached; no pixel-precision measurement |
| Calculator icon tap | Opened Calculator. Initial capture was launch animation; later read-only capture showed 0. No second tap; no measured visible-response latency |
| Upward swipe intended to return Home | **Failed visible effect.** API code 0, but Calculator remained. Not retried; operator returned Home physically |
| Left/right Home-page swipes | Changed to adjacent page and back to original page |
| Brief held input then Stop | Kernel acknowledged Stop/cleanup in 4.15 ms; status stopped/unowned. This is API round-trip time, not measured physical release latency |
| Rejected input while stopped | Old-token move returned 409; no replay attempted |
| Explicit Resume and release | New ownership acquired; pointer moved; release confirmed. Ended unowned, inactive, not stopped, generation 8 |
| Candidate shutdown | Graceful; kernel and child receiver exited, no force kill |

`visual-review.json` links the inspected frames. Per-step `result.json` files
record API replies/times and video/input snapshots. Their `completed` flag means
the scripted API step finished, not that its intended visible effect passed.
The failed Home gesture demonstrates why those assessments stay separate.

The one-off script reuses the existing accuracy runner's API/lease helper. It
does not replace the Gate 4 suite. The initial script required continuously
fresh frames on a static screen. After Calculator went quiet, later steps
recorded the cached before-frame, made one non-activating pointer move, and
required fresh delivery before activation. Both script versions are retained.
No product timing, calibration or FKA setting was changed.

## Restoration

The normal launcher restarted the original release: kernel 9152, C24C receiver
4260, C241 receiver 42612 and console 33532. Installed binaries, launcher, saved
configuration and operator settings content still matched their saved hashes.
The candidate processes exited; no test input process is left running.

The first restoration check at 05:05:59 UTC found C24C mirroring and both phones
free, but C241 had not connected. This initial state is preserved in
`restoration-confirmed.json` with `both_mirroring: false`; the filename does not
override its data. The operator was asked to close/reopen C241's mirroring menu
without cable, Wi-Fi or setting changes. The operator then reported C241 was
disconnected when checked and reconnected it; they did not report a missing
receiver name in this retry restoration. At **05:08:09 UTC**, both original
receivers were live with zero restarts and both phones were free, inactive and
generation 0. See `restoration-final.json`. This does not resolve the earlier
rediscovery issue, but this instance is not evidence of another missing-name delay.

## Remaining acceptance

Real console controls, queued-action notices, timeout injection, diagnostic export
through the actual button, varied-target accuracy, sustained video, broader rack
scale and endurance were not tested here. Home remains unresolved; the failed
pointer gesture is not a fix for its known Tab-producing keyboard sequence.
Typing remains deferred. No release gate is signed off, and nothing was pushed,
promoted or deployed. Next work should use these results rather than repeating
the now-passed runtime startup check without a relevant change.

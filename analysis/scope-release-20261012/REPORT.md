# Recovery after an unanswered control release

Started 12 October; completed 13 October 2026. Offline verification only.

## Reproduced failure

An explicit scope release cleared its private ownership token before the service
answered. If that answer was lost, the phone could still be owned while Resume
had no token to retry the release. The real kernel refuses Resume while a phone
has an owner. Normal close likewise had no token left to finish cleanup.

The test transport's Resume behavior previously omitted that real-kernel refusal.
It now refuses active ownership or a recorded board-release failure, matching
`InputSessions.Resume`. With this correction and the new regression check, the
unchanged product failed **Resume retries its own unconfirmed scope release before
resuming**. See `before-build-failure.txt` and the archived `before-source` copy.

## Product change

- Retain this console's token until release or lease closure is established,
  using the existing ownership-scoped release/status interpretation.
- An explicit Resume or normal close can retry an unanswered release. No input
  command is replayed and no automatic Resume is added.
- Concurrent requests for the same token/lifetime share their release task and
  answer. Reselecting that phone cannot bypass a pending or unconfirmed release.
- Different phones release independently, so one slow answer does not delay
  sending another phone's release.
- Apply a result only while its token and control lifetime still match. A result
  arriving after a newer Stop or replacement lease does not overwrite that
  newer confirmation, restore an old token or clear the replacement token.

The existing HTTP timeout and bounded normal-close behavior remain. Requests
still carry only each phone's own token. Stop still bypasses ordinary queues.
Kernel, receiver, typing timing and physical-phone configuration are unchanged.

## Verification

**382 console self-tests pass**, including ten new checks. The final Release
build has zero warnings/errors. Tests use simulated transport; window-lifecycle
checks never show a window or create a native handle.

| Regression | Evidence |
|---|---|
| Lost scope-release answer then Resume | Same private token is retried; mock refuses Resume while still owned; recovery succeeds after release |
| Lost answer then normal close | Close releases the retained token and records confirmation |
| Reselection during/after unanswered release | No new acquire or pointer command is sent |
| Duplicate scope releases | Both calls await one transport answer |
| Older failure after successful Stop | Stop's confirmation remains and the obsolete failure emits no notice |
| Older pending release plus new lease | New lease releases separately; older result cannot change its outcome |
| Two-phone release | Both releases start before either answer is returned; no unscoped Stop or replay |

Two controls establish that these checks detect the faults:

1. The preserved pre-fix product fails the Resume recovery check above.
2. A separate copy with only the token-equality guard removed fails **An older
   failed release cannot overwrite a newer confirmed Stop**. See
   `negative-stop-change.json` and `negative-stop-build-failure.txt`.

The final build and negative controls ran with normal temporary-file permissions.
The kernel's historical 179 self-tests were not rerun because its bytes/source
are unchanged. No UI button, mouse, screen capture, network service or phone ran
for this work. These checks establish protocol/lifetime behavior, not physical
release timing or every possible delayed UI notice ordering.

## Exact candidate and preservation

`console-manifest.json` records 36 source inputs and five output files. The build
was made from the recorded working source on base `9151f08`; its informational
version alone is not a clean-source identity. Console DLL SHA-256:
`a49c5100aa24cf504a033b121380f3734101518b69e3212a8b244f1fc5a2b743`.

`package-result.json` records the immutable combined review package, reusing the
unchanged kernel, patched receiver and preserved native runtime. The previous
package stays intact. `preparation.json` and `run-inventory.json` describe a new
C24C-only, hover-off candidate copy validated only through the no-window startup
modes. It is not launched. Installed files and operator settings retain their
recorded hashes.

The external archive receipt is `archive-verification.json` once completed.
No promotion, deployment, push, rack restart or phone-setting change is included.
Typing stays deferred. The actual candidate's physical accuracy, controls,
video/recovery, scale and endurance acceptance remain open.

A fresh read-only process/listener check (`rack-readiness.json`) found no iMouse
console, kernel or receiver, and no listener on port 9913. The rack was not
started. A coordinated C24C candidate window was requested; no response or
authorization is assumed from waiting.

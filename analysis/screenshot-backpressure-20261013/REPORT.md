# Slow screenshot readers cannot hold up frame delivery

13 October 2026. Offline repair on `local/combined-candidate-20261012`, following
`7aff93e`. No installed release, rack endpoint, phone setting, receiver or desktop
was operated. Typing remains deferred. No gate is signed off here.

## Reproduced failure

`FrameStore.WriteFrame` held `_gate` while synchronously writing the entire BMP
to the client's HTTP stream. The producer and status snapshots need that same
lock. A client that stops reading can therefore hold up incoming frames and
status, even when the receiver is healthy. This source defect is not asserted
as the cause of any previously observed physical freeze.

First, the unchanged locking/write behavior was exposed through an internal
callback, with the real HTTP method delegating to it. A blocked writer prevented
an independently scheduled producer/status check from advancing: **25/26 tests
passed, the new stall test failed**. The callback extraction did not move I/O or
change the lock lifetime. The saved `FrameStore-before.cs.txt` and reconstructed
`Program-before.cs.txt` match the original failing build's PDB source checksums
(`before-pdb-check.json`). The failing binary and log are preserved.

## Repair

- Capture frame metadata and a pooled byte copy together under the short delivery
  lock, then send asynchronously outside it. The producer's two buffers can be
  reused without corrupting an in-flight response or mismatching its sequence.
- Admit at most two transfers per phone. Excess requests do not queue or rent
  buffers; the kernel API sends HTTP 503, an explanatory JSON response and
  `Retry-After: 1`. Another phone has independent capacity.
- Each admitted transfer has a five-second deadline and listens to request/store
  cancellation. The real HTTP writer aborts its response on cancellation, including
  when the peer has stopped reading. HTTP.sys abort errors are classified as
  cancellation instead of a new receiver error.
- Return a pooled buffer only when the actual writer has finished, even if a
  callback ignores cancellation. There is no detached write followed by premature
  buffer reuse. The two-slot bound continues to apply during that wait.
- Pass server shutdown through the screenshot path. Cancellation handling is
  scoped to screenshot responses; input-request error handling is unchanged.

## Verification

| Check | Result |
|---|---|
| Default frame/metric suite | **34/34**; nine additions cover the stall, byte/metadata integrity, capacity/peer isolation, unavailable frames, error cleanup, caller cancellation, shutdown, deadline, and delayed-writer buffer lifetime |
| Deliberate buffer-alias regression | **33/34**; sending a producer-owned buffer instead of the retained copy fails the integrity case |
| Actual loopback HTTP writer | Two clients stopped reading 2048x2048 BMP bodies; producer sequence advanced; excess transfer was busy; both blocked responses cancelled at about **5.06 s**; a later complete response matched the new bytes/sequence |
| Kernel self-tests | **206 passed**, fake HID and synthetic private pipes only |
| Existing cleanup integration harness | All **nine scenarios passed**, including lost replies, Stop/release/Resume, lease expiry and mock port isolation; simulated board only |
| Final kernel and frame-tool Release builds | Zero warnings/errors |

`final-frame-tests.txt`, `final-http-tests.txt`, `final-kernel-self-tests.txt` and
`cleanup-harness-results.json` are the final results. The HTTP fixture invokes the
real `FrameStore.WriteFrameAsync` and manually maps the returned busy value to
503; it does not exercise the kernel API's JSON/Retry-After serialization or the
actual console's reaction to that response. Its optional mode contains no HID,
receiver or UI code and never contacts port 9913. Both listeners and sockets were
disposed before process exit. The ordinary 34-case suite opens no HTTP listener.

The first parallel integration-harness build stopped during restore with no
compiler errors reported. A serial build using the already-restored dependencies
completed successfully. Both build logs are retained; only the latter is a pass.

## Candidate identity and limits

The final scratch kernel is `final-kernel/iMouse2.Kernel.dll`, SHA-256
`62371502123f45af0649804a60ff01774143088a63de2fd9dad4fcc458127565`.
`kernel-manifest.json` records source/output bytes; `frame-tests-manifest.json`
explicitly includes the production files linked by the frame test project.
`harness-artifacts.json` records the integration run's assemblies.

This functional kernel change is **not** in the immutable package used for the
previous C24C live window. It is not promoted, installed, pushed or physically
accepted. The native receiver, its runtime and console source are unchanged.
Prepare and verify a new combined package before a later approved window; do not
silently replace files inside a prior package or use its live checks as sign-off
for this binary.

The copy limit bounds retained managed transfer buffers, not all operating-system
network buffers or full-rack memory. The 12 MiB synthetic frame deliberately
exceeds normal 500x1080 delivery to ensure real backpressure. CPU cost, displayed
FPS, many-viewer fairness, end-to-end delay, physical recasting and 19-phone load
remain unmeasured. Header age describes capture for the response and excludes
time in transit. No physical freeze/recovery/latency gate is closed.

All prior installed/configuration/settings hashes are compared separately from
the original receivers' actively written logs. Evidence and exact builds are
preserved outside the checkout with checksums; see `archive-verification.json`.

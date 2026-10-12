# Frame freshness and diagnostics — 12 October 2026

**Completed offline; not installed or promoted.** Main checkout `local/coordinator-work`, base `01fb669`, with existing uncommitted work preserved. Typing remains deferred.

## Findings and changes

Two regressions were demonstrated before the repair: a rate meter kept reporting about 35 updates/s after a two-second idle period, and a 5.1-second presentation gap was omitted (reported maximum about 23 ms). Both are now covered by deterministic monotonic-clock tests.

- Moved the UI-independent meters from `LiveFrame.cs` into `FrameMetrics.cs`. The rate window expires on reads and decays while waiting; jitter retains long intervals and exposes the current unfinished gap. The existing status timer refreshes the rate without requiring new frames. The label says updates/s, reflecting bitmap updates after pixel deduplication.
- The console FPS report now keeps zero samples, resets meters after warm-up and identifies the measurement scope. It still is not physical display-frame accounting.
- `FrameStore` now records an atomic delivery snapshot: instance identity, received sequence, monotonic age, connection, availability, dimensions, status and reason. Full identical BMPs advance delivery; polling an old picture does not. Stop, malformed/truncated frames, disconnect and cancellation clear picture availability. Reconnect preserves the store identity/sequence and clears the old failure after valid delivery.
- Kernel status includes the new per-phone telemetry and receiver messages. Screenshot metadata is written under the image lock, identifying the same stored picture. No socket/listener was required for the new status contract tests.
- Diagnostic exports preserve delivery information and receiver messages. Two new exporter tests failed before this change; all pass afterward. Legacy missing metadata stays unknown.

## Validation

| Check | Result |
|---|---|
| Focused synthetic frame/metric tests | 25 passed |
| Kernel self-tests, including four new status checks | 74 passed; fake HID and synthetic local pipes only |
| Console self-tests | 112 passed; mock transport, no window shown |
| Diagnostic exporter tests | 20 passed; host/UI/network boundaries mocked |
| Total | **231 passed** |
| Scratch kernel and console Release builds | Zero warnings or errors |
| Source/build manifests | Kernel 19 inputs / 6 outputs; console 15 inputs / 6 outputs verified |
| Installed kernel, console DLL, receiver hashes | All unchanged against the prior release record |
| Whitespace diff check | Passed |

The kernel self-tests ran with approved sandbox escalation because the sandbox blocks their private named-pipe connection. Self-test mode returns before hardware initialization. No real kernel API, receiver advertisement, phone input, screen control, installed-process restart, setting change, deployment or push occurred. The console self-test entry point returns before constructing a window and writes only its scratch QA result.

## Limits and next work

The two-second `quiet` threshold means only that no new BMP arrived. It does not distinguish an intentionally still source from a stalled pipeline. Cached screenshots remain available for compatibility; legacy `live` is not a freshness guarantee. The console does not yet consume screenshot delivery metadata to warn about old previews. Source capture time and physical compositor/display timing remain unknown, and long intervals can reflect still content. No live gate acceptance is claimed.

Next bounded offline task: consume the new metadata in the existing console polling path, retaining compatibility with older services; test stale/unknown delivery and reconnect handling without automatically stopping legitimate still screens. Full multi-phone load and real visible latency remain later acceptance work.

## Preservation

Original touched source files are in `before/`. Test logs, the scratch binaries and source/build manifests are alongside this report. The full batch, source snapshots and prior versions are copied to `../iMouseXP-2.0-evidence-archive/20261012-frame-freshness/` with SHA256SUMS.txt. Changes are local and uncommitted; earlier work and evidence are preserved.

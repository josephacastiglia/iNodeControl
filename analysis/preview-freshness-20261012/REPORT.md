# Selected-preview freshness — 12 October 2026

**Completed offline; not installed or promoted.** Work remains on `local/coordinator-work` at base `01fb669`, with prior local changes preserved. Typing remains deferred.

## What changed

- `ScreenshotIntoAsync` reads the frame session, sequence, age and delivery headers into the same reusable buffer as the image. Every request first clears old metadata. Missing/malformed metadata on an older service means unknown age, not a fabricated fresh image. Base64 fallback keeps metadata from its own response.
- `PreviewFreshness` tracks the image actually presented, separately from the latest fetched frame. Identical pixels with new delivery evidence refresh the status without forcing redraws. Cached identities cannot become younger on repeated polling. Sequence regressions are unknown; a new receiver session permits sequence reset.
- Selection epochs, monotonically numbered screenshot requests and content revisions reject old-phone responses, late successes/failures and obsolete pending presentations. Manual and continuous fetch histories cannot borrow one another's pixel comparisons.
- The selected phone has a persistent status below its title, plus the fuller Activity line. It reports recent receipt, unavailable age, potentially old preview, paused preview or failed updates. The existing five-second refresh updates it during quiet periods. Text wraps in Activity and is ellipsized with the full tooltip in the header.
- A screenshot timeout no longer exits the continuous pump as if it were a user cancellation. Lifetime cancellation still exits; screenshot failures use the existing bounded-delay retry path. This retries screenshot reads only, never input commands.
- Cleared pending frames are returned to the existing pool rather than abandoned.

## Validation

| Check | Result |
|---|---|
| New preview/parser/API transport tests | 36 passed |
| Existing synthetic frame and meter tests | 25 passed |
| Console mock self-tests | 112 passed |
| Total | **173 passed** |
| Console Release scratch build | Zero warnings / errors |
| Source/build manifest | Saved and verified against current source and outputs |
| Installed kernel, console DLL and receiver hashes | Unchanged against the recorded release |
| Whitespace diff check | Passed |

Tests cover malformed/legacy headers, culture-independent parsing, conservative request timing, cached-frame age, still-screen delivery, server replacement, request reordering, failed fetch cleanup and recovery, source-selection changes and pending-frame races. The new tests inject HTTP handlers that permit only mock screenshot GETs. Console self-test mode exits before constructing a window and uses mocked transport; output is in scratch `qa/self-tests.json`. The WPF markup builds, but no interactive UI/layout validation was run.

No rack API was needed despite the operator permitting it. No phone input, desktop control, operator settings writes, installed-process restarts, deployment or push occurred. These are main-checkout source changes, not a replacement for the separately preserved integration candidate.

## Limits and next step

Reported age is receiver delivery age plus a conservative request-time allowance, not source capture time or a physical-display guarantee. Two seconds without new delivery is labelled potentially old, never proven frozen. Legacy services stay usable and explicitly unknown. The existing input readiness rules are unchanged; this is an operator-facing diagnostic, not automatic cancellation or lockout. A still image may legitimately be old.

The smaller wall tiles still use their existing image/rate behavior. Next offline work can carry the same status into per-phone tiles and test multi-phone scheduling/failure isolation with synthetic streams. Full rack load and real visible latency remain later hardware acceptance work. The typing issue remains deferred.

## Preservation

Prior versions are in `before/`. Current source snapshots, scratch build, tests, manifest, changes and this report are archived under `../iMouseXP-2.0-evidence-archive/20261012-preview-freshness/`, with SHA256SUMS.txt. Nothing is committed or pushed in this batch.

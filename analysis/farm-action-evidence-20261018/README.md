# Fresh-frame action decisions — 18 October 2026

**Offline work completed. Live inspection remains disabled.** No rack API, phone input, PC control, publication, messaging, installed-release change or service restart was used in this pass.

## Problems reproduced and fixed

1. **A new dialog could arrive between slide inspection and movement.** The previous code checked only the stored frame's age. The new regression introduces a permission dialog after the first owned capture: the old code still sends a swipe before noticing it. The fixed workflow takes a fresh recognized frame before each swipe, checks the same expected slide and page position, and sends nothing when the dialog appears.
2. **Result retrieval could still return `visual_match` after a retained image was damaged.** Previously, the image endpoint checked its hash but the result endpoint checked only the source package. The second regression damages an inspection frame. Result retrieval now refuses damaged or missing images and observation records before returning a successful result.

Both regressions failed as assertions against the prior implementation and passed after the fixes. An initial test-fixture import error is retained separately and is not counted as evidence of either defect.

## Changes

- Every proposed swipe records its decision observation, image and OCR-record digests, stream/session/sequence, ownership generation, source package and from/to slide. The evidence is rechecked for integrity, freshness and ownership after journalling and before sending. A failed check is recorded as `not_sent`; a dispatched command whose answer is lost remains `outcome_unknown`. Neither is automatically retried.
- The fresh guard frame is separate from the slide's earlier capture and its sequence must advance. Every accepted guard retains its media comparison and expected position.
- `ObservationStore.current_evidence` obtains one stored record/image pair, validates the image, hashes the immutable record, then applies current age. The action cannot combine one capture's metadata with a different capture's image.
- New captures require OCR to identify the exact raw input frame. The Windows OCR bridge holds a read-only file lock, hashes the submitted PNG and recognizes that same file; Python verifies this digest before accepting the response. Existing historical capture records are not rewritten.
- Inspection version 2 retains an evidence manifest with image and record hashes. Result retrieval reads the record and frames in one SQLite snapshot and verifies the complete manifest. Image retrieval also checks against that manifest. Older version-1 inspections remain historical review holds; they are not silently upgraded or replayed.
- The candidate health endpoint reports `carouselInspectionVersion=2` and still reports `carouselInspectionLiveMovement=false`. No live-enabling request field, general input endpoint or new native start button was added.

## Validation

| Check | Result |
|---|---|
| New regression pair on prior code | Both failed for the intended assertions |
| Targeted decision/evidence tests | 12 passed |
| Complete Python farm suite | **271 passed**, no skips; 84.770 seconds |
| Native headless checks | **505 passed**; all commands used mock transport |
| Release build | Zero warnings and errors |
| Actual Windows OCR, generated local image | Exact `DRAFT ONLY`, raw-frame and submitted-image hashes verified; 541 ms in this one check |
| Candidate launcher `-ValidateOnly` | Correct isolated output, simulation backend on 9915, no process started |

Additional failure coverage includes wrong media before a swipe, evidence aging while the action is journalled, cancellation before transport, changed OCR records after a decision, absent retained frames, legacy evidence and incorrect OCR source hashes. Existing token, cancellation, lease-replacement, lost-answer, HTTP origin and result-recovery tests continue to pass. HTTP tests use only registered ephemeral mock listeners with a network guard; actual OCR reads a generated file, not a desktop or phone screen.

## Candidate and preservation

- Output: `output/codex-farm-action-evidence-20261018`.
- DLL SHA-256: `1a4eb3be8f66ae1e72f933b5256122d9c39572b440310f820eefd5b475f99283`.
- Backend source SHA-256: `d2010da25e747f336ea0eab94a004d64c2c4e642d716d4769a246a979920cc4a` (15 source files).
- `Open Marketing Farm Candidate.ps1` points to this separate candidate; installed shortcuts and release paths are unchanged. Native source is unchanged and was rebuilt/tested with the updated backend.
- Exact binaries, source, generated OCR fixture, regression failures/passes and final test logs are archived with checksums under `iMouseXP-2.0-evidence-archive/20261018-farm-action-evidence`. Raw run files stay outside Git; this report is tracked.

## Limits and next work

Freshness is measured from receiver delivery, not from iOS source capture. An app can still change after the latest frame; these checks reduce the stale-decision gap but cannot make screen input atomic. The 541 ms OCR result is one local generated-image check, not a responsiveness acceptance result.

This still does not prove account continuity, caption, draft saving or reopening. Those stages need a bounded, evidence-backed transition workflow and interruption recovery. Candidate-kernel paired-frame validation and a coordinated C24C rehearsal are still required before enabling live inspection. No such live window was run or assumed in this pass.

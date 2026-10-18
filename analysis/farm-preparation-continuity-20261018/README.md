# Scheduled preparation continuity and job recovery — 18 October 2026

This pass completes the local path from recurring preparation to reviewable carousel/video drafts. It does not enable unattended app operation. No phone input, rack API, PC control, publishing, messaging, installed-release changes or operator-settings writes were needed.

## Result

- Code commit: `6b395eec620ae5c55f268b45dccf04e2d1548a89` on `local/combined-candidate-20261012`, local only.
- Candidate: `output/codex-farm-preparation-20261018`; DLL SHA-256 `49cab77c792b532b17b51283654ac9a2621ce1ae0d7058d8f45c8c05951ffd1b`. Built from that committed source; report changes do not alter the product.
- Backend source hash: `db679de2de13448ad16711bc318b09bf81d60dfdc111335fe326048d9e85e174`. The separate launcher checks this exact source, uses simulation on loopback 9915, separate settings and hover tracking off.
- **318 Python tests, no skips; 532 native headless checks.** Clean Release build, zero warnings/errors. No desktop window was shown by the native checks.

## What changed

### Every prepared batch stays reviewable

Previously a scheduled run retained filenames, but editors selected the latest manifest. A newer render could therefore make an older run inconvenient or impossible to open correctly.

Each generation now retains its own checksum-pinned manifest. Successful C24C preparation also snapshots the carousel images and complete caption into the existing draft store. A missing/changed manifest or damaged/duplicate/incomplete image batch fails the run and holds future preparation; it never substitutes the latest batch. Later local edits survive repeated retrieval of the original preparation request.

The preparation window shows recent runs and opens the selected run's carousel, or prepares its original video and caption for the chosen destination. Old records without batch identity remain readable but cannot silently open newer content. The window shows the latest 30 run records; older records and source assets remain on disk, and saved carousels remain in the normal library. No automatic deletion was added.

Opening a scheduled carousel archives unrelated unsaved editor work first. Video requests pin generation, manifest hash and source bytes through response recovery. Missing/changed source files stop new video preparation; already saved video copies remain usable. Repeated exports of an unchanged carousel or video revision now have identical bytes/checksums instead of inheriting the current ZIP timestamp.

### Jobs remain recoverable around cancellation and crashes

Cancellation can arrive before submission and is recorded durably before acknowledgement. A delayed request with that ID cannot start, even after a backend restart. Cancellation and admission are serialized in SQLite; a worker also checks cancellation before calling its action. A second process cannot execute another job against the same journal while its worker lock is held. Reads distinguish another active backend from an interrupted process; a completion committed during the ownership check is recovered correctly.

Thread-start failures release the worker lock and leave a failed, non-replayable request. A crashed process releases the OS lock but its accepted work remains unknown/interrupted and is never replayed. Cancellation from another registry reaches a cooperative active worker through the journal. This does not forcibly interrupt an in-progress codec; it prevents subsequent cooperative work and reports the outcome.

A regression run caught a monitor race: it could wake before completion, acquire the registry lock after completion, and rewrite the terminal status to cancelling. The monitor now rechecks completion under that lock. The native client also retains the request bookmark after server/transport uncertainty instead of treating HTTP 500 or a conflicting response as proof that nothing was accepted.

## Evidence

| Check | Result and scope |
|---|---|
| Full guarded Python suite | 318 passed; `python-verified.txt`. Ephemeral loopback mocks only; external/rack networking forbidden. |
| Native headless checks | 532 passed; `native-self-tests.json`. Screens rendered from unshown WPF trees, no native window/PC control. |
| Real local preparation | Two background runs generated separate four-slide/MP4 batches. The first carousel stayed intact after the next batch. Worker stopped at its run limit. |
| Real video preparation | The older batch's source encoded and fully decoded for TikTok, X, YouTube Short and Instagram Reel draft packages. Two-second test video; no transfer listener or app action. |
| Lost replies and source changes | Original IDs recover saved copies without overwriting edits or generating duplicate drafts; damaged/missing batches refuse. |
| Actual process boundaries | Separate child worker excluded a competing process and observed durable cancellation; a deliberate child crash exited 73, released its lock, and was not replayed. |
| Negative controls | Cancel-before-admission, the terminal-monitor race and stable export checks fail on preserved `91dfda8` source and pass now. See `negative-controls.json`. |
| Initial failures kept | The earlier focused log contains the ZIP timestamp mismatch and terminal-status race. The initial sandbox-only job run hit TEMP rename restrictions; the authorized offline reruns pass. |

Reproducers are `exercise_preparation.py` (real local media, all networking forbidden) and `negative_controls.py` (preserved-source comparison). Full logs, generated media, databases, candidate and exact source are preserved locally outside Git at `iMouseXP-2.0-evidence-archive/20261018-farm-preparation-continuity`, with checksums. Nothing was pushed or promoted.

## What still needs live acceptance

1. Validate paired screenshot freshness on the compatible candidate kernel against an actual phone stream. The known installed release lacks the required metadata; this pass did not start or swap a kernel.
2. Validate the real app transition adapter through account, media selection, complete caption, Save draft, library and reopen checks. Existing synthetic rehearsals and earlier supervised phone saves remain separate evidence.
3. Exercise interruptions and recovery on those real workflows, including app/version changes and account identity. No unverified result authorizes phone input.
4. Add genuine account/post observations for analytics. Unattended publishing and messaging remain outside the approved scope and disabled.

The next live window is C24C only and must preserve the installed release. No test service or background schedule from this pass is left running. The current phone/mirroring state was not inspected or changed.

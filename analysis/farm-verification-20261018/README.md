# Account, media and reopened-draft evidence

18 October 2026. Branch `local/combined-candidate-20261012`, based on `ad082e5`. **Local review candidate; not accepted for unattended phone workflows.** No rack API calls, desktop control, phone input, publishing, messaging or installed-release changes occurred. This pass used recorded C24C screens and isolated tests.

## What is implemented

The native carousel editor's **Review phone evidence** opens a saved-evidence comparison for a specific local draft revision. It saves pending local edits first. The operator chooses the expected Instagram handle and recorded stages: account before, prepared slide views, library, reopened slide views and account after. Multiple slide observations are compared in capture-time order. Opening/refreshing this window reads existing records only; it does not take a screenshot or send phone input.

| Check | Behavior |
|---|---|
| Account | Reclassifies the stored OCR and requires exact handle text on account screens before and after. Mentions in captions do not establish identity. Account bracketing is not uninterrupted account continuity. |
| Source media | Exports the exact saved revision and checks each asset hash. Later local changes do not alter the review's source package. |
| Visible media | Compares the first fully visible preview against all expected assets using colour differences, local-block differences and separation from the next closest candidate. Low-detail and similar images remain unresolved. Every expected slide needs its own prepared and reopened view in the requested sequence. |
| Caption | Compares all visible lines in the supported carousel caption region, in spatial order, with the complete saved caption. Only CRLF/LF line-ending normalization is allowed; no character, punctuation or spacing repair. Hidden/wrapped/unsupported layouts require review. |
| Library | A sparse Drafts/Select screen can be checked for a matching first-slide thumbnail in the supported square-crop layout. Its app identity remains independently unknown; this never changes the observer's global unknown classification. The actual historical thumbnail does not pass the comparison. |
| Run context | Requires recent paired metadata at capture, stable/idle input, unchanged observer/device/receiver/input-generation/stream identity, advancing sequences, distinct observations and a chronological nonoverlapping sequence within 15 minutes. Missing context stays unresolved. |
| Durability | Stores an immutable review, exact source ZIP and selected screenshot/OCR snapshots in `draft-verifications.db`, bounded to 32 MiB per review. Checksums are verified on retrieval. Missing/pruned/old-unhashed captures are recorded as gaps. Saved review images survive subsequent observation pruning. |
| Recovery | Duplicate request IDs return the same record, including after restart. Different evidence under the same ID is refused. Lost responses recover through GET; no capture or phone action is replayed. Later draft revisions are prominently marked historical. |

The best result is `consistent_visual_evidence`, not an accepted app save. `savedDraftVerified`, `accountContinuityProven` and `automaticInputAllowed` remain false. Similar pixels cannot prove byte identity, capture order cannot prove how the carousel was navigated, and a library/reopened view cannot independently establish that a **new** draft was saved. A simulation remains labelled simulation; a saved historical observation is never current readiness. Reviews do not modify the local draft's `savedInInstagram` flag.

The initial comparator supports the recorded English Instagram carousel details layout on a portrait frame with the C24C aspect ratio. Bounds scale with the image; they are not universal app coordinates and are never used for taps. Other platform/format requests are refused rather than receiving borrowed acceptance.

## Results

| Test | Result |
|---|---|
| Complete Python suite | **223 passed**, 46.416 s, no skips. Mock transport and registered ephemeral loopback listeners only. |
| Native headless suite | **502 passed**. No native desktop window or input; new review render inspected. |
| Release build | Zero warnings/errors, separate candidate output. |
| HTTP review flow | Create/retrieve/list, idempotence, lost-result retrieval, retained-image access, foreign-origin refusal and invalid requests pass; no kernel client constructed. |
| Failure cases | Wrong accounts, caption mentions, missing/reordered/duplicate/wrong slides, partial caption, punctuation/space changes, lookalikes, flat images, permissions, stale captures, changed context, nonfinite time, damaged evidence and changed draft revisions stay unresolved. |
| Saved real profile | Earlier C24C Instagram profile OCR matches the designated test account exactly. No current-account claim. |
| Prepared/reopened real carousel | Exact expected first slide is the unique visual match in both captures; full three-line caption matches both. Mean image errors about 0.0134/0.0135 with a roughly 0.10 margin to the next candidate. |
| Actual library thumbnail | **Unresolved.** Mean difference about 0.067, worst local block about 0.318; thresholds are 0.045/0.12. The comparator refuses it. The visible crop was investigated without relaxing thresholds; the remaining difference's cause is not proven. |
| Launcher | ValidateOnly passed; no processes started; matching thirteen-file backend hash. |

The saved screens are development/regression material, not independent accuracy evidence. They also lack complete slide coverage, an account-after observation and paired frame freshness. The successful first-slide/caption comparisons do not close those gaps, and no historic timestamp or metadata was invented to obtain a pass. Earlier supervised saving evidence remains valid within its original scope.

The private replay script initially expected a library match and failed. Its final expected result explicitly retains that unresolved case. Initial failed replay output and the crop investigation are retained beside the final result; no false library success is reported. The initial native render exposed a record-debug label in a combo box; its user-facing label was corrected and the final build/headless tests rerun.

## Candidate and use

- Output: `output/codex-farm-verification-20261018`.
- DLL SHA-256: `36c8645d0bebb5d92c928a2cce85e5970e8d7ae4056409b45edb4c6976b9c188`.
- Backend source hash: `3f87387a7765f5685cc975a2478567e2057c9ca18ff5acacf51c33bb31395e57`.
- Candidate launcher: `Open Marketing Farm Candidate.ps1`, simulation backend on loopback 9915, isolated settings and hover tracking off. No installed shortcut or existing service was changed.

Use **Instagram carousel drafts → open a saved draft → Review phone evidence**. Select recorded Instagram observations and choose **Compare saved evidence**. Empty stages produce specific missing-evidence feedback. **Check saved result** recovers an uncertain request. Saved reviews identify their revision and source. **View retained image** retrieves the review's preserved image, not a new phone screenshot.

The review API is local-only: POST `/api/farm/draft-verifications`, GET the same path with `?draft_id=<id>` for history, GET `/<review-id>` for the record and GET `/<review-id>/frames/<observation-id>` for one retained image. Requests accept IDs and expectations only, never a caller-supplied verdict, frame or filesystem path. Phone capture remains a separate explicit action in the existing observation window. The installed kernel still lacks paired frame metadata, so it cannot supply a complete fresh evidence run today.

Reproduce with `python -m unittest discover -s tools -p 'test_farm*.py'`; build `src/iMouse.Console/iMouse.Console.csproj -c Release -o <new-scratch-directory>` and run that directory's `iMouse2.exe --self-test`, waiting for exit. Headless checks write `qa/self-tests.json` and `farm-draft-verification-headless.png`. Do not substitute `--ui-test` or an installed output path.

## Preservation and remaining work

Private evidence and exact binaries/source are preserved in `iMouseXP-2.0-evidence-archive/20261018-farm-verification/` with SHA-256 checksums. This includes the earlier test package and selected source screenshots, new OCR, replay results, tests and the native render. Raw account/screenshots are not added to Git. Operator settings retain their prior content hash. No test service is left running, and no current phone-state claim is made because this pass did not contact the rack.

Remaining: real-stream freshness on a coordinated candidate kernel; full slide coverage and stable account context; reliable library-thumbnail recognition; controlled save/reopen action evidence and interruptions; broader layouts/media types and independent validation. Publishing, messaging and automatic phone execution remain disabled. The previous supervised four-platform draft saves are not replaced or downgraded by these new verification gaps.

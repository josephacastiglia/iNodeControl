# C24C frame freshness and carousel save/reopen — 18 October 2026

**Live receiver-delivery freshness and one supervised existing-draft save/reopen passed. Unattended workflow acceptance remains open.** No PC control, publishing, messaging, C241 input, phone-setting changes or installed-release changes occurred.

## Exact scope

The rack was stopped at preflight. A separate C24C-only kernel ran on loopback 9916 with copied, verified receiver dependencies and isolated configuration. The operator connected mirroring and opened Instagram. No installed console or marketing desktop window was started. Input used the normal scoped kernel lease/API, with a separate lease for each reviewed step.

- Kernel source: `9fa7a859bbeb60495cdbbda326d25010c3ba7961`.
- Test kernel: `output/codex-farm-live-kernel-20261018`, DLL SHA-256 `c72fa4e0b02b82ec4f7a949c9a80375c69da68d7357084401c7bb422c194a873`.
- Native marketing console unchanged: `output/codex-farm-preparation-20261018`, source `6b395eec620a`, DLL SHA-256 `49cab77c792b532b17b51283654ac9a2621ce1ae0d7058d8f45c8c05951ffd1b`.
- Backend after the recognition change: `10d8146564aad2f9cba8e5a602534a9485e25b20ed31c9c34a73bbbebc236c91`. The separate launcher computes this from source; ValidateOnly passed without starting it.
- Original three-slide test package: SHA-256 `7f910284d9c7dc26d3c443183fdda33c78bdd4553036dabc75e38d158f48b616`.

## Observed results

| Check | Result and limit |
|---|---|
| Real frame metadata | Paired session/sequence/delivery/age arrived with screenshots and agreed with surrounding receiver status. Account-boundary captures had age upper bounds about 914, 610 and 628 ms, including observation work. |
| Quiet page | The first profile image was already old. It was refused. A move-only pointer challenge produced new frames; no stale frame authorized a tap. A quiet/static page is not itself proof of a frozen phone. |
| Slow observation | One OCR operation took about 1.72 seconds. Its frame exceeded the 1.5-second budget and no slide swipe was sent. |
| Retained expiry | The final capture became stale without recapture after a 1.7-second wait; its age upper bound was then about 2.34 seconds. |
| Before Save | All three full-size slides, page dots/order and the exact visible three-line caption matched the retained source package. |
| Save and library | One Save draft tap was acknowledged. The same test carousel moved from library column 2 to column 1. The cover was uniquely matched; the library still showed two drafts. This was an existing draft, not creation of a new draft. |
| Reopen | Reopened that matching cover; all three full-size slides and page positions matched again. The full visible caption remained exact. No media or caption edits were made. |
| Account boundaries | Exact expected handle before and after, on the same receiver session. Per-step lease generations changed and observations had gaps: this is sampled boundary evidence, not uninterrupted account continuity. |
| Exit | Preserved the unchanged reopened draft with a second, intentional Save draft on exit. This was not a retry of the earlier save. Returned to the same profile. |

The save responses were followed by an autoplaying media-picker preview, so an unmasked whole-screen stability check correctly stopped. The agent reviewed the returned picker and performed a new explicit step. A documented diagnostic mask covered only the autoplay rectangle when locating Drafts or closing the picker; it did not mask the action controls. No uncertain command was replayed.

## Changes and limits

`tools/farm_live_verification.py` is a reusable **read-only** probe. It verifies the prepared kernel hash, process and single-phone mapping, accepts only the isolated loopback endpoint, refuses redirects, and whitelists status/device/screenshot reads. It cannot acquire control or send input. It uses the production observer and retains real expiry evidence without claiming a saved draft.

Instagram sometimes visibly truncates the Suggested audio label, while OCR reads Next as `ext`. Recognition now accepts four exact truncated label variants only when all five existing toolbar anchors are present in their expected region. Bare `Suggested`, misplaced labels and partial Next still remain unknown. Account and caption text are never repaired.

Some reopened editor captures still remained unknown. For those supervised slide inspections only, the agent reviewed the fresh image and the diagnostic helper additionally checked the exact source package, full-size image match, page dots and complete toolbar. **The product's unknown result, `automaticInputAllowed=false` and `savedDraftVerified=false` were retained.** This helper is not a live product adapter or a successful unattended rehearsal.

There were 29 explicit step records and 94 acknowledged reset/move/click/swipe commands. Ten steps stopped for review, including changed animation, stale OCR, unresolved editor labels and autoplay. These are retained rather than hidden as successful automated transitions. Every acquired lease was released.

## Validation and restoration

**330 Python regression tests passed, no skips**, in `python-tests-final.txt`; the suite permits only its disposable loopback servers. Replaying 36 retained OCR cases preserved every expected screen outcome and accepted no mismatched account; these are regression data, not an independent accuracy set. The isolated kernel Release build was clean and **290 kernel self-tests passed without opening real HID transport**. The initial restricted test attempt failed on a synthetic named pipe; its log is retained separately. Native marketing code did not change: its earlier 532 headless checks were not rerun or represented as current live-window validation.

Cleanup initially refused because PowerShell had deserialized the UTC JSON timestamp into a DateTime, and reparsing its formatted text shifted it by four hours. The recorded PID, exact path, full arguments and actual creation time were rechecked. The diagnostic stop script now preserves the DateTime's kind (or uses round-trip string parsing). Normal Ctrl+C then stopped the exact test kernel and its receiver; no force kill was used.

Final read-only verification found no rack/test kernel, console, receiver or listener left on the test/rack ports. All **25 protected release/settings files** matched their preflight hashes. The original stopped rack state was restored. The last observed phone screen was the expected Instagram profile; FKA was unchanged.

## Preserved evidence and next work

`summarize.py` rechecks the retained source ZIP, all three reopened slide images, caption, account boundaries, expiry and cleanup without network access. Private frames, OCR, command journals, initial failures, build logs, exact sources/kernel/runtime and restoration records are archived outside Git at `iMouseXP-2.0-evidence-archive/20261018-farm-live-verification` with verified checksums. No raw personal screenshots or account records are staged for Git.

Next: use these retained frames offline to handle the autoplay picker and scrolling/truncated editor labels with narrowly defined layout checks. Then implement and validate the actual save/reopen action adapter, including interruptions, cancellation, account changes and lost responses. The existing synthetic recovery suite remains useful but does not establish real-app recovery. No automatic phone workflow, publishing or messaging was enabled.

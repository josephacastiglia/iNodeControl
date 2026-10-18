# Fresh C24C autoplay and saved-draft validation

18 October 2026. Fresh-phone follow-up to
`analysis/farm-layout-stability-20261018/README.md`. **Supervised live validation passed within the scope below.** An existing Instagram test carousel was saved and reopened; all three slides, their order and the complete visible caption matched. Fresh autoplay frames passed the protected-control comparison. A new Next-label OCR failure was corrected and checked on the phone. **Unattended marketing automation remains unaccepted.**

The isolated kernel started at 22:24 UTC and stopped normally at 22:52:34 UTC. The initial stopped rack state was restored. All 25 protected installed-file hashes remained unchanged. No PC control, publishing, messaging, C241 input, FKA change or installed-console launch occurred.

## Scope and starting state

- C24C only; Instagram account `xs.halle.xo`, the existing labelled three-slide test draft.
- API input and phone frames only. No PC control, publishing, messaging, C241 input or FKA changes.
- The rack was stopped. This run uses its own data, receiver/runtime copy and loopback kernel on port 9916. It does not launch the installed console or change the installed release.
- At completion, the test lease was released and this exact candidate stopped normally, returning to the initial stopped state. The installed release remains stopped.

## Candidate identity

- Initial recognition/backend source: `1fd4849e55ebc569f374e60978cb0afdfbd64501`; preparation committed as `3750e26`. The label-crop patch below was applied after the fresh step-11 hold.
- Preserved kernel source: `9fa7a859bbeb60495cdbbda326d25010c3ba7961`; no later kernel changes.
- Kernel DLL SHA-256: `c72fa4e0b02b82ec4f7a949c9a80375c69da68d7357084401c7bb422c194a873`.
- Private runtime: `output/candidate-runs/farm-live-layout-20261018/`.
- `preparation.json` records dependency hashes, the one-phone mapping and startup validation. `protected-files.json` records the installed-file baseline without storing settings contents. `validation-sources.json` freezes the original Python/helper sources; `validation-sources-v2.json` and `source-v2/` retain the changed sources used after the hold. Earlier records remain attributed to the earlier source.

## Procedure used

1. Validate the isolated kernel's exact hash, process, C24C board identity, receiver and free lease. Ask the operator to connect C24C to **iMouse2-C24C**, dismiss Control Centre and open Instagram's profile. FKA stays unchanged; C241 stays untouched.
2. Observe the exact signed-in handle. Use a scoped move-only pointer challenge on quiet video, then require paired receiver metadata and unchanged stream/ownership. The 1,500 ms delivery-age limit includes download, OCR and decision overhead; it is not an iOS capture timestamp.
3. Open the existing uniquely recognized test draft. Compare all three full-size slides and page dots to the original package; verify the complete visible caption before saving. An unknown editor cannot be accepted through the earlier manual fallback.
4. Verify the exact **Next** label on the current frame, using the product's single fixed crop OCR when needed. Retain the OCR method and complete age at dispatch. Never infer Next from partial text or button color.
5. Request the Save sheet and send **Save draft once**. If the answer is uncertain, inspect only; do not replay Save or continue navigation.
6. On the post-save picker, collect two independently fresh frames under the same lease/stream. Use the product's fixed preview exclusion and protected control/grid comparison. Record whether the preview actually moved. Stable images alone do not demonstrate autoplay tolerance.
7. Verify a unique matching cover in Drafts, reopen it, compare every slide in order and the caption, then verify the account on return. Preserve the existing draft on exit. These are sampled checks, not continuous account observation.
8. Release the lease, stop the candidate normally, verify the installed-file hashes and archive raw evidence with checksums. Report any incomplete check without claiming unattended acceptance.

The run helper is an agent-supervised diagnostic with one explicit action per invocation. It uses the product recognizer and comparison functions, but it does **not** implement or certify an unattended production adapter. It restricts transport to the private loopback endpoint and C24C, refuses redirects, journals attempted actions before dispatch, and releases only its own lease.

## Preparation checks (before connection)

- `prepare.py`: validated preserved receiver/runtime checksums and C24C configuration; kernel `--validate-startup` passed with no hardware/listener/receiver/settings side effects.
- `test_phone_step.py`: **10 passed**, 0.527 s. Offline checks of the supervised helper; full results in `helper-tests.txt`.
- Product recognition, read-only probe, save/reopen model, draft-verification and frame-evidence tests: **73 passed**, 76.892 s; `recognition-tests.txt`.
- Actual Windows OCR read exact cropped Next from the retained ambiguous editor fixture in **1,158 ms**. This excludes live download/age overhead and is not a fresh-phone pass; `ocr-readiness.json`.
- Start, stop and read-only preflight PowerShell scripts parsed successfully; Python helpers compiled.
- Historical complete suite: 353 passed in the preceding offline pass. It is not counted as a new run here.

## Live results and limits

| Check | Result | Evidence and limit |
|---|---|---|
| Fresh frames | Passed for accepted observations | Paired receiver/session/sequence metadata; step observation ages 473–1,128 ms. A retained frame expired after 1.7 seconds without recapture. The unchanged 1,500 ms limit includes download, OCR and decision overhead; it is not an iOS capture timestamp. |
| Autoplay preview | Passed on four changing-preview pairs | Two independently fresh frames per pair; controls/grid stayed stable while preview pixels changed. Steps 15, 17, 24 and 26. No control-pixel threshold was relaxed. |
| Exact Next label | Fresh failure corrected | Step 11 refused the click when full-frame OCR was incomplete and the old crop returned no words. After the crop fix, steps 12 and 21 read exact Next at fresh-frame ages of 838 and 931 ms. |
| Source media before save | Passed visually | All three full-size images and page positions/count matched the original package; `pre-save-slides.json`. Visual comparison does not prove image-byte identity. |
| Save and reopen | Passed for the existing test draft | Step 15 saved once; the library had one matching cover among two items. Step 18 reopened it; every slide and the full visible caption matched in `reopened-comparisons.json`. No app restart, server persistence or newly created draft is claimed. |
| Account identity | Passed at boundaries only | Exact authorized handle on the initial/final profiles. Per-step leases and capture gaps do not establish continuous account identity. |
| Cleanup | Passed | Every owned lease released. C24C returned to the same profile, unowned and not stopped. Candidate processes/listeners exited; all 25 protected installed-file hashes matched. |

There were 23 supervised step records and 19 semantic click/swipe actions. Move-only pointer challenges produced new frames on quiet screens; they did not bypass freshness checks. The Save at step 24 was a separate preservation action while exiting the reopened draft, not a retry of step 15.

The compared source is `analysis/farm-phone-transfer-20261017/test-carousel.zip`, SHA-256 `7f910284d9c7dc26d3c443183fdda33c78bdd4553036dabc75e38d158f48b616`. The exact visible caption before and after reopening was:

```text
iMouse carousel draft test.
Three numbered slides in order: 1, 2, 3.
DRAFT ONLY - do not publish.
```

## Five review holds were retained

1. **04-post-picker:** the current Create sheet includes an Edits row while OCR omitted Reel. No Post selection was sent. The diagnostic helper now requires exact positioned Create, Edits, Post, Story and Instants anchors for this variant; it does not infer missing words.
2. **05-open-post-picker:** the format click succeeded, but post-action comparison held for a changing home-indicator area outside the preview exclusion.
3. **06-open-drafts:** the earlier reviewed frame still disagreed with the settled area. It held before acquiring or sending input. A newly captured, separately reviewed frame was used for the next explicit step.
4. **08-open-test-draft:** editor captures differed after opening. It held for review even though both classified as editors. There was no automatic continuation.
5. **11-caption-details:** exact Next text was absent. It held before the Next click; this frame is the fresh failure fixture for the product correction.

These holds are not hidden retries or unattended successes. An agent reviewed images between invocations. Automatic live movement remains disabled; the diagnostic helper is not a production save/reopen adapter.

## Product correction: separate the Next label from its arrow

The old fixed crop included the entire button and its adjacent arrow. On the fresh editor it produced no words. The single optional crop now covers only the label, at `(404,987)-(447,1026)` on the supported 500×1080 frame, enlarged 3× to 129×117. The full button geometry and action target remain unchanged.

The crop must return exact Next. Its proof remains bound to the entire source frame's pixels, crop bytes, bounds, scale and dimensions. Old full-button crop proofs cannot authorize this version. Full-frame OCR is preserved; account/caption text is never repaired. There is still one fixed crop, no fallback cascade and no weakened age budget.

Actual Windows OCR replay read exact Next from 12/12 retained editor frames containing **three distinct label-crop images**. These are development fixtures, not 12 independent accuracy trials. Processing took approximately 0.97–1.92 seconds; the slowest offline replay would exceed the live limit and is not counted as a live pass. Fresh phone captures after the change met the unchanged limit.

Two regressions check that arrow changes leave the label crop unchanged but invalidate whole-frame proof, and that previous crop geometry is rejected. A diagnostic-helper regression checks missing/mispositioned Create-sheet anchors and the wrong action intent.

## Final validation

- Diagnostic helper: **11 passed**; `helper-tests-label-fix.txt`.
- Focused product checks: **43 passed**, 66.519 seconds; `next-label-regressions.txt`.
- Full Python suite: **355 passed**, no skips, 233.398 seconds; `python-tests-final.txt`. Tests used isolated temporary services with a network guard; no rack input was sent by the suite.
- Candidate launcher `-ValidateOnly` passed without starting processes. Effective backend source hash: `e1597503d8fae59d90511e4f2d8c9364b7580a7012797b385c2cb04bcd079cea`.
- Native console/kernel source and binaries are unchanged in this pass; their earlier checks are historical, not rerun here.

## Restoration and archive

`restoration.json` at 22:53:28 UTC confirms no remaining rack processes/listeners and restoration of the initial stopped state. `protected-after.json` confirms all 25 installed/settings-file hashes unchanged without retaining settings contents. C24C was left on the authorized profile; stopping the test receiver ended its test mirroring.

Raw frames, OCR, action journals, comparisons, source snapshots, process records and test logs are preserved outside TEMP in `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261018-farm-live-layout`, with a SHA-256 inventory. The separate preparation archive is retained. Raw phone evidence is not published.

## Next work

Build and test the bounded live save/reopen adapter using these observations: explicit transition handling, account continuity, cancellation and unknown-result recovery without replay. This run still needed agent review at five holds. Broader layouts, repeated interruption cases and an actual native-window-to-phone workflow remain open. Publishing and messaging remain disabled.

# Fresh C24C autoplay and saved-draft validation

18 October 2026. Preparation for the fresh-phone follow-up to
`analysis/farm-layout-stability-20261018/README.md`. **Prepared; waiting for the operator to connect C24C. Phone validation is pending.**

At 22:24 UTC the isolated kernel started as PID 37932, with only the C24C receiver (PID 34420). Read-only checks confirmed the exact build and board identity, C24C free, video waiting and all 25 protected installed-file hashes unchanged. No phone input or console launch has occurred. These PIDs are historical; recheck before input. The initial sandboxed loopback read was refused by Windows; the read-only check then completed with approved local-socket access.

## Scope and starting state

- C24C only; Instagram account `xs.halle.xo`, the existing labelled three-slide test draft.
- API input and phone frames only. No PC control, publishing, messaging, C241 input or FKA changes.
- The rack was stopped. This run uses its own data, receiver/runtime copy and loopback kernel on port 9916. It does not launch the installed console or change the installed release.
- At completion, release the test lease and stop this exact candidate normally, returning to the initial stopped state. Do not start a release that was initially stopped.

## Candidate identity

- Recognition/backend source: `1fd4849e55ebc569f374e60978cb0afdfbd64501`.
- Preserved kernel source: `9fa7a859bbeb60495cdbbda326d25010c3ba7961`; no later kernel changes.
- Kernel DLL SHA-256: `c72fa4e0b02b82ec4f7a949c9a80375c69da68d7357084401c7bb422c194a873`.
- Private runtime: `output/candidate-runs/farm-live-layout-20261018/`.
- `preparation.json` records dependency hashes, the one-phone mapping and startup validation. `protected-files.json` records the installed-file baseline without storing settings contents. `validation-sources.json` freezes the Python/helper sources before launch.

## Procedure and acceptance

1. Validate the isolated kernel's exact hash, process, C24C board identity, receiver and free lease. Ask the operator to connect C24C to **iMouse2-C24C**, dismiss Control Centre and open Instagram's profile. FKA stays unchanged; C241 stays untouched.
2. Observe the exact signed-in handle. Use a scoped move-only pointer challenge on quiet video, then require paired receiver metadata and unchanged stream/ownership. The 1,500 ms delivery-age limit includes download, OCR and decision overhead; it is not an iOS capture timestamp.
3. Open the existing uniquely recognized test draft. Compare all three full-size slides and page dots to the original package; verify the complete visible caption before saving. An unknown editor cannot be accepted through the earlier manual fallback.
4. Verify the exact **Next** label on the current frame, using the product's single fixed crop OCR when needed. Retain the OCR method and complete age at dispatch. Never infer Next from partial text or button color.
5. Request the Save sheet and send **Save draft once**. If the answer is uncertain, inspect only; do not replay Save or continue navigation.
6. On the post-save picker, collect two independently fresh frames under the same lease/stream. Use the product's fixed preview exclusion and protected control/grid comparison. Record whether the preview actually moved. Stable images alone do not demonstrate autoplay tolerance.
7. Verify a unique matching cover in Drafts, reopen it, compare every slide in order and the caption, then verify the account on return. Preserve the existing draft on exit. These are sampled checks, not continuous account observation.
8. Release the lease, stop the candidate normally, verify the installed-file hashes and archive raw evidence with checksums. Report any incomplete check without claiming unattended acceptance.

The run helper is an agent-supervised diagnostic with one explicit action per invocation. It uses the product recognizer and comparison functions, but it does **not** implement or certify an unattended production adapter. It restricts transport to the private loopback endpoint and C24C, refuses redirects, journals attempted actions before dispatch, and releases only its own lease.

## Preparation checks

- `prepare.py`: validated preserved receiver/runtime checksums and C24C configuration; kernel `--validate-startup` passed with no hardware/listener/receiver/settings side effects.
- `test_phone_step.py`: **10 passed**, 0.527 s. Offline checks of the supervised helper; full results in `helper-tests.txt`.
- Product recognition, read-only probe, save/reopen model, draft-verification and frame-evidence tests: **73 passed**, 76.892 s; `recognition-tests.txt`.
- Actual Windows OCR read exact cropped Next from the retained ambiguous editor fixture in **1,158 ms**. This excludes live download/age overhead and is not a fresh-phone pass; `ocr-readiness.json`.
- Start, stop and read-only preflight PowerShell scripts parsed successfully; Python helpers compiled.
- Historical complete suite: 353 passed in the preceding offline pass. It is not counted as a new run here.

No physical outcome is recorded until fresh phone evidence is collected.

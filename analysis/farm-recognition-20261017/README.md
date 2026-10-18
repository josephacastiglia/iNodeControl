# Marketing draft recognition and frame freshness

17 October 2026. Local branch `local/combined-candidate-20261012`, built on `aac6089`. **Draft automation is still not accepted for unattended use.** This pass used saved screens, isolated tests and one read-only C24C capture. No desktop control, phone input, publishing, messaging, settings change or installed-release replacement occurred.

## Changes

- Recognize the tested TikTok photo and video details layouts with independent labels in their expected screen regions. Recognize Instagram carousel details, and distinguish its Reel caption editor from background draft controls.
- Keep a sparse Drafts/Select page unknown because it lacks app-specific evidence. Wrong/multiple/ambiguous handles remain unresolved. Known OCR variants are allowed only for specific UI labels; account and caption text never receive character substitutions or invented spaces.
- Exclude navigation/footer text and the tested carousel slide-preview area from caption comparisons. Comparisons remain exact single-line OCR matches, not proof of complete multiline text, media identity, image order or persisted save.
- Require screenshot-bound session, sequence, age and delivery headers consistent with the before/after receiver identity, process, restart count and frame counters. Missing, partial, malformed or inconsistent evidence cannot pass.
- Include download, recognition and PNG encoding in a conservative age bound. Further wall-clock/monotonic elapsed time ages saved evidence. A 1.5-second limit determines recent receiver delivery; backend restart expires old observations without replaying a capture. Counter movement alone is only delivery progress.
- Explain review blockers for unknown/editor/permission screens, wrong app, missing account/caption, active input or stale evidence. No review result enables phone input or claims a draft was saved.
- The native review's freshness notice expires using a local timer, including time spent fetching/displaying its saved frame. It makes no background phone requests. The candidate requires observer protocol version 2; the launcher hashes all twelve backend source files.

The delivery age is time since the kernel received a BMP, **not iOS's source capture timestamp**. Even a recent delivery can contain a repeated or delayed source image; semantic validation remains necessary. Fixed English layout patterns are intentionally narrow and are not app authenticity checks.

## Verification

| Check | Result | Scope |
|---|---|---|
| Python suite | **208 passed**, 35.737 seconds, no skips | Mock phone transport and ephemeral registered loopback listeners |
| Native self-test | **494 passed** | Mock transport; no desktop window or mouse control; headless review render inspected |
| Release build | Zero warnings/errors | New output folder only |
| Frame suite | **34/34 passed** | Existing production frame storage/transport logic, no hardware |
| Screenshot HTTP test | Passed: bounded readers, busy response, advancing producer, timeout abort and exact recovery | Real ephemeral loopback socket; no rack contact |
| Production metadata contract | **4/4 passed** | Production FrameStore decoding/atomic transfer/headers: recent delivery, quiet delivery, processing delay, immutable in-flight bytes as producer advances |
| Prior-code regressions | Prior observer accepted a frame after two seconds of OCR and retained recent status across restart; this observer marks stale/unavailable respectively | Same synthetic input against `aac6089` and current source |
| Saved-frame regression | **39/39 expected outcomes**, including one intentionally unknown sparse library | 36 earlier OCR frames plus three carousel frames. Rules use these samples; not an independent accuracy estimate |
| Real C24C observation | Home recognized; frame age unavailable; review blocked | One screenshot; status reads only; no input |
| Launcher | ValidateOnly passed; no process started | Simulation backend, separate settings and hover tracking off |

The previous 18-frame additional set is now regression data: one earlier wrong label was corrected, and the caption-editor and TikTok photo gaps informed the new rules. A video details layout is also covered. Carousel OCR reads the static UI label “Add AI Label” as “Add Al Label”; that exact UI-label variant is supported while AI/Al substitutions in captions remain refused. One carousel image has no caption but includes DRAFT ONLY inside its slides; that text is correctly rejected as caption evidence. The reopened carousel's first caption line matches; its full multiline caption is not inferred.

All saved-frame cases use a deliberately unrelated expected account and never accept it. No case grants automatic input. These negative checks are not a false-positive-rate measurement. Freshness/ownership tests also cover slow processing, partial metadata, nonfinite age, wrong sessions, changed generation/process, quiet delivery, backend restart and HTTP retrieval aging without recapture.

## Candidate

- Output: `output/codex-farm-recognition-20261017`.
- Native DLL SHA-256: `f9ee7b384d7f62d022238cf557b6276acdca347eb16138e36aa04b7c6a469392`.
- Backend source SHA-256: `4e430c98fa099ecda3f69c41425eaf44a93770cdba6ba13619e6edaef7e8ffab`.
- `Open Marketing Farm Candidate.ps1` points to this candidate. Installed shortcuts still target their prior build. Observer changes do not alter recurring local preparation, publishing restrictions or live-route refusal.

From the repository, run `python -m unittest discover -s tools -p 'test_farm*.py'`. Build `src/iMouse.Console/iMouse.Console.csproj` in Release into a separate output, then run its `iMouse2.exe --self-test` and wait for exit. It writes `qa/self-tests.json` and the headless render. Do not use the installed output folder or substitute `--ui-test` for headless validation.

Build `tools/frame_tests/FrameTests.csproj` into scratch. Run without arguments for the frame suite, with `--http-self-test` for the loopback transport test, or `--farm-evidence-out=<new-file>` to export the four production metadata cases. The new probe uses production FrameStore with synthetic BMPs and an injected clock; it never enumerates boards, starts receivers or contacts a phone.

## Rack and preservation

Final read-only status: original kernel, both receivers, installed console and farm service retain their process IDs and paths. C24C is live with zero receiver restarts and input generation 230. C241 remains offline as at preflight, with zero restarts and generation 0. Both are unowned, inactive and not stopped. Operator settings SHA-256 remains unchanged. No test worker is left running.

The live capture had no session/sequence/age headers; a same counter during that short read is not evidence of a stuck phone. The observer correctly retains unknown age. Final verification initially used the wrong status request envelope and got code 41 without input; the correct read-only RPC returned code 0 and unchanged generations. Both responses are retained.

Private archive: `iMouseXP-2.0-evidence-archive/20261017-farm-recognition/`, outside Git. It preserves the exact candidate, source, run logs, regression scripts, original saved-frame/OCR dependencies and live read evidence with SHA-256 checks. Raw OCR/screens may contain account details and are not committed. Earlier archives are untouched.

Key records: `python-final.txt`, `console-build.txt`, native `qa/self-tests.json`, `frame-tests.txt`, `frame-http-tests.txt`, `production-frame-evidence.json`, `production-frame-results.json`, `regression-proof.json`, `recognition-replay.json`, `carousel-recognition.json`, `live-observation.json`, `live-audit.json`, `final-rack.json`, `launcher-validation.json`.

## Remaining acceptance

1. Validate this metadata contract on a real candidate-kernel stream in a separately coordinated window. The installed release is unchanged and cannot supply this evidence today.
2. Collect independent screens covering more layouts, overlays and ambiguous accounts. A sparse library stays unknown; account continuity across profile and composer is not yet proven.
3. Verify media/order, full caption and reopened persisted draft under interruptions. None of these review changes authorizes an unattended action.
4. Continue genuine analytics and longer-running local schedule validation separately. Phone recurrence, publishing and messaging remain disabled.

# Marketing Farm: screen review and recurring local preparation

17 October 2026. Local branch `local/combined-candidate-20261012`, built on `c3c5ce3`. **Full marketing automation remains unaccepted.** No publishing, messaging, desktop control or phone input occurred in this pass. No installed release file or running service was replaced.

## What changed

| Feature | Result |
|---|---|
| Read C24C screen | New native review window and local-only API: one explicit screenshot, local English OCR, screen-pattern classification, exact expected handle/caption checks, saved evidence and freshness status. Opening the window reads history only. |
| Interruption review | Permission/share dialogs override background app patterns. Unknown states remain unresolved. Uncertain requests survive restart and are never replayed; lost responses fetch the existing record/frame. The newest 50 frames are retained; all request identities remain. |
| Preparation schedule | New native window and durable background worker. Explicit 60–10,080-minute interval, 1–30-run limit, first run due immediately. Local C24C media generation only. Default off. |
| Scheduling recovery | Shared operation boundary, OS ownership lock, durable acceptance before rendering, missed runs skipped after a two-minute grace period, no catch-up bursts. Failed/interrupted runs hold for review. Pause cancels a pending configuration ID so a delayed request cannot restart it. |
| Review history | Runs retain content item IDs, captions and immutable file references after later slates replace the current manifest. Current and earlier files are not deleted automatically. |
| Analytics integration | Existing submitted-evidence pause now gates recurring preparation. Better counts never clear that pause or resume the schedule. OCR never supplies inferred metrics. |
| Emergency Stop ordering | Phone Stop is dispatched before saving the schedule pause. Failed schedule storage returns a partial-result error with the phone result; it cannot prevent Stop dispatch. |
| Availability | Native feature readiness and health advertise read-only review and local preparation separately from unaccepted live automation. Candidate launcher checks all eleven backend source files, including the OCR helper. |

Closing the preparation window does not stop an explicitly configured backend schedule. Pause stops future runs; an already running local render may finish. Closing/restarting the backend during a render leaves a review hold. Media is retained, so disk usage needs review during longer runs. No schedule from this test remains running.

## Verification

| Check | Observed result | Limit |
|---|---|---|
| Python regression suite | **189 passed**, 35.695 seconds, no skips | Isolated mock phone transport and registered loopback listeners |
| Native self-test | **491 passed**, all commands used mock transport | No native desktop window shown; two WPF views rendered into PNGs and visually inspected |
| Release build | Zero warnings, zero errors | Separate output only |
| Candidate launcher | ValidateOnly passed; exact source hash; StartsProcesses false | Interactive launch not run |
| Real background preparation | Final source produced four JPEGs and one MP4, five format records, checksums verified, references retained, run limit reached | Disposable backend; no external network or phone connection. Multi-interval timing covered with a controlled clock, not a days-long soak |
| Development screen frames | 18/18 selected frames matched their labels | Rules were developed using these frames; not independent accuracy |
| Additional screen frames | Original 15/18. Visual review corrected one wrong label, yielding 16/18; two screen variants still unrecognized | Same C24C sessions/apps, not general app-version/device coverage. Raw results retained; no recognition change made to fit them |
| Real C24C read | Current Home pattern recognized; exact frame age unavailable; expected app/account not accepted | One screenshot and status reads only. No input/lease change |

The three additional-frame discrepancies are recorded in `holdout-review.json`:

- Step 23 was wrongly labelled a profile; the screenshot is a TikTok draft library, correctly recognized.
- Step 161 is an Instagram caption editor sheet. It remains unknown, rather than being accepted as the details screen behind it.
- Step 24 is a TikTok photo draft details screen with different Cover/Edit labels. It remains unknown; this is a recognition gap.

Across both sets, the deliberately wrong expected account was never accepted and no result authorized input. This is a negative check, not a false-positive rate estimate. OCR confused uppercase I and lowercase l in one real handle and in test captions. Exact mismatches stay unresolved; the code does not substitute characters or invent spaces. A text match is not proof of app authenticity or of the current signed-in account.

The installed kernel does not send `X-iMouse-Frame-Age-Ms`; the observer reports unavailable, not fresh. Candidate code can consume that header when present but this pass did not swap kernels. Ownership/receiver state is checked around capture. Observations expire after 15 seconds, and clock rollback also expires them.

## Candidate and reproduction

- Output: `output/codex-farm-observations-20261017`.
- DLL SHA-256: `433ccabd9d769f4eba0695bf2c1efc477544408cfe5c3911972a142204dc0d86`.
- Backend source hash: `da65d004cd8f0899a3dda24419facbf4d0aa8de2829e980b160eb7a7c6f0061b`.
- Launcher: `Open Marketing Farm Candidate.ps1`, separate settings, hover tracking off, loopback 9915, simulation input mode. Explicit screen-read still reads the real C24C mirror and says so in the UI.

From the repository, run `python -m unittest discover -s tools -p 'test_farm*.py'`, then build `src/iMouse.Console/iMouse.Console.csproj` in Release to a separate output directory and run its `iMouse2.exe --self-test` with a wait for process exit. Never substitute the installed release folder. The headless suite writes its own `qa/self-tests.json` and rendered PNGs. Tests importing `farm_test_network` prohibit real service connections.

`Read-FarmImageText.ps1` uses Windows PowerShell 5.1 and the installed English WinRT OCR language, with a process-only execution-policy override. PS7 cannot load these WinRT types. The helper accepts a local image only; it has no desktop, input or network control. Its source reference is Microsoft's [OcrEngine documentation](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine?view=winrt-26100). Missing language/runtime or recognition timeout produces a failed observation, never a successful verification.

## Evidence and preservation

Final private archive: `iMouseXP-2.0-evidence-archive/20261017-farm-observations-final/` outside the repository, with per-file SHA-256 verification. It holds the run folder, exact candidate, headless views and source snapshot. The earlier `20261017-farm-observations` snapshot is retained unchanged; final review subsequently corrected the Emergency Stop ordering and added its regression check. No native code changed after the 491-check run. Raw OCR can contain account identifiers or sharing-sheet details, so it is not added to Git. Previous draft evidence remains in the separate `20261017-farm-platform-drafts` archive.

Key records: `python-stop-order-final.txt`, `build-final.txt`, `launcher-validation-final.json`, `saved-state-results.json`, `holdout-results.json`, `holdout-review.json`, `background-preparation-result-final.json`, `live-observation.json`, `live-ownership.json`, `final-rack.json`. Initial failed WinRT invocation logs and earlier passing test checkpoints remain distinct from final results.

Final read-only rack check: original kernel, receivers, installed console and farm service PIDs unchanged. C24C live, receiver restarts zero, input generation 230; C241 still offline, restarts zero, generation zero. Both phones unowned and inactive. Operator settings SHA-256 unchanged. No test worker or temporary media service remains.

## Remaining work

1. Expand and independently validate screen/account recognition, including caption editors, photo details, permissions, app versions and ambiguous handles. Keep unknown states stopped for review.
2. Establish frame freshness on a validated candidate kernel before trusting any observation for input decisions; no installed-release change is included here.
3. Verify selected media/order, exact caption and persisted draft; then exercise interruptions and recovery through the actual native workflow. Prior supervised saves do not close this gate.
4. Build a genuine analytics provider with verified account/post/time context. Submitted observations are the only available metrics path today.
5. Accept long-running recurring execution separately. Current recurrence prepares files only. Automatic phone deployment, publishing and messaging remain disabled.

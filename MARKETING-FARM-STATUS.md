# Marketing Farm candidate — 17 October 2026

## Latest candidate: native transfer controls and acceptance audit

The new separate build is `output/codex-farm-transfer-20261017`, DLL SHA-256 `81dd034a5910edd95b0fec8bc92a6f1e6df5236def7569c7def0b1274472a591`. **149 Python tests and 459 native headless checks pass**, with a clean Release build. The candidate launcher now points here; installed shortcuts and release files are unchanged.

The carousel editor has **Transfer to C24C** controls for an expiring media link, delivered-image counts, status recovery and Stop. Sessions keep the selected revision immutable, survive lost responses without replay, close on expiry and never restart automatically after a backend restart. The native tab also shows **Feature readiness**. These controls were tested headlessly and through loopback HTTP; the earlier successful phone draft test used the separate media tool.

The broader audit corrected phase-one warmup planning, date-specific daily upload budgets, and analytics that could mislabel lifetime counts as 24-hour views or silently clear a pause. Timestamped, account-specific submitted observations are now required for low-view evaluation; automatic observation extraction remains unavailable.

**Full marketing acceptance remains open.** Other platform workflows, recurring live schedules, automatic observations, publishing and messaging are not established by the passing simulations. See **[MARKETING-FARM-ACCEPTANCE.md](MARKETING-FARM-ACCEPTANCE.md)** for exact use limits, criteria and remaining work; `analysis/farm-native-transfer-20261017/README.md` records this pass. The older sections below are historical evidence, not a claim that every feature is ready.

## Earlier live evidence: C24C Instagram draft saved and reopened

The follow-up media-transfer test **passed on one C24C account designated by the operator**. Three clearly numbered test slides were served from a temporary media-only LAN server, saved in Photos, selected in Instagram as 1 → 2 → 3, and saved using Instagram's **Save draft** option. Reopening that draft preserved all three images and the exact three-line caption, including spaces. The phone was left showing the saved draft in the Drafts library. Nothing was published.

`tools/farm_media_transfer.py` serves only an immutable, checksum-verified carousel export to an explicit client IP, through a secret expiring URL. It has no farm control API or upload/publish endpoint. Its page provides numbered images and a copy-caption button; the caption was pasted from Safari instead of typed through HID. The known HID first-space issue remains deferred. No desktop control, installed release change, kernel/receiver restart, phone-setting change or C241 input occurred. The temporary server was stopped and port 9916 verified closed; C24C's lease was released.

**Scope:** this was an agent-supervised, screen-observed phone API workflow using the existing release kernel and a new transfer tool. It was not a one-click run from the WPF editor. Native transfer controls, automated app-state verification and broader live repeatability are still pending. The existing local editor and autonomous live-route refusal remain unchanged. The full Python suite now passes **119 tests**, including 13 transfer checks. No C# changed in this pass; the 447 native checks below belong to the previous candidate build.

Report and reproduction: `analysis/farm-phone-transfer-20261017/README.md`. Screenshots, phone-step records, package and final-state evidence are preserved locally outside Git in `iMouseXP-2.0-evidence-archive/20261017-farm-phone-transfer/` with checksums. The earlier candidate details below remain its offline build record.

## Previous native candidate checkpoint

**The native Marketing Farm tab is the target. The candidate is ready for offline use, not accepted for unattended publishing.**

The existing desktop shortcut still targets `output/gemini-farm-tab-r4/iMouse2.exe` (the screenshots show build `9a5aa793`). The latest separate candidate is `output/codex-farm-carousel-20261017`, **build `4c1a4949`** (DLL SHA-256 `4c1a49490c6f20e65c1f331aefcfb53ba6734caad5b4a6c3f86459ecd0933926`). The earlier `f6ed99e3` candidate is preserved. Nothing was installed, promoted, pushed or run on a phone during this pass. No desktop control was used.

## Use the candidate

Run **Open Marketing Farm Candidate.ps1** from this repository when you want to open it. It starts a matching simulation backend on **127.0.0.1:9915**, then the native console with its own `candidate-data` folder and hover tracking off. It does not restart the kernel or receivers, close another console, change the old shortcut, or use the operator's settings. If port 9915 holds an incompatible backend, it refuses to open the console; it does not kill that process.

In the Marketing Farm tab:

1. Edit and save the **C24C profile**.
2. Choose **Create content only**, then **Instagram carousel drafts → From generated content**, or start an empty draft and add your own JPEG/PNG images. Edit the title/caption, move slides earlier/later, remove slides and inspect the preview. Generated material uses local templates; no AI provider is configured.
3. **Save draft** saves locally. **Export review package** produces ordered JPEGs, the full caption, a review page, a manifest and SHA-256 checksums. This does **not** save anything inside Instagram. Exports require 2–10 slides; imports accept up to 8 MiB per image, fit the whole image into 1080×1350 without cropping, and leave originals untouched. These are the candidate's editing limits, not a platform-wide guarantee.
4. Simulation jobs can run without selecting or connecting a phone. Job status distinguishes running, succeeded, failed, cancelled and interrupted. Check job retrieves a pending result; it does not repeat the action.
5. **Stop C24C + cancel job** also sends a real Stop to C24C if the console is connected. **Resume simulation** only resets the mock. Manual preview taps and Spotlight are real C24C controls, separate from simulation.

The backend stays running after the console closes; a lost job heartbeat requests cancellation within 30 seconds. An accepted request ID is saved before execution. Reusing it never replays work, including after a restart. Terminal results survive a backend restart. The console now saves its pending job ID before submission, restores it on restart and blocks new work until the outcome is checked. Recovering an old live job keeps manual input paused; completion still requires explicit Resume.

Drafts and their image bytes are stored transactionally in `output/farm-data/v2/<mode>/carousel-drafts.db`. They survive regenerated content and deleted original images. Unsaved edits are kept in the console's own data folder; reopening restores them. Stale saves are refused. If another session saved a newer revision, conflicting edits are archived before the newer version is opened. **Reload saved version** also preserves unsaved edits in a separate JSON file. Captions are never silently truncated; unsupported phone typing is reported separately from local editing.

## What works and what remains

| Area | Current result | Remaining acceptance |
|---|---|---|
| Profiles and targets | Saves validated C24C profile; canonical phone IDs normalize correctly. Unbound persona cards are labelled as profiles and cannot deploy. | Bind/validate additional physical phones separately. |
| Content | Creates decodable 4:5 JPEGs and MP4, a local review page, checksums and manifest. Old assets survive a new or failed render. | External AI generation is not configured; drafts need editorial review. |
| Instagram carousel drafts | Native editor and local recovery work offline. Follow-up: media transfer, exact caption paste, correct image order and save/reopen in Instagram passed once on C24C using the separate transfer tool. | Integrate transfer into the native candidate; reliable observed automation and repeatability beyond this supervised test. |
| Jobs and recovery | Durable request IDs, console restart recovery, single-operation execution, cancellation, heartbeat timeout, Stop latch, explicit simulation Resume, no automatic replay. | Live console/backend lease handover is implemented but not phone-validated. |
| Upload flows | All 14 format paths execute against simulated transport and release ownership. Invalid text and unsupported formats fail before input. | Real app identification, correct account/media selection, media transfer and publication confirmation. Current live autonomous routes refuse instead of using unverified coordinates. |
| Schedule and warmup | Read-only schedule preview; C24C warmup and full create/upload/pin simulations run. | Real timing, app-state observations and workload acceptance. |
| Keyword replies and analytics | Missing observations return unavailable, never a fabricated keyword match, DM or view count. New profiles start with unknown analytics. | Implement and validate a text-observation provider, recipient selection and explicit approved messaging workflow. |
| Manual C24C controls | Explicit C24C target never expands to checked followers. Tap mapping uses the actual preview geometry; stale frames refuse input. | Real-window and phone checks on this build. |

The farm control server is loopback-only by default. The exported Shortcut plist remains an unvalidated draft definition. The separate `farm_media_transfer.py` delivery path now has one successful supervised C24C test; it exposes only the selected package and never the control server. No Shortcut installation or signing was needed.

## Verified in this pass

| Check | Result |
|---|---|
| Original feature regressions | All 32 pass; 14 had failed before the fixes. |
| Combined Python tests | **106 pass**, including eight real HTTP tests on an ephemeral simulation server and 17 local draft/store tests. Generated-content → editable-draft integration is tested. |
| Native Release build | **Zero warnings/errors.** |
| Native headless tests | **447 pass**; farm checks never show a desktop window or create a native window handle. Includes editor recovery, saved-job recovery and a headless editor render inspected for layout. |
| Engine/server self-checks | Passed on the previous candidate. Existing engine behavior is covered by this pass's complete Python suite; no new live acceptance is inferred. |
| Candidate launcher | ValidateOnly passes and includes the new draft module in its backend source hash. The candidate has its own data folder with hover tracking off. Actual interactive launch not run. |
| Real phones, accounts, posting, DMs | **Not run.** |

Latest logs, source/binary inventories and the rendered editor: `analysis/farm-carousel-20261017/`. Prior evidence remains under `analysis/farm-functionality-20261017/` and `analysis/farm-feature-validation-20261016/`. The sandbox initially blocked temporary file replacement and loopback sockets; the approved isolated rerun passed. Intermediate native test setup/layout assertion failures are distinguished from the final passing result. The incoming Gemini report's claims do not replace this candidate's acceptance matrix.

## Next work

The operator selected **Instagram carousel draft first**. The local editor and the supervised phone transfer/save/reopen now have evidence. Next: native transfer-session controls and a phone workflow that stops on unexpected screens and verifies account, slide order, pasted caption and persisted draft. Do not turn the observed coordinates into an unattended publishing script. Publishing remains separate; the editor has no publish button or phone-input route.

After that acceptance, extend the proven workflow to other platforms, then finish real observations for scheduling, analytics and approved keyword replies. Do not treat preset coordinates, successful API replies or the old exported Shortcut file as proof of phone completion. Live autonomous routes remain disabled. Keep other phones and the installed release unchanged.

## Reproduce offline

Use Python 3.11 with the recorded dependencies in `tools/requirements-farm.txt`. From the repository:

```powershell
python -m unittest discover -s tools -p 'test_farm_*.py' -v
dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o output/codex-farm-carousel-20261017
dotnet output/codex-farm-carousel-20261017/iMouse2.dll --self-test
& '.\Open Marketing Farm Candidate.ps1' -ValidateOnly
```

The Python suite blocks external services; HTTP tests allow only their own temporary server. On this host the restricted sandbox prevents atomic temporary-file replacement and loopback test sockets, so those tests were run outside that restriction. No live UI tests were run.

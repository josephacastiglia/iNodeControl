# Marketing Farm candidate — 17 October 2026

**The native Marketing Farm tab is the target. The candidate is ready for offline use, not accepted for unattended publishing.**

The existing desktop shortcut still targets `output/gemini-farm-tab-r4/iMouse2.exe` (the screenshots show build `9a5aa793`). This work is a separate candidate at `output/codex-farm-functional-20261017`, **build `f6ed99e3`**. Nothing was installed, promoted, pushed or run on a phone during this pass. No desktop control was used.

## Use the candidate

Run **Open Marketing Farm Candidate.ps1** from this repository when you want to open it. It starts a matching simulation backend on **127.0.0.1:9915**, then the native console with its own `candidate-data` folder and hover tracking off. It does not restart the kernel or receivers, close another console, change the old shortcut, or use the operator's settings. If port 9915 holds an incompatible backend, it refuses to open the console; it does not kill that process.

In the Marketing Farm tab:

1. Edit and save the **C24C profile**.
2. Choose **Create content only**, then **Review content**. Review the template copy, caption, JPEG slides and MP4 before use. These are local template drafts; no AI provider or external service is configured.
3. Simulation jobs can run without selecting or connecting a phone. Job status distinguishes running, succeeded, failed, cancelled and interrupted. Check job retrieves a pending result; it does not repeat the action.
4. **Stop C24C + cancel job** also sends a real Stop to C24C if the console is connected. **Resume simulation** only resets the mock. Manual preview taps and Spotlight are real C24C controls, separate from simulation.

The backend stays running after the console closes; a lost job heartbeat requests cancellation within 30 seconds. An accepted request ID is saved before execution. Reusing it never replays work, including after a restart. Terminal results survive a backend restart. The UI does not yet persist its job ID across a console restart; the backend journal retains it.

## What works and what remains

| Area | Current result | Remaining acceptance |
|---|---|---|
| Profiles and targets | Saves validated C24C profile; canonical phone IDs normalize correctly. Unbound persona cards are labelled as profiles and cannot deploy. | Bind/validate additional physical phones separately. |
| Content | Creates decodable 4:5 JPEGs and MP4, a local review page, checksums and manifest. Old assets survive a new or failed render. | External AI generation is not configured; drafts need editorial review. |
| Jobs and recovery | Durable request IDs, single-operation execution, cancellation, heartbeat timeout, Stop latch, explicit simulation Resume, no automatic replay. | Live console/backend lease handover is implemented but not phone-validated. |
| Upload flows | All 14 format paths execute against simulated transport and release ownership. Invalid text and unsupported formats fail before input. | Real app identification, correct account/media selection, media transfer and publication confirmation. Current live autonomous routes refuse instead of using unverified coordinates. |
| Schedule and warmup | Read-only schedule preview; C24C warmup and full create/upload/pin simulations run. | Real timing, app-state observations and workload acceptance. |
| Keyword replies and analytics | Missing observations return unavailable, never a fabricated keyword match, DM or view count. New profiles start with unknown analytics. | Implement and validate a text-observation provider, recipient selection and explicit approved messaging workflow. |
| Manual C24C controls | Explicit C24C target never expands to checked followers. Tap mapping uses the actual preview geometry; stale frames refuse input. | Real-window and phone checks on this build. |

The media server is loopback-only by default. The exported Shortcut plist is a draft definition, not proof of installation, signing, transfer to Photos or clipboard state. A phone-accessible, media-only delivery path still needs design and validation; do not expose the control server to the LAN as a workaround.

## Verified in this pass

| Check | Result |
|---|---|
| Original feature regressions | All 32 pass; 14 had failed before the fixes. |
| Combined Python tests | **87 pass**, including six real HTTP lifecycle tests on an ephemeral simulation server. |
| Native Release build | **Zero warnings/errors.** |
| Native headless tests | **428 pass**; farm checks never show a desktop window or create a native window handle. |
| Engine/server self-checks | Pass in temporary storage with real services blocked. Results explicitly distinguish simulation from live acceptance. |
| Candidate launcher | Syntax and ValidateOnly checks pass; startup validation confirms isolated paths without connecting. Actual interactive launch not run. |
| Real phones, accounts, posting, DMs | **Not run.** |

Detailed logs and source/binary inventories: `analysis/farm-functionality-20261017/`. The earlier failing evidence is retained under `analysis/farm-feature-validation-20261016/`. The handoff claims in the incoming Gemini report are historical and do not replace this candidate's acceptance matrix.

## Next work

Finish one real publishing workflow before expanding platforms: start with an Instagram carousel draft unless the operator chooses otherwise. Add verified screen/account/media observations and a review-before-publish boundary, then arrange a C24C-only test account check. Do not treat preset coordinates, successful API replies, or the exported Shortcut file as proof the phone completed a step. Keep the other phones and installed release unchanged.

## Reproduce offline

Use Python 3.11 with the recorded dependencies in `tools/requirements-farm.txt`. From the repository:

```powershell
python -m unittest discover -s tools -p 'test_farm_*.py' -v
dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o output/codex-farm-functional-20261017
dotnet output/codex-farm-functional-20261017/iMouse2.dll --self-test
& '.\Open Marketing Farm Candidate.ps1' -ValidateOnly
```

The Python suite blocks external services; HTTP tests allow only their own temporary server. On this host the restricted sandbox prevents atomic temporary-file replacement and loopback test sockets, so those tests were run outside that restriction. No live UI tests were run.

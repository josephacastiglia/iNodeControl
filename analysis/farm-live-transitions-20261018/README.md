# Fresh C24C validation of bounded draft transitions

18 October 2026. Validation of the five holds addressed in `c9d67f8`. **Attempt 1 held before opening the draft; a refined diagnostic is prepared for a separate attempt.** The installed release is unchanged. This is an explicitly invoked, bounded diagnostic; it does not enable a live marketing endpoint or claim unattended product acceptance.

## Scope

- C24C only, on the existing authorized Instagram profile `xs.halle.xo`.
- Reuse the existing labelled three-slide test draft. No media creation/import, text entry, account switching, publishing, messaging, FKA changes or PC control.
- Own C24C continuously for one run. The original 90-second admission budget and six-second/four-capture transition budgets stay unchanged; an in-flight request and lease cleanup can extend wall time.
- Refuse wrong identity, an existing owner, stale frames, changed controls, unknown screens, ambiguous covers or uncertain responses. Never retry a semantic action. A separate Save when leaving the reopened editor preserves the same draft; it is not a retry of the initial Save.
- Move-only pointer challenges at two known points produce fresh delivery on quiet video. They do not bypass the 1,500 ms frame-age limit, account checks, screen recognition or final stable comparisons.

## Candidate and starting state

The initial read-only check found no iMouse kernel, console, receiver or rack/test listener. Record that state again immediately before starting. Only the private C24C kernel/receiver may start; the installed console remains closed.

- Kernel: preserved `output/codex-farm-live-kernel-20261018/iMouse2.Kernel.exe`, built from `9fa7a859bbeb60495cdbbda326d25010c3ba7961`.
- Kernel DLL SHA-256: `c72fa4e0b02b82ec4f7a949c9a80375c69da68d7357084401c7bb422c194a873`.
- API: `http://127.0.0.1:9916/api/`. The restricted transport refuses any other endpoint, target, redirect or command family.
- Private data, receiver and copied runtime: `output/candidate-runs/farm-live-transitions-20261018/`.
- `preparation.json` records exact runtime/configuration hashes. Startup validation passed without hardware access, listeners, receivers or settings writes.
- `validation-sources.json` freezes helper and product source bytes before startup. `protected-files.json` records installed-file hashes without settings contents.

## Procedure

1. Complete offline checks, freeze sources, then start the private receiver. Ask the operator to connect C24C to **iMouse2-C24C**, dismiss Control Centre and show `xs.halle.xo`'s profile. C241 stays untouched; the installed console must stay closed.
2. Confirm exact runtime, board mapping, receiver and free ownership. A read-only profile check must match before even the initial pointer challenge.
3. Run `validate_workflow.py --out <new-attempt-directory>`. Existing output directories are refused. Creating a file named `STOP` inside that directory requests cancellation; cleanup releases only this run's token.
4. One run follows profile → Create → Post-format picker → Drafts → existing test carousel. The shared product waiter handles the Create, picker and editor transitions. Library selection requires one unique matching cover and uses that observed cell.
5. Verify slides 1, 2 and 3 in order, exact Next, and the full visible caption. Return to the editor, request the Save sheet, then Save once.
6. Reopen from the uniquely matched saved cover; verify all three slides and caption again. Save once on exit to preserve the reopened draft, return to the profile and check the same account.
7. Audit every captured observation for one sampled ownership/stream/account history. This is not continuous iOS observation or proof of server persistence. A lost reply stops immediately; only scoped lease cleanup follows.
8. Stop only the recorded test kernel normally, return to the initially stopped rack state, check all protected hashes and archive evidence. A held run is not automatically restarted or manually advanced inside the same acceptance record.

Phone evidence shows that Back from details retains slide 3, whereas the earlier synthetic model returned to slide 1. This helper explicitly expects the observed slide 3 and never guesses its position. Navigation icons without text must match their fixed retained control crops; full captions/accounts are never cropped or repaired.

## Offline checks

- The existing transport helper: **11 checks passed**. It blocks other phones, unsupported commands, redirects and prohibited/ambiguous targets.
- Shared transition/read-only-probe/frame-evidence checks: **29 passed**. No rack or external service was contacted.
- The new full-flow fixture suite: **10 passed in 55.556 seconds**, including normal and transient paths, one ownership interval, all media/caption checks, account boundaries, cancellation, lost Save replies, stale evidence, wrong account/caption, changed navigation icons and action replay refusal. Failed OCR retains its observation ID/reason. `workflow-tests-preserved-failure.txt` records the final result. With the other two suites above, **50 preparation checks passed**.
- Actual Windows OCR correctly recognized the retained profile, Create sheet and exact Next. Processing took 722, 590 and 1,272 ms respectively; live download, delivery age and final decision overhead still count toward the unchanged 1,500 ms budget.
- All three lifecycle scripts parsed. No native binary was rebuilt. The prior 370 product tests are historical validation, not counted as a new run here.
- Earlier failed checks remain retained: the sandbox blocked atomic replacement of temporary evidence files; normal file permissions resolved that environment limitation. A fixture run also exposed a missing caption argument in the final account-history audit; it was corrected before phone use.

## Acceptance record to complete

For each of the five former holds, record the fresh screen, captures, exact waiter outcome and whether the transient actually occurred. Passing its archived replay does not prove it was reproduced during this phone run. Report Save/reopen, all-slide/caption checks, sampled account continuity, cleanup and file preservation separately. Preserve failures and timing holds without relabelling them as successes.

## Attempt 1 and diagnostic refinement

`attempt-01` recognized the authorized profile and Create sheet, then held before opening Drafts because the fourth picker capture exceeded the unchanged six-second settling budget. There were only two semantic actions: open Create and choose Post. No Save was sent. C24C's lease was released, with the picker still open.

The four picker frames were individually fresh (656–689 ms age). Their home-indicator brightness rose from 114 to 195 to 237 and then remained at 237. Offline comparison of the last pair passed, but it arrived too late to accept live. The first pointer challenge took about 610 ms to move away from the clicked control; subsequent moves took about 50 ms. This is evidence for a diagnostic timing refinement, not a retroactive pass.

The revised helper parks the pointer only after a confirmed action, before starting the next settling interval. The overall 90-second budget still includes that move, and six-second/four-frame settling, 1,500 ms freshness and protected control comparisons are unchanged. Uncertain action replies still stop with no further navigation. A separate `--return-profile-only` operation can close only a freshly recognized Post picker and verify the account profile; it cannot open or save a draft.

The revised full-flow suite passed **12 checks in 63.978 seconds**, including picker-only recovery, cancellation and parking after confirmed actions (`workflow-tests-parking.txt`). Together with the unchanged 11 transport and 29 shared guard checks, this revision has 52 applicable preparation checks. Original preparation evidence and source hashes remain preserved; every phone attempt has its own record.

## Attempt 2 and OCR processing time

`recovery-01` freshly verified and closed only the picker, confirmed the authorized profile and released its lease. In the separate `attempt-02`, Create passed in two captures; the fading picker required four; the first editor's changing suggestion required three. The helper then verified all three slides and the full caption. After returning to slide 3, its last stable editor pair aged past the 1,500 ms budget at the final decision check. The run stopped before requesting Save and released C24C. It remains a failed acceptance attempt, leaving the existing draft open.

The editor's OCR path started PowerShell twice: once for the whole image and once for the fixed Next label. The new bridge reads both exact files through one WinRT engine/process, checks each file's checksum and dimensions, and uses the crop only when a recognized editor lacks exact whole-frame Next. It never repairs caption/account text. Its frame-age accounting, semantic checks and refusal rules are unchanged.

`ocr-batch-comparison.json` compares both implementations on five retained images. Whole-frame text and Next evidence were identical. Three editor reads fell from 876/957/944 ms to 543/562/523 ms; profile and picker were approximately unchanged. These are local processing measurements, not fresh-phone acceptance. **58 focused tests passed** including swapped/missing/mis-sized control evidence, original frame binding, freshness, transitions and no replay.

The separate `--preserve-open-draft` recovery requires the known final slide and exact full caption, saves once, then returns to the authorized profile. A lost Save reply stops; it cannot silently restart the main workflow. This operation is marked preservation, not save/reopen acceptance.

# Carousel thumbnails, complete slide checks and account history

18 October 2026. Based on `dd7ba39`, branch `local/combined-candidate-20261012`. Separate candidate; **not accepted for unattended saved-draft execution**. C24C only; API input, no PC control, publishing, messaging, release modification or restart.

## Delivered

- Library comparison handles Instagram's lower dark gradient and carousel badge. The two fixed rendering models are plain and the observed lower gradient; there is no fitted colour adjustment or arbitrary crop search. Original mean-error (0.045), worst-block (0.12) and separation (0.025) limits remain unchanged. The square thumbnail is a cropped cover hint, never full-image proof.
- Searches the supported four-column library's seven fully visible rows. A matching cover can move when another draft is added. Exactly one matching first-slide cover is required; two copies are ambiguous. Off-screen drafts and other layouts remain outside scope.
- Recognizes the full-size carousel editor from independent toolbar text. Reads page-dot position and total count. Prepared and reopened stages require each expected slide once, in order, with the corresponding page index/count, plus an exact full caption from the details screen. A repeated image with a different dot, an extra slide, partial coverage or an unreadable dot cannot pass.
- Audits **every stored C24C observation** between the account boundaries, including observations omitted from the operator's selection. Different/unreadable accounts, foreign apps, unknown/permission screens, failed/pruned images, changed ownership/receiver context, nonadvancing frames and gaps over 15 seconds block a consistent history. Row insertion order prevents wall-clock shifts from hiding intervening records. This is sampled history, not continuous recording.
- Retains intervening records/images in the immutable review archive, within the existing 32 MiB source/frame/OCR budget. The native review displays slide coverage, sampled-history status and intervening screenshots. Backend review version is 2; the updated native view requires that version. Existing saved records remain historical and are not recomputed.

No result sets `savedDraftVerified`, `accountContinuityProven` or `automaticInputAllowed` to true. Even a consistent sampled history cannot prove activity between captures, app authenticity, media byte identity, or that a new save was performed. This feature strengthens evidence review rather than relaxing acceptance.

## Live C24C checks

The existing approved test carousel was inspected through leased release API calls, one visually checked action at a time. No new media or draft was created, no text was entered, and no account/settings were changed. Source content was the earlier checksummed three-slide export. Raw images/handles stay in the private evidence archive.

| Component | Result |
|---|---|
| Account before | Exact expected handle on Instagram's profile |
| Library | Correct cover uniquely matched in row 1, column 2, beside the existing video draft; mean error about 0.0226, worst block 0.1184 |
| Reopened slide 1 | Full-size source match; position 1 of 3 |
| Reopened slide 2 | Full-size source match; position 2 of 3 |
| Reopened slide 3 | Full-size source match; position 3 of 3 |
| Caption | Exact complete three-line saved caption |
| Account after / continuous account context | **Not completed.** Another controller acquired C24C before the exit step; preflight refused input |
| Paired frame age | **Unavailable on the installed kernel**; not inferred or fabricated |

The initial slide-1 capture was still showing a faint/unfinished suggested-audio header, and OCR could not classify it. The later **before** frame from the slide-2 action had settled and passed. The original failed replay is retained; recognition was not loosened to accept the incomplete frame. The new slide-2 image was acquired after the fixed matching/dot rules were implemented. The live second-column library informed the grid extension; these samples are development evidence, not an independent general-image accuracy benchmark.

Step `12-back-from-details` acquired no lease and sent no input: C24C reported owned and active. No subsequent input was sent by this run. Our preceding step had released normally. The last page left by our actions was the draft details screen; the other controller was not interrupted and may have navigated elsewhere. The account-after gap remains open. C241 received no input. No kernel, receiver, installed console or shortcut was stopped, restarted or replaced. Operator settings retain SHA-256 `72F51CC0BEE805F722D73BC024CAD771B19A68E2E7C04D9D47F8E9E4A8A5E5BA`.

The first read-only preflight was sandbox-blocked; its approved retry used an incorrect status URL and returned 404. The corrected `/api` URL succeeded. Neither failed attempt sent phone input.

## Validation

| Check | Result |
|---|---|
| Full Python suite | **234 passed**, 61.009 seconds; real kernel/external connections prohibited by the test guard |
| Native headless suite | **505 passed**; review render inspected, no desktop window/input |
| Release build | Zero warnings/errors; separate output |
| Historical C24C replay | Two library thumbnails and editor slides 1/3 match; no old freshness metadata invented |
| Fresh C24C component replay | Expected profile, moved library cover, all three editor slides/dots and caption match |
| Negative cases | Wrong/duplicate covers, occlusion, rotated media, repeated slides, ambiguous/wrong counts, omitted account switches/dialogs/failures, stale/context gaps and missing evidence refused |
| Durability/HTTP | Checksums, source revision, retained intervening frames, restart/idempotence/lost-response behavior and local-origin policy pass |
| Launcher | ValidateOnly passes, fourteen-file backend hash, no processes started |

Candidate output: `output/codex-farm-continuity-20261018`.

- DLL SHA-256: `70ab2b31cf2beb5258febd3a5c28d27331a8634c2084e20358c7d8b7dbfc8bc4`.
- Backend source hash: `20d88de8c8ba0879421ea24d99ae55e502b81b3255ff22b0967f608a05b3c721`.
- Launcher: `Open Marketing Farm Candidate.ps1`; separate settings, hover tracking off, simulation backend on loopback 9915. Installed launchers remain unchanged.

Run `python -m unittest discover -s tools -p 'test_farm*.py'`. Build the console to a new scratch folder and run its `iMouse2.exe --self-test`, waiting for process exit. Do not use the installed output or `--ui-test` for these headless checks.

## Remaining acceptance work

1. A managed, continuously owned capture/action run with real paired frame metadata and before/after account evidence. The current strict review rejects ownership-generation changes; it does **not** pretend that separate manually leased actions prove continuity. Restarting/replacing the release was outside this task.
2. Witness the actual save and reopen transitions and interrupted recovery; current work verified content of an existing saved test draft. Unknown legitimate navigation pages still need explicit recognition before an unattended runner can traverse them.
3. Independent validation on more photos, layouts, app versions and libraries with duplicate covers; additional platforms are outside this carousel comparator's scope.

Source, exact candidate binaries, tests, raw C24C frames, historical source inputs and comparison results are preserved under sibling `iMouseXP-2.0-evidence-archive/20261018-farm-continuity/` with SHA-256 inventory. Raw private evidence is not committed to Git. Earlier archives and the installed release remain intact.

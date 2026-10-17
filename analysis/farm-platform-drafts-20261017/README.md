# C24C platform drafts — 17 October 2026

## Verdict

**Supervised draft saves passed for the cases below. Full marketing automation remains unaccepted.** The operator authorized any accounts already signed in on C24C for draft-only tests. Phone input used the existing lease-aware release API and inspected mirrored frames. No desktop control, publishing, messaging, C241 input, release installation, kernel/receiver restart or FKA change occurred.

| App | Saved and reopened | Review result | Evidence steps |
|---|---|---|---|
| TikTok | Three-photo draft | Numbered slides and exact label retained | 07 account; 13–25 selection/save/reopen |
| X | One-image draft | Test image and exact label retained | 31 account; 34–45 draft |
| YouTube Shorts | Photo-derived Short | Exact title; editor used a 2-second clip and cropped the 4:5 photo to 9:16 | 51 account; 54–66 draft |
| TikTok | Actual H.264 MP4 draft | Reopened and played; exact label; suggested sound removed and resaved | 94–112 |
| X | Actual H.264 MP4 draft | Reopened with exact label; initially blank preview played the correct video after Play | 114–130, especially 127 |
| YouTube Shorts | Actual H.264 MP4 draft | 3.0-second trim view, complete frame, exact title, reopened playback | 131–151, especially 140, 148–150 |
| Instagram Reels | Actual H.264 MP4 draft | Exact caption, whole frame, reopened playback; resaved to library | 152–168, especially 165–167 |

The earlier Instagram carousel test is separate: `../farm-phone-transfer-20261017/README.md`. It verified three numbered images and a multiline caption with spaces. The account identities and private frames for this pass stay in the local archive, not this tracked report.

Photo label: `IMOUSE-DRAFT-TEST-20261017`. Video label: `IMOUSE-VIDEO-DRAFT-TEST-20261017`. These labels contain no spaces; they provide no new evidence that the deferred HID first-space defect is fixed. No existing draft was deleted.

## Tested media and transfer

The MP4 is a clearly labelled, silent test animation: three seconds, 720×1280, H.264, yuv420p. Its progress bar makes a played frame distinguishable from the thumbnail. SHA-256: `cb512a27903b53600f512936f47c49acc72fec3158e5b5f4d4f828a09c051673`. Its saved local draft ID is `e300f851-9554-4c6a-a0d4-305f1066be4a`. The original source, normalized copy, package and preparation metadata are in the archive.

The successful phone path was **hold Open video to save → Download Linked File → Safari Downloads → imouse-draft → local file Share → Save Video**. Photos then showed the labelled 0:03 clip (step 90). Opening the HTTP video directly played it but did not save it to Photos. Server range requests and downloads are not proof of an app save.

One temporary media-only server on port 9916 served only the immutable package to the verified C24C client IP through a secret URL. It was closed after transfer; the final snapshot records no listener. Its final nine video requests include partial requests and downloads, not nine complete saves. The original test media remains in Photos and Downloads, and the saved test drafts remain in the apps.

## Observations, interventions and limits

- YouTube's optional local-network permission dialog ignored pointer clicks and Escape. The operator physically chose **Don't Allow**. This manual dependency prevents an unattended pass claim.
- TikTok attached a suggested sound to the photo draft. It remains there. It also suggested a sound for the MP4; the editor's remove control cleared it before the final save. The source MP4 is silent; no physical audio-output measurement was made.
- An iOS share sheet changed between two taps. The second tap opened an empty **New Shared Album** form. No name, participant or Create action was supplied; it was cancelled and the regular Save Video option was then used. Nothing was shared or invited. This is why the transfer instructions require waiting for the actual menu.
- Several ordinary taps failed to open TikTok's gallery. Pointer reset, explicit move, a short settling wait and a fresh observed frame preceded the successful click. This is one observed sequence, not a universal timing fix.
- X initially showed a blank preview in its reopened video draft. Playback, not the blank thumbnail, supplied the confirmation.
- YouTube's photo-derived Short cropped a 4:5 image; it is not evidence for exact carousel geometry. The real MP4 review retained the full frame.
- Instagram's Reel **Preview** includes sample engagement UI. Those numbers are not published-post metrics. The Share button was never used.
- The installed vendor Home command can insert Tab. This run used it only after observing a noneditable view. The Home defect remains open.
- Account identity was observed before the supervised flow. The candidate has no accepted automatic account recognizer. The new native controls were tested headlessly; no claim is made that a native one-click automation completed these phone flows.

## Candidate implementation

Output: `output/codex-farm-video-20261017`. Final `iMouse2.dll` SHA-256: `61764a45cf1ad1adced31cca087ff36412842af12f8d638104d800b0f48fee1e`.

- `tools/farm_video.py` adds immutable SQLite video copies and an exact package containing video, caption and manifest. Only checksummed generated C24C sources are accepted. Preparation converts to H.264/AAC as needed, fits the whole frame into 720×1280, verifies duration, fully decodes video/audio and preserves originals. Limits are 64 MiB and 45 seconds; no silent trimming or caption truncation.
- `VideoDraftWindow` adds destination/caption review, saved-copy selection and recovery. A lost request before storage retries the same ID only after checking storage. A lost response, busy backend or server error after save preserves the ID. Selecting a saved copy shows its actual stored caption and destination; editing invalidates transfer of that copy.
- The existing explicit media-transfer controls now support video, Safari byte ranges and partial-request status. Expiry, stop, conflict and restart rules remain in force. Links do not certify Photos or draft saves.
- `farm_capabilities.py` distinguishes supervised live passes, local candidate functions, simulation and unavailable routes. No automatic publishing or messaging was enabled.
- `Open Marketing Farm Candidate.ps1` points at the new output, retains separate settings and simulation backend port 9915, and validates all eight backend source files. Its ValidateOnly check starts no process. Installed launchers were not edited.

## Verification

| Check | Result / record |
|---|---|
| Full isolated Python suite | **161 passed**, no skips; `python-release-check.txt` |
| Native headless checks | **478 passed**; final candidate `qa/self-tests.json` |
| Release build | **0 warnings, 0 errors**; `build-final-preserve.txt` |
| Candidate launcher | ValidateOnly passed, no processes started; `launcher-validation-final.json` |
| Native editor layout | Headless render visually inspected at 650×740; saved fields and buttons readable |
| Real codecs | Silent and audio-bearing fixtures normalize, decode fully, preserve duration and content; MP4 ranges/HEAD/expiry tested via loopback HTTP |
| No phone transport in offline tests | Guarded ephemeral mock listeners; API test records zero dispatched phone commands |

Reproduce from this checkout with Python 3.11, `tools/requirements-farm.txt` and FFmpeg/ffprobe with libx264 available:

```powershell
python -m unittest discover -s tools -p 'test_farm*.py'
dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o output/codex-farm-video-20261017
$exe = (Resolve-Path 'output/codex-farm-video-20261017/iMouse2.exe').Path
$process = Start-Process -FilePath $exe -ArgumentList '--self-test' -WorkingDirectory (Split-Path -Parent $exe) -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Self-tests failed; read self-test-failure.txt' }
& '.\Open Marketing Farm Candidate.ps1' -ValidateOnly
```

The initial sandbox-blocked HTTP run, the expiry-boundary failure and a native instruction-text assertion failure are preserved separately. Later passing logs do not erase them. The expiry race and stale assertion were fixed before final verification. Final QA must be checked with the process exit code; a prior `self-tests.json` can remain after a failed run.

## Final state and preservation

At the final snapshot (`final-rack-complete.json`), C24C was at Home, unowned, inactive and not stopped, generation 230. C241 stayed unowned at generation 0 and was never addressed. Its video was offline already at preflight; no recovery attempt was made on it. C24C remained live. Kernel 6108, receivers 6700/37088, installed console 34016 and the old farm backend 44176 were unchanged. Receiver restart counts remained zero. The settings hash matches the earlier end-of-video-transfer snapshot; no claim is made for an uncaptured beginning-of-run settings hash.

`phone_step.py` is an observed-step evidence helper, **not an unattended app workflow**. It refuses a nonfree or nonlive C24C, uses the normal scoped lease, captures frames and releases in `finally`. Do not replay old coordinates or run the 168 steps unattended. The local `video_fixture.py` contains run-specific network/account values and stays out of Git.

`preserve.py` copies this run, the exact candidate and source to sibling archive **`iMouseXP-2.0-evidence-archive/20261017-farm-platform-drafts/`**, refuses to overwrite an existing archive, and verifies every file against `SHA256SUMS.txt`. Raw frames, private account evidence, logs, databases, test downloads and failed-run records are preserved there. Tracked code/report changes are a local candidate checkpoint; nothing is promoted or deployed.

Remaining acceptance: reliable observed app/account recognition, media/caption verification, repeated interruption recovery, recurring job execution and observation providers; other untested format modes; separately authorized publishing and messaging. See `MARKETING-FARM-ACCEPTANCE.md` for the full matrix.

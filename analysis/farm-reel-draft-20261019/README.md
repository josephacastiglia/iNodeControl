# Priority 3: platform coverage and the Instagram Reel draft candidate

Scope: **C24C, Instagram @xs.halle.xo, draft only.** This is offline work. No
phone input, rack service, desktop control, publishing, messaging, FKA change or
installed-release change was used. The Reel candidate is **implemented and tested
offline, disabled without its isolated configuration, and not live-accepted**.

## 1. Per-format evidence matrix

Source of truth: `tools/farm_format_coverage.py` (one row per `UploadFormat`,
tested by `tools/test_farm_format_coverage.py`). The backend reports it at
`/api/farm/capabilities` (`formats`), and the native readiness window lists it.
A level is the strongest *recorded* draft evidence, never a publishing claim.

| Format | Level | Draft mechanism | Evidence | What remains |
|---|---|---|---|---|
| `ig_carousel` | Scoped live acceptance | Observed | Priority 1/2 on C24C: three distinct slides, short visible ASCII caption | Other slide counts, wrapped/hidden captions, accounts, phones |
| `ig_reel` | **Offline candidate** | Observed | 17 Oct supervised MP4 Reel save/reopen/play; this candidate's offline tests | **Fresh integrated C24C acceptance**; multiline captions; repeated runs |
| `ig_post` | Simulation only | Not observed | — | Observe a single-image draft; the carousel route needs 2–10 images |
| `ig_story` | Unsupported | Not observed | — | No verified story draft; sharing a story is publication |
| `tt_video` | Supervised phone | Observed | 17 Oct MP4 draft saved, reopened, played; suggested sound removed | Integrated adapter, sound detection, recovery |
| `tt_photo_carousel` | Supervised phone | Observed | 17 Oct three-photo draft; a suggested sound stayed attached | Integrated adapter, sound handling, recovery |
| `tt_story` | Unsupported | Not observed | — | No verified story draft |
| `tt_text` | Unsupported | Not observed | — | No observed text-post draft save |
| `x_post` | Supervised phone | Observed | 17 Oct one-image draft saved and reopened | Integrated adapter, drafts-list identity |
| `x_video` | Supervised phone | Observed | 17 Oct MP4 draft reopened; blank preview played after Play | Integrated adapter with playback evidence |
| `x_thread` | Unsupported | Not observed | — | No observed thread draft |
| `yt_short` | Supervised phone | Observed | 17 Oct photo-derived and MP4 Shorts; permission prompt needed a physical tap | Integrated adapter; the prompt blocks an unattended claim |
| `yt_video` | Unsupported | Not observed | — | No observed long-video draft |
| `yt_community_post` | Unsupported | Not observed | — | No observed community-post draft |

All 14 formats still execute in the legacy simulation engine; those runs end at
simulated publish targets and prove nothing about a phone draft. Live legacy
upload routes keep refusing live mode. Only `ig_carousel` and `ig_reel` have a
candidate route, and only with the explicit isolated configuration.

## 2. What the Reel candidate does

`/api/farm/reel-creations` (`tools/farm_reel_runs.py`) admits one saved Instagram
Reel copy from the existing immutable video-draft store, binds the request ID to
the package checksum, and runs two bounded owned workflows
(`tools/farm_reel_creation.py`):

**Creation** (fixed 720 s total, 120 s per phase), starting on the exact profile:

1. Home → Safari → the C24C-only expiring page (port 9917). The Reel page is new
   and OCR-friendly: title, `File imouse-reel-xxxxxx`, a button-styled **Download
   video** link and **Copy caption**, all above the fold (17 Oct showed the old
   underlined link reads as garbage).
2. **Copy caption** must confirm *Caption copied*. Long-press **Download video** →
   **Download Linked File** → the Safari download badge → **Downloads** → the
   **unique package file** (a package-bound, OCR-safe name such as
   `imouse-reel-awmekh`, so older `imouse-draft` files can never be confused) at
   its exact complete size → the Files preview must play the package video →
   Share → settled sheet → **Save Video** → Home.
3. Instagram → exact profile → `+` → **Reel** (icon template; OCR often omits the
   label) → the **one Recents tile** that matches the package video, with a margin
   over every other tile → its selection circle → settled numeral **1**, tray
   thumbnail and Next → editor (playing media must match) → details (empty caption,
   matching cover).
4. Caption field → long-press → **Paste** (unique, adjacent to AutoFill) → OK. OK
   only closes the sheet. The exact single-line caption must then be read on
   details, where no caret corrupts OCR, before the **single Save draft**.
5. Instagram must return to the Reel picker with a **Drafts** chip; when both counts
   are readable it must have increased by exactly one. Close → exact profile.

**Independent verification** (new lease, 120 s): profile → `+` → Reel → Drafts →
the **one** Reels drafts row whose square thumbnail matches the package → the
reopened details (Cancel/Edit header, exact caption, matching cover) → Preview:
the **exact account handle**, exact caption, and two fresh frames that match the
package video at **different sample times** (visible playback) → the supervised
exit **Save draft** once → Reels drafts again. Every stored capture in the run must
have been recognized for its role, in one ownership/stream context, with no gap
over 15 s.

Safety properties kept from the carousel route: one lease per run, fresh paired
frames ≤1,500 ms per decision, settled two-frame decisions (`farm_transitions`
now accepts screen-family checks), journal-before-dispatch, Stop, no replay of an
uncertain command, release in `finally`, retained frames, and no automatic
resume. Every tap goes through the existing publish-label guard. Share is never a
target. A second request for the same video and caption is refused once any
earlier attempt could have downloaded, saved, selected, pasted or saved a draft.

## 3. Evidence base and its limits

- Recognizers and geometry come from the retained 17 Oct supervised Reel and
  video-transfer frames (steps 69–90, 152–168) and the 19 Oct Create sheet,
  re-read locally with the production Windows OCR. Those OCR files contain
  personal content and stay in the private archive, outside Git.
- Nine control templates (`tools/farm_reel_controls.json`, built by
  `build_reel_controls.py`) are icon crops only. Each matches independent frames
  (≤0.005 error) and is refused on frames without the control (≥0.12).
- Video identity compares frames decoded from the package (5 fps samples) inside
  fixed boxes; no fitted colour or position. Real 17 Oct renderings match their
  own video (picker 0.023, editor 0.018, details 0.035, Preview 0.043, drafts list
  0.019–0.023, Files preview 0.014–0.030; threshold 0.060). They are refused
  against the new acceptance media (≥0.42), and two acceptance tokens refuse each
  other (≥0.15).
- **Not yet observed on a phone:** the new transfer page rendering, the Reel
  caption sheet's Paste callout position, a settled selection without a Drafts
  chip, the Reel picker close returning to the profile, and a fresh
  Preview-playback pair. Their recognizers fail closed; the protocol fixtures use
  labelled synthetic composites for them.
- The 17 Oct frames came from a kernel without frame-age metadata; one captured a
  selection badge mid-animation. The candidate waits a fixed read-only interval
  before animated screens and needs two agreeing fresh frames.

## 4. Offline verification

| Check | Result |
|---|---|
| Complete Python farm suite | **491 passed**, none skipped, 841 s (was 452; see `python-full.txt` and `validation.json`) |
| Reel protocol fixture (`test_farm_reel_creation.py`) | 9 tests: full creation + verification; lost answer at every creation action; Stop at every dispatch journal; receiver change; lost Save answer never repeated; ambiguous tile, unknown prompt, stale frame, failed OCR, missing Drafts chip, wrong caption, wrong media (nothing reaches Photos), frozen Preview, wrong account |
| Reel recognizers (`test_farm_reel_layout.py`) | 12 tests: every retained route screen, eight real-frame negative controls, new media refused on old renderings, synthetic boundaries |
| Reel service/HTTP (`test_farm_reel_runs.py`) | Disabled by default; one-line ASCII captions only, never truncated; duplicate holds; pre-import retry; no overrides; cancel before admission; local-only routes; package-bound download name and page |
| Native Release build | 0 warnings/errors, `output/claude-farm-reel-20261019` |
| Native headless checks | **578 passed** (was 564): Reel window route/bookmark/lost reply/Stop/verified-only-with-confirmed-creation, Reel button rules, readiness matrix |
| Headless Reel probe dry run | Assembly hash, Reel route/capability/bookmark, zero window handles; no HTTP |

Retained-frame tests need the private local artifacts and skip cleanly in a
GitHub-only clone; synthetic and service tests always run.

## 5. Live acceptance plan (prepared, not run)

Prepared offline by `prepare_reel_live.py`; recheck with `live/verify_preparation.py`. Re-prepared later on
19 Oct, after the TikTok work changed shared sources; the earlier preparation
(token `c0bb4ce25dae`) and an intermediate one (`1fbf9bfdcb71`) were never used and were
replaced.

| Item | Value |
|---|---|
| Run folder | `output/candidate-runs/farm-reel-20261019` (fresh; C24C-only mapping/calibration copied byte-identically) |
| Test media | Labelled `REEL DRAFT TEST`, 4 s, 720×1280, silent; token `397aae4ea4ca`, colour code `[2,1,6,3,7,5]` |
| Video SHA-256 | `ca5df0982d1f9a4fcc6ec0bdda213e94a4e3a0fdce49f5cc6e5318e58bddf0f2` |
| Caption | `Fresh reel acceptance` |
| Download name | `imouse-reel-awmekh` |
| Native DLL | `58b4057833d360d2077617c4f0f49b14f7ae749ab780c9207a3b8fd619c83aa1` |
| Backend source fingerprint | `6f6e84c4ac3fd925eae8e095cc9e6a4426c804ccdcc81124781fd3c715121ef0` (same backend as the TikTok window) |
| Private kernel | unchanged `c72fa4e0…a873` on 9916; media 9917 bind 192.168.4.26 → C24C 192.168.4.57 (recheck the phone's address) |

Window steps (C24C only; no C241 input, desktop control, publishing or FKA change):

1. Operator: connect C24C mirroring to `iMouse2-C24C` and open the
   @xs.halle.xo profile. No other physical help is expected unless a genuinely
   blocked iOS prompt appears (for example a first-time Photos permission), which
   stops the run for review.
2. `python live/verify_preparation.py` → `ready: true`.
3. `live/Start-ReelWindow.ps1` — refuses if any rack/test service or listener
   exists, validates the kernel offline, starts only the private kernel/receiver
   and the 9915 backend, and checks the exact source fingerprint and draft-only
   Reel scope.
4. `live/Run-Reel.ps1` — one headless native Reel creation; never replays an
   attempt or native data folder.
5. `live/Stop-ReelWindow.ps1` — graceful stop of only the owned private services,
   final free-input check, 25 protected installed-file hashes, restored stopped
   state.
6. Review the retained frames and journals, archive them with checksums, and
   update the seven-priority record with the actual result, pass or fail.

Expected side effects on C24C: one labelled test video in Photos and in Safari
Downloads, one new Reel draft, the phone clipboard holding the caption, and
Safari left on the Files preview (the next run closes it with Done). Nothing is
deleted. Repeating the window needs a fresh preparation (new token and run folder).

## 6. Remaining Priority 3 work

- Live acceptance of this Reel candidate, then repeated runs, multiline captions
  once the details layout is observed, and other accounts.
- Next adapters, one at a time from supervised evidence: TikTok video (detect or
  remove suggested sounds; since built offline, see
  [farm-tiktok-draft-20261019](../farm-tiktok-draft-20261019/README.md)), X
  post/video, YouTube Short (permission prompt blocks an unattended claim). Story, text, thread, long-video and community formats stay
  unsupported until a real draft mechanism is observed.
- A Reel saved-draft inspection (Priority 2 analogue) and a continuation that can
  reuse an already imported video, so a stopped run never needs a second import.

### Observed routes for the next adapters (17 Oct supervised steps)

These come from the retained step records and frames. They were driven step by
step with HID-typed, space-free labels; an adapter must use the validated paste
route instead.

| Format | Route observed | Hazards an adapter must handle |
|---|---|---|
| TikTok video (steps 94–113) | Feed `+` → camera → gallery (needed a settled tap) → select the `00:03` tile's circle → Next → editor → Next → details (`Add description`, `Drafts` left, `Post` right) → **Drafts** → Profile → `Drafts: N` tile → drafts list → reopen → Next → details → **Drafts** again | A suggested sound is attached automatically (remove it with its X and verify `Add sound`); the editor puts **Your Story** beside Next, which is publication, so the tap guard must treat it as prohibited; the details page puts Post beside Drafts; gallery taps were unreliable |
| X video (steps 114–130) | Compose `+` → text first → media picker → select video → attach → close → **Save draft** dialog → compose again → Drafts list → reopen | The reopened video preview is blank until played; the draft list is reached from the composer; X requires text before media is accepted |
| YouTube Short (steps 131–151) | Create → Short → gallery → select MP4 → trim review → editor → details → title field → **Save draft** → library route → drafts → reopen → resave | An optional local-network permission dialog ignored pointer input and needed a physical tap, so no unattended claim is possible until that prompt is resolved by setup |

## 7. Reproduce

```powershell
$taskPython = 'C:\Users\joey_\AppData\Local\Programs\Python\Python311\python.exe'
& $taskPython -m unittest discover -s tools -p 'test_farm*.py'
& $taskPython analysis/farm-reel-draft-20261019/build_reel_controls.py   # private frames
./analysis/farm-reel-draft-20261019/Build-And-Test-Native.ps1
```

None of these start a rack service or contact a phone.

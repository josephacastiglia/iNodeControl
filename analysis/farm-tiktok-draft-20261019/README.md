# Priority 3: the TikTok video draft candidate

Scope: **C24C, TikTok @xs.halle.xo, draft only.** This is offline work. It used no
phone input, rack service, desktop control, publishing, messaging, FKA change or
installed-release change. The TikTok candidate is **implemented and tested offline**.
It stays **disabled without its isolated configuration and is not live-accepted**. It is
the second adapter after the Instagram Reel candidate
([farm-reel-draft-20261019](../farm-reel-draft-20261019/README.md)). The per-format
matrix now lists `tt_video` as an offline candidate.

## 1. What the candidate does

`/api/farm/tiktok-creations` (`tools/farm_tiktok_runs.py`) admits one saved
TikTok video copy from the immutable video-draft store and binds the request ID to
the package checksum. It then runs two bounded owned workflows
(`tools/farm_tiktok_creation.py`). The admission, duplicate-hold and retry rules
are the Reel service's (`ReelCreationRuns`), now configurable. TikTok has its own
committing actions.

**Creation** has a fixed budget of 720 s in total and 120 s per phase. It starts on
the exact TikTok profile:

1. The video reaches Photos by the Reel route, unchanged: Home → Safari → the
   C24C-only expiring page → **Copy caption** confirmed → long-press **Download
   video** → **Download Linked File** → Downloads → the unique package file at its
   exact size → Files preview playing the package video → Share → **Save Video** →
   Home.
   - The page is now generated for `tt_video` too. Its title is *TikTok draft*.
     The download name is package-bound and OCR-safe (`imouse-tt-xxxxxx`). The
     copy confirmation names TikTok. The page says to remove suggested sounds and
     never to tap Post, Share or Your Story.
2. TikTok → the exact profile. TikTok resumes where it was left; the For You feed
   is accepted only to tap **Profile**. The **Drafts: N** tile count is recorded.
3. `+` (template) → camera → the bottom-left gallery button → the upload picker.
   - The picker must show Recents, the tabs, the close control, **Select multiple**
     enabled and a disabled Next. No item may show a selection badge.
   - Exactly **one complete tile** must match the package video (centre-square
     crop), with a margin over every other tile. Its duration label, if read, must
     equal the package's (`00:04`).
   - Its circle is tapped. The settled picker must then show exactly one
     numeral-**1** badge, a single tray thumbnail of the package video, and an
     enabled Next. The selected tile is drawn zoomed and dimmed, so its own match
     is recorded only.
4. Editor (the playing canvas must match):
   - The run waits, read-only, until the sound control settles. One state must be
     seen twice at least 1.5 s apart.
   - A suggested sound (name plus ×) is removed **once**, then the editor must be
     silent (*Add sound* with the note icon) before Next.
   - A spinner is never a decision point.
5. Details: empty *Add description...*, matching cover card, *Drafts* and *Post*
   where observed.
   - Focus the field → long-press → **Paste** (unique, next to AutoFill).
   - The exact one-line description must then be read on a frame **without the
     blinking caret**: up to four settled observations, all recorded.
   - **Drafts** is pressed once.
6. TikTok lands either on the feed or directly on the profile. On 17 Oct the
   video draft landed on the feed and the photo draft on the profile, both with a
   *Draft saved* toast, which is recorded. From the feed, only **Profile** is
   tapped. When both counts are readable, the Drafts count must have risen by
   exactly one.

**Independent verification** is a new lease with a 120 s budget:

- Profile → Drafts tile → the **one** drafts tile whose cover matches the package
  video (3:4 crop), with its sound label recorded → the reopened editor.
- The editor must settle silent. A kept suggested sound is removed once, as the
  supervised check did, and the removal is recorded.
- Next → reopened details: **Back/Cancel** header, exact one-line description,
  matching cover → **Drafts** once.
- Drafts list: count unchanged, and the kept tile shows **no sound label**.
- Every stored capture must have been recognized for its role, in one context,
  with no gap over 15 s.

**TikTok-specific safety:**

- The shared publish-label guard runs on every tap.
- These targets are also refused outright, even when OCR misreads their labels:
  - **Post** (17 Oct OCR read it as `ost`);
  - **Your Story**, which publishes from the editor;
  - the camera's **CREATE/LIVE** modes.
- Labels containing *story*, *live*, *repost*, *upload*, *gift* or *message* near
  a target also refuse it.
- TikTok taps rest the pointer on the target for 0.6 s before the single click.
  Two immediate clicks on the gallery button did nothing on 17 Oct; settled taps
  worked. Safari keeps the Reel route's plain taps.
- Descriptions are limited to one visible line of up to 24 printable ASCII
  characters. The 17 Oct 32-character label wrapped beside the cover card, and
  nothing is ever truncated or reassembled.

## 2. Shared changes (Instagram behaviour unchanged)

| File | Change | Proof it is unchanged for Instagram |
|---|---|---|
| `farm_draft_workflow.py` | `Workflow.PLATFORM` (default `instagram`) names the app in every observation request and validation | Carousel, recovery and Reel suites pass |
| `farm_transitions.py` | `wait_for_transition(..., platform='instagram')` | Same |
| `farm_draft_creation.py` | `step(..., settle=False)`: optional move, 0.6 s rest, single click | Default path untouched; carousel suites pass |
| `farm_reel_creation.py` | Video import extracted into `import_video()` with a `transfer_page()` hook | 9 Reel protocol fault-matrix tests pass |
| `farm_reel_runs.py` | Service texts, format and workflow classes are class attributes | 13 Reel service/HTTP tests pass with identical texts |
| `farm_video.py` | Per-format page table (`PAGES`); `tt_video` gets the package page and name | Reel page bytes identical (SHA-256 compared before/after) |
| `imouse_farm_server.py` | TikTok GET/POST/cancel routes, local-only, health `tiktokCreation`, source hash list | Reel route tests pass |
| `Open Marketing Farm Candidate.ps1` | Same source list (39 files, identical order) and a TikTok permission check | Offline hash comparison |
| Native | `FarmDraftRunWindow(..., tiktok: true)`; **Create TikTok draft on C24C…** for saved TikTok copies | 588 headless checks |

`x_video` and `yt_short` keep the supervised `imouse-draft` page. Two existing
tests assumed `tt_video` kept that page. One now checks X and YouTube instead
(`test_farm_reel_runs`); the other now checks the TikTok page's own warning and
no-completion wording (`test_farm_video`). The first complete-suite run caught
the second (`python-full-first-run.txt`).

## 3. Evidence base and its limits

- **Screens.** Recognizers come from the retained 17 Oct supervised TikTok steps:
  video 94–113 and photo 10–25. Their 102 frames were re-read locally with the
  production Windows OCR into the private archive
  `iMouseXP-2.0-evidence-archive/20261019-farm-tiktok-offline` (outside Git; it
  contains personal content; manifest SHA-256
  `96d56b7941951be04d5be312a7e6dd1c2f3f2f0d8cda2e254d3ff1e2a3eebed9`).
- **Review fixes from the photo steps.** They were read after the first commit
  and showed two things:
  - **The landing screen after Drafts.** The photo draft landed on the profile,
    not the feed. The first version required the feed and would have stopped
    after a successful save.
  - **A playing feed never settles.** The first version also protected every
    pixel of the entry check, so if TikTok reopened on the feed, the playing video
    would never settle.

  Both are fixed and tested.
- **Templates.** Eleven control templates (`tools/farm_tiktok_controls.json`,
  built by `build_tiktok_controls.py`, results in `tiktok-controls-check.json`) are
  UI glyph crops only. Each matches independent frames and is refused on frames
  without the control.
- **Media matching.** Every TikTok thumbnail is a centre crop of the video: square
  in the picker and tray, 3:4 on profile and drafts tiles, about 0.68 on the cover
  card, and the full frame in the editor.
  - Real renderings of the 17 Oct video match at mean 0.019–0.049.
  - Different test media is refused at ≥0.43.
  - The picker tile beat every other tile by 0.17.
- **The suggested sound is the main hazard.**
  - On 17 Oct the editor showed a loading spinner. The saved draft later carried
    *Whispers in…*, visible both in the drafts list and in the reopened editor.
  - The candidate waits for the control to settle and removes a suggestion once.
  - The verifier removes a kept suggestion and requires the final tile without a
    sound label.
  - Whether TikTok can attach a suggestion *after* Next is unknown. The verifier
    would detect it.
- **Not yet observed on a phone:**
  - Paste in TikTok's callout. On 17 Oct the photo description's long press
    showed the callout **with only AutoFill** (the clipboard was empty), above the
    press point. The candidate refuses that frame, as a test checks;
  - caret blink timing under the live receiver;
  - suggestion timing;
  - whether *Select multiple* is always enabled;
  - drafts-list rows beyond the first;
  - a profile without any drafts (no Drafts tile; the count stays unknown).

  All of these fail closed. The protocol fixture uses labelled synthetic parts for
  the callout, a caret frame, the one-line description and a "Drafts: 1" read.

## 4. Offline verification

| Check | Result |
|---|---|
| Complete Python farm suite | **522 passed**, none skipped, 1,440 s (was 491; see `python-full.txt` and `validation.json`). Earlier complete runs are kept: the first had one test failure, fixed as described in section 2 (`python-full-first-run.txt`); another hit a transient Windows read-sharing error in the pre-existing carousel creation test, which passed 6/6 alone and in the final run (`python-full-transient-error.txt`). That reader-side race predates this work and is not changed here |
| TikTok protocol fixture (`test_farm_tiktok_creation.py`) | 10 tests: full creation + independent verification; landing on the profile after Drafts; lost answer at every one of 27 creation actions; Stop at every dispatch journal; receiver change; lost Drafts answer never repeated; ambiguous tile, unknown prompt (picker, details), stale frame, failed OCR, a sound that returns after removal, a caret that never clears and a wrong description all stop before the draft; no-suggestion path; wrong media never reaches Photos; the verifier removes a kept suggestion and refuses a wrong account, a wrong description and a sound that stays; Post, Your Story and LIVE refused even when OCR misreads them |
| TikTok recognizers (`test_farm_tiktok_layout.py`) | 10 tests: every retained route screen including the photo route's post-save profile, the real AutoFill-only callout refused, caret and wrap refusals, ten real-frame negative controls, new media refused on old renderings, synthetic crop/caret/feed boundaries |
| TikTok service/HTTP (`test_farm_tiktok_runs.py`) | 11 tests: disabled by default; one-line ASCII descriptions ≤24 only; Reel/TikTok formats never cross; duplicate holds; pre-import retry; TikTok committing actions; no overrides; package page and header; local-only, store-bound routes |
| Native Release build | 0 warnings/errors, `output/claude-farm-tiktok-20261019` |
| Native headless checks | **588 passed** (was 578): TikTok button rules, TikTok window route/bookmark/lost reply/Stop/verified-only-with-confirmed-creation, one window never drives both routes |

Retained-frame tests need the private local artifacts and skip cleanly in a
GitHub-only clone; synthetic, guard and service tests always run.

## 5. Live acceptance plan

Prepared offline by `prepare_tiktok_live.py`; recheck with `live/verify_preparation.py`. Not run.

| Item | Value |
|---|---|
| Run folder | `output/candidate-runs/farm-tiktok-20261019` (fresh; C24C-only mapping/calibration copied byte-identically) |
| Test media | Labelled `TIKTOK DRAFT TEST`, 4 s, 720×1280, silent; token `e4c33174fe15`, colour code `[3,6,1,2,1,7]` |
| Video SHA-256 | `a9bb5e16f7cf5dd34b2d9cec827f2aa53522efecc0761e0f11f04e1ef4ca5a9a` |
| Description | `Fresh tiktok acceptance` (23 characters, one line) |
| Download name | `imouse-tt-tktykw` |
| Native DLL | `3d058ca4a2c85cc5db921ef62203920c8cc355992687125b87c756cedf3001d7` (`output/claude-farm-tiktok-20261019`) |
| Headless driver | `output/farm-tiktok-native-probe-20261019/TikTokProbe.exe`; dry run 3/3 (assembly, TikTok route/capability/bookmark, zero window handles; no HTTP) |
| Backend source fingerprint | `f3e083ae0230da93293df1ace6cef935d083b605c765c0b0527ef32475570819` (same backend as the re-prepared Reel window) |
| Private kernel | unchanged `c72fa4e0…a873` on 9916; media 9917 bind 192.168.4.26 → C24C 192.168.4.57 (recheck the phone's address) |

Window steps (C24C only; no C241 input, desktop control, publishing or FKA
change). This is a separate window from the Reel one; the scripts refuse to start
while any rack/test service, listener or either probe exists.

1. Operator: connect C24C mirroring to `iMouse2-C24C` and open the
   @xs.halle.xo **TikTok profile**. No other physical help is expected unless a
   genuinely blocked prompt appears (for example a first-time TikTok Photos
   permission), which stops the run for review.
2. `python live/verify_preparation.py` → `ready: true`.
3. `live/Start-TikTokWindow.ps1` — validates offline, starts only the private
   kernel/receiver and the 9915 backend, and checks the exact source fingerprint
   and draft-only TikTok scope.
4. `live/Run-TikTok.ps1` — one headless native TikTok creation and its independent
   check; never replays an attempt or native data folder.
5. `live/Stop-TikTokWindow.ps1` — graceful stop of only the owned private services,
   final free-input check, 25 protected installed-file hashes, restored stopped
   state.
6. Review the retained frames and journals, archive them with checksums, and
   update the seven-priority record with the actual result, pass or fail.

Expected side effects on C24C: one labelled test video in Photos and Safari
Downloads, one new silent TikTok draft with the test description, the phone
clipboard holding the description, Safari left on the Files preview (the next run
closes it with Done) and TikTok left on its drafts list. Nothing is deleted.
Repeating the window needs a fresh preparation (new token and run folder).

What this window will settle for the first time: Paste in TikTok's callout,
suggestion timing with this media, settled selection, which screen TikTok lands on
after Drafts, the Drafts count rising by one, and the caret-free description read
under the live receiver.

## 6. Remaining Priority 3 work

- Live acceptance of the Reel and TikTok candidates. Then repeated runs, wrapped
  descriptions once their OCR and layout are observed, and other accounts.
- TikTok photo carousel: it shares this picker and editor. A suggested sound
  stayed attached on 17 Oct.
- Next adapters: X post/video (text first, Save draft dialog, blank reopened
  preview) and YouTube Short. YouTube's permission prompt blocks an unattended
  claim until setup resolves it.

## 7. Reproduce

```powershell
$taskPython = 'C:\Users\joey_\AppData\Local\Programs\Python\Python311\python.exe'
& $taskPython analysis\farm-tiktok-draft-20261019\ocr_retained.py          # private OCR archive
& $taskPython analysis\farm-tiktok-draft-20261019\build_tiktok_controls.py # templates + check
& $taskPython -m unittest discover -s tools -p 'test_farm*.py'
& analysis\farm-tiktok-draft-20261019\Build-And-Test-Native.ps1
```

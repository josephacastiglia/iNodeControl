# Priority 3: YouTube Short draft candidate (offline)

Scope: built and checked offline only, on retained 17 Oct C24C frames and a
simulated HID kernel. It used no phone input, service, desktop control,
publishing or messaging. It is **not** fresh-phone acceptance, and no live
window is prepared. Like the Reel, TikTok and X routes, it is disabled unless the
backend is started with its isolated configuration.

Branch `local/youtube-short-20261020`. It was built in its own worktree from
`71b3b35` while the Reel, TikTok and X windows were prepared, then rebased (before
its first push) onto `800b695`, the combined-candidate tip after those windows had
run, so it inherits their fixes: reconfirming an aged decision with a newer
matching frame, the fresh-frame challenge that never targets the pointer's own
spot, the wrapped copy confirmation and the shifted Safari link menu. Merging it
changes the backend source fingerprint (section 6).

## 1. Which YouTube channel and which phone

| Question | Decision | How the candidate follows it |
|---|---|---|
| Which channel? | **Whichever channel is already signed in on the phone** (the operator's rule of 20 Oct for every platform, as for X) | On 17 Oct C24C's YouTube was signed in to a channel other than `@xs.halle.xo` (You page, step 51; every Add details screen in steps 58–66 and 142–149). Add details is the only screen in the route that names the channel, and it names the channel the draft is saved to. The run reads the one handle there before the title is touched and binds the draft to it; every later details read, and the verifier's reopened details, must show the same handle. A different handle stops with no further input. Backend: `account: null`, `accountPolicy: first_signed_in`. Handles stay out of Git. |
| Which phone? | **The rack phone in box slot 16** (board F215, receiver `iMouse2-16`), not C24C, from configuration | Nothing new hard-codes C24C. The candidate configuration may carry a `phone` block: `{"board": …, "deviceId": …, "receiver": …, "slot": …}` (`creation_config` accepts it; only YouTube reads it). Without it the route is disabled. The run's admission checks that the configured receiver mirrors the configured device ID, and it addresses the configured board and device ID. The native window shows the configured phone. |
| Until the farm is multi-phone | Disabled for slot 16 | This branch's shared transport, observation store and lease still drive one phone (`DEFAULT_SAFE_TEST_DEVICE`). `transport_drives()` refuses any other configured phone with *needs the multi-phone farm*; the coordinator's multi-phone work replaces that check. |
| Permission prompts | Through `tools/farm_permission_prompts.py`, unmodified | Section 4. |

## 2. What was built

| Part | Change |
|---|---|
| `tools/farm_youtube_layout.py` | Recognizers: home feed (four-item bar), Short camera (Add, Drafts, Short mode), gallery picker (tiles, the badge on the chosen tile, the tray, Next), trim review (the whole video selected), editor, Add details (blank, focused, titled; channel handle; cover), Paste callout, Drafts list (exact title, wrapped once at most, plus a matching thumbnail) |
| `tools/farm_youtube_controls.json` | 13 control templates cut from retained frames by `build_youtube_controls.py`, each checked with the production comparison against frames that show the control and frames that do not (`youtube-controls-check.json`). No account, title or personal content is cropped |
| `tools/farm_youtube_creation.py` | `YouTubeCreationWorkflow` and `YouTubeVerification` on the shared Reel base: the configured phone (`phone_from_config`, `transport_drives`), shared Safari/Files import, settled taps, aged-decision reconfirmation on every settled screen, channel binding, per-screen moving masks (the iOS home indicator dims over the dark full-screen views), caret-free title reads, forbidden rectangles (Upload Short, record, the Video/Short/Live/Post tabs, the AI buttons, Edit, Add sound, a draft's ⋮ menu) and prohibited labels (upload, live, subscribe, install, remix, premium, record, feedback) |
| `tools/farm_youtube_runs.py` | `YouTubeCreationRuns`: route `/api/farm/youtube-creations`, format `yt_short`, `first_signed_in`, the configured phone (reported in `capability`; a saved copy must be for its board), YouTube committing actions, its own duplicate hold |
| `tools/farm_creation_runs.py` | `creation_config` accepts the optional `phone` block and still requires every other key exactly |
| `tools/farm_video.py` | `yt_short` gets its own package page and `imouse-yt-…` download name; it says *Save draft* and *Do not tap Upload Short, Post or Live*. No video format is left on the supervised `imouse-draft` page |
| `tools/farm_tiktok_layout.py` | The shared leftover-preview check also recognizes an `imouse-yt-…` download, so any route can close it with Done |
| `tools/imouse_farm_server.py`, `Open Marketing Farm Candidate.ps1` | YouTube GET/POST/cancel routes, local-only and store-bound; health `youtubeCreation`; the source fingerprint list (47 files, identical order in both; a test now checks that). The launcher refuses a backend that enables YouTube without a creation configuration; a configuration without a YouTube phone leaves YouTube disabled |
| `tools/farm_format_coverage.py`, `tools/farm_capabilities.py` | `yt_short` is `integrated_offline` with its candidate route; feature `youtube-draft` |
| Native | `FarmDraftRunWindow(..., youtube: true)` and **Create YouTube Short draft…** for saved YouTube Short copies. The window requires the backend's `first_signed_in` policy and a configured phone (it names it: *Configured phone: iMouse2-16 (board F215, box slot 16)*), refuses a verified result whose check saw another channel, and shows the bound channel. No YouTube text names C24C |

## 3. Route as implemented

**Creation** (one owned run, one lease, journal before every dispatch):

1. Admit on the YouTube home feed of the configured phone, after checking that
   the configured receiver mirrors it. A permission prompt over the feed stops
   admission with its one-time request; nothing is sent.
2. Shared video import: Home → Safari → transfer page → Copy caption → long-press
   *Download video* → download → Downloads → file preview → Share → Save Video
   (Photos) → Home → search `YouTube` → open YouTube → the home feed again.
3. **+** → the Short camera (Short mode required) → **Add** → the gallery picker.
4. The one complete tile that matches the package video by a unique margin is
   selected at its circle; **Next** is pressed only when the white "1" badge and
   frame are on that same tile and the tray holds one item.
5. Trim review: **Done** only when the selection frame spans the whole strip
   (nothing trimmed) and the video matches; a read length label must equal the
   package's (`3.0s` on 17 Oct).
6. Editor (the package video playing) → **Next** → Add details. The channel
   handle is read and bound here.
7. Tap the empty title → long press → **Paste** (the exact title copied from the
   page; never HID typing) → the exact title must be read on a frame without the
   caret, fully inside the field → **Save draft** once → the home feed (the
   *Draft saved* toast is recorded, not required).

**Verification** (a separate owned run): home → **+** → camera → **Drafts** →
the row whose full title equals the caption and whose thumbnail matches → the
reopened editor must show two frames at different video times → **Next** → the
reopened details must show the exact title, the bound channel and the cover →
**Save draft** once → home → **+** → **Drafts** again: the same row, the same
number of rows → a check of the sampled history. YouTube is left on its Drafts
list.

Upload Short, recording, Live, Post and a draft's ⋮ menu are never targets, even
if OCR misreads them. An unknown or uncertain answer stops the run; nothing is
repeated or resumed.

## 4. Evidence base and its limits

- **Screens.** Recognizers come from the retained 17 Oct supervised YouTube
  steps: the photo Short 46–66 and the transferred MP4 Short 131–151. Their
  frames were re-read with the production Windows OCR into the private archive
  `iMouseXP-2.0-evidence-archive/20261020-farm-youtube-offline` (117 files,
  manifest `f763e5a860f66b7d4b67c50f0b27a2b92eb5625742c10669242ca3d3a8a9d33c`,
  written by `analysis/farm-permission-prompts-20261020/ocr_retained.py`). The
  archive is outside Git because it shows personal channel and feed content.
- **Two layouts on one day.** Between 6:22 and 6:56 on 17 Oct YouTube changed its
  navigation bar (five labelled items → four unlabelled ones) and its gallery
  picker ("Recents" grid → "Create from gallery"). The candidate implements the
  later layout, which the MP4 route used. The earlier frames are negative
  controls: that layout stops the run before any YouTube input.
- **The observed route, its hazards and how each is handled:**

  | Step | Observed (17 Oct) | Handling |
  |---|---|---|
  | Launch | Local-network prompt *Allow "YouTube" to find devices on local networks?*; the pointer's click and Escape were ignored; the operator tapped *Don't Allow* (132–136) | `farm_permission_prompts` (unmodified) recognizes it at admission and on every screen. With no validated method the run stops with *Choose "Don't Allow" … one-time step per phone and app*; with a validated method it answers *Don't Allow* once as a journaled action |
  | Camera | **+** opens the Short camera with Add, Drafts (only once drafts exist), record, Video/Short/Live/Post (137, 146; 52 without Drafts) | Only Add and Drafts are targets; Short must be the selected mode; the tool labels fade, so they are not required |
  | Picker | Three columns, newest first; circle at each tile's top right; selecting draws a white "1" disk, a white frame and a tray item; *Edit with AI*, *Next* (138–139) | The supervised pointer sat on the badge in the retained selected frames; the white badge is visible only in 140/pointer and 140/immediate, where the pointer covers Next instead. Tests join two retained frames of that screen (section 5) |
  | Trim | *Drag to adjust video*, the whole 3-s clip selected, *Done*; the photo route selected 2 s of a longer strip (140–141; 55) | Done only with the whole strip selected; the 2-s photo selection is refused |
  | Editor | Plays the video; *Add sound*, tools, *Edit*, *Next* (141–142, 148–149) | Add sound and Edit are forbidden; the playing editor is the playback proof |
  | Details | *Caption your Short* → *Title*; channel row; *Visibility Public*; **Save draft** / **Upload Short** (142–145, 149) | Upload Short is forbidden. *Public* is the upload setting; a saved draft is local to the device |
  | Title | The 32-character title filled the field and OCR lost its first letter on both details reads (145, 149); the caret was read as an extra `1` (60) | Titles are limited to 24 ASCII characters (a 26-character title was read exactly, step 65) and must be read caret-free and fully inside the field. The clipped retained reads are refused |
  | Save | Home with *Draft saved* (145, 150) | The toast is recorded, never the proof |
  | Drafts | Camera → Drafts: *Removing the YouTube app will delete all draft videos created on this device*, each draft's title (wrapped at a hyphen when long), relative time, thumbnail with duration (147) | Exact title proof: one line, or two that rejoin to the caption at a hyphen or a space; the thumbnail must match |
  | Reopen | The editor plays the draft; Next → details with the title; Save draft keeps it (148–150) | Two playback frames at different times; exact title, same channel; one Save draft |

- **Media matching** (fixed crops of frames decoded from the package; mean
  difference, match limit 0.06): picker tile 0.017, nearest other tile 0.199;
  selected tile 0.035; trim review 0.017–0.021; editor 0.012–0.024 (reopened
  frames at sampled indices 5 and 9); details cover 0.026; drafts thumbnail
  0.024, the other draft 0.200. A different test video is refused on all six
  screens, and the labelled light acceptance media drawn into the same boxes is
  accepted on all six (synthetic composite).
- **Not yet observed on a phone.** Each fails closed:
  - YouTube's Paste callout on the title field (the fixture uses a labelled
    synthetic callout in the shape observed on Instagram's caption sheet);
  - a title shorter than 26 characters in this layout, and the caret's blink
    timing (the title is drawn into retained frames in the fixture);
  - first-run Photos access for YouTube's own gallery, and camera/microphone
    access for its camera (each would stop with its one-time request);
  - the camera preview in a lit scene (the Short-mode check compares the
    selected tab's grey pill with the others);
  - a drafts list longer than three visible rows; trim and editor loading time;
  - the five-item layout coming back (stops at admission);
  - **the slot 16 phone itself.** Every position, crop and template comes from
    C24C's mirrored 500×1080 frames. A frame of another size is refused, and a
    phone of another model or iOS/YouTube version may show other positions;
    either way the run stops before acting. Slot 16's YouTube may also be in
    another layout, may show its local-network prompt on first launch, and may be
    signed in to another channel (bound, as above).
- **Channel binding** relies on OCR of one handle line under the channel name;
  other text on the screen is never read as an account.

## 5. Offline verification

| Check | Result |
|---|---|
| Complete Python farm suite | **607 passed**, none skipped, 3,576 s at Windows Idle priority (`python-full.txt`, `validation.json`); 567 on the base `800b695` plus 40 YouTube tests |
| YouTube protocol fixture (`test_farm_youtube_creation.py`) | 13 tests: full creation + independent verification on the bound channel; a different channel stops creation (before the title) and verification; lost answer at every creation action stops without replay; lost Save draft answers (creation and keep) are never repeated; an ambiguous tile, an unknown prompt over the camera or titled details, a stale frame, a trimmed selection, a caret that never clears and a wrong pasted title stop before the draft; wrong media never reaches Photos; the retained local-network prompt stops admission with nothing sent and stops the run when YouTube reopens, and a validated method answers *Don't Allow* once; the earlier layout is refused at admission; the configured receiver must mirror the configured phone, and a phone the shared transport cannot drive (slot 16) is refused before anything starts; a slow recognition is reconfirmed by a newer matching frame, and a screen that changed after recognition is never tapped; the verifier refuses wrong text and a frozen video; committing purposes name real actions; upload/record/Live/Post/AI/Edit/Add sound/⋮ are never targets |
| YouTube recognizers (`test_farm_youtube_layout.py`) | 11 tests: every retained route screen and its target; 19 real-frame negative controls (earlier layout, prompt over home, pointer over the badge, trimmed selection, clipped 32-character title, photo draft, …); the local-network prompt is the shared module's family; caret and whole-video rules on real frames; Short mode; light acceptance media accepted in every media box; new media refused on old renderings; title, wrap and Paste rules |
| YouTube service/HTTP (`test_farm_youtube_runs.py`) | 16 tests: signed-in channel policy (Reel and TikTok stay fixed); disabled by default; the phone only from configuration (none → disabled; slot 16 → named but disabled until the multi-phone farm; a malformed block stops the backend); a saved copy must be for the configured board; the configuration's optional `phone` block; one-line ASCII title ≤24 only; formats never cross routes; duplicate holds; pre-import retry; YouTube committing actions; no overrides; package page and header; leftover preview; server and launcher pin the same 47 files in the same order; local-only, store-bound routes |
| Control templates | 13 templates; every positive and negative frame as expected (`youtube-controls-check.json`) |
| Native Release build | 0 warnings/errors, `output/claude-farm-youtube-20261020`, DLL `7df3c1fd25188b36f4efdd15fcbc621dae872aa7a273b5c9b070a07dc9a312ae` |
| Native headless checks | **617 passed** (600 on the base), mock transport only: the YouTube button rules; the YouTube window's route, bookmark, lost reply and Stop; a fixed-account backend refused; a backend with no configured phone refused; the configured phone named; a verified result checked on another channel refused; the bound channel shown; one window never drives YouTube with another route |

Retained-frame tests need the private local artifacts (the ignored 17 Oct frames
and the OCR archives) and skip cleanly in a GitHub-only clone; synthetic, guard
and service tests always run. In this worktree the ignored frames were copied
byte-identically from the combined-candidate checkout.

Reproduce: `cd tools; python -m unittest discover -s . -p "test_farm*.py"` (or
`python analysis/farm-youtube-draft-20261020/run_suite.py`, the same discovery at
Windows Idle priority so a live window on the PC keeps the CPU),
`powershell -File analysis/farm-youtube-draft-20261020/Build-And-Test-Native.ps1`,
then `python analysis/farm-youtube-draft-20261020/record_validation.py`
(`validation.json` pins the product and test bytes).

## 6. Live acceptance: not prepared

On instruction, no live window is prepared, no phone input was sent and nothing
was merged into `local/combined-candidate-20261012`; the coordinator drives the
rack. Merging this branch changes the backend fingerprint (47 files), so every
prepared window must be re-prepared. A YouTube window on slot 16 first needs the
multi-phone farm (transport, observation store, lease, runtime checks and video
copies for board F215) and then a configuration with the slot 16 `phone` block;
`transport_drives()` is the one place that then changes. It would follow the X
pattern (`prepare_x_live.py`): fresh run folder, labelled test video, a title of
at most 24 ASCII characters, and the operator starting YouTube on its home feed
in the four-item layout. The local-network prompt, if it appears, needs one
physical *Don't Allow* unless an input method has been validated first.

## 7. Remaining Priority 3 work

- The multi-phone farm for slot 16 (section 6), then evidence from slot 16's own
  frames before trusting C24C geometry there.
- Live acceptance of the Reel, TikTok and X candidates, then of this one; a
  permission-prompt validation window.
- The TikTok photo carousel (sound kept unless testing no sound) and X image
  posts.
- `MARKETING-FARM-STATUS.md` and the handoff do not mention this branch yet; add
  a line when it is merged.

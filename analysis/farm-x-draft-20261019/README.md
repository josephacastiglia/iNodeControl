# Priority 3: X video draft candidate (offline)

Scope: built and checked offline only, on retained 17 Oct C24C frames and a
simulated HID kernel. It used no phone input, service, desktop control,
publishing or messaging. It is **not** fresh-phone acceptance. Like the Reel and
TikTok routes, it is disabled unless the backend is started with its isolated
configuration.

## 1. Operator decisions (20 Oct)

| Question | Decision | How the candidate follows it |
|---|---|---|
| Which X account is authorized? | Any X account that is signed in first | The run reads the one handle in X's side menu **before any other X input** and binds the draft to it. Every later menu read, and the separate check, must show the same handle; a different handle (or more than one) stops with no further input. There is no configured X account. The handle stays in private run records and is never written into Git. |
| Permission prompts | Develop automatic handling so people do not have to keep stepping in | `analysis/farm-permission-prompts-20261020/README.md`. Every X screen check first looks for a system prompt; until an answer method has been validated on a phone, a prompt stops the run with a one-time request. The iOS system photo picker needs no Photos permission. |
| Carousel sound | Uploaded carousels keep a sound unless the test is about no sound | Applies to the future TikTok photo-carousel adapter, not to X. |

## 2. What was built

| Part | Change |
|---|---|
| `tools/farm_x_layout.py` | Recognizers: timeline, side menu (handle), composer empty/text/media (and a reopened blank card), Paste callout, the iOS photo picker (Loading…, tiles, the selected tile's badge), the Save to drafts sheet and the Drafts list |
| `tools/farm_x_creation.py` | `XCreationWorkflow` and `XVerification` on the shared Reel/TikTok base: account binding, settled taps, per-screen MOVING masks, forbidden rectangles (Post, media remove ×, Discard) and prohibited labels (repost, quote, reply, like, bookmark, message, Grok, Premium, subscribe) |
| `tools/farm_x_runs.py` | `XCreationRuns`: route `/api/farm/x-creations`, format `x_video`, account policy `first_signed_in`, X committing actions, its own duplicate hold |
| `tools/farm_reel_runs.py` | `PINNED_ACCOUNT` class setting. Reel and TikTok keep `fixed` (`@xs.halle.xo`); X reports `account: null`, `accountPolicy: first_signed_in` and passes the bound handle to its verifier |
| `tools/farm_video.py` | `x_video` gets its own package page and download name (`imouse-x-…`); it says *Save to drafts* and *Do not tap Post or Discard* |
| `tools/imouse_farm_server.py`, `Open Marketing Farm Candidate.ps1` | X GET/POST/cancel routes, local-only and store-bound; health `xCreation`; the source fingerprint list (43 files, identical order in both) |
| `tools/farm_format_coverage.py`, `tools/farm_capabilities.py` | `x_video` is `integrated_offline` with its candidate route; feature `x-draft` |
| Native | `FarmDraftRunWindow(..., x: true)` and **Create X draft on C24C…** for saved X copies. The window requires the backend's `first_signed_in` policy, refuses a verified result whose check saw another handle, and shows the bound handle |

A related fix found by the protocol tests: when a different handle appeared, the
run stopped correctly but reported a generic frame error, because the shared
frame check rejects any account mismatch first. X now names the cause (*A
different X account … is shown; no further input is sent*).

## 3. Route as implemented

**Creation** (one owned run, one lease, journal before every dispatch):

1. Admit on the X home timeline. Open the side menu, bind the handle, close it.
2. Shared video import: Home → Safari → transfer page → Copy caption → long-press
   *Download video* → download → Downloads → file preview → Share → Save Video
   (Photos) → Home → search `X` → open X. Recheck the handle in the side menu.
3. Compose → focus the empty text → long press → **Paste** (the exact text
   copied from the page; never HID typing).
4. Gallery icon → system photo picker. While it shows *Loading…* the run only
   observes again (up to 6 read-only tries). The one tile that matches the package
   video by a unique margin is selected; **Add** is pressed only when the blue
   badge is on that same tile.
5. The media card must match the package video. Cancel → **Save to drafts** once →
   the timeline.

**Verification** (a separate owned run): the same handle in the side menu →
compose → **Drafts** → the row whose full line equals the text and whose
thumbnail matches → reopen → Play if the card is blank → two playback frames at
different video times → Cancel → **Save to drafts** once → the timeline → a check
of the sampled account history.

Post, Discard and the media remove × are never targets, even if OCR misreads
them. An unknown or uncertain answer stops the run; nothing is repeated or resumed.

## 4. Evidence base and its limits

- **Screens.** Recognizers come from the retained 17 Oct supervised X steps:
  image post 28–45 and video 114–130. Their 98 frames were re-read locally with
  the production Windows OCR (`ocr_retained.py`) into the private archive
  `iMouseXP-2.0-evidence-archive/20261019-farm-x-offline`. The archive is outside
  Git because it contains personal and third-party feed content. Manifest SHA-256:
  `7286f446722732bdbb227a00747a7f475731729e63fe62920602affd10412231`.
- **The observed route, its hazards and how each is handled:**

  | Step | Observed (17 Oct) | Handling |
  |---|---|---|
  | Account | Avatar → side menu with display name, **@handle**, Profile, Communities, Download Grok, Settings and privacy | The handle is the only identity proof (the timeline shows none); it is bound here and rechecked |
  | Compose | **Cancel**, **Drafts** (only while empty), **Post**, *What's happening?*; first-use tips (*Your drafts are here*, *Choose who can reply*) | Post is forbidden; tips are masked as moving content and filtered from the guards |
  | Text | Text first, media after; the avatar overlaps the first letter in OCR and the caret corrupts the end | The composer is not an exact-text proof; the Drafts list row is |
  | Media | System photo picker (*Photos/Collections, Add, Search your library*, newest first) → blue numbered badge on the chosen tile, *Show Selected (1)* | Selected tiles render dimmed, so identity comes from the chosen tile's position plus the badge |
  | Attached | Video card with duration, `720p`, remove ×, edit; *Mark your media as sensitive* tip | The card is matched against the package; × is forbidden |
  | Save | Cancel → *Save to drafts* / **Discard** / *Keep editing* | Discard is forbidden; *Save to drafts* is pressed once |
  | Drafts | Empty composer → **Drafts** → each draft's full text line and a thumbnail | Exact text proof. 17 Oct still read `l` for `I` (`VlDEO`), so test text avoids ambiguous capitals |
  | Reopen | The video card is **blank grey** until Play | A blank card is never media proof; playback must show two different frames |

- **Media matching** (fixed centre crops of frames decoded from the package):
  - picker tile mean 0.022, while the nearest other tile was 0.19;
  - composer card 0.025;
  - reopened, playing card 0.026.

  A different test video is refused on all four of those screens.
- **Not yet observed on a phone.** Each of these fails closed:
  - X's Paste callout (the fixture uses a labelled synthetic callout in the shape
    observed on Instagram's caption sheet);
  - how long the picker shows *Loading…*;
  - a drafts list longer than the two observed rows;
  - first-use tips on another account;
  - a first-time Photos or other system prompt in X.
- **Account binding** relies on OCR of the menu handle. The shared classifier
  reads handles only in the top 35% of an account menu, never from posts.

## 5. Offline verification

| Check | Result |
|---|---|
| Complete Python farm suite | **556 passed**, none skipped, 1,994 s (was 531 after the journal read-race fix; `python-full.txt`, `validation.json`) |
| X protocol fixture (`test_farm_x_creation.py`) | 8 tests: full creation + independent verification on the bound handle; a different handle stops creation and verification with that reason; lost answer at every creation action stops without replay; a lost Save to drafts answer is never repeated; an ambiguous tile, an unknown prompt and a stale frame stop before the draft; wrong media never reaches Photos; the verifier refuses wrong text and a frozen video; committing purposes name real actions; Post, Discard and × are never targets |
| X recognizers (`test_farm_x_layout.py`) | 5 tests: every retained route screen and its target; ten real-frame negative controls; new media refused on old renderings; the text rules; the save sheet needs all three choices |
| X service/HTTP (`test_farm_x_runs.py`) | 11 tests: signed-in account policy (Reel and TikTok stay fixed); disabled by default; one-line ASCII text ≤32 only; formats never cross routes; duplicate holds; pre-import retry; X committing actions; no overrides; package page and header; local-only, store-bound routes |
| Native Release build | 0 warnings/errors, `output/claude-farm-x-20261019`, DLL `9652c2316b900c1264c449f8bc15acbd078ab3f0d16f8193b5464585d80262ef` |
| Native headless checks | **600 passed** (was 588): X button rules; X window route/bookmark/lost reply/Stop; a fixed-account backend refused; a verified result checked on another handle refused; the bound handle shown; one window never drives X with another route |

Retained-frame tests need the private local artifacts and skip cleanly in a
GitHub-only clone; synthetic, guard and service tests always run.

## 6. Live acceptance plan (prepared, not run)

Prepared offline on 20 Oct by `prepare_x_live.py` from the committed sources
(`c358e74`). Recheck with `live/verify_preparation.py`, which also recomputes the
backend source fingerprint that `live/Start-XWindow.ps1` requires. Nothing about
an X account is prepared: the run binds whichever account is signed in.

| Item | Value |
|---|---|
| Run folder | `output/candidate-runs/farm-x-20261019` (fresh; C24C-only mapping/calibration copied byte-identically) |
| Test media | Labelled `X DRAFT TEST`, 4 s, 720×1280, silent; token `dcecea04c632`, colour code `[0,2,3,4,2,5]` |
| Video SHA-256 | `ffce68c88e71a93508c97dce160ff6c758dc14edfc172d3a10e32d7627451a4a` |
| Text | `Fresh x acceptance` (18 characters, one line) |
| Download name | `imouse-x-vakvtp` |
| Native DLL | `9652c2316b900c1264c449f8bc15acbd078ab3f0d16f8193b5464585d80262ef` (`output/claude-farm-x-20261019`) |
| Headless driver | `output/farm-x-native-probe-20261019/XProbe.exe`; dry run 3/3 (assembly, X route/capability/bookmark, zero window handles; no HTTP) |
| Backend source fingerprint | `c5784346da3d24e9f334212fb16dbe50356f45660adbc10160e7fa0c83b18e48` (same backend as the re-prepared Reel and TikTok windows; the launcher's offline `-ValidateOnly` reports the same value) |
| Private kernel | unchanged `c72fa4e0…a873` on 9916; media 9917 bind 192.168.4.26 → C24C 192.168.4.57 (recheck the phone's address) |

Window steps (C24C only; no C241 input, desktop control, posting or FKA change).
This is a separate window from the Reel and TikTok ones; the scripts refuse to
start while any rack/test service, listener or probe exists.

1. Operator: connect C24C mirroring to `iMouse2-C24C`, open X **on its home
   timeline** and leave it signed in to the account the draft should use. No
   other physical help is expected. A first-time system prompt stops the run with
   a one-time request.
2. `python live/verify_preparation.py` → `ready: true`.
3. `live/Start-XWindow.ps1` — validates offline, starts only the private
   kernel/receiver and the 9915 backend, and checks the exact source fingerprint
   and draft-only X scope (`account: null`, `accountPolicy: first_signed_in`).
4. `live/Run-X.ps1` — one headless native X creation and its independent check;
   never replays an attempt or native data folder. Its output (which names the
   bound handle) goes to the private run folder, not to this record.
5. `live/Stop-XWindow.ps1` — graceful stop of only the owned private services,
   final free-input check, 25 protected installed-file hashes, restored stopped
   state.
6. Review the retained frames and journals, archive them with checksums, record
   the result here without the handle, and update the seven-priority record, pass
   or fail.

Expected side effects on C24C: one labelled test video in Photos and Safari
Downloads, one new X draft with the test text, the phone clipboard holding the
text, Safari left on the Files preview (the next run closes it with Done) and X
left on its timeline. Nothing is posted or deleted. Repeating the window needs a
fresh preparation (new token and run folder).

What this window will settle for the first time: Paste in X's callout, how long
the picker shows *Loading…*, the live picker order, and first-use tips on this
account.

## 7. Remaining Priority 3 work

- Live acceptance of the Reel, TikTok and X candidates, then repeated runs and
  other accounts.
- A permission-prompt validation window
  ([record](../farm-permission-prompts-20261020/README.md)).
- X image posts (same composer; the picker selects a photo) and threads (no draft
  mechanism observed).
- YouTube Short, and the TikTok photo carousel with its sound kept.

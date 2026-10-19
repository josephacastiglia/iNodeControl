# iMouse 2.0 — 19-iPhone Marketing Farm & Social Automation Handoff (`IMOUSE_MARKETING_FARM_HANDOFF.md`)

**Date:** 2026-10-15
**Target Checkout:** `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-combined-candidate`
**Base Kernel Commit:** `250e589` (Gate 4 `1000/1000` taps PASS on `C24C`, 0 lease errors, 0 dropped frames)
**Kernel Endpoint:** `http://127.0.0.1:9913/api` (Vendor port `9911` is strictly refused)
**Marketing Farm Server Endpoint:** `http://127.0.0.1:9914`

## 1. Executive Summary & What Was Built

This handoff documents the design, implementation, and offline verification of the **7-Layer 19-iPhone Marketing Farm & Social Automation System** built on top of the iMouse 2.0 C# Kernel (`src/iMouse.Kernel/ApiServer.cs`, `InputSessions.cs`, and `FrameStore.cs`).

All new code lives in **additive files** under `tools\` and `src\iMouse.Console\FarmAutomationWindow.cs`. No protected release files (`Start iMouse2.vbs`, `Stop iMouse2.vbs`, `Launch iMouse2.ps1`, `config\airplay.Edge.config.json`, or `src\iMouse.Kernel\*`) were modified.

### Deliverable File Inventory

| File Name | Target Path in Checkout | Size | SHA-256 Prefix | Role |
| :--- | :--- | :--- | :--- | :--- |
| **`imouse_social_automation.py`** | `tools\imouse_social_automation.py` | `120,433 B` | `5c57370f6fc5` | Complete 7-layer Python backend engine: `IMouseKernel` (`9913`), `HumanizedTargetJitter`, `FarmDatabase` (SQLite), `LlmCodeAnimationEngine` (`.mp4` + `4:5` `.jpg`), `VideoGenUgcApiClient`, `AntiDuplicateSpinEngine` (`dHash`/EXIF/QuickTime UUID), `MediaPullOrchestrator` (`iMousePull.shortcut.plist`), `SocialUploadOrchestrator` (14 formats), `AccountWarmupEngine`, `ConversionFunnelEngine`, `ShadowbanGuardAndDiagnostics`, and `MockApiServer` `--self-check` |
| **`imouse_farm_server.py`** | `tools\imouse_farm_server.py` | `70,189 B` | `5b86ecb3d695` | Localhost HTTP server (`127.0.0.1:9914`) serving the web Command Center (`/`), REST endpoints (`/api/farm/*`), iPhone Camera Roll staging (`/stage/<device_id>/manifest.json` + `.mp4`/`.jpg`), and live CORS proxy (`/kernel-proxy/*` $\rightarrow$ `127.0.0.1:9913/api`) |
| **`imouse_farm_command_center.html`** | `tools\imouse_farm_command_center.html` | `49,298 B` | `423da75a7e0b` | Standalone dark-mode 19-iPhone Marketing Farm Command Center UI with live `500x1080` Gaussian click visualizer, 5-stage pipeline strip, 19-phone rack wall, and RPC stream log |
| **`FarmAutomationWindow.cs`** | `src\iMouse.Console\FarmAutomationWindow.cs` | `16,802 B` | `78b5a04f2d6b` | Native C# WPF window for `iMouse2.exe` (`namespace IMouse2.ConsoleApp`) with 1-Click Auto-Create & Deploy, Cohort Warmup, Emergency Stop, and `500x1080` Gaussian tap visualizer |
| **`setup_imouse_farm.py`** | Run from `Downloads\` | `94,978 B` | Self-verifying | 1-click self-extracting installer that writes all 4 files above with UTF-8 encoding, verifies SHA-256 hashes, creates `Open Marketing Farm.ps1`, runs both `--self-check` suites, and launches `http://localhost:9914` |
| **`imouse_social_automation_blueprint.md`** | `docs\imouse_social_automation_blueprint.md` | Reference | Documentation | Reference blueprint for kernel protocol, `500x1080` coordinates, and 4-phase warmup rules |

## 2. Quick-Start Installation & Verification Commands

### Option A: 1-Click Automated Setup (Recommended)
Download `setup_imouse_farm.py` from Canvas and run in PowerShell:
```powershell
python "$env:USERPROFILE\Downloads\setup_imouse_farm.py"
```
To install and run self-checks without keeping the server open in that terminal:
```powershell
python "$env:USERPROFILE\Downloads\setup_imouse_farm.py" --no-server
```

### Option B: Manual CLI Verification & Server Launch
From `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-combined-candidate`:
```powershell
# 1. Run offline 7-layer engine self-check (touches no hardware)
python -B tools\imouse_social_automation.py --self-check

# 2. Run offline localhost:9914 server self-check (verifies SQLite, .mp4 + .jpg staging, uploads & funnel)
python -B tools\imouse_farm_server.py --self-check

# 3. Boot the live Marketing Farm Command Center on http://localhost:9914
python tools\imouse_farm_server.py
```

### Option C: Opening the Native WPF Window Inside `iMouse2.exe`
`src\iMouse.Console\FarmAutomationWindow.cs` compiles directly into `iMouse2.exe`. Wire a toolbar button or hotkey in your main console window to open it:
```csharp
var farmWindow = new IMouse2.ConsoleApp.FarmAutomationWindow { Owner = this };
farmWindow.Show();
```

## 3. Architecture of All 7 Farm Layers

### Layer 0 — Kernel Client & `500x1080` Anti-Detection Physics (`IMouseKernel`, `HumanizedTargetJitter`)
* **Strict Kernel Contract (`127.0.0.1:9913/api`)**:
  * Preflights every phone via `GET /api/kernel/status` (`input_leases_required == true` and receiver `live == true`) and `POST /api/` `{"fun": "/input/status", "data": {}}` (asserts `owned`, `active`, `stopped`, `releasing`, and `release_failed` are all `false`).
  * Acquires per-phone lease tokens (`"/input/acquire"`, `lease_ms=120000`), auto-renews when `lease_remaining_ms < 25000` (`"/input/renew"`), and guarantees `"/input/release"` in `finally`.
  * Captures uncompressed 24-bit `500x1080` BMP screenshots (`GET /api/pic/screenshot?id=<pid>&binary=true`), masks the top `60px` iOS status bar (`STATUS_BAR_PX = 60`), and runs `parse_bmp_grid()` + `wait_still()` to verify UI transitions settled.
* **Non-Repeating 2D Truncated Gaussian Clicks**:
  * Samples integer `(x, y)` coordinates inside each button's 14%-inset `PixelBoundingBox` (`UI_BOXES_500x1080`) with a 48-tap ring buffer so **no button is ever clicked at the same `(x, y)` pixel twice**.
  * Sends an approach waypoint (`/mouse/move`) prior to `/mouse/click` and randomizes swipe lengths (`0.35–0.88`), durations (`210–680 ms`), and multi-point cubic Bézier drags (`generate_drag_waypoints`).
* **FKA-Safe Text Entry & Keyboard Dismissal**:
  * Defaults to `TextEntryStrategy.ON_SCREEN_KEYBOARD_JITTER` (taps individual keys on the `500x1080` iOS QWERTY grid `IOS_QWERTY_BOXES` with Gaussian jitter) or `IOS_CLIPBOARD_PASTE` to avoid the deferred iOS Full Keyboard Access (FKA) missing-first-space bug.
  * Dismisses the iOS keyboard by tapping the neutral safe zone (`keyboard_dismiss_safe`: `[410, 520, 485, 575]`)—never `Home`, which injects `Tab` when FKA is enabled.

### Layer 1 — SQLite Farm Database & Dual-Track Video/Carousel Factory (`FarmDatabase`, `ContentFactoryEngine`)
* **Persistent SQLite State (`output/farm-data/imouse_farm.db`)**:
  * Pre-seeded with all 19 rack phones (`C24C`, `C241`, `RACK-03` .. `RACK-19`) across 5 staggered cohorts (`personas`, `content_slates`, and `upload_logs` tables).
* **Track A — LLM Code-Driven `.mp4` Animation & `4:5` Carousel Compiler (`LlmCodeAnimationEngine`)**:
  * Calls the configured LLM endpoint (`IMOUSE_LLM_API_KEY`, with a deterministic offline procedural spec fallback) via `generate_animation_code_spec()`.
  * Compiles the generated animation spec frame-by-frame into a real 9:16 vertical `.mp4` video (`compile_code_spec_to_mp4` using `cv2.VideoWriter` + `Pillow` + smoothstep easing curves) and renders 4:5 (`540x675` / `1080x1350`) multi-slide `.jpg` carousels (`render_carousel_slide_bytes`) ([Sprout Social](https://www.google.com/search?q=https%3A%2F%2Fsproutsocial.com%2Finsights%2Finstagram-carousel%2F)).
* **Track B — Pluggable External VideoGen / AI UGC API Client (`VideoGenUgcApiClient`)**:
  * Accepts a `VideoGenUgcJobSpec` (`provider` such as `"heygen_ugc"`, `"creatify_ugc"`, `"arcads_ugc"`, `"runway_gen3"`, `"luma_dream"`, `"custom_webhook"`, plus `avatar_id`, `voice_id`, `script_text`, `product_url`), submits/polls the job, and stages the resulting `.mp4` with per-phone anti-duplicate spin.
* **Hook Winner Cloner (`clone_winning_hooks`)**:
  * Detects any phone whose 24h views exceed $2\times$ the rack median and clones niche-adapted variations of that hook across sibling accounts.

### Layer 2 — Anti-Duplicate Spin Engine (`AntiDuplicateSpinEngine`)
* **Per-Phone Cryptographic & Perceptual Uniqueness**:
  * Applies a `1.2%–2.2%` asymmetric micro-crop & bicubic rescale, subtle RGB brightness/contrast LUT shift, and corner pixel perturbation to every carousel slide and video frame ([Ssemble](https://www.google.com/search?q=https%3A%2F%2Fwww.ssemble.com%2Fblog%2Faccount-warmup-guide-2026)).
  * Injects fresh Apple iPhone EXIF comments into `.jpg` files and appends a unique Apple QuickTime `free`/`UUID` atom trailer to `.mp4` files so every phone's staged media has a distinct 64-bit `dHash` (`compute_dhash_hex`) and `SHA-256`.

### Layer 3 — Zero-Touch PC $\rightarrow$ iPhone Media Pull (`MediaPullOrchestrator`)
* **Local Staging Server (`localhost:9914/stage/<device_id>/manifest.json`)**:
  * Stages 1 spun `.mp4` (`video_01_<phash>.mp4`) + 4 spun `.jpg` carousel slides (`slide_01_<phash>.jpg` .. `slide_04_<phash>.jpg`) + caption JSON per phone, and auto-purges staged files older than 24h.
  * Auto-exports a ready-to-import Apple iOS Shortcut plist (`output/media-stage/iMousePull.shortcut.plist`).
  * Before uploading, `SocialUploadOrchestrator` sends `fn_key="Home"` and jitter-taps the `iMousePull` Shortcut icon (`[350, 140, 445, 235]`) so the iPhone downloads its fresh media into the Camera Roll and copies the caption to the iOS clipboard.

### Layer 4 — Native Mobile Upload Orchestrator (`SocialUploadOrchestrator`)
* **All 14 Upload Formats Mapped in `500x1080` Coordinates**:
  * **Instagram**: `ig_reel`, `ig_carousel` (locks `4:5` aspect ratio on Slot 1 before tapping multi-select `[390, 515, 460, 570]`), `ig_post`, `ig_story` ([Sprout Social](https://www.google.com/search?q=https%3A%2F%2Fsproutsocial.com%2Finsights%2Finstagram-carousel%2F)).
  * **TikTok**: `tt_video`, `tt_photo_carousel` (enables `Multiple` `[360, 130, 470, 175]`), `tt_story` (`Post to Story` `[30, 970, 240, 1025]`), `tt_text` ([Metricool](https://www.google.com/search?q=https%3A%2F%2Fmetricool.com%2Fhow-to-post-on-tiktok%2F), [TikTok Support](https://www.google.com/search?q=https%3A%2F%2Fsupport.tiktok.com%2Fen%2Fusing-tiktok%2Fcreating-videos%2Fediting-tiktok-videos-and-photos), [Coinis](https://www.google.com/search?q=https%3A%2F%2Fcoinis.com%2Fhow-to%2Fpost-story-on-tiktok)).
  * **X (Twitter)**: `x_post`, `x_video` (includes Bézier drag on the right trim handle `[340, 840, 380, 905]` $\rightarrow$ `[455, 840, 485, 905]` so videos $>45\text{s}$ are not truncated), `x_thread` ([MicroPoster](https://www.google.com/search?q=https%3A%2F%2Fmicroposter.so%2Fblog%2Fhow-to-upload-videos-on-twitter)).
  * **YouTube**: `yt_short`, `yt_video` (selects `No, it's not made for kids` `[40, 580, 450, 645]`), `yt_community_post` ([YouTube Help](https://support.google.com/youtube/answer/57407?hl=en&co=GENIE.Platform%3DiOS), [YouTube Shorts Help](https://support.google.com/youtube/answer/12779649?hl=en-GB&co=GENIE.Platform%3DiOS), [YouTube Community Help](https://support.google.com/youtube/answer/7124474?hl=en&co=GENIE.Platform%3DiOS)).
* **Built-In Growth Enhancers**:
  * **iOS Spotlight App Launcher (`_launch_app_spotlight`)**: Pulls down Spotlight from Home, types the target app query, and taps the top hit (`[35, 225, 135, 310]`).
  * **In-App Trending Audio 3% Volume Mixer (`_attach_trending_audio_3pct`)**: Attaches a trending niche sound and drags the added-sound slider (`[320, 740]` $\rightarrow$ `[65, 740]`) to ~3% volume underneath original audio.
  * **Story Link & Poll Sticker Placer (`_attach_story_link_or_poll_sticker`)**: Opens the Story sticker tray (`[335, 68, 390, 115]`) and attaches a Link Sticker with the persona's `offer_url`.

### Layer 5 — 4-Phase Account Warmup & Cohort Scheduler (`AccountWarmupEngine`, `VlmComputerUseAdapter`)
* **4-Phase Trust Ramp (`WARMUP_PHASES`)**:
  * **Phase 1 (Days 1–3)**: `0 uploads` allowed; 35% quick-skip swipes (`1.4–3.6s`) + 65% full niche watches (`14–42s`) + likes/saves/sentence comments ([Ssemble](https://www.google.com/search?q=https%3A%2F%2Fwww.ssemble.com%2Fblog%2Faccount-warmup-guide-2026), [Followr.ai](https://www.google.com/search?q=https%3A%2F%2Ffollowr.ai%2Fblog%2Fhow-to-warm-up-your-social-media-account)).
  * **Phase 2 (Days 4–7)**: `1 upload/day` on TikTok/YT/X; Instagram waits until Day 5–6 ([ViralFeed](https://www.google.com/search?q=https%3A%2F%2Fviralfeed.ai%2Fguides%2Faccount-warmup)).
  * **Phase 3 (Days 8–14)**: `1–2 uploads/day` with a `3.5–7.5 hr` post-warmup cooldown buffer.
  * **Phase 4 (Day 15+)**: `2–4 uploads/day` + daily `5–10 min` trust maintenance session.
* **Pluggable VLM Screen Locator (`VlmComputerUseAdapter`)**:
  * Supports `ExecutionMode.API_BOUNDED_VISION` (deterministic `500x1080` bounding boxes) and `ExecutionMode.AI_COMPUTER_USE` (passes `500x1080` BMP bytes to an external VLM callback for dynamic bounding-box detection and contextual comment generation).

### Layer 6 — Conversion Funnel & Golden-Hour Loop (`ConversionFunnelEngine`)
* **Auto-Pinned CTA Comment (`post_and_pin_cta_comment`)**: Opens the comment drawer immediately after publishing, jitter-types `"Comment <KEYWORD> below and I will DM you the link"`, posts it, swipes left on the comment row, and taps `Pin` (`[310, 280, 385, 340]`).
* **Comment-to-DM Keyword Bot (`run_comment_to_dm_responder`)**: Checks the Activity/Inbox notifications tab, replies publicly to keyword commenters, opens their profile, taps `Message` (`[255, 365, 455, 408]`), and sends `offer_url`.
* **Cross-Rack Micro-Swarm Seeder (`run_cross_rack_micro_swarm`)**: Dispatches 1–2 peer phones from a different cohort to watch, like, save, and comment on a newly published post during the first 15 minutes.

### Layer 7 — Shadowban Guard & 3–5 Clip Zero-View Circuit Breaker (`ShadowbanGuardAndDiagnostics`)
* **3–5 Clip Zero-View Circuit Breaker (`evaluate_device_views`)**: Tracks view velocity across each phone's last 3 clips; if all 3 record $\le 5$ views after 24 hours, sets `paused_zero_view = 1` in SQLite and blocks `SocialUploadOrchestrator` from uploading on that device until warmup recovery completes ([Ssemble](https://www.google.com/search?q=https%3A%2F%2Fwww.ssemble.com%2Fblog%2Faccount-warmup-guide-2026)).
* **Popup & Captcha Watchdog (`inspect_popup`)**: Checks every BMP frame before clicking; auto-dismisses iOS `"Allow Paste"` / `"Not Now"` dialogs and immediately calls `/input/stop` on the phone if a Captcha or 2FA challenge is detected.

## 4. REST API Contract on `localhost:9914` (`imouse_farm_server.py`)

| Endpoint | Method | Request Body Example | Response / Action |
| :--- | :--- | :--- | :--- |
| `/` or `/dashboard` | `GET` | — | Serves the interactive 19-iPhone Command Center HTML UI |
| `/health` | `GET` | — | Returns `{"status": "ok", "port": 9914, "layersBuilt": 7, "personasCount": 19}` |
| `/api/farm/state` | `GET` | — | Returns live `9913` connection state, all 19 SQLite `personas`, and recent `content_slates` |
| `/api/farm/auto-create-and-deploy` | `POST` | `{"cohort": "all"}` or `{"cohort": "1"}` | Runs all 5 pipeline stages (`.mp4` + `4:5` `.jpg` render $\rightarrow$ `pHash` spin $\rightarrow$ `iMousePull` $\rightarrow$ upload $\rightarrow$ pinned CTA & hook cloning) |
| `/api/farm/upload-single` | `POST` | `{"device_id": "C24C", "platform": "instagram", "upload_format": "ig_reel"}` | Acquires lease on `9913` and runs `SocialUploadOrchestrator` for one phone/format |
| `/api/farm/warmup-wave` | `POST` | `{"cohort": "1"}` | Runs `AccountWarmupEngine` across the selected cohort and records timestamps in SQLite |
| `/api/farm/funnel-action` | `POST` | `{"device_id": "C24C", "action": "pin_cta" \| "comment_to_dm" \| "micro_swarm"}` | Runs the requested `ConversionFunnelEngine` workflow |
| `/api/farm/shadowban-scan` | `POST` | `{"device_id": "C24C", "recent_views": [420, 810, 650]}` | Evaluates view counts and updates the 3–5 clip zero-view circuit breaker in SQLite |
| `/api/farm/update-persona` | `POST` | `{"device_id": "C24C", "niche": "...", "cta_keyword": "SYSTEM"}` | Updates a phone's niche, voice, CTA keyword, offer URL, or warmup day in SQLite |
| `/stage/<id>/manifest.json` | `GET` | — | Returns staged `.mp4` and `.jpg` URLs + caption for the iPhone's `iMousePull` Shortcut |

## 5. Next Engineering Steps for the Next Session

1. **Plug In Live LLM & VideoGen / AI UGC API Credentials**:
   * Set `IMOUSE_LLM_API_KEY` (and your preferred model endpoint in `LlmCodeAnimationEngine`) for live LLM animation/carousel code generation.
   * Wire your specific AI UGC provider endpoint and polling schema (e.g., HeyGen, Creatify, Arcads, Runway, or Kling) into `VideoGenUgcApiClient.create_and_stage_ugc_video()`.
2. **Scoped Live Calibration on `C24C`**:
   * With `C24C` mirroring and idle in `/api/input/status`, run a single-step live test via `localhost:9914` (or `SocialUploadOrchestrator` with `settle_between_steps=True`) and fine-tune any app-version-specific bounding boxes in `UI_BOXES_500x1080`.
3. **Install the `iMousePull` iOS Shortcut Across the Rack**:
   * Import `output/media-stage/iMousePull.shortcut.plist` onto `C24C` first, place its icon at Home Screen slot `[350, 140, 445, 235]`, and point its URL to your Windows host LAN IP (`http://<LAN_IP>:9914/stage/<DEVICE_ID>/manifest.json`).

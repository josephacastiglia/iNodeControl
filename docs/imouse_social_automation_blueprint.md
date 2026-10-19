# iMouse 2.0 — 7-Layer 19-iPhone Marketing Farm & Social Automation Blueprint

## 1. System Overview & Architectural Boundaries

This blueprint defines the architecture, coordinate contracts, text-entry state machine, warmup rules, and C# console integration for the **iMouse 2.0 19-iPhone Marketing Farm & Social Automation System**.

- **Authoritative Kernel Endpoint**: `http://127.0.0.1:9913/api` (Vendor port `:9911` is strictly refused at both the Python client and C# console layers).
- **Marketing Farm Server Endpoint**: `http://127.0.0.1:9914` (`tools/imouse_farm_server.py`).
- **Frame Geometry & Status Bar Mask**: Uncompressed 24-bit `500x1080` portrait BMP (`GET /api/pic/screenshot?id=<pid>&binary=true`). The top `60px` (`y < 60`, `STATUS_BAR_PX = 60`) is masked during stillness verification (`wait_still`) and prohibited for click targets.
- **Per-Phone Lease Isolation**: Every automation session preflights `/api/kernel/status` (`input_leases_required == true`) and `/input/status`, acquires a dedicated lease token (`/input/acquire`, `lease_ms = 120000`), renews automatically when `lease_remaining_ms < 25000`, and guarantees `/input/release` in `finally`.
- **Emergency First-Click Stop**: `/input/stop` revokes all active lease tokens and halts ongoing sessions immediately without retries.

---

## 2. The 7-Layer Stack (`tools/imouse_social_automation.py`)

| Layer | Module / Class | Responsibility |
| :--- | :--- | :--- |
| **Layer 0** | `IMouseKernel`, `HumanizedTargetJitter`, `type_text_on_ios` | Lease-enforced `9913` RPC client, 2D truncated Gaussian non-repeating click sampler (48-tap ring buffer, 14% box inset), cubic Bézier drag generator, `wait_still()` BMP grid comparator, and 3-strategy iOS text entry. |
| **Layer 1** | `FarmDatabase`, `ContentFactoryEngine`, `LlmCodeAnimationEngine`, `VideoGenUgcApiClient` | Thread-safe SQLite store (`personas`, `content_slates`, `upload_logs`), Windows TrueType (`Segoe UI` / `Arial`) `1080x1350` (`4:5`) JPEG carousel renderer, procedural `9:16` `.mp4` animator, external VideoGen UGC API client (submit $\rightarrow$ poll $\rightarrow$ download $\rightarrow$ spin), and `clone_winning_hooks()` SQLite cloner. |
| **Layer 2** | `AntiDuplicateSpinEngine` | Per-phone anti-duplicate spinner applying `0.8%–1.8%` asymmetric crop + bicubic resize, brightness/contrast perturbation, Apple iPhone EXIF comment injection, and QuickTime ISO `free` + `UUID-APPLE-IOS-MOV` atom injection for `.mp4` files. |
| **Layer 3** | `MediaPullOrchestrator` | Auto-detects host LAN IPv4 (`detect_host_lan_url`), exports per-device `iMousePull.shortcut.plist` files pointing to `http://<lan-ip>:9914/stage/<device_id>/manifest.json`, and triggers the iOS Shortcut icon on the Home Screen. |
| **Layer 4** | `SocialUploadOrchestrator` | Executes all 14 native mobile upload formats across Instagram (`IG_REEL`, `IG_CAROUSEL` with `4:5` aspect-ratio lock on Slot 1, `IG_STORY`, `IG_FEED_POST`), TikTok (`TT_VIDEO`, `TT_PHOTO_CAROUSEL`, `TT_STORY`), X (`X_VIDEO` with 45s Bézier trim guard, `X_PHOTO`, `X_THREAD`, `X_TEXT`), and YouTube (`YT_SHORT`, `YT_VIDEO`, `YT_COMMUNITY_POST`) with `wait_still()` screen-transition settling. |
| **Layer 5** | `AccountWarmupEngine`, `BackgroundCohortScheduler`, `VlmComputerUseAdapter` | 4-phase account warmup engine (real on-screen comment typing + feed watch/swipe/like/save), 5-cohort staggered wave scheduler (`MAX_CONCURRENT_PHONES_PER_COHORT = 4`, `3.5h–7.5h` post-warmup upload cooldown), and BMP luminance/OCR adapter. |
| **Layer 6** | `ConversionFunnelEngine` | Golden-Hour Pinned CTA comment (45s post-publish), Comment-to-DM keyword lead responder (reads notification row, posts public reply, opens profile $\rightarrow$ Message $\rightarrow$ sends `offer_url` via `type_text_on_ios`), and Cross-Rack Peer Micro-Swarm (Search $\rightarrow$ `@<device_id>` $\rightarrow$ latest post $\rightarrow$ like, save & seed question). |
| **Layer 7** | `ShadowbanGuardAndDiagnostics` | Captures `500x1080` profile-grid BMP screenshots (`scan_device_profile_views`), extracts the 3 latest clip view counts, and trips the 3–5 Clip Zero-View Circuit Breaker (`paused_zero_view = 1`) when 3 consecutive clips record $\le 5$ views after 24h. |

---

## 3. 3-Strategy iOS Text Entry & 3-Plane `500x1080` Keyboard Map

Per `KEYBOARD-SPEC.md` and `IMOUSE-PROJECT-HANDOFF.md`, hardware HID `sendkey` is deferred on iOS due to Full Keyboard Access (FKA) intercepting `Space` / `Enter` / `Tab`. `type_text_on_ios()` supports three explicit strategies:

1. **`ON_SCREEN_KEYBOARD_JITTER` (Default — 100% FKA-Safe)**:
   - Stateful 3-plane (`ABC`, `123`, `#+=`) on-screen iOS portrait keyboard tapper in `500x1080` coordinates (`build_ios_qwerty_boxes()`):
     - **Plane 1 (`ABC`, `y = 695..942`)**: `q–p`, `a–l`, `shift`, `z–m`, `backspace`, `123` (`[6, 890, 115, 942]`), `space` (`[130, 890, 365, 942]`), `return` (`[375, 890, 492, 942]`).
     - **Plane 2 (`123`)**: `0–9` (`y = 695..748`), `-/:;()$&@"` (`y = 760..813`), `#+=` (`[6, 825, 66, 878]`), `.,?!'` (`y = 825..878`), `abc_mode` (`[6, 890, 115, 942]`).
     - **Plane 3 (`#+=`)**: `[]{}#%^*+=` (`y = 695..748`), `_\|~<>` (`y = 760..813`), `123_from_sym` (`[6, 825, 66, 878]`), `abc_mode` (`[6, 890, 115, 942]`).
   - Automatically transitions between planes to type hashtags (`#`), handles (`@`), URLs (`https://...`), numbers, and punctuation, returning to `ABC` plane on completion.
2. **`IOS_CLIPBOARD_PASTE` (Fast Caption / URL Paste)**:
   - Taps the focused text input twice to invoke the iOS context bar, taps `ios_paste_tooltip_btn` (`[180, 195, 310, 232]`), inspects the screenshot via `VlmComputerUseAdapter.inspect_popup()`, and automatically taps `popup_allow_paste_btn` (`[255, 595, 395, 640]`) if iOS 16+ prompts `"Allow Paste"`.
3. **`CHUNKED_SENDKEY` (Hardware HID — Opt-In Only)**:
   - Strictly enforces `KEYBOARD-SPEC.md`: printable ASCII `32..126` only, `200`-character cap, `12`-character chunks, and zero retries on uncertain delivery.

### Keyboard Dismissal Contract
Never send `Home` or `Tab` to dismiss the iOS keyboard. Always tap the neutral safe zone `keyboard_dismiss_safe` (`[410, 520, 485, 575]`).

---

## 4. Calibrating `500x1080` UI Bounding Boxes (`config/ui_boxes_500x1080.json`)

All default `500x1080` bounding boxes live in `UI_BOXES_500x1080` inside `tools/imouse_social_automation.py`.
Operators can override any bounding box without editing Python code by saving `[x_min, y_min, x_max, y_max, inner_margin_ratio]` entries to `config/ui_boxes_500x1080.json` or calling `POST /api/farm/calibrate-box`:

```json
{
  "ig_carousel_aspect_ratio_btn": [20, 515, 75, 570, 0.14],
  "ig_carousel_multi_select": [390, 515, 460, 570, 0.14],
  "keyboard_dismiss_safe": [410, 520, 485, 575, 0.14]
}
```

---

## 5. 4-Phase Account Warmup & Staggered Cohort Schedule

| Phase | Account Age | Max Uploads / Day | Daily Consumption & Trust Rules |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Days 1–3 | `0` (Strict Lock) | 12–18s watch dwell on niche videos, 35% skip swipe rate, 18% like rate, 1–2 genuine sentence comments/session. |
| **Phase 2** | Days 4–7 | `1` (IG waits til Day 5) | 10–16s watch dwell, 1–2 comments/session, mandatory `3.5h–7.5h` post-warmup cooldown before upload. |
| **Phase 3** | Days 8–14 | `2` | 8–15s watch dwell, 2–3 comments/session, `3.5h–7.5h` post-warmup cooldown. |
| **Phase 4** | Day 15+ | `4` | 7–14s watch dwell, 2–4 comments/session, full multi-platform deployment + Golden-Hour funnel. |

---

## 6. Native C# Console Integration (`src/iMouse.Console`)

- **`MainWindow.xaml` & `MainWindow.xaml.cs`**: Adds `FarmButton` (`Content="Farm"`) in `TopBar` next to `ActivityButton` so operators can launch `FarmAutomationWindow` in one click while preserving `TopBar` single-line geometry and `StopInputButton` hit-testing.
- **`FarmAutomationWindow.cs`**:
  - Shares the console's kernel endpoint (normalizing `:9911` defaults to `http://127.0.0.1:9913/api` and refusing to send farm traffic to vendor port `:9911`).
  - Walks up parent directories from `AppContext.BaseDirectory` (`ResolveFarmServerScriptPath`) so builds running from `output/...` locate `tools\imouse_farm_server.py` automatically.
  - Provides native WPF controls for 1-Click Auto-Create & Deploy, Cohort Warmup Wave, Single-Format Deploys, Comment-to-DM Responder, 0-View Profile Grid Scan, and Emergency `/input/stop`.

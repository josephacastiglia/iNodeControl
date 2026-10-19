# iMouse 2.0 — Marketing Farm & Social Automation Integration Handoff

**Date:** 2026-10-16  
**Target Repository:** `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-combined-candidate`  
**Current Active Build:** `output\gemini-farm-tab-r4\iMouse2.exe`  
**Desktop Shortcut:** `C:\Users\joey_\Desktop\iMouse 2.0 (Marketing Farm Test).lnk`  
**Target Hardware:** iPhone XR (`C24C`, MAC: `86:1D:4A:04:2F:F6`, Board: `C24CBFBD`)  
**Kernel Endpoint:** `http://127.0.0.1:9913/api`  
**Farm Server Endpoint:** `http://127.0.0.1:9914` (PID: 55592)

---

## 1. Executive Summary

This session accomplished the full transition from a separate browser-based mock dashboard (`http://localhost:9914`) into a fully integrated, native **WPF Console Test Tab** within `iMouse2.exe`. All protected release and candidate invariants were strictly preserved:
- The operator's installed release remains byte-identical and untouched.
- All candidate builds compile into isolated folders (`output\gemini-farm-tab-r4\`).
- Candidate settings and logs use `--data-dir` isolation to prevent overwriting `%APPDATA%\iMouse2`.
- Hardware blast radius is strictly scoped to test phone `C24C`, maintaining refusal guards on `C241` ("Phone in hand").

---

## 2. Key Architecture & Deliverables Built

### A. Native WPF Test Tab (`src/iMouse.Console/`)
1. **Isolated View Switcher:** Added `Rack View` and `Marketing Farm (Test Tab)` in `MainWindow.xaml` and `MainWindow.FarmTab.cs`. Clicking between views smoothly toggles visibility with zero connection disruption.
2. **Native Live AirPlay Stream:** Replaced static wireframe diagrams with direct binding to `_live.Source` (`FarmPhoneImage`). Displays the physical iPhone screen in real-time at native 500×1080 resolution.
3. **Interactive Click-to-Touch:** Mouse clicks on the live phone image automatically normalize to 500×1080 coordinates, apply 2D Gaussian jitter and approach waypoints, execute physical taps via Kernel `:9913`, and render an animated visual touch marker.
4. **Clean Code & Test Invariants:** Zero test-helper churn in `MainWindow.xaml.cs`. Core `--self-test` passes cleanly with return code 0.

### B. Farm Backend Server (`tools/imouse_farm_server.py`)
1. **Security Hardening:** Restricted CORS/Origin headers strictly to `localhost` / `127.0.0.1` / `::1`. Verified untrusted cross-origin requests (`https://malicious-site.com`) are rejected with `HTTP 403 Forbidden`.
2. **Route Alignment:**
   - Added `/api/farm/upload-single` and alias `/api/farm/single-upload`.
   - Added `/api/farm/funnel-action` and alias `/api/farm/funnel-suite`.
   - Implemented `/api/farm/emergency-stop` to revoke kernel lease tokens.
   - Added `device_id`, `clips`, and `time_scale` controls to `/api/farm/warmup-wave`.
3. **Media Staging:** Verified generation of 4:5 aspect ratio carousels (`540×675`), video rendering, manifests (`/stage/C24C/manifest.json`), and iOS Shortcut synchronization (`iMousePull.shortcut.plist`).

---

## 3. Live Hardware Verification Evidence (`C24C`)

All actions below were executed and visually verified on physical iPhone XR hardware (`C24C`) via live frame captures:

| Action / Test | Result | Physical Evidence & Measured Data |
| :--- | :---: | :--- |
| **Real AirPlay Stream** | **PASS** | Continuous 500×1080 BMP stream displaying live in the Console tab. |
| **Physical Touch Delivery** | **PASS** | Click at `(250, 539)` successfully launched the Mail app located at that icon. |
| **Native Spotlight Flow** | **PASS** | Swipe down opened Spotlight Search; USB-HID typed `"Notes"`; `Enter` launched Apple Notes. |
| **Automated Warmup Engine** | **PASS** | `AccountWarmupEngine.run_warmup_session` executed live on TikTok: <br>• Before video: `green_eye_girl_nc` (fishing rod) <br>• After video: `Biscuit Johnson` (car clip) <br>• Confirmed video advanced via engine swipe; recorded in `imouse_farm.db`. |
| **Lease & Safety Lifecycle** | **PASS** | Identified single-controller exclusivity in Kernel `:9913`. Cleaned stale locks; verified `owned: false, stopped: false` recovery cycle. |
| **Desktop Shortcut Launch** | **PASS** | Created desktop shortcut `iMouse 2.0 (Marketing Farm Test)` targeting `r4` with `--data-dir` isolation. |

---

## 4. Current State & Known Invariants

- **Kernel `:9913`:** Up and healthy. Phone `C24C` is mirroring live at 500×1080.
- **Farm Server `:9914`:** Running live under PID 55592 with CORS hardening and corrected routes.
- **Lease Exclusivity Invariant:** Kernel `:9913` enforces that only one client may hold a phone lease at a time. The WPF Console acquires and auto-renews this lease while running. Any external Python automation script must either run while the Console is idle, or receive a clean lease handover (`/input/release`) from the Console.

---

## 5. Next Steps for Full Automation

1. **Multi-Step Upload Orchestrator:** Test `execute_upload` end-to-end on a test account for TikTok / Instagram carousel posting.
2. **Comment-to-DM Funnel:** Test automated keyword detection and direct message dispatch.
3. **Tab Lease Handover:** Wire the WPF Console buttons to release the local lease before delegating long background tasks to the Python server, restoring it upon completion.

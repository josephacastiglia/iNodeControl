# iPhone build: confirmed scope

The user confirmed that version 2.0 is a Windows application for controlling iPhones. For the current step, preserve the existing build and establish its capabilities; functional changes remain for the next step.

## Existing build

The `build/` directory contains the matching iMouse XP Windows installation. Its console, Windows service, display helper, AirPlay helper, hotkey definitions, and phone configuration align with the site's iPhone product documentation. The native build has already been copied and hashed; it has not been recompiled, changed, or installed as another service.

The site distinguishes the Android Panda product from iMouse XP for iPhones. Its iPhone architecture uses a Windows console and background service, dedicated control hardware, and phone screen mirroring. The documented setup uses iPhone accessibility options and a shared LAN with the PC. Source: [iMouse XP installation](https://doc.some3c.com/iphone-farm-setup/imouse-xp-new-version), [iPhone setup](https://doc.some3c.com/iphone-farm-setup/iphone-farm-settings).

## Verified integration opportunity

### User-provided hardware reference

The user supplied two photos showing multiple cabled control boards with illuminated indicators inside a phone rack, plus its enclosure, cooling, power supply, and external connections. The user confirmed the connection sequence is phone to hardware to PC.

- Close-up: `C:/Users/joey_/Downloads/photo_2026-09-07_21-51-20.jpg`
- Enclosure: `C:/Users/joey_/Downloads/photo_2026-09-07_21-51-15.jpg`

These images establish the physical deployment context. They do not identify the exact board model, firmware, USB protocol, or meaning of indicator colors. The initial software integration should retain the existing boards and service, keeping each phone's identity and hardware binding explicit. Screen mirroring is a separate documented path over the local network; the photos alone do not establish its transport.

The XP interface supports HTTP and WebSocket on port 9911, with `/api` as the base path. The documentation also provides the `imouse-py` client. A new Windows console can use these interfaces while retaining the installed engine and hardware. This narrows the earlier source-code limitation: the original source is still needed to rebuild or directly modify its binaries, but it is not necessarily needed to implement a replacement console through the documented API. Sources: [XP API](https://doc.some3c.com/iphone-farm-setup/xp-api-documentation), [Python client](https://doc.some3c.com/iphone-farm-setup/xp-api-documentation/python-library).

On September 7, 2026, a single read-only request to `http://127.0.0.1:9911/api/device/get` returned:

- Response status: 200.
- Operation result code: 0.
- Device records: 12.
- Models represented: iPhone XR and iPhone 12 Pro.

This confirms that the currently installed local service exposes the documented device-list interface. It does not establish that all 12 devices are online, that the copied service runs independently, or that every documented API works in this version. No phone inputs, screen-cast connections, account changes, or service restarts were issued.

## Feature coverage for a future editable console

| Area | Documented capabilities | Saved reference |
| --- | --- | --- |
| Device workspace | Device lists, groups, sorting, mirroring configuration, connect/disconnect, mouse calibration | `site-reference/xp-api-documentation--equipment-related.md` |
| Hardware and settings | Hardware list, supported models, engine configuration | `site-reference/xp-api-documentation--configuration-related.md` |
| Input | Click, swipe, press/release, movement, wheel, keyboard input | `site-reference/xp-api-documentation--keyboard-and-mouse.md` |
| Image tools | Screenshots, image matching, OCR, text/color search | `site-reference/xp-api-documentation--picture-text-recognition.md` |
| Phone shortcuts | Clipboard, files/media, URL opening, device settings | `site-reference/xp-api-documentation--shortcuts.md` |
| Live status | Device/USB changes, groups, rotation, logs, errors, settings events | `site-reference/xp-api-documentation--callback.md` |
| Account integration | Existing sign-in/session and subaccount interfaces | `site-reference/xp-api-documentation--user-related.md` |

Each saved page's public URL and retrieval time is recorded in `site-reference/sources.json`.

## Boundaries for the next implementation step

Preserve the copied installation as the original reference and create new editable application source separately. Use the existing installed service initially, with its current hardware and account configuration. Keep app preferences distinct from the original installation.

A replacement display requires additional investigation: the docs establish mirroring controls and screenshot retrieval, but neither is proof of a directly embeddable live video stream. Confirm the supported display/video integration before promising full original-console parity. Validate selected commands and reconnect behavior against the actual hardware during implementation.

The supplied installation page describes downloading an installer but its text does not expose a direct installer or source-project download link. No newer package was downloaded. The delivered build remains the verified local installation copy, with the documented API now identified for future development.

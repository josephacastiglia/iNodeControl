# iMouse 2.0 — Test build 1

## Open the app

1. Leave your existing iMouse XP service running. Use the original console for account login, hardware binding, and phone accessibility setup.
2. Double-click `iMouse2.exe` in the extracted package (or in this project's `release/iMouse2/` folder). Keep the adjacent DLL and runtime configuration file together with the executable.
3. The app connects automatically to `http://127.0.0.1:9911`. The address can be changed if your service is elsewhere.
4. Select a phone. If it is offline, start Screen Mirroring on the iPhone and select the iMouseXP receiver. The **Start casting** button also requests casting through the existing service.
5. When the phone reports online, its preview begins. Test Home and the swipe buttons on one phone, then type a short value into a field you have focused on the phone.

The .NET 8 Windows Desktop Runtime (x64) is required and is already installed on this PC. No new service installation is needed. Closing this console leaves your original service and mirroring sessions running.

## Included

- Native Windows interface with device status, model, OS, group, network address, and board binding information.
- Device refresh every 5 seconds, search, group filtering, and online-only filtering.
- Single-phone controls by default. Check phones and enable **Apply buttons to checked phones** for batch operations. The target count includes checked phones hidden by filters; **Clear checks** clears all groups.
- Start/stop casting, Home, Back, App Switcher, Control Center, directional swipes, Enter, Backspace, Select All, phone-side Paste, and mouse reset.
- Explicit ASCII text sending. Paste on phone uses the phone's current clipboard; it does not copy the PC clipboard.
- Screenshot-based preview at up to 1, 2, or 5 frames per second, depending on the service and network. Only the selected phone is polled for images. Minimized windows pause image polling.
- Optional click/drag control on the preview. Pointer gestures always target the selected phone, independently of batch buttons. Enable **Click / drag on preview to control** to use it. A preview older than 10 seconds cannot send pointer gestures; refresh it first.
- Save the current preview as PNG and export a diagnostic report. Export does not include typed text, screenshots, or a full device inventory.
- Connection retries and explicit operation error reporting. Phone commands are not automatically retried after an error or timeout.

## Test sequence

1. Confirm the device count and names match the original console.
2. Mirror one phone and confirm the preview matches it.
3. Test Home and a single swipe. A successful service response still needs visual confirmation on the phone.
4. Enable preview pointer control and tap a known position. Check alignment; if it is offset, confirm mouse parameters and accessibility settings in the original console. Landscape mapping is implemented but has not been verified on physical hardware.
5. Type into a harmless text field. The console sends the text exactly once and does not press Enter automatically.
6. After single-phone controls work, check two phones, enable batch mode, and test Home. Disable batch mode afterwards if you want to return to single-phone operation.
7. Use **Export diagnostics** if something fails, and describe which action failed and what happened on the phone.

## Current limits

This build reuses the existing service, hardware, and account. It does not replace board firmware or the original engine. Hardware binding, account management, new group creation, calibration, OCR, file/shortcut transfer, macro recording, and native full-rate video display remain in the original application.

The preview is a sequence of screenshots, not a full-rate AirPlay video stream. Its refresh settings are maximum polling rates, not guaranteed frame rates.

The live read-only test returned 12 device records and 0 online phones. Consequently real screen decoding, pointer alignment, Home/navigation behavior, and text entry on physical phones remain for your test. Command routing and error states were tested through a simulated service; no input commands were sent to your phones during build verification.

## Developer verification

The executable accepts `--self-test`, `--ui-test`, and `--smoke-test`. Results go to its adjacent `qa/` folder. The first two use simulated transport. The live smoke test reads the device list and can read one preview if its selected phone is online; it sends no phone input commands.

Run `build-console.ps1` with PowerShell 7 to rebuild using the bundled compiler. The script includes the XAML resources and produces a Windows launcher plus the .NET application. It does not modify `C:\iMouseXP` or register a service. A normal .NET SDK build can instead use `src/iMouse.Console/iMouse.Console.csproj`.

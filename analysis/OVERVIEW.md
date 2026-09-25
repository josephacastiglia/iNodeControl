# Initial software analysis

## Scope and evidence

Static inspection of the copied installation: file inventory, PE headers, executable version resources, batch scripts, JSON configuration, and interface translations. Features below are indicated by these artifacts; they have not been verified through interactive operation. No source decompilation, installation, service changes, or network requests were performed.

## Components

| Component | Observed metadata | Likely responsibility |
| --- | --- | --- |
| `IMConsole.exe` | Native x86, version 2026.7.8.1294 | Main console, device list, groups, settings, and hotkey configuration |
| `IMService.exe` | Native x86, version 2026.7.4.169 | Background coordination; bundled scripts register/start/stop `iMouseService` |
| `DisplayCore.exe` | Native x86, version 2026.7.8.736 | Device display windows and interaction tools |
| `x64/AirplayMirroring.exe` | Native x64, version 1.6.6.11 | AirPlay mirroring helper |
| `mDNSResponder.exe`, `dnssd.dll` | Executable identifies itself as Bonjour(iMouse) | LAN service discovery |
| `iMouseKeyboard.dll`, `MouseKeyItem.dll` | Bundled native libraries | Input/control support, inferred from names |
| `x64/avcodec*`, `avutil*`, `swscale*`, `swresample*`, `SDL2.dll` | Bundled media libraries | Media decoding, conversion, audio, and rendering support |
| CUDA/NVIDIA libraries | Present in root and x64 directories | Optional GPU processing, consistent with the hardware acceleration setting |

PE inspection shows no CLR header in the six executables. The main applications are native Windows binaries. The exact original language, compiler, internal interfaces, and dependency graph are not established by this inspection. Window/control names in settings suggest a Delphi/VCL-style UI, but this is an inference rather than a confirmed source stack.

## Feature surface indicated by settings and UI labels

- Device discovery, binding, online/offline status, naming, groups, and selection of multiple devices.
- Screen mirroring with audio, frame-rate and image-size settings, optional hardware acceleration, and connection retries.
- Mouse and keyboard control, customizable shortcuts, phone navigation, clipboard transfer, screenshots, and media controls.
- Individual display windows, grouped device operations, layout preferences, and persisted window positions.
- Automation tools including clicks/swipes, text entry, color searches, OCR/text searches, and phone shortcut integration.
- Account sign-in, authorization/license status, and hardware binding appear in the UI text. Their actual server dependencies remain unverified.
- Chinese, English, and Russian localization data.

## Configuration map

| File | Purpose suggested by contents |
| --- | --- |
| `IMService.json` | Mirroring options, general behavior, and saved account fields |
| `UserConfig.json` | Window geometry, device-list columns, group tabs, and UI selections |
| `DeviceList.json` | Persisted device information |
| `deviceModel.json`, `model.txt` | Device model reference data |
| `HotkeyConfig.json` | User-configurable mappings for 33 actions |
| `HotkeysList.json` | Phone input action definitions |
| `languages.json` | Interface translation dictionaries; some keys differ only by letter casing |
| `Display/`, `ScreenPoint.json`, `RestartPoint.json` | Display and stored coordinate settings |
| `log/` | Runtime debug/error history |

## Implications for 2.0

The immediate request is complete: a separate, unchanged copy of the installed build is available as a reference. Source-level edits and a reproducible rebuild require the original source project or a new implementation. Neither is present yet.

Before implementing changes, establish the desired screens and behavior, then determine how much of the device/service protocol can be reused through documented interfaces. The installed folder alone does not establish that it can run independently: Windows service registration, external device hardware, account services, registry state, and other machine dependencies may matter.

The bundled `install_kernel.bat` installs and starts the globally named `iMouseService`; the uninstall script also terminates console/display processes by executable name. Those scripts are preserved as reference and were not executed. A future independently runnable 2.0 needs its own service identity and settings locations if it will coexist with the original.

## Verification

All 624 files were copied. SHA-256 comparisons matched 622 files, including every non-log file. `log/IMConsole_DEBUG_20260907.log` and `log/IMService_DEBUG_20260907.log` differed because the original application was writing to them during the copy/verification interval. The saved manifest records the exact copied hashes and source hashes observed during verification. This is a live file copy, not an atomic system snapshot.

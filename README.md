# iMouse 2.0 — Windows iPhone console

This repository contains the editable console and kernel source, the AirPlay receiver source,
build and test scripts, and project findings. Installed executables, downloaded toolchains,
screen captures, USB traces, and local device tokens stay on the development PC. A fresh
clone needs the build dependencies and a new build before the launch scripts can run.

**Current independent AirPlay app:** see [Open this app](OPEN-THIS-APP.md).
**Definition of finished:** see [Completion criteria](FINISH-CRITERIA.md).
The build and launch notes below describe earlier project stages.

## Native app: `release/iMouse2/iMouse2.exe`

Rebuilt on 8 September 2026 with the same live pipeline as the browser console: raw BMP frames,
30 fps live view, hover crosshair with a tap-coordinate readout, and separate control/video status
per phone. The .NET 8 SDK was installed to make this possible.

Rebuild after any source change:

```bash
dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o release/iMouse2
```

Test suites, all passing: `iMouse2.exe --self-test` (40 checks, mock transport),
`--ui-test` (17 interaction checks, mock transport), `--smoke-test` (live, read-only).
Results land in `qa/` next to the executable.

**Test build 1 is implemented and compiled.** Launch `release/iMouse2/iMouse2.exe` on this PC. The editable WPF/C# source is in `src/iMouse.Console/`.

This new console connects to the existing iMouse XP service. It provides device search/group filtering, single and explicit batch controls, screen-cast commands, screenshot-based previews, mouse click/drag, navigation, and ASCII text entry. It is an initial working console, not full feature parity with the original application.

Validation: 26 transport/coordinate checks, 17 interface interaction checks, rendered UI inspection, and a read-only live service smoke test. At the live check, the service returned 12 saved phones and 0 online. Hardware inputs and real phone previews still need the user's online-device test.

## Preserved original installation

Copied from `C:\iMouseXP` on September 7, 2026. The original installation was left unchanged.

Confirmed target: **Windows application for controlling iPhones**, as specified by the user. The copied iMouse XP build is the matching product. See `analysis/IPHONE-BUILD.md` for the documentation findings and successful read-only API check. The original service exposes documented interfaces that can support a new editable console without replacing the control engine.

- `build/`: copied installed application, including DLLs, settings, logs, and empty directories.
- `analysis/HARDWARE.md`: live hardware analysis - board identification, USB HID protocol shape, hub/slot map, and the two-channel control-vs-video model.
- `analysis/OVERVIEW.md`: initial component and feature analysis.
- `analysis/IPHONE-BUILD.md`: confirmed iPhone scope, integration path, and validation limits.
- `analysis/site-reference/`: 11 saved iPhone setup/API pages and their source URLs.
- `analysis/file-manifest.json`: SHA-256 hashes of every copied file and comparison with the source.
- `analysis/verification.json`: copy verification totals and differences.
- `analysis/binary-inventory.json`: executable/DLL architecture and version metadata.
- `analysis/ui-labels-english.json`: English interface text extracted for future feature mapping.
- `analysis/copy.log`: Robocopy report.

The copy contains 624 files totaling 311,074,050 bytes (about 297 MiB). At verification, 622 files matched the source byte for byte. Two active debug logs continued changing in the running installation; their copied snapshots are preserved. All copied non-log files matched.

The `build/` subdirectory is the original installed binary snapshot. No original source files, solution/project files, or build instructions were present. Its application behavior has not been changed, and the copied executables and service scripts have not been run. Runtime independence of that original copy has not been tested. New application source and releases live separately, as described above.

The build includes the original account settings, device data, and logs. Keep this local reference separate from any future public source repository; `.gitignore` excludes it by default.

# Bus Hound installation — post-reboot update

The user rebooted; bhound10 was confirmed RUNNING. The authorized single-port test is concluded and Automatic mode restored. See LIVE-INDICATOR-TEST.md. The following notes preserve the earlier pre-reboot state.

User explicitly approved installation on 23 September 2026 after being told it installs a system driver and may require a restart. Automatic reboot was explicitly suppressed.

- Installed the previously signature-verified official Bus Hound 8.0 MSI using `/qn /norestart REBOOT=ReallySuppress`.
- Windows Installer returned **3010**: installation succeeded, restart required.
- Installed files are in `C:\Program Files\Bus Hound`: bushound.exe, buscmdr.exe, bhound10.sys, dinstall.exe, help.rtf.
- `sc.exe query bhound10` reports **STOPPED**, exit 1077 (no start attempt since boot).
- C24C's current hub still shows the Microsoft USBHUB3 stack without the new filter.
- Post-install enumeration: **19 control boards present, 19 Started**. This does not independently verify phone input or mirroring.
- No reboot, USB reset, LED control transfer, phone input, or app-code change was performed.
- Full MSI log: `install.log`.

## Resume after the user restarts Windows

1. Query bhound10 status and fresh hub/board PnP relationships. Do not reuse old path/port assumptions after restart.
2. Open Bus Hound and inspect the target hub. Use the computer-use skill for native UI interaction. Check installed `help.rtf` for command support; do not invent CLI arguments or driver IOCTLs.
3. Follow `SINGLE-PORT-TEST.md`: read port status, verify Automatic mode, coordinate an observer, test Off briefly on C24C's verified hub port, and restore Automatic.
4. Check board connection and phone input/video afterward. A USB command's success alone does not prove which physical LEDs changed.
5. Do not expose a Rack lights control in iMouse until a supported app transport and actual physical effect have been verified.

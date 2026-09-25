# UxPlay disconnect/reconnect test — 14 September 2026

Authorized target: iPhone XR 86:1D:4A:04:2F:F6, board C24C.
Console process 30320, window 3934502, remained open throughout this test.

## Disconnect verified

- Before stopping UxPlay, the console visibly showed live Home Screen video,
  Mirroring, Control ready, and Cast iMouse2-C24C. Mirror-to-all was unchecked.
- Stopped only verified receiver process 38772. Kernel 38720 kept running.
- Kernel immediately reported live:false; screenshot endpoint returned JSON
  code 25 (No live frame), not a stale BMP.
- The same console cleared its picture and showed Not mirroring, Online 0,
  with Control ready retained. It remained connected to the kernel.
- Evidence: receiver-disconnect-status.json and tool-captured console states.

## Recovery verified

The receiver is launched only at kernel startup; it is not automatically
supervised/restarted. Restarted the single-phone test kernel to bring it back:
new kernel process 37900, child UxPlay 12548. This recovery also briefly
interrupted the HTTP API. The same console remained open and reconnected.

Receiver initialized normally, name iMouse2-C24C, live:false, frames:0.
After the user recast the phone, the API reported live:true and 363 frames,
then continued increasing. Device identity remained C24C / C24CBFBD.
The same console process/window restored its live picture and Mirroring state
without relaunching the console or clicking Connect. A Search click in the
focused console opened Spotlight, visually verified in that same window.
The first click while the window was inactive had no visible effect; after
explicit activation, the next click worked. This does not establish first-click
reliability for an inactive window.

Evidence: receiver-reconnected-status.json, reconnect-console-click.bmp, and
tool-captured console states. The manual restart/recast recovery test passed
for this one phone with the console kept open. It does not establish automatic
receiver restart or automatic iPhone recasting.

No vendor service or other board was stopped or controlled. Firewall rules
were not modified. During this test the API `receiver_pid` field retained the
old PID while its child was dead; `live:false` was accurate. Source now reports
`receiver_pid` 0 once that child has exited (kernel self-test covers a finished
process). That change is not in the running `iMouse2-kernel-verified` instance.
Automatic receiver restart is still not implemented.

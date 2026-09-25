# UxPlay automatic restart test — 14 September 2026

Authorized target: iPhone XR `86:1D:4A:04:2F:F6`, board C24C / C24CBFBD.
Kernel 39096 and console 16672 stayed open for the crash and recovery.
Original UxPlay before the kill was 32960.

## Crash

Stopped only UxPlay 32960. Kernel and console PIDs did not change.

Within ~2 s the kernel reported `receiver_state=restarting`, `receiver_pid=0`,
`live=false`, `receiver_restarts=1`. Screenshot returned JSON code 25
(`No live frame…`), not a stale BMP. Console overlay: **Receiver restarting**,
with a recast hint for `iMouse2-C24C`.

New UxPlay PID **13412** then came up; state became `offline` (helper running,
no iOS session). Evidence: `receiver-autorestart-status.json`,
`receiver-autorestart-noframe.json`, `receiver-autorestart-console.png`,
`receiver-autorestart-log.txt`.

## Recast and input

Manual recast to `iMouse2-C24C` (192.168.4.28 / 2F:F6) restored `live:true`
on the same kernel, console, and UxPlay 13412 (`receiver_restarts=1`).

| Check | Result | Evidence |
|---|---|---|
| Live video | Home Screen 500×1080 | `post-crash-live.bmp` |
| Home | Home Screen | `post-crash-home.bmp` |
| One Search click (250,900) | Spotlight | `post-crash-search.bmp` |
| 3× Home + Search | Spotlight each time | `post-crash-repeat-1/2/3.bmp` |
| Frames still advancing | 3423 → 3865 | kernel status |
| Console | Mirroring, Control ready, Cast iMouse2-C24C | `post-crash-console.png` |

PIDs after recovery: kernel 39096, console 16672, UxPlay 13412.

## Remaining manual step

iOS will not recast by itself. After an automatic UxPlay restart the operator
must pick **iMouse2-C24C** in Control Centre → Screen Mirroring.

Not tested live: hitting the 5-restart cap, hours-long freeze, landscape, other boards.
No vendor service was stopped. Firewall rules were not changed.

# Multi-phone bring-up, 20 Oct 2026

One private kernel (port 9916) with four receivers: C24C, C214, 724E, F215. C241 is excluded.
No backend and no farm automation run here. The only phone input sent was move-only pointer
squares (`pointer_identify.py`).

## Box slots

The operator numbered the 20-phone box from 1 (far left) to 20 (far right). See `phone-slots.json`.

| Slot | Board | Receiver | Proof |
|---|---|---|---|
| 16 | F215 | iMouse2-F215 | operator; receiver log shows an iPhone XR, not the C241 phone. Board pairing not yet proven: F215 input is not enabled until its phone is bound. |
| 17 | 724E | iMouse2-724E | locked receiver accepted only its saved phone; pointer square moved its own mirror only; operator confirmed |
| 18 | C24C | iMouse2-C24C | same |
| 20 | C214 | iMouse2-C214 | same |

The September pointer calibrations are off: commanded moves landed short. Recalibrate before any tap.

## One-at-a-time connection (option 1)

Every phone on the Wi-Fi lists every advertised receiver, so phones being set up saw names
meant for other phones. The kernel now accepts `--hold-receivers <boards>`. Held receivers are
not started, so no phone can list them. `POST {"fun":"/device/airplay/connect","data":{"pid":"C214"}}`
starts one held receiver; it then stays advertised until the kernel stops. `/kernel/status`
reports a held receiver's state as `held`.

```powershell
.\Start-Multiphone.ps1 -Stage held      # every receiver held
.\Release-Receiver.ps1 -Board C24C      # advertise one; connect that phone; repeat per board
.\Stop-Multiphone.ps1 -Stage held       # Ctrl+C stop, then withdraw every name
```

`prepare_multiphone.py --held` writes `held/preparation.json` and its own run folder, pinned to
the rebuilt kernel in `output/multiphone-kernel-20261020` (DLL sha256 `2350ca22…`). The live
Reel/TikTok/X windows still pin the 18 Oct kernel and are unaffected.

Run on 20 Oct: C24C 21:27, C214 21:29, 724E 21:29, F215 21:40, each picked from a list with one
new name. Releases are logged in `held/releases.jsonl`.

## Stale names after a restart

The first held start still showed all four names in a Bonjour browse. Cause: the kernel ends each
UxPlay receiver by killing it, and UxPlay's built-in mDNS responder (`lib/mdnsd`) only sends its
goodbye on a clean unregister. Listeners then keep the names for the record TTL
(`MDNSD_TTL_SERVICE`, 4500 s, 75 minutes). `tools/mdns_goodbye.py` sends that goodbye
(the `_airplay._tcp` and `_raop._tcp` PTR records with TTL 0, from port 5353, on every IPv4
interface). It refuses any receiver its kernel reports running. This PC's Bonjour removed the
three stale names within a second. `Stop-Multiphone.ps1` now sends it after every stop.

The same kill-without-goodbye likely explains earlier cases where a restarted receiver was
not relisted by a phone until a replug.

## Mistake recorded

On the earlier live windows (same day), `archive_attempt.py` was run in parallel with
`Stop-ReelWindow.ps1`. Stop failed ("Private process identity changed: backend") because the
processes had already exited. Afterwards no process or listener remained and the 25 protected
files were unchanged; the records are archived as `reel-prep8-unused`. Archive only after Stop
has finished.

## Not committed

Kernel logs, `receivers-ready.json`, and the `identify/` frames and records contain phone device
IDs and home-screen captures. They are kept in the private evidence archive.

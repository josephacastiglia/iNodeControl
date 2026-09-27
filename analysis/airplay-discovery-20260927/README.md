# Receivers not listed in Screen Mirroring after a restart: 27 Sep 2026

**Status: investigated; cause not yet demonstrated; nothing changed.** The release kernel, receivers, network, firewall and phone settings are unchanged. Both phones were mirroring through the release again at 18:58:50 (C24C) and 18:58:53 (C241).

## Ruled out

- **The PC not advertising on the LAN.** `tools/airplay-diagnostics/mdns_probe.py` sends one standard mDNS query out of Ethernet (192.168.4.26) and lists answers. The PC answered `_airplay._tcp` and `_raop._tcp` with both receivers (`JoeyDesktop.local`, 192.168.4.26, ports 7111 and 7121), repeatedly, including with the unicast-reply bit that an iPhone's first query carries. The probe also heard other LAN devices (router, Chromecasts, speakers), so it works. One first probe got no answer; three repeats did.
- **The receivers being unreachable.** Two other rack phones reached both receivers at 18:48–18:49 (`8A:23:B5:71:35:8D` from 192.168.4.27; `3A:DC:15:FB:DD:EC` from 192.168.4.65). The allow list refused them, as designed.
- **A changing receiver identity.** UxPlay 1.74 without `-key` derives its Ed25519 key from the device ID (`lib/crypto.c`, `ed25519_key_generate`; README 1.68 notes). The kernel fixes the device ID with `-m`, so the TXT `pk` is the same after every restart. The TXT `pi` is UxPlay's fixed constant for every instance.

## Observed pattern

At each window, the kernel stop ended the receivers while C24C and C241 were mirroring to them. The kernel ends uxplay with `Process.Kill(entireProcessTree)` in `AirplayProcess.Dispose`. uxplay on Windows has a Ctrl+C handler (`SetConsoleCtrlHandler`) that stops its server and unregisters from DNS-SD; the kill bypasses it.

| Receivers killed | New receivers up | C24C listed and connected | C241 listed and connected |
|---|---|---|---|
| 18:26:11 (window 1) | test 18:26:22; release 18:29:22 | 18:29:55 (release) | 18:32:38 (release) |
| 18:35:14 (window 2) | test 18:35:23; release 18:45:46 | 18:58:50 (release) | 18:58:53 (release) |

- Phones that had never connected listed the release receivers within about 3 minutes of the 18:45 restart.
- When C24C (192.168.4.57) and C241 (192.168.4.56) finally connected, `mdns_listen.py` recorded each asking directly for its own receiver (a QU query for `02494D32C24C@iMouse2-C24C._raop._tcp.local`, and likewise for C241).

## Leading hypothesis (not demonstrated)

A phone whose active session was severed by a killed receiver keeps stale state for that receiver identity, and hides it for minutes after it reappears.

**Candidate fix:** stop receivers cleanly. Send uxplay Ctrl+C and wait before any kill, so sessions are torn down and the DNS-SD records withdrawn. It is not implemented; it would change the kernel and need a release deployment.

## Proposed confirming test (needs approval and a window)

Restart one receiver at a time; the kernel's supervisor relaunches an exited receiver, so the kernel keeps running.
- **Control:** on C24C, tap Stop Mirroring, then its receiver is restarted. Measure the time until C24C lists and connects.
- **Test:** C241 keeps mirroring while its receiver is restarted. Measure the same.
- Record with `mdns_listen.py` throughout.

A fast control and a slow test would support the hypothesis. The clean-shutdown change would then be verified the same way before any release change.

## Evidence

- `iMouseXP-2.0-evidence-archive/20260927-home-window/`: `mdns-listen-1.txt`, `window2-release-reconnect.txt`, and the user's photos.
- Receiver logs in `analysis/two-phone-config/receiver-*.log` in the main checkout. They are read only, not copied.

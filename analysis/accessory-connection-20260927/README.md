# C24C cable replug at about 20:40, 27 Sep 2026: read-only review

This review follows the graceful receiver trial, which is closed and recorded in commit 3c1f035 (`analysis/airplay-discovery-20260927/README.md`).

Nothing was unplugged, restarted or changed for this review. The sources were:
- Windows PnP device properties (last arrival and removal times for all 587 device nodes);
- Windows event logs from 20:30 to 20:46;
- the kernel's read-only endpoints;
- the receiver logs;
- the three passive mDNS captures;
- the webcam frames.

## What the cable is, from existing documentation

- Rack path (`analysis/HARDWARE.md`, `HANDOFF.md`): PC → USB hub → WCH HID control board → Lightning cable → iPhone.
  - The board's USB link to the PC carries only the input channel (vendor HID reports).
  - Video goes over Wi-Fi (iPhone → Wi-Fi → PC), not over the cable.
- C24C's board, per `/api/config/usb/get`:
  - VID `720A`, PID `C24C`, uid `C24CBFBD`, at `Port_#0001.Hub_#0010`;
  - `state` 2 ("board enumerated and phone attached") at 20:40:59 and again at 20:43:05.
- **Not established from software:**
  - which end of which cable was unplugged;
  - whether the Lightning cable also powers or charges the phone;
  - whether the phone sees the board as a keyboard/pointer accessory only, or as anything more.
  - The operator answered the first two below: the Lightning plug at the phone, and yes, it charges. The third remains open.

## Observed (from evidence)

1. **The PC's USB side of C24C's board was not interrupted.**
   - Its USB and HID nodes last arrived at 14:01:07 today and have no later removal.
   - Across all 587 device nodes, the only arrival or removal between 20:30 and 20:46 is the Apple device in item 2.
   - If the board's own USB cable to the PC had been pulled, Windows would have recorded a removal and a new arrival.
   - The cable that was replugged was therefore on the phone side (board ↔ phone), or a separate cable, and not the board's PC connection.
2. **An unrelated iPhone left the PC's USB at 20:35:52.**
   - It was an Apple composite device (VID `05AC`, PID `12A8`), serial `(withheld: personal device)`, connected directly at `Port_#0007.Hub_#0003`.
   - It arrived 20:01:48, was surprise-removed 20:35:52, and has not returned.
   - Its UDID family (8130) is not an iPhone XR (8020), and C24C reports `iPhone11,8` (XR). This is not C24C, and its timing (about 4 minutes earlier) does not match the replug.
   - Which phone it is was not established.
3. **C24C's IP address was the same before and after:** 192.168.4.57 (queries at 20:09 and from 20:40:02; the resolve at 20:42:49 that preceded the connection).
4. **C24C's discovery traffic, as captured on the PC's Ethernet:**
   - At 20:09:07, 20:09:13 and 20:09:14 it sent `_raop._tcp`-only queries.
     - C241 sent the same kind at 20:09:14–20:09:54, though its receiver was untouched.
     - So these look like a reaction to the receiver being withdrawn and re-registered, not a picker browse.
   - From 20:09:14 to 20:40:02 it sent nothing that was captured. The two captures ran 20:06:11–20:34:11 and 20:34:54–20:42:49; the 43 s gap was not covered.
   - From 20:40:02 it sent the picker pattern: `_airplay` + `_airplay-bds` + `_raop` in a burst, with the retries spaced out.
   - At 20:42:22 its last browse before the connection was captured. At 20:42:49 it resolved `iMouse2-C24C`, and the connection request followed in the same second.
5. **Every other phone's picker openings were captured as the same burst:** .24 many times, .27, and C241 (.56) at 20:14:04.
   - Each burst's first packet is a QU query with 0 known answers, the same as C24C's at 20:40:02.
   - So "0 known answers" does not by itself indicate a flushed cache on C24C.
   - Picker bursts back off: C241's last captured query was 20:16:06, although its list stayed on screen through 20:33. An open picker is quiet on the LAN after a few minutes.
6. **The webcam showed C24C's Screen Mirroring list open and empty** (spinner) at every frame from 20:19:17 to 20:33:36. No frames exist after 20:35 (the Camera window was closed or minimised), so the replug itself was not recorded.
7. **The receiver log (PID 6264) has no entries between 20:09:03.799 and 20:42:49.403.** No client contacted it until the connection.
8. **The kernel has no history of board or phone state.**
   - It writes only receiver logs.
   - Whether C24C's board `state` changed from 2 to 1 and back during the replug was not recorded.

## Hypotheses (not established)

Each is consistent with the evidence above; none is shown by it.

- **H1: the phone's discovery browse stopped.**
  - C24C's Screen Mirroring browse had stalled after its session ended, so an open or reopened picker sent nothing.
  - The accessory detach/attach (or the wake and UI change it causes) restarted it.
- **H2: C24C's Wi-Fi multicast path was impaired.**
  - Its queries left the phone but did not reach the PC, or it was in a Wi-Fi power-saving state.
  - A power or charging change on replug altered that. This depends on whether the cable supplies power, which is unknown.
- **H3: the fresh browse came from reopening the picker, not from the cable.**
  - A fresh picker opening after the replug produced the burst, and the cable was incidental.
  - It turns on whether the picker was opened between 20:34:54 and 20:40 without producing any captured burst. If it was, H3 is weakened.
- **H4: another state change on the phone.**
  - The replug reset something else in the phone's accessory or input state, such as the HID accessory session.
  - No evidence connects the input path to discovery.

Not supported by the evidence: a PC-side USB, hub or board re-enumeration. Also not supported: a change of the phone's IP address. An unchanged address does not rule out a Wi-Fi reassociation.

## Questions for the operator (physical details)

1. Which cable, and which end did you unplug: the Lightning plug at the phone, the plug at the board, or some other cable?
2. Does that cable charge the phone, for example with a charging bolt on the battery icon? Does the phone have any other power source?
3. The sequence and approximate clock times:
   - Did you reopen Screen Mirroring on C24C between about 20:36 and the replug, as suggested at 20:36? If so, did the list stay empty?
   - Was the list open during the replug, or did you open it afterwards?
4. Did C24C show anything on replug, such as the screen waking, an accessory prompt, or a keyboard/trackpad notice?
5. What is the iPhone that was plugged directly into the PC from 20:01:48 to 20:35:52, and was it unplugged on purpose?

### Operator's answers (27 Sep 2026, after the review)

1. The cable was on the 3rd phone from the end of the rack (C24C). It was unplugged **at the phone's Lightning port** and plugged back in.
2. **The cable charges the phone.** It carries both the board's input (HID) connection and charging power.
3. The list was empty right before the unplug. After the unplug and replug it showed the receivers.
4. Nothing special appeared on the phone. **Before the unplug, the operator closed and reopened Screen Mirroring, and the list stayed empty.** Only the replug brought it back.
5. The iPhone removed from the PC at 20:35:52 was probably the operator's personal phone, which was charging. It is unrelated to the rack.

### What the answers change

- **The unplug removed two things at once:** the input accessory and charging power. Existing evidence cannot say which of the two mattered, or whether the unplug and replug events themselves (wake, accessory session) did.
- **H3 is weakened.**
  - The reopen before the replug did not bring the list back.
  - The listener captured no burst from C24C at that reopen: it ran from 20:34:54, and nothing from .57 appeared until 20:40:02.
  - Unlike every other phone's picker opening, that reopen produced no captured browse traffic.
  - This assumes the reopen came after 20:34:54, which fits the 20:36 suggestion to do it; its exact time was not recorded.
- **No browse queries from C24C were observed at the PC between 20:09:14 and 20:40:02.**
  - That does not prove C24C sent none. They could have been sent and lost before reaching the PC's Ethernet capture.
  - So H1 (not sent) and H2 (not delivered) both remain open.
  - The first observed burst came right after the replug, from the same IP address.
- **H4 cannot be separated from H1 or H2 with existing evidence:** the replug changed the accessory state and the power source together.
- **Still not established:**
  - whether C24C was connected to the network while stuck (no reachability record exists);
  - whether its Wi-Fi reassociated at the replug;
  - whether a network-only reset would have had the same effect.

## Finding kept

**A Lightning replug at the phone was followed by recovery once.** At about 20:40, C24C's list was empty after a reopen. After the replug, browse traffic from C24C was observed at 20:40:02, the receivers were listed, and the phone connected at 20:42:49.

- This is a single observed recovery.
- The charging state and the accessory (input) connection changed together, so the finding does not say which mattered.
- The finding is not a cause, and not a validated recovery procedure.

## Status: pending until the problem recurs naturally

- No monitoring is running.
- No receiver will be restarted to reproduce the problem.
- Both phones are left as they are.

## Possible next experiment (not approved; nothing run)

This is for the next natural recurrence only. It must not be run by creating a failure. Its limits are stated first:
- **Neither outcome alone identifies the cause.**
- **Absence of observed traffic at the PC** means none was observed there, not that the phone sent none.
- **A failed ping or a cached ARP entry alone** cannot establish whether the phone is connected to the network.

1. **Confirm the stuck state, read-only.**
   - Run the passive listener.
   - The operator closes and reopens C24C's picker once and notes the time.
   - Record whether any browse traffic from .57 is observed and whether the list stays empty.
   - A reachability check may be recorded as supporting context only.
2. **One network-level intervention.** The two forms test different things; only one would be used in a given recurrence:
   - **Control Centre Wi-Fi toggle.** This disconnects from and reconnects to the current network. It is not a full Wi-Fi off/on: the radio stays on.
   - **Settings → Wi-Fi off, then on.** This is a full Wi-Fi off/on. It needs a coordinated window.
   - No cable, board, receiver or PC setting is touched in either case.
3. **Record separately:** first observed browse traffic from .57, the list appearing, the connection request and live video.

How the outcomes read:
- **The list returns:** consistent with the stuck state being in the phone's network or discovery path, and with a cable-free recovery. It does not rule out other contributors. It also does not show why the Lightning replug worked.
- **It does not return:** consistent with the accessory or power change mattering, but it does not rule out a network cause that the chosen intervention did not reset. Separating accessory from power would be a later, separate decision.

Unplugging stays off the table until agreed.

## Evidence

- `iMouseXP-2.0-evidence-archive/20260927-rediscovery/`:
  - `mdns-listen-trial1.txt` and `mdns-listen-trial1-recovery.txt`;
  - `operator-notes-trial1.txt`;
  - `webcam-trial1-window/`;
  - `trial-200609-Graceful-G-M.txt`.
- Windows sources, read live on 27 Sep 2026 and not copied:
  - `Microsoft-Windows-Kernel-PnP/Device Management` event 1010 at 20:35:52;
  - `Microsoft-Windows-WPD-MTPClassDriver/Operational` event 1002 at 20:35:52;
  - PnP `DEVPKEY_Device_LastArrivalDate` / `LastRemovalDate`.

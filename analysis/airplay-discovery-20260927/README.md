# Receivers not listed in Screen Mirroring after a restart: 27 Sep 2026

**Status: investigated; cause not demonstrated; nothing changed.** A controlled test plan is prepared and awaits a coordinated window. The release kernel, receivers, network, firewall, identity keys, product code and phone settings are unchanged. Both phones were mirroring through the release again at 18:58:50 (C24C) and 18:58:53 (C241).

## What is established, and what is not

- **This PC answers AirPlay discovery on its Ethernet segment.**
  - `tools/airplay-diagnostics/mdns_probe.py` sends one standard mDNS query out of 192.168.4.26. The PC answered `_airplay._tcp` and `_raop._tcp` for both receivers (`JoeyDesktop.local`, 192.168.4.26, ports 7111 and 7121), including to a query with the unicast-reply bit. It did so on three runs; one first run got no answer.
  - The probe heard other LAN devices, so it works.
  - **Not established:** that every relevant answer reached C24C or C241 over Wi-Fi at the times they were searching.
- **Some phones on the LAN reached both receivers.** Two other rack phones connected at 18:48–18:49 (`8A:23:B5:71:35:8D` from 192.168.4.27; `3A:DC:15:FB:DD:EC` from 192.168.4.65), and the allow list refused them as designed.
  - This shows some LAN reachability.
  - It says nothing about C24C's or C241's path.
  - Receiver ports are fixed, so those phones may also have used cached records.
- **The receiver identity does not change across restarts.**
  - UxPlay 1.74 without `-key` derives its Ed25519 key from the device ID (`lib/crypto.c`, `ed25519_key_generate`; README 1.68 notes). The kernel fixes that ID with `-m`.
  - The TXT `pk` read at 18:54 and again at 19:32 in the same receiver run was identical. Across restarts this follows from the source and still has to be observed; the trial runner records it before and after each trial.
- **The listen at 18:57–19:01 saw only two AirPlay-related queries from these phones:** each phone's direct query for its own receiver, at the moment it connected.
  - No browse query appeared in that capture.
  - **This does not show the phones never searched.** Queries can fall outside the window, be sent unicast, or be missed by a single listener.

## Observed pattern (uncontrolled)

The kernel ends uxplay with `Process.Kill(entireProcessTree)` (`AirplayProcess.Dispose`). uxplay on Windows has a Ctrl+C handler that quits its main loop, logs "Stopping RAOP Server...", destroys the RAOP server, unregisters DNS-SD, and exits (`uxplay.cpp`: `CtrlHandler`, `handle_signal`, `stop_raop_server`, `stop_dnssd`). The kill bypasses that.

| Receivers killed (phones mirroring) | New receivers up | C24C listed and connected | C241 listed and connected |
|---|---|---|---|
| 18:26:11 (window 1) | test 18:26:22; release 18:29:22 | 18:29:55 (release) | 18:32:38 (release) |
| 18:35:14 (window 2) | test 18:35:23; release 18:45:46 | 18:58:50 (release) | 18:58:53 (release) |

These are observations across different conditions: different kernels, receiver code, timing and phones. They motivate the test; they do not establish a cause.

## Questions to separate

1. **Does manually stopping mirroring on the phone before a receiver restart change rediscovery time?** The shutdown method is held at Forced.
2. **Does a graceful receiver shutdown improve rediscovery compared with forced termination?** The phone state is held at "mirroring".

A result for question 1 does not answer question 2, and neither alone proves the root cause.

## Controlled plan

### Fixed for every trial

- **Phone: C24C only.** C241 and its receiver are never signalled. Each trial records C241's receiver PID (it must be unchanged) and its video state.
- **Receiver: the release `iMouse2-C24C` only.** It is restarted through the running release kernel's own supervisor, which relaunches an exited receiver after 2 s; the kernel is never restarted.
- **Verified mapping**, checked by `tools/airplay-diagnostics/Invoke-ReceiverTrial.ps1` before each stop:
  - the kernel's receiver PID for `86:1D:4A:04:2F:F6` equals the only uxplay process named `iMouse2-C24C`;
  - its executable is the release uxplay and its parent is the release kernel;
  - its arguments restrict it to `86:1D:4A:04:2F:F6`;
  - the other receiver is running.

  Dry run at 19:32: PID 35448 under kernel 30652, 0 relaunches used.
- **Identical arguments and identity.** The full command line and the advertised `deviceid`/`pk` are recorded before and after. A trial whose replacement differs is invalid.
- **Exactly one replacement.** After the stop, the runner requires one new `iMouse2-C24C` process, and records its PID and start time.
- **Relaunch budget.** The supervisor allows 5 relaunches per kernel lifetime, and on a 6th exit the receiver stays down until the kernel restarts. The runner refuses at 4 used, leaving one spare. **At most 4 trials per kernel lifetime.**

### Conditions

| Code | Phone state at the stop | Stop method |
|---|---|---|
| F-M | Mirroring | Forced: the process is terminated, as the kernel does today |
| G-M | Mirroring | Graceful: Ctrl+C to uxplay's console. Valid only if its log then shows "Stopping RAOP Server" |
| F-S | Stopped first: Stop Mirroring tapped on C24C, teardown confirmed in the receiver log, then 60 s wait | Forced |

- Question 1 compares **F-S with F-M**.
- Question 2 compares **G-M with F-M**.

### Recommended sessions (each within one kernel lifetime's budget)

- **Session A, question 2:** F-M, G-M, G-M, F-M (ABBA). It answers whether graceful shutdown helps.
- **Session B, question 1, later:** F-M, F-S, F-S, F-M.

It needs a fresh relaunch budget, which comes with the next normal kernel start. No causal conclusion is drawn unless both repetitions agree. If they disagree, order is reversed in a further session.

### Step 0 (before Session A, optional but recommended)

Validate the graceful stop on a **throwaway** uxplay that is not part of the rack:
- name `iMouse2-selftest`, restricted to a device ID no phone has, port 7150, MAC `02:49:4D:32:00:99`;
- the release uxplay executable is used unchanged.

Then Ctrl+C it with the helper and confirm three things: "Stopping RAOP Server" in its log, a goodbye (TTL 0) from `mdns_listen.py`, and the process exiting. It is visible for about a minute in nearby phones' Screen Mirroring lists, but nothing can connect to it.

### Timed observation procedure (operator, C24C)

1. I announce T0, the exact time the stop is issued.
2. You open Control Center, then Screen Mirroring, at **T0+30 s and then every 60 s** (T0+90, T0+150, …). Keep the list open for 20 s each time, then close it.
3. At each opening, note the clock time and whether `iMouse2-C24C` is listed. A photo showing the time is ideal.
4. The first time it is listed, tap it immediately.

### Recorded separately for every trial

- T0; old receiver exit; replacement PID and start time (supervisor);
- **receiver ready**: "Initialized server socket(s)" in the receiver log;
- announcements and goodbyes from 192.168.4.26 (`mdns_listen.py`, now showing TTLs);
- **appearance in C24C's list** (operator, at a resolution of 60 s);
- **connection request** from `86:1D:4A:04:2F:F6` (receiver log);
- **live video**: the kernel shows the receiver offline, then live again (its frame counter is not reset by a restart, so "live again after offline" is used).

### Bounds and recovery

- **Observation window: 25 minutes from T0.** The earlier worst case was about 23 minutes. If C24C has not listed and connected by then, the trial result is "> 25 min".
- **Recovery:** no further restart of anything. You keep checking the list every 2 minutes up to T0+50 min. If C24C has still not recovered then, the session ends with C24C unmirrored and the next step is agreed with you. A phone restart, for example, is your decision.
- **Between trials:** the next trial starts only after C24C has had live video for 2 minutes, plus a fixed 5-minute settle, identical for every trial.
- **Duration.** Each trial takes 10–55 minutes, so Session A is **about 45 minutes at best and over 3 hours at worst**. It can end after any trial. **No short interruption is promised:** earlier recoveries took up to about 23 minutes.

## Results: staged window, 27 Sep 2026 (preliminary; one trial)

### Step 0: graceful stop of a disposable receiver (passed, run 2)

- The disposable `uxplay-selftest-noconnect` receiver ran on ports 7150–7152 as `02:49:4D:32:00:99`, restricted to `00:00:5E:00:53:99`.
  - That device ID is an exclusion precaution; it doesn't guarantee a phone could never connect.
  - No phone selected it.
- Its console held only the uxplay and the helper.
- The log shows "Stopping RAOP Server", and the receiver exited with code 0.
- Recorded separately:
  - withdrawal: Bonjour `Rmv` at 20:03:42.761 (it was added at 20:03:22.406);
  - process exit;
  - ports freed.
- Limits:
  - `Rmv` can't tell an explicit unregistration from a closed connection.
  - The LAN goodbye and the advertisement were not observed: this host's own multicast isn't visible to a local listener, which is why run 1 saw neither.

### Trial 1: graceful restart of C24C's receiver (condition G-M)

T0 was 20:09:00. The stop went to uxplay PID 35448 alone.

| Measure | Result |
|---|---|
| Graceful path | "Stopping RAOP Server" logged; the old receiver had exited 20:09:02 |
| Replacement | exactly one, PID 6264, started 20:09:03.731, arguments identical, identity/pk identical |
| Readiness | 20:09:03.798 (about 3.8 s after T0); Bonjour `Rmv` 20:09:02.823, `Add` 20:09:03.802 |
| Appearance in C24C's list | **none within the 25-min window**. The webcam showed an empty list with a spinner through 20:33. C241 and a third phone listed `iMouse2-C24C` during the same period. |
| Connection request | none within 25 min |
| Live video | none within 25 min (offline from 20:09:09) |
| C241 | PID 6100 unchanged, live throughout |
| Restart budget | 1 of 5 used, 4 left |

**Discovery traffic.**
- C24C (192.168.4.57) sent `_raop._tcp` queries at 20:09:07, 20:09:13 and 20:09:14.
- After that, nothing from C24C was captured through 20:34, or in the second capture from 20:34:54 to 20:40:02.
- Other phones kept querying.
- An absent query in the capture doesn't prove the phone never searched.

**Manual intervention (not recovery, not a trial result).**
- At about 20:40 the operator unplugged C24C's cable and plugged it back in; the receiver list then appeared on C24C.
- C24C's queries resumed at 20:40:02. The first was a QU query with 0 known answers.
- The operator connected at 20:42:49 (connection request); the kernel showed C24C live at 20:42:50.
- The receiver was the same PID 6264 and no further restart was made.
- The board binding was unchanged: `86:1D:4A:04:2F:F6`, uid `C24CBFBD`, board C24C.

**Reading (preliminary).**
- In this one trial, a graceful stop did not give fast rediscovery. The replacement was advertised and other phones saw it. C24C's list stayed empty until the cable was reconnected.
- This weakens "forced termination alone causes the delay" but doesn't rule it out.
- It points to C24C's own discovery state, possibly tied to its accessory/cable connection, as the next thing to examine.
- It doesn't establish that the cable caused the recovery: the timing is one coincidence, and the session was already 31 minutes past T0.
- No further trial was run; Q1 wasn't started.

**Next investigation (not yet approved).**
- Consider the phone and accessory connection state: what the board's USB/HID connection does to the phone's network and discovery behaviour.
- Don't repeat the unplug until a method is agreed.

## Evidence

- `iMouseXP-2.0-evidence-archive/20260927-home-window/`: `mdns-listen-1.txt`, `window2-release-reconnect.txt`, and the user's photos.
- `iMouseXP-2.0-evidence-archive/20260927-rediscovery/`, containing:
  - `step0/` and `step0-run1/`;
  - `trial-200609-Graceful-G-M.txt` and `dns-sd-browse-200609.txt`;
  - `mdns-listen-trial1.txt` and `mdns-listen-trial1-recovery.txt`;
  - `operator-notes-trial1.txt` (the manual intervention and the final rack state);
  - `recovery-watch.txt`;
  - `webcam-trial1-window/`: PrintWindow frames of the webcam every 10 s from 20:25; `gaps.txt` lists the times the Camera window was closed or minimised;
  - `webcam-trial1/`: the earlier screen-region frames; after about 20:20 they show a covering window, not the phones.
- Recording tools: `tools/airplay-diagnostics/Save-WindowCapture.ps1` (used) and `Save-ScreenRegion.ps1` (superseded; it records whatever window covers the region).
- Receiver logs in `analysis/two-phone-config/receiver-*.log` in the main checkout. They are read only, not copied.

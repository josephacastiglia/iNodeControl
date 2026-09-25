# Windows rack validation handoff — NodeTheory portal and rack agent

For Codex, on the Windows rack PC. Written 25 September 2026.

| | |
|---|---|
| Repository | `josephacastiglia/iNodeControl` |
| Branch | `claude/focused-noether-s600e0` |
| **Code under test** | **`c945512b4cadd2d5d0732db2d942b11e1d31e778`** |
| This document | Added in the commit after that one (documentation only). The branch tip has the same code. |
| Base | `ee445d70e5f7e3cd9497a9162fc89ba9f6061e4a` (kernel and console source unchanged since) |
| Status | Milestone 1 is implemented and tested **in simulation only**. Nothing has run on Windows or touched a phone. Milestone 2 is paused. |

**Evidence rule.** The simulator and the Linux fake-HID conformance harness prove software behaviour only. Only steps done on this PC with real phones count as Windows or phone evidence. Record every result as observed. A step that was not run stays "not run".

---

## 1. Ground rules: don't disrupt the current installation

- **Leave these alone.** Do not stop, replace, rebuild or reconfigure:
  - the running kernel (`iMouse2.Kernel.exe`);
  - the desktop console (`iMouse2.exe`);
  - the UxPlay receivers and vendor services;
  - `Open iMouse 2.0.ps1`, the desktop shortcut, or any `release\` folder.
- **No system changes.** No firewall rules, URL ACL reservations, Windows services, scheduled tasks or permanent `PATH` edits. Everything here listens on `127.0.0.1` only and runs from a separate folder.
- **Stay local.** No public exposure: no `NT_HOST=0.0.0.0`, port forwarding, tunnels or reverse proxy.
- **Inspect first.** Check the running processes and phone identities (Part C) before any live step. If the running kernel does not advertise `input_protocol: 1` with `input_leases_required: true`, **stop and report**. Do not swap kernels as part of this validation.
- **One controller per phone.** The portal and the desktop console share each phone's single input lease. While the portal controls a phone, do not operate that phone from the console, and the reverse.
- **Stop latches.** A Stop from the portal, from a group, from Stop all or from emergency stop latches the kernel's Stop on that phone. **Anyone** then needs Resume before controlling it, including the desktop console. Resume every phone you stopped before handing the rack back (Part G).
- **Protect operators' work.** Emergency stop affects **every input-enabled phone on the kernel** (currently up to five), not just the test phones. Run it only with the operator's explicit agreement (step D2.6).

## 2. Prerequisites

| Need | Check | If missing |
|---|---|---|
| Node.js **22.13 or newer** (the portal uses `node:sqlite`) | `node --version` | Use the portable **Windows x64 zip** from nodejs.org (no installer). Extract to `C:\NodeTheory\node`, then per shell only: `$env:Path = "C:\NodeTheory\node;$env:Path"` |
| npm registry access for `npm ci` | `npm ping` | Copy `node_modules` from a machine with the same Node major version |
| Git | `git --version` | Download the branch as a zip from GitHub and note the commit |
| .NET 8 SDK (conformance tests only) | `& "C:\Program Files\dotnet\dotnet.exe" --list-sdks` | Skip A1's conformance part and record "not run" |
| Chrome or Edge | — | — |
| Free loopback port **9930** | `Get-NetTCPConnection -LocalPort 9930 -State Listen -ErrorAction SilentlyContinue` returns nothing | Pick another port and use it everywhere below |

Ports already in use on this PC: **9913** (kernel), **9911** (vendor service) and **8777** (old browser console). This validation uses **9930** for the portal. The agent listens on no port.

**Use a separate working copy.** Do not switch branches inside the live project folder.

```powershell
git clone --branch claude/focused-noether-s600e0 https://github.com/josephacastiglia/iNodeControl C:\NodeTheory\portal-validation
cd C:\NodeTheory\portal-validation
git log -1 --format=%H          # record it; the code must match c945512… (the tip adds only this document)
git diff --stat c945512b4cadd2d5d0732db2d942b11e1d31e778 HEAD -- portal rack-agent   # must print nothing
$evidence = "C:\NodeTheory\portal-validation\analysis\portal-m1-windows-$(Get-Date -Format yyyyMMdd)"
New-Item -ItemType Directory -Force $evidence | Out-Null
```

---

## Part A — simulator and conformance only (no phones touched)

### A1. Install and run the automated tests

```powershell
cd C:\NodeTheory\portal-validation\rack-agent
npm ci
npm test 2>&1 | Tee-Object "$evidence\A1-rack-agent-tests.txt"
cd ..\portal
npm ci
npm test 2>&1 | Tee-Object "$evidence\A1-portal-tests.txt"
```

Expected on Linux: **rack-agent 33/33** (23 simulator/unit + 10 conformance) and **portal 38/38**. Record the Windows counts exactly.

- **Conformance tests.** These build `rack-agent\conformance\KernelHarness` into a temporary folder. It compiles the kernel's HTTP and ownership source with a **logging fake instead of USB HID**, plus synthetic frames, and serves it on a random loopback port with its own named pipes.
  - It never opens a board for writing. On Windows, `/config/usb/get` enumerates the real boards read-only through SetupAPI.
  - If they fail with HttpListener "Access is denied", run only that file from an **elevated** PowerShell: `node --test test/conformance.test.mjs`. Record that you did. Do not add a URL ACL.
- **Portal tests.** These use the simulated kernel only.

### A2. Look at the portal with the simulator (optional)

```powershell
cd C:\NodeTheory\portal-validation\portal
$env:NT_PORT = '9930'; npm run dev
```

Open http://127.0.0.1:9930 and use the printed demo accounts. The simulator runs on its own random loopback port and **never contacts 9913**. Every screen says SIMULATOR. Stop with Ctrl+C. Close this window before Part B, since it uses port 9930.

---

## Part B — start the portal and agent against the real kernel (loopback only)

### B1. Local validation accounts (once)

```powershell
cd C:\NodeTheory\portal-validation\portal
$env:NT_DB_PATH = 'data\winval.db'
npm run bootstrap-validation -- --out data\validation --timezone America/New_York
```

This creates:
- `staff@validation.local`;
- `a-admin@validation.local` for customer **Validation A** (10-phone plan);
- `b-admin@validation.local` for customer **Validation B** (1-phone pilot);
- one rack credential.

Passwords are in `data\validation\accounts.txt` and the credential is in `data\validation\rack-credential.txt`. Neither is printed, and `data\` is git-ignored. No phone is assigned yet.

### B2. Start the portal (PowerShell window 1)

```powershell
cd C:\NodeTheory\portal-validation\portal
$env:NT_DB_PATH = 'data\winval.db'
$env:NT_INSECURE_DEV = '1'          # plain HTTP on 127.0.0.1 only; never for internet use
$b = New-Object byte[] 48; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
$env:NT_SESSION_SECRET = [Convert]::ToBase64String($b)
$env:NT_PORT = '9930'
node --disable-warning=ExperimentalWarning server\main.js 2>&1 | Tee-Object "$evidence\portal.log"
```
(Running `node` directly, rather than `npm start`, avoids the "Terminate batch job?" prompt on Ctrl+C.)

Expect `NodeTheory portal PID <n> listening on 127.0.0.1:9930 (INSECURE DEV MODE: plain HTTP, loopback only)`. **Record the PID.**

### B3. Start the rack agent (PowerShell window 2)

```powershell
cd C:\NodeTheory\portal-validation\rack-agent
$env:NT_PORTAL_URL = 'ws://127.0.0.1:9930/agent'
$env:NT_AGENT_CREDENTIAL_FILE = 'C:\NodeTheory\portal-validation\portal\data\validation\rack-credential.txt'
$env:NT_KERNEL_URL = 'http://127.0.0.1:9913/api/'
node src\main.js 2>&1 | Tee-Object "$evidence\agent.log"
```

Expect:
- `NodeTheory rack agent 0.1.0, PID <n>. Kernel http://127.0.0.1:9913/api/ …`, then `Connected to portal 127.0.0.1:9930`;
- **no** "SIMULATOR" warning and **no** "Input disabled".

**Record the PID.** A second copy refuses to start ("Another rack agent is already running"), which you can check once.

The agent reads the kernel's status, device and input endpoints every second and the board list every 5 s. It captures screenshots only while someone views a phone, and **sends input only when a portal user has taken control**.

### Configuration reference

| Variable | Used by | Value here | Notes |
|---|---|---|---|
| `NT_DB_PATH` | portal, bootstrap | `data\winval.db` | SQLite file; delete it to start over |
| `NT_SESSION_SECRET` | portal | random, 48 bytes | Changing it invalidates CSRF tokens; users reload |
| `NT_INSECURE_DEV` | portal | `1` | Allows plain HTTP; only valid on loopback |
| `NT_PORT` / `NT_HOST` | portal | `9930` / (default `127.0.0.1`) | Do not set `NT_HOST` |
| `NT_PUBLIC_ORIGIN`, `NT_TRUST_PROXY` | portal | unset | Production only |
| `NT_PORTAL_URL` | agent | `ws://127.0.0.1:9930/agent` | `ws://` only allowed for a portal on this PC |
| `NT_AGENT_CREDENTIAL_FILE` | agent | credential file path | Or `NT_AGENT_CREDENTIAL`; never logged |
| `NT_KERNEL_URL` | agent | `http://127.0.0.1:9913/api/` | Refused unless loopback |
| `NT_AGENT_LOCK_FILE` | agent | default `%TEMP%\nodetheory-rack-agent-9913.lock` | Single-instance lock |
| `NT_HARNESS_PORT` | conformance test | unset | Fixed port for the harness if needed |

### Stopping (any time)

1. In the **agent** window, press **Ctrl+C**. It releases every phone it controls, then exits. If it hangs: `Stop-Process -Id <agentPID>`.
2. In the **portal** window, press **Ctrl+C**.
3. Check that nothing is left holding a phone:
   ```powershell
   (Invoke-RestMethod http://127.0.0.1:9913/api/input/status).data.phones | Format-Table id,owned,stopped,releasing,message,generation
   ```
   `owned` must be `False` for every phone the agent held. If a phone shows `stopped: True`, see Part G.

---

## Part C — inspect the live rack first (read-only)

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 9911,9913,9930,8777 | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table
Get-CimInstance Win32_Process | Where-Object Name -in 'iMouse2.Kernel.exe','iMouse2.exe','uxplay.exe','node.exe' |
  Select-Object ProcessId,Name,ExecutablePath,CommandLine | Format-List | Out-File "$evidence\C-processes.txt"
foreach ($p in 'kernel/status','device/get','input/status','config/usb/get') {
  Invoke-RestMethod "http://127.0.0.1:9913/api/$p" | ConvertTo-Json -Depth 6 | Out-File "$evidence\C-$($p -replace '/','-').json"
}
Get-FileHash (Get-Process -Name iMouse2.Kernel).Path -Algorithm SHA256 | Out-File "$evidence\C-kernel-hash.txt"
```

**Stop and report if any of these hold:**
- `kernel/status` lacks `input_protocol: 1` or `input_leases_required: true`;
- port 9930 is in use;
- another `node.exe` is already running a rack agent;
- the kernel command line or phones differ from what the operator expects.

Write down, for the phones you'll use, their `deviceid`, `name`, board `pid`, `receiver_name`, `video_state` and physical position, confirmed your usual way:

- **P1**: the first test phone, suggested C24C (`86:1D:4A:04:2F:F6`). KEYBOARD-SPEC.md notes that C24C types directly into fields.
- **P2**: the second test phone, suggested C241 (`FE:A9:BC:D7:A0:44`). It has Full Keyboard Access on, so typing needs Typing Mode (KEYBOARD-SPEC.md).

If `input/status` shows `owned: True` for P1 or P2, the desktop console holds it. Ask the operator to release it (select another phone in the console). Do not force it.

**D0 baseline (before the portal views anything).** In the desktop console's Activity drawer, record P1's displayed fps for 60 s while scrolling Settings on P1. Record the kernel's frame counter for P1 at the start and end of that minute (`kernel/status` → `receivers[].frames`).

---

## Part D — staged live checklist

Before every action, **write down the expected visible effect**, then record the observed effect, the portal's outcome (Sent / Not sent / Uncertain), and a screenshot or phone photo where useful. "Sent" means the rack confirmed the input was delivered. It does **not** prove the phone reacted, so judge by the screen.

### D1. Stage 1 — one phone (P1), one customer (A)

| # | Step | Expected |
|---|---|---|
| 1.1 | Sign in as staff (use a normal browser window). **Racks** tab. | Rack connected. The kernel shows **Compatible** and not SIMULATOR. The agent PID matches B3. |
| 1.2 | **Phones** tab. | Every kernel phone listed as *Unverified*, with the board and video status matching Part C. |
| 1.3 | After confirming P1's identity, set P1 to **In service** and **Assign** it to *Validation A* as "Validation phone 1". Leave P2 unassigned. | Assigned. An unverified phone's Assign button is disabled. |
| 1.4 | In a second browser profile (or InPrivate), sign in as `a-admin`. Go to **Phones**. | Exactly one phone. Its tile updates about once a second. **Control** and **Video** show separate statuses. |
| 1.5 | Open P1. Open **Measurements** and click **Start recording**. | Video *Live*. Displayed fps shown. |
| 1.6 | Click **Take control**. Run the `input/status` command. | *You're in control*. P1 `owned: True`. |
| 1.7 | **Home** | First Home Screen. Outcome Sent. |
| 1.8 | Click the Search pill on the Home Screen (near the bottom centre) | Spotlight opens |
| 1.9 | Type `hello2026` | Outcome says all 9 characters were sent as keystrokes. **Check that the text actually appears.** |
| 1.10 | Press **Delete** four times | `hello` remains |
| 1.11 | **Home**. Drag left across the Home Screen, then drag right. | The page changes, then changes back |
| 1.12 | Hold on an app icon for about 1 s, then release | Context menu appears. No stuck press: Home works next. |
| 1.13 | App switcher, then Home. Control Centre, then Home. | Each opens, then closes |
| 1.14 | **Reset pointer** | Outcome Sent; the pointer goes to the corner |
| 1.15 | **Latency run.** Repeat 20 times: tap the Search pill (Spotlight opens), then Home. | Measurements table fills. **Download JSON** → `$evidence\D1-measurements.json` |
| 1.16 | **Release control** | *Ready*. `owned: False` |

### D1-S. Stage 1 safety tests (P1)

**S1. Desktop and portal conflict**
1. The portal controls P1. In the desktop console, try one harmless action on P1, such as Home.
   - Expect: the console refuses or reports it owned elsewhere, and **nothing happens on the phone**.
2. Portal: **Release control**. In the console, select P1 and press Home once, so the console holds P1.
   - Expect: the portal shows *In use by NodeTheory*, and **Take control** is refused with "Our operators are using this phone…".
3. The console releases P1 (select another phone).
   - Expect: the portal shows *Ready* again within a few seconds.

**S2. Stop during typing**
1. Take control of P1. Open Notes, create a new note, and tap in the body.
2. Type this 150-character marker string. Each group of 10 starts with a letter A–O, so you can read how far it got:
   ```
   A123456789B123456789C123456789D123456789E123456789F123456789G123456789H123456789I123456789J123456789K123456789L123456789M123456789N123456789O123456789
   ```
3. About 3 s after sending, click **Stop this phone**. Screen-record the phone if you can.

Expect:
- typing halts within about 1 s;
- the outcome is **Uncertain**: "*N* of 150 characters were confirmed as keystrokes, the next 32 are uncertain, and *M* were not sent";
- P1 shows **Stopped**, and `input/status` shows `stopped: True`;
- on screen, the count of typed characters is between N and N+32, and no characters appear after Stop;
- **Resume input**, then **Take control**, works.

Record N, the on-screen count, and the time from Stop to halt.

**S3. Lease expiry (agent killed)**
1. Take control of P1 and leave it idle. Then run `Stop-Process -Id <agentPID> -Force`.
2. Expect:
   - the portal shows the rack offline;
   - within 30 s, `input/status` P1 shows `stopped: True` with "Controller lease expired";
   - nothing happens on the phone.
3. Restart the agent (B3). The stale lock is taken over automatically.
4. Expect: P1 shows **Stopped**, nothing is replayed (the phone is unchanged), and **Resume input** followed by **Take control** is required.

**S4. Portal connection loss**
1. Take control of P1. Press Ctrl+C in the portal window.
2. Expect:
   - the agent logs "Portal connection lost; releasing all phones";
   - within about 2 s, `input/status` P1 shows `owned: False` and `stopped: False`.
3. Restart the portal (B2's `node …` line in the same window, so `NT_SESSION_SECRET` is unchanged and the browser session stays valid).
4. Expect:
   - the agent reconnects within 30 s;
   - P1 shows **Ready**, not "You're in control";
   - nothing is replayed; control must be taken again.

**S5. Uncertain outcome**
1. Take control of P1 in a Notes body. Send the 150-character string.
2. About 3 s later, run `Stop-Process -Id <agentPID> -Force`.
3. Expect:
   - the portal reports that action as **Uncertain**, with "did not confirm this action, so it may have run fully, partly or not at all";
   - it is **not** retried;
   - within 30 s the kernel shows P1 `stopped: True`.
4. Restart the agent. Expect:
   - after the kill, the chunk already in flight may keep typing until it ends (up to 32 more characters, a few seconds), because the kernel finishes a command it has started;
   - after that, the text never grows, even after the agent restarts;
   - Resume plus Take control are needed.

   Record the on-screen count at the kill, and again 10 s later.

### D2. Stage 2 — two phones, two customers

| # | Step | Expected |
|---|---|---|
| 2.1 | Staff: set P2 to **In service** and assign it to *Validation B* as "B phone 1" | — |
| 2.2 | In a third browser profile, sign in as `b-admin` | Only P2 is listed |
| 2.3 | As B, paste P1's page address (copy it from A's address bar) | "Phone not found". Nothing happens on P1. |
| 2.4 | A controls P1 and B controls P2 at the same time. Each presses Home and opens an app. | Each action affects only its own phone |
| 2.5 | B clicks **Stop all phones** and confirms | Only P2 stops. P1 is still in A's control and A's next action works. B's result lists only "B phone 1". |
| 2.6 | **Optional, only with the operator's explicit agreement that no other phone is in use.** Staff → **Emergency stop** → type STOP. | **Every input-enabled phone** stops, including any the console holds. Portal A and B both show Stopped. Resume all of them afterwards (Part G). |
| 2.7 | Staff: unassign P2 from B and assign it to A ("Validation phone 2"). As A: **Select phones for a group action** → tick P1 and P2 → **Take control** → **Home** | Results dialog: both **Sent**. |
| 2.8 | As A, group **Type text…** with `ok` (each phone showing a text field) | Both Sent, and `ok` appears on both phones |
| 2.9 | Open P2 alone and **Release control**. Back on **Phones**, re-enter group mode, tick both, and press **Home**. | P1 **Sent**, P2 **Not sent: you are not in control**. The dialog offers "Retry on the 1 phone where nothing was sent". |
| 2.10 | Close the dialog, press **Take control** in the group bar, then **Last results** → **Retry** | The retry goes only to P2, and P2 receives Home. P1 shows no second action and is not part of the retry. |
| 2.11 | **Optional, with the operator's agreement to recast:** stop Screen Mirroring on P2 | Portal: Video *unavailable* while Control still works (Home still reaches the phone). Recast to P2's receiver: *Live* again with no page reload. |
| 2.12 | End of session: Staff → **Racks** → **Revoke** | The agent logs "Portal refused the agent (HTTP 401)" and cannot reconnect. `input/status` shows `owned: False` for all. |

---

## Part E — measurements and how each is taken

Recommended workload: continuous scrolling in Settings on the viewed phone, 60 s per sample. Record screen state and conditions with every number.

| Metric | How it is measured | Where |
|---|---|---|
| **Displayed FPS (portal)** | Frames the browser actually displayed per second over the last 3 s. A frame is only sent when pixels change, so a still screen correctly shows 0. The focused view is capped at about 8 fps by design (encode budget). | Phone view → Video card and Measurements; JSON `frames[]` |
| **Receiver FPS (kernel)** | Increase of the kernel's per-phone frame counter (`/kernel/status` `receivers[].frames`) over about 5 s, computed by the agent. It is independent of viewers. | Measurements panel; JSON `receiverFpsSamples` |
| **Displayed / received ratio** | Over the same 60 s: min(received, 8 × 60 s) compared with frames displayed (FINISH-CRITERIA gate 7 method). Expect the ratio to be limited by the 8 fps cap when the receiver runs faster. | From the JSON |
| **Frame age** | (a) *Capture → display*: browser time at image load minus the agent's capture time. Valid only because browser and agent are on the same PC, and it excludes the phone → AirPlay → kernel delay. (b) *Portal hold*: time a frame waited in the portal cache. | JSON `summary.captureToDisplayMs`, `summary.portalHeldMs` |
| **Input-to-visible latency** | From the click to the first displayed frame whose mean pixel difference (0–255) against the last frame before the click reaches **8**. For taps: inside ±24 source px of the tap point. For keys, text and swipes: the most-changed 1/12 × 1/24 block, ignoring the status bar. It includes the preview pipeline, so it is an upper bound on what a remote user sees. Misses (no change within 5 s) are counted, never dropped. Also recorded: *confirmed sent* time. | Measurements table and JSON `latency[]`, with median / p95 / misses in `summary.latency` |
| **Glass-to-glass (optional)** | Film the phone and the browser together with a high-frame-rate camera and count frames from the click to the phone's change | Video file |
| **CPU and memory** | Run `rack-agent\scripts\sample-processes.ps1` for 10 min per scenario, using the PIDs of: agent `node`, portal `node`, `iMouse2.Kernel`, both `uxplay`, `iMouse2` (console) and the browser. It reports CPU as % of the machine and of one core, working set and private MB. Staff → Racks also shows agent CPU (% of one core), RSS, encode ms, and frames sent and dropped. | `$evidence\E-cpu-<scenario>.csv` |
| **Console impact** | Repeat the D0 baseline with the portal's focused view open on P1 | Compare with D0 |

Sampler example (Windows PowerShell 5.1 or 7):
```powershell
cd C:\NodeTheory\portal-validation\rack-agent\scripts
.\sample-processes.ps1 -ProcessIds <agentPID>,<portalPID>,<kernelPID>,<uxplayPID1>,<uxplayPID2> -Seconds 5 -Minutes 10 -OutFile "$evidence\E-cpu-focus-scrolling.csv"
```
If the script is blocked by execution policy, run it for this process only: `powershell -ExecutionPolicy Bypass -File .\sample-processes.ps1 …`. That changes no system setting.

**Scenarios:**
1. Idle, with the portal Overview open.
2. Phones grid with both tiles visible.
3. Focused P1 while scrolling.
4. Scenario 3 plus the desktop console showing P1.
5. Both customers each focused on their own phone.

---

## Part F — send back

`$evidence` should contain:
- test outputs (A1);
- `C-*` inspection files;
- `portal.log` and `agent.log`;
- the measurement JSON files;
- the CPU CSV files;
- screenshots and videos;
- a results table with one row per step above: *expected / observed / outcome shown / pass-fail / notes*.

Mark anything not run as **not run**, with the reason.

## Part G — rollback and cleanup

1. Stop the agent (Ctrl+C), then the portal (Ctrl+C).
2. Check `input/status`. For each phone with `stopped: True`:
   - resume it from the portal before stopping it: open the phone and click **Resume input**; or
   - use the desktop console's Resume; or, as a last resort:
     ```powershell
     $s = (Invoke-RestMethod http://127.0.0.1:9913/api/input/status).data.phones | Where-Object id -eq '<PHONE_ID>'
     $body = @{ fun = '/input/resume'; data = @{ id = $s.id; expected_generations = @{ $s.id = $s.generation } } } | ConvertTo-Json -Depth 4
     Invoke-RestMethod http://127.0.0.1:9913/api/ -Method Post -ContentType 'application/json' -Body $body
     ```
     The last option is the kernel's documented Resume. It succeeds only once cleanup has finished, and it never replays input.
3. The agent removes its lock file on a normal exit. A leftover `%TEMP%\nodetheory-rack-agent-9913.lock` is harmless and taken over on the next start. Delete it if you want.
4. Delete `C:\NodeTheory\portal-validation\portal\data\validation\`, which holds passwords and the credential. Optionally delete the whole `C:\NodeTheory\portal-validation` folder and any portable Node folder.
5. **Nothing else to undo.** No services, firewall rules, URL ACLs, `PATH` entries, kernel or console files were changed.

---

## Relationship to the separate desktop text-chunking fix

- **The problem.** The desktop console sends a whole text box, up to 2,000 characters, in one `/key/sendkey`. The kernel cancels any command after 8 s and latches Stop, so text over about 50 characters fails.
- **The fix does not exist on any branch yet.** On 25 September, `origin/main` was still `ee445d7`. It was queued as a separate task.
- **No conflict is possible.** This branch changes **no** file under `src/`, `console/` or `tools/`, no `.ps1` launcher, and not `KEYBOARD-SPEC.md` (`git diff ee445d7 -- src console tools KEYBOARD-SPEC.md` is empty).
  - The portal's chunking lives entirely in `rack-agent/src/actions.js` (32 characters per chunk, 200 per send) and `rack-agent/src/phone-lane.js`.
  - The desktop fix should change only `src/iMouse.Console/*` and `KEYBOARD-SPEC.md`.
  - The two share no code. It is best if they use the same 32-character chunk size, so the documented limits agree.
- **Kernel changes.** If the desktop fix changes kernel timing or limits, rerun `rack-agent` `npm test`. The conformance tests compile the kernel source directly and will show any contract change.

## Known limitations (at this commit)

- **Not yet validated.** No Windows run and no phone contact yet. Only one local portal instance, and control sessions are kept in memory (a restart releases everything, safely).
- **Previews.** Pulled JPEG stills: grid about 1 fps, focused view up to about 8 fps. Latency and CPU on this rack are unmeasured.
- **What "Sent" means.** Confirmed means HID was written, not that iOS reacted. Text is English (US) printable ASCII only. Full Keyboard Access, Typing Mode, Smart Punctuation and autocorrect still apply (KEYBOARD-SPEC.md).
- **Gestures.** Drags are sent when the pointer is released, not streamed.
- **Needs someone at the rack.** Screen-mirroring recast and board or USB problems stay with staff at the rack. The kernel returns 41 for USB restart and rebinding.
- **Latency measurement caveats.** It can be fooled by unrelated screen changes, such as notifications. Use targets with a clear, local visual change, and review misses.

# NodeTheory rack agent

Runs on the Windows rack PC, beside the iNodeControl kernel. It connects **out** to the
NodeTheory portal, so the rack needs no inbound port. It drives the kernel only on
`http://127.0.0.1:9913/api/`.

```
Customer browser ──HTTPS──> Portal ──WSS (agent credential)──< Rack agent ──HTTP 127.0.0.1──> Kernel
                                                                              ├─ USB HID boards → iPhones
                                                                              └─ UxPlay → BMP frames
```

## What it does

- **Inventory.** Polls `/device/get`, `/kernel/status`, `/input/status` and `/config/usb/get`. Reports each phone's control channel and video channel separately. Video freshness comes from the receiver frame counter advancing, not from `live:true` alone. A still screen can be live.
- **Control.** One lane per phone ([`src/phone-lane.js`](src/phone-lane.js)):
  - It holds that phone's kernel lease. Tokens never leave this process.
  - It renews the lease every 10 s, independently of the command queue.
  - It runs commands strictly one at a time.
  - Stop skips the queue, cancels pending work and latches the kernel's Stop.
  - A command whose outcome is unknown is never retried; the phone is stopped instead.
- **Allowed actions.** Only these ([`src/actions.js`](src/actions.js)): tap, long press, drag, Home / App switcher / Control Centre / Return / Delete / Tab / Esc, US-ASCII text (max 200 characters, sent in 32-character chunks), and reset pointer. The portal can never name a kernel function.
- **Previews.** [`src/preview.js`](src/preview.js) reads the same raw BMP endpoint as the desktop console and encodes small JPEGs on worker threads.
  - One capture loop per watched phone, shared by all viewers and both tiers.
  - Grid tiles are 144 px at about 1 fps; the focused phone is 360 px at up to about 8 fps.
  - Frames are dropped, never queued, when the portal link is backed up.
- **Safety on disconnect.** If the portal link drops, every phone the agent controls is released immediately. Nothing is resumed or replayed on reconnect.

## Why text is chunked

The kernel cancels any single command after 8 s (`InputSessions.ExecuteAsync`), and a cancelled command latches Stop. Typing costs 140–170 ms per character (`InputRouter.Stroke`), so one `/key/sendkey` can safely carry only about 50 characters. `test/conformance.test.mjs` reproduces this against the real kernel source.

## Install on the rack PC (Windows)

1. Install Node.js 22.5 or newer, then run `node --version`.
2. Copy this folder, then run `npm ci`.
3. In the portal, go to **Staff → Racks → Create rack credential**. Save the credential, which is shown once, to a file only the service account can read:
   ```powershell
   Set-Content -Path C:\NodeTheory\rack-credential.txt -Value '<credential>' -NoNewline
   icacls C:\NodeTheory\rack-credential.txt /inheritance:r /grant:r "$env:USERNAME:(R)"
   ```
4. Start it:
   ```powershell
   $env:NT_PORTAL_URL = 'wss://portal.example.com/agent'   # ws://127.0.0.1:8080/agent only for a local test portal
   $env:NT_AGENT_CREDENTIAL_FILE = 'C:\NodeTheory\rack-credential.txt'
   $env:NT_KERNEL_URL = 'http://127.0.0.1:9913/api/'        # default
   npm start
   ```
   The log shows `Connected to portal …`. If the kernel is the simulator, the agent says so. If the kernel lacks `input_protocol: 1` with required leases, input stays disabled.
5. To run it permanently, use a Windows service wrapper such as NSSM or a Task Scheduler "At startup" task, with the same environment variables. Ctrl+C or a service stop releases every phone before exiting.

To revoke access, click **Revoke** in the portal. The agent is disconnected at once and cannot reconnect with that credential.

## Development without a rack

```bash
npm ci
npm run sim          # SIMULATED kernel on 127.0.0.1:9913 — no phones, no USB, no AirPlay
npm test             # unit/contract tests (simulator) + kernel conformance (needs the .NET 8 SDK)
```

- **`sim/kernel-sim.js`** implements the kernel's HTTP contract and ownership rules for development. It stamps every frame "SIMULATOR" and reports `simulated: true`.
- **`conformance/KernelHarness`** compiles the real kernel source (`src/iMouse.Kernel`) with a logging fake in place of USB HID, and synthetic frames in place of AirPlay. `test/conformance.test.mjs` drives it with this agent's own adapter.
  - This checks the adapter against the real ownership logic.
  - It is **not** Windows integration and **not** phone validation.
  - On Windows, HttpListener may need `netsh http add urlacl` or an elevated shell. Set `NT_HARNESS_PORT` to a reserved port.

## Measured

Preview encoding on the development container (one core, synthetic noisy 500×1080 frame): 150 px ≈ 18 ms, 360 px ≈ 42 ms, 500 px ≈ 85 ms per JPEG (`bmp.js` + jpeg-js). Rack-PC numbers are still to be measured (see the Windows checklist in `PORTAL-MILESTONE-1.md`). **Staff → Racks** shows live counters: frames sent, frames dropped under backpressure, and average encode time.

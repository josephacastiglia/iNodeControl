# Notice for the portal and rack agent: re-evaluate TEXT_CHUNK = 32

**For:** branch `claude/focused-noether-s600e0` (tip `6b24a96`, not edited from here). It sets its chunk size independently:
- `portal/server/actions.js`: `export const TEXT_CHUNK = 32`, also used in `commandTimeoutMs` (`15_000 + ceil(len / TEXT_CHUNK) * 9_000`) and `routes/customer.js`.
- `portal/test/units.test.mjs`: asserts the portal and agent values are equal.
- `rack-agent/src/actions.js`: `TEXT_CHUNK`.

**What was found (26–27 Sep 2026):**
- Live on C24C, through the console, with host CPU at 85–100%: one 32-character `/key/sendkey` ran 8,021 ms. The kernel's 8 s deadline cut it after 30 characters (code 33, phone stopped until Resume). Evidence: `live-20260926/check1b-deadline-overrun.txt`.
- Offline, the kernel's own `InputRouter` with its unchanged timing, on a simulated board, measured with spinning threads oversubscribing all 16 cores: 32 characters took 8.4–8.6 s, and the per-character rate reached 371 ms (idle: about 164 ms). Data: `chunk-timing/`. Load effects varied widely between runs.
- The console now uses 12 characters (about 2 s idle, about 4.5 s at the worst measured rate). No size guarantees completion under arbitrary load; an overrun is reported and never retried.

**Asked of the portal work:** evaluate its own `TEXT_CHUNK` against these measurements, including its per-step timeout budget. Keep the agent and portal values equal, as its test requires. Nothing on that branch was changed by this work.

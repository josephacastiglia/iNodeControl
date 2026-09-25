# Next bounded task: console ownership and Stop integration

Work in `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0`.
Read `analysis/input-ownership-20260916/REPORT.md` and `API.md` first.

Codex implemented the kernel ownership boundary and cancellation; 70 kernel
checks pass. Do not replace it with a client-only busy flag. The staged build is
`release/iMouse2-kernel-ownership/iMouse2.Kernel.exe`. It requires input leases.
The desktop console is not compatible yet, so the launcher was left unchanged.

The newer precise-movement deployment failed C241 and was rolled back. Keep
legacy pacing; do not enable `--precise-movement`. See the newer gap audit and
deployment verification linked in the report. Do not run either rejected kernel.

Implement this bounded next step:

1. Add capability detection and a per-phone lease manager to the console API
   layer. Cache tokens privately, renew every ten seconds while controlled, and
   serialize commands per phone. Keep the lease across the full gesture rather
   than resetting ownership for every hover/down/move/up call. Different phone
   sessions may progress independently. Preserve the existing BMP/paint pipeline.
2. Add prominent, plainly named Stop and Resume controls with exact affected-phone
   scope. Stop must bypass `_commandBusy` and any ordinary input queue, cancel
   local hover/drag work, send `/input/stop`, and remain stopped until deliberate
   Resume plus fresh ownership. It must remain available when video is offline.
   Show ownership/expiry/release failures accurately; never auto-retry a rejected tap.
3. Clean up ownership on master/group changes, connection changes, and shutdown.
   Prevent late work from an old UI session from acquiring a fresh token or sending
   into a new session. Group actions must use the exact explicit target/token map.
4. Add meaningful mocked console checks: independent client identities, one lease
   across drag, renewal during work, Stop while busy, no stale hover/click after
   reconnect or Resume, other-phone isolation, expiry UI, group membership changes,
   and unsupported-kernel behavior. Run kernel, console self-tests, and UI mocks.
5. Build to a staging directory; do not overwrite the validated console/kernel or
   edit the one desktop shortcut until the paired build has passed acceptance.
   Record exact hashes, results, and any gaps. No unrelated visual redesign.

No live hardware testing is needed for this UI implementation task. After mocks
pass, prepare a short C24C/C241 live test plan and report readiness for it. Do not
stop vendor services, change firewall, touch other phones, or claim concurrent
automation scheduling is implemented. The scheduler is a later feature.

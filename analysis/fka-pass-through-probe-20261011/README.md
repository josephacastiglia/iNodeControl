# FKA pass-through probe — 11 October 2026

**Repeated within-field success; persistence failed, so Gate 5 remains open.** C24C's Commands page lists Pass-Through Mode as Control–Option–Command–P. Five unique matched-wait API fields produced Hithere / Hi there / Hithere / Hi there / Hithere. The actual unchanged candidate Send text button preserved short text and 100 characters when the shortcut was applied inside that fresh note. Moving to a new note without another shortcut lost the first space again. A same-field append click produced no completion entry or visible change and is unverified. A named mode message was not confirmed. See [REPEAT-REPORT.md](REPEAT-REPORT.md) for the latest evidence and restoration; [LIVE-REPORT.md](LIVE-REPORT.md) preserves the earlier one-sequence result.

## Evidence and scope

The read-only frame `commands-page-4.png` in the main checkout's `analysis/fka-typing-mode-20261011/` shows the command and binding. No command assignment or FKA setting was changed. Apple's [Mac FKA guide](https://support.apple.com/en-my/guide/mac-help/-mchlc06d1059/mac) describes the same shortcut as toggling temporary pass-through. That describes macOS, not verified iOS behavior. C24C must establish whether it keeps spaces and how its mode can be recognized and restored.

The preceding offline investigation loaded the actual release kernel and preserved `b0708e3` console binaries: all 60 assertions passed, including explicit Space reports. Those checks end at the transport method; physical board delivery and iOS insertion are unresolved.

## Isolated candidate

| Item | Value |
|---|---|
| Branch | `local/fka-passthrough-probe` |
| Base | `d0c4ccf2bf7bd7dcc1df99183d305700638e40c4` (`claude/input-timeout-integration`) |
| Worktree | `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-fka-passthrough-probe` |
| Build | `analysis/fka-pass-through-probe-20261011/build/` |
| Kernel DLL SHA-256 | `DC3EF3A46D81F2F3D91BFF0757A0B7564AE1E284FF1FD4BEA83B717BE5AF49B4` |
| New source changes | InputRouter, Program, ApiServer, InputSessionTests, SelfTests |

The build uses the integration source, not an exact copy of the installed release. Existing Home variants and receiver-management source are inherited from that branch; the earlier Home report records two receiver files whose source differs from the release PDB. Before any live window, recheck and record the complete source/binary comparison against the release. No receiver behavior was changed in this probe.

### Test-only operation

- Startup opt-in: `--fka-pass-through probe`; absent or `disabled` leaves the command unavailable. Invalid or missing values exit before data initialization or hardware enumeration.
- Existing leased `/key/sendkey` command: `fn_key=FkaPassThrough`, one phone, no accompanying `key` text. There is no new raw-HID endpoint.
- The exact reports are `A200000000000000`, `A20D130000000000`, `A200000000000000`: neutral, left Control/Option/Command + P, neutral. Existing stroke timing is unchanged.
- Normal per-phone ownership, board serialization, cancellation and cleanup apply. Failed or uncertain toggles are not retried.
- `/kernel/status` exposes `fka_pass_through_probe_enabled`; this reports host capability, **not the phone's mode**.
- Text never automatically toggles pass-through, adds a space, or changes its key mapping. There is no production UI button or automatic workaround.

## Offline validation

Release build: zero warnings/errors. **123 kernel self-tests passed, including 25 new probe checks.** The new checks cover the default-disabled gate, exact reports, unchanged Space output, ownership, one target only, no combined text, competing command rejection, Stop, neutral cleanup, stale tokens and failure without retry. Every transport is injected and simulated.

An initial full-suite run stopped at the pre-existing named-pipe test because the sandbox refused its temporary pipe. The unchanged build then passed the full suite outside that sandbox. This was not a product failure. Three additional invalid-startup checks passed, including a missing option value; data-directory initialization was never reached.

Reproduce **offline only**:

```powershell
dotnet build src/iMouse.Kernel/iMouse.Kernel.csproj -c Release -o analysis/fka-pass-through-probe-20261011/build
dotnet analysis/fka-pass-through-probe-20261011/build/iMouse2.Kernel.dll --self-test
python analysis/fka-pass-through-probe-20261011/verify_invalid_startup.py
```

Do not start this executable normally outside a coordinated phone window; normal startup enumerates hardware and may start receivers.

## Phone-window method — subsequently authorized and run

This test needs the new kernel to emit the shortcut through the existing safeguards. Switching kernels interrupts mirroring, including C241's receiver even though C241 receives no input. Rediscovery previously took up to 31 minutes and once required operator intervention, so no quick recovery is promised. Receiver restart and temporary FKA mode changes need explicit approval. The operator must be available at C24C and for recasting both phones afterward.

1. Record current process paths, hashes, arguments and release configuration. Confirm the phones are idle, C24C is the intended device and no controller owns it. Preserve the working release and restoration instructions. Candidate settings remain isolated with hover tracking off. Leave other agents off the rack.
2. Close the installed console normally and stop the release kernel gracefully. Start this test kernel with copied, isolated C24C-only configuration, the usual Home default and the probe enabled. No force-kill, USB reset, configuration overwrite or automatic settings change. Recast C24C manually; do not proceed without video and a verified free phone.
3. First characterize the shortcut and restoration using normal leased API commands. Prepare a disposable fresh Notes field using physical Home to avoid the known Tab side effect. Record the baseline text, FKA highlight and all submitted reports. Send one explicit toggle, inspect any mode indication, then send `Hi there` as a separate text command under the same lease. Read the visible text, not just response code 0. This is an API-path probe, not console acceptance.
4. If delivery or mode is uncertain, stop without blindly sending a second toggle. Coordinate physical mode restoration with the operator. If the first change and restoration are observable, compare fresh-field baseline / pass-through / restored baseline; a promising result then needs repeated trials through the original candidate's real Send text button, with the helper's lease released and verified free before the console takes ownership. Do not call one success a fix.
5. Verify the original FKA state, release ownership, close the test processes normally and restore the exact release launch. The operator recasts both phones. Check release hashes, settings hash, receiver mapping, no remaining test processes and no C241 input; report any incomplete restoration immediately.

The list above records the proposed method. In the first live window, the operator explicitly authorized C24C-only input, the kernel swap, mirroring interruption and restoration. The shortcut and text used separate leases, not the same lease described in step 3. No named mode indication was verified; restoration used physical FKA Off → On rather than a guessed second toggle. That first window had no desktop automation or console-button acceptance. The subsequent repeat window included the real Send text button and is recorded separately in [REPEAT-REPORT.md](REPEAT-REPORT.md), including completed release and FKA restoration. No deployment or promotion occurred. Earlier six-note results and the first 41-file offline archive remain preserved; this probe is a separate supplement.

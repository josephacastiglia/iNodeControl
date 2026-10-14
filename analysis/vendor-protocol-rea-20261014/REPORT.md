# Vendor HID protocol investigation — 14 October 2026

## Result

REA was useful for understanding the original host-to-board interface. Static
analysis of `MouseKeyItem.dll` resolved the vendor Fn field, traced the shortcut
Tab prelude, and identified movement-completion and identifier reply handlers.
It also revealed an alternate absolute-coordinate path whose support on our
boards is unknown. This is new protocol evidence and offline tooling, not a
product fix or a physical acceptance pass.

No vendor executable or DLL was executed. No rack API, device handle, phone,
desktop window, installed settings, kernel or receiver was operated. Firmware
was not extracted. Typing/FKA experiments remain deferred.

## Provenance and method

Worktree: `iMouseXP-2.0-combined-candidate`, branch
`local/combined-candidate-20261012`, starting at `138f4eb`.
Targets were copied from the original checkout's `build` folder and verified
against their originals. Only these three binaries were copied; vendor account
configuration was excluded.

| Target | SHA-256 | Analysis |
|---|---|---|
| MouseKeyItem.dll | `a57812aed066d1bcf3b665e97813cf0ddc58e8e5e7f425026a45dde424db4a45` | 27 targeted functions decompiled, key paths checked against instructions |
| IMService.exe | `fb6b792a83158df1d457d9588a32e2016ca122c8497eb6215bd73aadc76f1341` | PE inventory only |
| iMouseKeyboard.dll | `c4b2587caf9b3952f254d6b7235cce41d4a3aa8696e50ee511d9bb71bae6fdfe` | PE inventory only |

All three are x86. IMService has `.themida`/`.boot` sections, sparse imports and
high-entropy sections consistent with protection/packing. Its named-export
MouseKeyItem dependency was the more useful static target. No unpacking was
attempted. Addresses below refer to that exact DLL at preferred base
`0x10000000`; they are not addresses to use in a running process.

Tools are portable under `../.tooling/imouse-rea-20261014`: REA 6.5.0, Ghidra
12.1.4, Temurin 21.0.12.1+1, pefile 2024.8.26 and Capstone 5.0.6. REA ran through
its MCP static-analysis tools, with an explicit tool allowlist in `rea_batch.mjs`.
No global install, agent registration, Frida attachment or vendor launch ran.
Pinned Ghidra/JDK downloads were SHA-256 checked; npm's lockfile is archived.
REA needed a permission-reviewed retry because its private snapshot ACL could
not be created in the default sandbox. All three analysis batches subsequently
closed successfully.

Tool sources: [REA](https://github.com/morluto/rea),
[Windows/Ghidra support](https://github.com/morluto/rea/blob/main/docs/windows-ghidra-p0.md),
[Ghidra release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build).

## Findings and implications

### 1. Tab is inserted by the host shortcut wrapper

`CusKeyInput_Union_KeyEx` (`0x1000c050`) prepends Tab and release to many multi-key
shortcuts. The case-insensitive exceptions include `win+c`, `win+x`, `win+v`,
`win+a`, `ctrl+ ` (literal trailing space), and a `CTRL+ALT+SHIFT` prefix.
Commands without `+` skip this generic prelude; explicit Tab combinations have
separate handling. The wrapper uses roughly 30–35 ms prelude delays and a
50–80 ms final chord hold. The underlying USB writer also enforces a minimum
write interval of 30 ms.

This agrees with the saved Home sequence: Tab, release, Command+H, release.
The DLL also exposes direct key operations without the generic wrapper.
Therefore the prelude is host-library policy, not an unavoidable packet-format
requirement. This does **not** prove that removing it provides reliable Home on
iOS. The existing command-h experiment still needs its own physical acceptance.

### 2. The last keyboard payload byte is a separate vendor Fn field

The token table at `0x10019a68` identifies `FN` with pseudo-usage `0x201`.
The parser recognizes that token and passes value `2` in a separate extension;
the writer at `0x100024b0` places it at payload byte 7:

```text
A2 modifier usage0 usage1 usage2 usage3 00 fn
```

Known values are `00` and `02`. This is distinct from Left Shift in modifier
byte 1. Other extension values remain unknown. The saved AppSwitch packet
`A2 00 52 00 00 00 00 02` is vendor Fn+Up; ControlBar uses vendor Fn+C.
Four Fn reports in the historical keyboard capture agree with this decoding.
It does not establish how iOS interprets them with FKA On or Off.

### 3. The vendor reads board replies and waits on movement signals

The background reader at `0x1000cd20` removes the Windows report-ID prefix,
dispatches incoming payloads and maintains per-board events/state:

| Family | What the host library demonstrably does | Limit |
|---|---|---|
| A0 / A1 | Sets a completion flag and signals the event used by movement waits | No decoded sequence ID, physical coordinates or iOS success |
| A5 | Copies six identifier bytes; `HT_GetUID` formats those cached bytes | Not proven equivalent to our DeviceStore UID |
| A6 / AF | Changes recovery/pacing counters and forwards the event | Physical trigger/meaning unverified |
| Other | Forwards through the callback | No local proof of keyboard completion |

Movement paths commonly wait up to 100 ms on this event. Our current
`HidConnection.SendAsync` writes and flushes; it has no incoming-report reader.
That is a useful implementation difference to investigate, but adding waits
blindly could stall input or misattribute late replies. A board signal must
never be promoted to proof of text appearing, an accurate tap, or safe replay.
The incoming layout is static evidence only; this session captured no incoming
payloads from a board. Earlier USB records establish the 16-byte input size.

### 4. An alternate absolute-coordinate mode exists in the library

`HT_SetIOSVer` (`0x1000ca70`) sets a mode field. When that field equals 1,
`HT_MoveToAA` (`0x10008210`) builds:

```text
A0 buttons x-low x-high y-low y-high 00 00
```

The host scales coordinates by the configured dimensions to a 0–32767 range,
then waits for completion. The normal path emits calibrated relative A1 moves.
The setter name alone does not establish which iOS or firmware supports this
mode. No A0 report was sent in this investigation; current-board support,
orientation and accuracy are untested. September's statement that no absolute
packet was **observed** remains true for those captures.

### 5. Pointer position and reset counts are host state

`HT_GetCurrMousePos` (`0x100042a0`) returns cached coordinates, not measured
phone position. Relative reset at `0x100044f0` sends repeated `(-127,-127)`
moves. The default count is 30 but configuration can override it; our historical
capture had four. Do not replace the measured profile with the vendor default.
The reader also influences pacing, so a completed host call is not independent
confirmation of physical position.

`HT_OpenEx` includes A5 and A3 initialization writes and waits. These are static
observations, **not approved safe probes**: do not send speculative queries to
the rack. A serial/UART path also exists; it does not identify the board's MCU.

## Validation and reusable output

- `verify_findings.py`: **14 checks passed** against the exact DLL's bytes,
  table entries and imports, independent of Ghidra's text rendering.
- `tools/test_vendor_hid_decode.py`: **13 offline tests passed** for strict
  framing, direction, signed movement, Fn separation, unknown fields and limits.
- `tools/vendor_hid_decode.py` decoded **221 saved outgoing reports**: 40 in
  `hid-keys-20260914.jsonl` and 181 in `hid-observation-20260914.jsonl`. This was
  a historical capture check, not 221 new phone tests.
- Saved call sites are consistent with the DLL's WriteFile return offset, but
  the historical module base and DLL hash were not recorded. Exact historical
  binary identity is not claimed from an address suffix alone.

The decoder accepts saved bytes only, with explicit direction and framing. It
never opens a device. Example from the repository root:

```powershell
python tools/vendor_hid_decode.py --direction out --framing windows --hex "00 a2 00 52 00 00 00 00 02"
python -m unittest discover -s tools -p test_vendor_hid_decode.py -v
python analysis/vendor-protocol-rea-20261014/verify_findings.py
python analysis/vendor-protocol-rea-20261014/validate_offline.py
```

The last two commands need the pinned local target/tool directory; the combined
validator also reads the original saved captures and writes `validation.json`.
`targets.json`,
`static-inventory.json`, `verified-offsets.json` and the two capture-check JSON
files preserve the selected evidence. Batch inputs and setup scripts preserve
the method. Raw decompilation, target copies, package provenance and logs are
kept in the local archive, not added to source control:

`C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261014-vendor-protocol-rea`

See `archive-verification.json` for verified counts and the manifest hash. This
is local preservation, not an off-machine backup. Candidate/runtime sources and
the staged `combined-timing-20261013` package are unchanged.

## Recommended continuation

Use the decoder to validate **actual incoming reports** in a bounded capture
under the existing lease-aware controller before implementing reply-driven
pacing. Account for late replies, disconnects, cancellation and command scope;
preserve raw bytes and compare against observed phone behavior. Do not start a
second competing device reader or assume it is a passive observer.

Only after that evidence should a candidate add incoming-report diagnostics or
adjust movement pacing. Absolute mode is a separate unvalidated experiment.
No firmware change, automatic retry, FKA workaround, runtime alteration or
promotion follows from this static pass.

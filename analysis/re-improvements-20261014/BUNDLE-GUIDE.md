# Integrated reverse-engineering candidate

14 October 2026. Local review/test package only; not installed or promoted.

This combines the existing input ownership, timeout/cleanup, video and settings
repairs with bounded incoming-board observations, explicit Tab-free navigation
options, a move-only absolute capability probe, and binary/symbol pairing checks.
The native receiver/runtime retain their preceding verified bytes.

## Verify before preparing a separate run

```powershell
python verify_package.py verify --bundle .
python dependencies/receiver-runtime/verify_runtime.py verify --bundle dependencies/receiver-runtime
```

These commands inspect files only. The first checks every recorded file,
preserved source, and both DLL/PDB identities and content checksums. Keep this
bundle immutable; use separate copies for reports and runtime settings.

## Candidate choices

Normal defaults are unchanged. A prepared C24C navigation run uses
`--home-sequence command-h --navigation-sequence direct-fn --hid-replies-pid C24C`.
Fn+H is a separate Home alternative for a defined comparison if needed, not an
automatic fallback. These modes need physical validation before adoption.

The separate absolute probe adds `--absolute-probe-pid C24C`. That mode permits
only pointer moves/reset and refuses all clicks, drags and keyboard commands.
It cannot be used as the everyday console profile. Hardware support is unknown.

All input still requires the normal per-phone lease. There are no raw protocol
endpoints, automatic retries, phone-setting changes or implicit control takeover.
AF and movement replies are diagnostic observations, not action acknowledgements.

## Physical acceptance remains pending

Start nothing from this package without a coordinated window. A temporary
kernel swap interrupts mirroring and requires operator help recasting; discovery
has historically taken up to 31 minutes. Use C24C only and preserve the installed
release/settings/launchers. Confirm restoration of both phones afterward.

The source report contains a bounded acceptance procedure. UI/phone behavior,
absolute support, wider accuracy/recovery, scale/endurance, clean-PC installation
and native redistribution clearance are not established by packaging. Typing's
missing-space issue remains deferred. No release gate is newly signed off.

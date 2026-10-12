# Next: candidate launch preparation

Read-only source review, 12 October 2026. No launcher was executed.

Reuse `tools/candidate-launcher/Start-iMouse2Candidate.ps1`; do not replace the
installed shortcut or `Open iMouse 2.0.ps1` while preparing the candidate.

The existing helper predates the combined startup validation and package records:

- It validates the reported data path but does not verify executable/assembly
  bytes against the recorded candidate build before invoking it. A normal-window
  launch must be tied to the exact validated candidate, not its executable name.
- It starts the optional proxy before probing the console/data directory. A
  later probe failure can leave that proxy running. Complete all offline checks
  before creating a background process and report/clean up owned processes on
  failure through a supported shutdown path.
- A fresh data directory has no `trackPointer:false` preference. The product
  default is On, which can acquire control from a preview hover. The test launcher
  should prepare an explicit observation-safe profile without changing the
  operator's settings or silently modifying an existing profile.
- `-CheckOnly` still contacts the service, deletes `data-path.txt` beside the
  executable and starts the console's reporting mode. Separate a pure offline
  preparation check from live readiness checks. Never write probe output into an
  immutable packaged build; prepare a distinct candidate run directory.
- Endpoint validation/normalization should occur before any request, require the
  intended explicit port, and refuse redirects to another service.

Use the new `--validate-startup` mode only after verifying this exact build
supports it. An old build could interpret an unknown flag as normal startup.
Tests must use synthetic profiles and fake process/network adapters, without
opening the real console, starting services or contacting phones.

This review identifies preparation work, not authorization to launch a candidate
or restart the rack. Physical gates remain open.

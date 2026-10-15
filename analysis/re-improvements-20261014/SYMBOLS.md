# Binary and symbol consistency checkpoint

14 October 2026. Goal item: prevent mismatched managed binaries and debugging
symbols from entering new combined candidate packages.

## Implemented and verified

`tools/managed_symbols.py` reads PE/Portable PDB metadata without loading either
file, running a compiler or following the embedded symbol path. It compares the
full 20-byte identity (GUID plus stamp), verifies CodeView age/type, and checks
the PDB content checksum. Unsupported, missing, truncated or conflicting metadata
is refused with a clear reason. This checker is deliberately scoped to our
external .NET Portable PDB builds, not every Windows symbol format.

The existing `stage_release.py` now checks both managed components before
creating a bundle. Its standalone verifier repeats the check. New bundles carry
the small standard-library-only checker, so verification still works after the
repository has been removed and writes nothing into the bundle. The native
runtime capsule's standalone verifier remains self-contained.

Format details follow the official [.NET PE debug-directory specification](https://github.com/dotnet/runtime/blob/main/docs/design/specs/PE-COFF.md)
and [Portable PDB metadata specification](https://github.com/dotnet/runtime/blob/main/docs/design/specs/PortablePdb-Metadata.md).
The checksum uses the complete PDB with its 20-byte identifier zeroed, as specified.

## Evidence

- 11 symbol-parser checks, 32 package checks, 22 native-runtime packaging checks
  and nine build-manifest checks passed: **74 checks total**.
- Three new package protections fail when the symbol checker is disabled:
  swapped symbols with refreshed build hashes, changed PDB contents with the
  same identity, and a rehashed wrong PDB inside a staged package.
- Actual new kernel DLL/PDB and both managed pairs in the previous immutable
  candidate pass identity and content validation.
- The installed release kernel's mismatched pair is rejected. It was only read;
  no installed file was modified.

See `symbols-validation.json` and the test logs. Fixtures contain synthetic
metadata and no executable code. An initial mutable-bytearray test failure and a
missing lazy import in the standalone native verifier were fixed before the
recorded final run.

## Limits and continuation

This establishes symbol pairing and package consistency, not trusted origin,
reproducible compilation, source correctness or physical acceptance. SHA-256
manifests and the existing source records remain separate checks.

Existing immutable bundles are not rewritten. Their embedded verifiers retain
their recorded behavior. New staging/verification requires `managed_symbols.py`;
use a newly built bundle to receive this protection. The current goal's combined
build will incorporate this check after the remaining source changes are ready.
Home, App Switcher, reply handling and absolute positioning remain separate
pending acceptance items.

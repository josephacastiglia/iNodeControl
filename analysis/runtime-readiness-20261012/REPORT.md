# Candidate runtime inventory

12 October 2026. Read-only host/filesystem inspection, with no receiver, GUI or phone input started.

## Findings

- The patched receiver, plugin scanner and selected software-video pipeline lead to **127 non-system x64 PE files** in the recorded dependency walk. All were inspected and hashed; no missing imports were found in that scope. `native-files-final.json` records paths, hashes and resolution edges.
- The host lists .NET 8.0.14 and 8.0.30 core and Windows Desktop runtimes. This establishes installed runtime entries, not successful execution of the complete candidate on a clean PC.
- **Correction:** the recorded receiver uses built-in mDNS, not an external Apple Bonjour implementation. Its build cache selects `USE_MDNS=1`; current CMake selects `lib/mdnsd`; the receiver's symbol table contains `dnssd_mdnsd.c`, `mdnsd_start` and `mdnsd_announce`. Earlier review guides incorrectly listed Bonjour as a prerequisite. Current guide/package text is corrected; earlier archived packages remain historical, immutable records. No Bonjour service or network setting was changed.
- `process-snapshot.json` found no running iMouse console, kernel, receiver, or dotnet-hosted iMouse assembly. This is a dated snapshot, not ongoing monitoring. The rack remains stopped; no API or phone test was attempted.

## Validation and limitations

The extended native tooling performs a bounded import walk using `objdump -p`; it does not execute the inspected receiver or load its DLLs. Nine synthetic tests pass, covering missing/transitive dependencies, cycles, malformed imports, architecture, system/API contracts and C++ runtime names. The package suite passes 22 cases after the dependency-text correction.

The first native audit rejected legitimate `libstdc++-6.dll` names because the tool's name filter omitted plus signs. That report is retained as `native-files.json`; it is a tooling failure, not twelve missing runtime files. A regression and corrected rerun resolve it.

This does **not** emulate the Windows loader, attest system DLLs or API-set contracts, cover every dynamic/optional plugin, grant redistribution rights, or validate live discovery/decoding. The report always sets `launch_ready: false`. Previous synthetic decoding tests remain separate evidence. A future installer still needs a minimal reproducible runtime distribution and license review; physical acceptance remains open.

The latest review bundle includes the combined console, bounded-logging kernel and patched receiver. It is unpromoted and contains no operator configuration. Source/build hashes, ZIP integrity and an external evidence archive are recorded separately.

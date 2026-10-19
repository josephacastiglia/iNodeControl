# Receiver memory investigation — 12 October 2026

## Result

**A real leak in periodic streaming-report parsing is fixed in source and verified offline.** The installed receiver is unchanged. The effect on the full rack's recorded memory growth still needs later live validation.

The receiver's `case 0x05` parses each nonempty phone performance report with `plist_from_bin`. It previously discarded the local root pointer without freeing the parsed tree, whether or not FPS logging was enabled. The four-line change frees a non-null root after optional logging. Parsing, logging, input behavior and video timing are otherwise unchanged.

## Evidence

The native regression extracts that exact case from the source and uses the real local libplist. It substitutes logging and unrelated receiver state, uses generated dictionaries, and opens no socket. Ownership counters wrap real parsing/freeing calls.

| Test | Original source | Patched source |
|---|---|---|
| 10,000 valid reports, logging off/on, trailer absent/present | All four cases fail: 10,000 roots parsed, zero freed | All four pass: 10,000 roots parsed and freed |
| Private-memory increase in those four cases | 58,060,800–58,171,392 bytes (about 55 MiB) | 0–69,632 bytes |
| 10,000 malformed reports, same four combinations | No parsed roots; all four pass | No parsed roots; all four pass |

The old failure and new success are saved in `reports-before-2/results.json` and `reports-after/results.json`. An initial harness compilation attempt used a nonexistent cleanup function; it failed before running any native test and is preserved under `reports-before/`. The corrected harness uses `plist_mem_free` for its own serialized fixture buffer.

These generated reports do not establish the size or frequency of actual phone reports. They prove this ownership leak; they do not prove it explains all of September's roughly 18–19 MB/hour growth per receiver.

## Native build provenance

Before modifying product source, the complete receiver was rebuilt into `provenance/build` using the existing local compiler and libraries. **All 34 compiled objects match the saved objects byte-for-byte.** The rebuilt and installed executables have the same length. Their only eight differing bytes lie in the COFF timestamp, export timestamp and PE checksum fields. Ignoring only those fields makes the entire binaries identical.

That establishes reproduction from the current local source/dependencies, not authentication of the historical dependency supply chain or the exact dynamic libraries loaded during September's run. Source hashes, commands, object/section comparisons and normalization offsets are saved in `provenance/`.

The patched full receiver also builds into `patched-build/build`. Exactly one of the 34 objects differs: `raop_rtp_mirror.c.obj`. Its executable is a scratch artifact and was never launched or installed.

- Installed receiver SHA-256: `4c1a24f35de00d2c3a8d50a4b0bcfb06a9f5c16bd185810ec54466ac090d2208`.
- Patched scratch receiver SHA-256: `46fd3c38745fd63bdd188c45c98b55f1a875ecce5dc7718d07e5d150e31cb136`.

## Synthetic video comparison

The separate probe includes the production frame-bridge header unchanged. It generates 500 × 1080 video at a requested 30 fps, testing raw and H.264 video with either sample disposal or the BMP callback. H.264 uses local OpenH264 encoding and `avdec_h264` decoding. The bridge writes only to a newly created, PID-specific local pipe consumed by the same test process; it never uses a kernel frame pipe.

Four three-second smoke tests and all four 180-second measurement runs completed successfully. Measurements use a declared 30-second warm-up and exclude teardown from slope fitting. Final machine-readable results are in `run-180s/summary.json`.

| Synthetic path | Frames processed | Frames received by private pipe | Private-memory slope after warm-up |
|---|---:|---:|---:|
| Raw, discard samples | 5,400 | Not used | 0.00 MiB/hour |
| Raw, production BMP callback | 5,401 | 5,401 | 0.00 MiB/hour |
| H.264 encode/decode, discard samples | 5,401 | Not used | −5.94 MiB/hour |
| H.264 encode/decode, production BMP callback | 5,402 | 5,402 | −5.95 MiB/hour |

The raw paths were flat after warm-up. The H.264 paths varied downward by 229,376 bytes over their measured intervals; annualizing or extrapolating that short-term trimming is not a prediction of long-term behavior. No sustained growth was reproduced in these four limited video conditions.

This is a limited rendering comparison. It excludes AirPlay transport/report handling, audio, reconfiguration, reconnects and iPhone-encoded stream variations. Short flat traces cannot rule out other receiver leaks or pass endurance acceptance. Loaded runtime DLLs are recorded and hashed separately.

## Validation and operating scope

- Eight native ownership regression cases pass after the fix; four valid-report cases failed before it.
- Eight offline tool tests pass for slope calculations, warm-up/teardown filtering, insufficient evidence, isolated child settings and narrow PE normalization. Native source and probe compilation are also exercised by the commands above.
- No phone input, desktop control, kernel API request, AirPlay advertisement, installed-process restart, setting change or deployment occurred.
- The installed kernel, console and receiver hashes match their recorded release values.
- Changes are local, uncommitted and unpushed. Earlier unrelated working-tree changes are preserved.

## Next

Keep this receiver patch as an offline-verified candidate. Later, during a separately coordinated window, measure the complete patched receiver against the existing workload with recorded warm-up and resource budgets. Do not restart the rack merely to apply this fix.

Continue offline with the existing accuracy-harness consolidation and simulated recovery checks. Missing-space/FKA work remains deferred at the operator's request.

Commands and test limitations: `tools/receiver_memory_probe/README.md`.

The completed record, source snapshot, scratch builds and focused product patch are preserved in the local archive `../iMouseXP-2.0-evidence-archive/20261012-receiver-memory/`, with a SHA-256 inventory. This is a local evidence copy, not an upload or deployment.

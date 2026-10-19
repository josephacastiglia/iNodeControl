# Offline receiver memory checks

These tools exercise synthetic data only. They do not start UxPlay, announce an
AirPlay receiver, contact the kernel, open a phone, or control the desktop.
They use the existing local MSYS2 compiler and libraries; nothing is installed.
Run commands from the repository root. Every output folder must be new.

## Streaming-report regression

```powershell
python tools/receiver_memory_probe/test_reports.py --out analysis/my-report-regression
```

The test extracts the exact `case 0x05` body from `raop_rtp_mirror.c` and compiles
it against the real local libplist. Logging and unrelated receiver state are
replaced. Eight combinations cover logging on/off, the 25 KB trailer, and valid
or malformed reports. Each child handles 10,000 synthetic reports. Wrappers
count parsed and freed roots while still calling the real library; a leaked
root makes the test fail. Private-memory deltas provide supporting evidence.

This tests report ownership, not networking, the phone's actual report schema,
or the complete receiver's long-term memory behavior.

## Generated-video comparison

```powershell
python tools/receiver_memory_probe/run.py --out analysis/my-video-probe --seconds 180 --warmup 30
```

Four separate children test raw and encoded/decoded H.264 video, each with
either sample disposal alone or the unchanged production BMP frame callback.
Frames are 500 × 1080 at a requested 30 fps. The bridge uses a new local pipe
named for the child PID and an in-process consumer that checks framing and BMP
dimensions. No installed frame pipe is used. Per-child environment overrides
remove inherited iMouse/GStreamer settings and use a private plugin cache.

The H.264 source uses the locally installed OpenH264 encoder and `avdec_h264`.
It is not a recording of an iPhone's compressed stream. The comparison excludes
AirPlay transport, audio, reconnects, changing resolution and receiver startup
logic. A short flat trace cannot rule out leaks elsewhere.

Each child is bounded to the requested duration plus 30 seconds. Pipe failures,
pipeline errors and mismatched frame counts fail the run. Logs record loaded
modules; `runtime-modules.json` hashes the runtime DLLs actually loaded by the
probe. `summary.json` fits private-memory slope after the declared warm-up,
excluding the final teardown sample. It never reports release acceptance.

## Scratch native build and provenance

```powershell
python tools/receiver_memory_probe/provenance.py --out analysis/my-receiver-build
```

This builds into the new output folder without running or installing the
receiver. It compares the result with `tools/airplay/uxplay/build-imouse` and
records source hashes, all saved object comparisons and executable sections.
The normalized comparison ignores only COFF/export timestamps and the PE
checksum. It does not modify either executable. A candidate with a source fix
should differ from the installed receiver.

Matching output establishes reproduction with the current local dependencies.
It does not authenticate an upstream download or establish which dynamic DLLs
were loaded during a historical rack run.

## Tool checks

```powershell
python -m unittest discover -s tools/receiver_memory_probe -p test_tools.py -v
```

These eight tests cover slope calculations, warm-up/teardown exclusion,
insufficient evidence, child-environment isolation and narrowly scoped binary
normalization. They launch no native process.

Keep synthetic results separate from live acceptance. Never copy a scratch
receiver over the working installation or restart receivers as part of these
checks. The 12 October investigation is recorded in
`analysis/receiver-memory-20261012/REPORT.md`.

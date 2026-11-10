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

## Test a staged runtime

The existing generated-video probe accepts `--toolchain-runtime` for compilation
and a different `--test-runtime` for execution. Set `--reference-receiver` to the
installed executable to hash it before/after without running it. With a reduced
runtime, keep the synthetic `videotestsrc`/OpenH264 encoder plugins and encoder
DLL in separate `--test-plugins` and `--test-dlls` folders. They are test support,
not product dependencies. Duplicate runtime DLL names in the test folder fail.

Each child's PATH contains only the chosen runtime, explicit test DLLs and Windows
folders. GStreamer uses a private registry and the selected scanner/plugins.
Loaded modules outside the declared runtime/support/Windows/executable are a test
failure. Source, runtime path and actual loaded-library hashes are recorded.
Five-second runs are functional smoke checks, not memory-slope evidence.

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
`analysis/receiver-memory-20261012/REPORT.md` at tag `evidence-20261109` (`docs/EVIDENCE.md`); the fix
it led to is `tools/airplay/patches/0003-free-periodic-report-plist.patch`.
# Offline runtime file audit

`runtime_audit.py` uses an explicitly selected `objdump` to read x64 PE import
tables. It never starts UxPlay or loads GStreamer plugins. Pass `--receiver`,
`--runtime`, `--system-dir`, `--objdump`, and a new `--out` JSON filename.
The seeded plugins cover the configured software video and fakesink audio
pipelines, including UxPlay's unconditional playback/autodetect startup checks.
It follows non-system DLL imports, records hashes, and lists unresolved imports.

This is a file inventory, not a Windows loader emulator or launch approval. System
DLLs are checked for presence; API-set contracts and dynamic dependencies are not
fully validated. It does not verify networking, discovery, decoding or licenses.
Run `python tools/receiver_memory_probe/test_runtime_audit.py` for ten offline
fixture tests. Reports cannot overwrite an existing evidence file.

## Renderer startup check (no receiver or phone)

Before a live window, test the reduced runtime with the production renderer
initialization code, not only the generated-video pipeline:

```powershell
python tools/receiver_memory_probe/check_startup.py --out analysis/my-renderer-startup --toolchain-runtime <ucrt64> --test-runtime <capsule>/runtime --receiver-source <package>/source/receiver
```

This builds a small executable linked to the selected receiver's unchanged audio/video
renderers and logger. It calls `gstreamer_init`, initializes the AAC/ALAC fakesink
audio pipelines and H.264 appsink video pipeline, starts the video renderer and
tears down. It does not link UxPlay's server, advertise a name, contact a phone,
play sound, open a window or connect to the installed frame pipe. Children have
bounded timeouts, restricted runtime search paths and a private plugin registry.
The result records source and loaded-module hashes; unexpected modules fail it.

The 13 October live startup exposed playback/autodetect missing from the earlier
video-only capsule. The check reproduces that failure offline. A passing result
checks renderer initialization only; it does not prove discovery, transport,
live audio/video decoding, or clean-PC compatibility. Keep the old failure record.

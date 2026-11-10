# The AirPlay receiver: UxPlay 1.74 with three changes

The farm's receiver (`uxplay.exe`) is a build of the source in `uxplay/`. This file says where that
source comes from, what was changed, how to build it, and under which terms it may be passed on. A
release package carries this file beside the binary as `receiver/NOTICE.md`, the licence as
`receiver/LICENSE`, and this whole folder as `receiver/source/`.

## Where it comes from

- Upstream: UxPlay, https://github.com/FDH2/UxPlay
- Commit: `44024fe07f7f` (version 1.74). The id is abbreviated on purpose: the release build refuses
  any 40-digit hexadecimal string in a packaged text file, because phone IDs look like that.
- Fetched 14 Sep 2026 as GitHub's source archive `FDH2-UxPlay-44024fe`
  (SHA-256 of that download: `a7fdd56cc3f7009af756ab170ca444ff6825ce8f3cb5b3ba756f2db0b9ae8b18`).

## Licence

UxPlay is free software under the **GNU General Public License, version 3** (`uxplay/LICENSE`).
Two bundled libraries carry their own notices: `uxplay/lib/playfair/LICENSE.md` (GPL 3) and
`uxplay/lib/llhttp/LICENSE-MIT` (MIT). The changes below are published under the same terms as UxPlay
(GPL 3 or later). Anyone who receives the binary is entitled to this source and may change and pass
on both under the GPL; there is no warranty.

## What was changed

`uxplay/` is the upstream commit plus exactly these three patches, in order (checked on 9 Nov 2026:
the archive above with the patches applied is byte-identical to the files Git stores in `uxplay/`;
compare with `core.autocrlf=false`, since a Windows checkout may rewrite line endings):

| Patch | File | Change | Date |
|---|---|---|---|
| `patches/0001-add-imouse-frame-pipe.patch` | `renderers/imouse_frame_pipe.h` (new) | When `IMOUSE2_FRAME_PIPE` names a local pipe, every decoded video frame is also written to it as a BMP. This is how the kernel sees a phone's screen. Without the variable nothing changes. | Sep 2026 |
| `patches/0002-attach-frame-pipe-to-video-renderer.patch` | `renderers/video_renderer.c` | Three lines that attach the frame pipe to the video pipeline and tell it when the stream stops. | Sep 2026 |
| `patches/0003-free-periodic-report-plist.patch` | `lib/raop_rtp_mirror.c` | Frees the parsed property list of each periodic streaming report, which upstream leaks. | 12 Oct 2026 |

To update UxPlay: take the new upstream commit, apply the three patches, replace `uxplay/`, and record
the new commit and archive hash here.

## Building

`build-receiver.sh`, in an MSYS2 UCRT64 shell with the packages upstream's README lists for Windows
(cmake, ninja, gcc, GStreamer and its plugins, libplist, OpenSSL). The result is
`uxplay/build-imouse/uxplay.exe`; it needs the MSYS2 UCRT64 runtime folder beside it at run time
(the kernel's `--receiver-runtime`).

The script passes `-DNO_MARCH_NATIVE=ON`. Without it, upstream's `lib/CMakeLists.txt` compiles the
C library with `-O3 -march=native`, which uses whatever instructions the building PC's CPU has; such
a binary can stop with an illegal-instruction error on a different CPU.

## The binary in use today was built for one PC

The receiver the rack runs, and the one in the 5 Nov 2026 package, is SHA-256
`46fd3c38745fd63bdd188c45c98b55f1a875ecce5dc7718d07e5d150e31cb136`. It was built on 12 Oct 2026 from
exactly this source with the recipe in `tools/receiver_memory_probe/provenance.py`, before the flag above was set:
its configure log says `Using CFLAGS with -march=native` (the log is in the private evidence archive,
`20261012-receiver-memory/patched-build/build-0.txt`). It is known to run on the development PC only.
**Rebuild with `build-receiver.sh` before a package goes to any other PC.** No build has been made
with the corrected script yet.

## What ships beside it

The GStreamer and MSYS2 runtime files that a package carries under `receiver/runtime/` are separate
third-party programs and libraries under their own licences (mostly LGPL). Their licence texts and
sources are not collected in the package yet, so a package is for this operator's own PCs and is
not cleared for redistribution (`release.json`: `redistribution_cleared: false`).

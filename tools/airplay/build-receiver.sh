#!/usr/bin/env bash
# Builds the receiver (uxplay/build-imouse/uxplay.exe) in an MSYS2 UCRT64 environment. See UPSTREAM.md.
# NO_MARCH_NATIVE: without it upstream compiles its C library with -march=native, and the binary
# then runs only on CPUs like the one that built it.
set -euo pipefail
export PATH="/ucrt64/bin:/usr/bin:$PATH"
cd "$(dirname "$0")/uxplay"
cmake -S . -B build-imouse -G Ninja -DCMAKE_BUILD_TYPE=Release -DUSE_MDNS=1 -DNO_MARCH_NATIVE=ON
cmake --build build-imouse -j 4

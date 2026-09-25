#!/usr/bin/env bash
set -euo pipefail
export PATH="/ucrt64/bin:/usr/bin:$PATH"
cd "$(dirname "$0")/uxplay"
cmake -S . -B build-imouse -G Ninja -DCMAKE_BUILD_TYPE=Release -DUSE_MDNS=1
cmake --build build-imouse -j 4

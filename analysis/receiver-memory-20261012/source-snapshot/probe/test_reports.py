"""Native regression on the exact streaming-report case extracted from source.

No sockets or receiver startup. Real libplist parses synthetic reports; only
logging and unrelated receiver state are replaced. Ownership counters wrap the
real libplist functions, and memory is measured in the probe process itself.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from run import ROOT, RUNTIME, environment

SOURCE = ROOT / "tools/airplay/uxplay/lib/raop_rtp_mirror.c"
PREAMBLE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <stdint.h>
#include <windows.h>
#include <psapi.h>
#include <plist/plist.h>
static int parsed, released;
static void parse_report(const char *p, uint32_t n, plist_t *root) {
    plist_from_bin(p, n, root); if (*root) parsed++;
}
static void release_report(plist_t root) {
    if (root) released++; plist_free(root);
}
static unsigned long long memory(void) {
    PROCESS_MEMORY_COUNTERS_EX m = {0}; m.cb = sizeof(m);
    if (!GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS *)&m, sizeof(m))) exit(5);
    return m.PrivateUsage;
}
#define plist_from_bin parse_report
#define plist_free release_report
#define logger_log(...) ((void)0)
static char *utils_data_to_string(const void *p, int n, int width) {
    (void)p; (void)n; (void)width; return calloc(1, 32);
}
static void process_report(unsigned char *payload, int payload_size, bool show, bool logger_debug) {
    struct {bool show_client_FPS_data;} state = {show}, *raop_rtp_mirror = &state;
    switch (5) {
'''
POSTAMBLE = r'''
    }
}
#undef plist_from_bin
#undef plist_free
int main(int argc, char **argv) {
    if (argc != 4) return 2;
    bool show = atoi(argv[1]), trailer = atoi(argv[2]), malformed = atoi(argv[3]);
    plist_t root = plist_new_dict();
    for (int i = 0; i < 24; i++) {
        char key[32]; snprintf(key, sizeof(key), "synthetic-metric-%d", i);
        plist_dict_set_item(root, key, plist_new_uint(i));
    }
    char *bin = NULL; uint32_t size = 0; plist_to_bin(root, &bin, &size); plist_free(root);
    int bytes = size + (trailer ? 25000 : 0);
    unsigned char *payload = calloc(1, bytes); memcpy(payload, bin, size); plist_mem_free(bin);
    if (malformed) memset(payload, 0, size);
    unsigned long long before = memory();
    for (int i = 0; i < 10000; i++) process_report(payload, bytes, show, true);
    unsigned long long after = memory();
    free(payload);
    printf("{\"parsed\":%d,\"released\":%d,\"private_growth_bytes\":%lld}\n", parsed, released, (long long)after-(long long)before);
    return parsed == released && parsed == (malformed ? 0 : 10000) ? 0 : 1;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    source = SOURCE.read_text(encoding="utf-8")
    # Unique anchors fail loudly if upstream changes; never test a stale copy.
    assert source.count("case 0x05:") == 1
    start = source.index("case 0x05:")
    end = source.index("            default:", start)
    case = source[start:end]
    (out / "extracted-case.c").write_text(case, encoding="utf-8")
    generated = out / "report-test.c"
    generated.write_text(PREAMBLE + case + POSTAMBLE, encoding="utf-8")
    env = environment(out)
    flags = subprocess.check_output([str(RUNTIME / "bin/pkgconf.exe"), "--cflags", "--libs", "libplist-2.0"], env=env, text=True)
    exe = out / "report-test.exe"
    command = [str(RUNTIME / "bin/cc.exe"), "-O2", str(generated), "-o", str(exe), *shlex.split(flags), "-lpsapi"]
    build = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
    (out / "build.txt").write_text(build.stdout + build.stderr, encoding="utf-8")
    if build.returncode: raise RuntimeError(build.stderr)
    results = []
    for show in (0, 1):
        for trailer in (0, 1):
            for malformed in (0, 1):
                result = subprocess.run([str(exe), str(show), str(trailer), str(malformed)], env=env,
                                        capture_output=True, text=True, timeout=30)
                row = {"show": bool(show), "trailer": bool(trailer), "malformed": bool(malformed),
                       "returncode": result.returncode, **json.loads(result.stdout)}
                results.append(row); print(json.dumps(row), flush=True)
    record = {"source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "extracted_sha256": hashlib.sha256(case.encode()).hexdigest(), "results": results}
    (out / "results.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return 0 if all(r["returncode"] == 0 for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

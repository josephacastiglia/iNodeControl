"""Build and run only the synthetic probe, never the UxPlay receiver.

Fresh output is mandatory. Child timeout bounds pipe/pipeline teardown failures.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tools/airplay/msys64/ucrt64"
SOURCE = Path(__file__).with_name("probe.c")
RECEIVER = ROOT / "tools/airplay/uxplay/build-imouse/uxplay.exe"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment(out):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("GST_", "IMOUSE2_")):
            del env[key]
    env["PATH"] = str(RUNTIME / "bin") + os.pathsep + env.get("PATH", "")
    env["GST_PLUGIN_SYSTEM_PATH_1_0"] = str(RUNTIME / "lib/gstreamer-1.0")
    env["GST_PLUGIN_PATH_1_0"] = ""
    env["GST_PLUGIN_SCANNER_1_0"] = str(RUNTIME / "libexec/gstreamer-1.0/gst-plugin-scanner.exe")
    env["GST_REGISTRY_1_0"] = str(out / "registry.bin")
    return env


def summarize(rows, warmup):
    # Exclude final post-teardown sample and predeclared warm-up.
    points = [r for r in rows[:-1] if r["seconds"] >= warmup]
    if len(points) < 10:
        return {"status": "insufficient_samples"}
    xs = [p["seconds"] / 3600 for p in points]
    ys = [p["private_bytes"] / 1048576 for p in points]
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x-xbar)*(y-ybar) for x, y in zip(xs, ys)) / sum((x-xbar)**2 for x in xs)
    return {"status": "measured", "samples": len(points), "warmup_seconds": warmup,
            "private_mib_per_hour": slope, "private_range_bytes": max(p["private_bytes"] for p in points)-min(p["private_bytes"] for p in points),
            "frames": rows[-1]["frames"], "received": rows[-1]["received"],
            "seconds": rows[-1]["seconds"], "acceptance": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--warmup", type=int, default=30)
    args = parser.parse_args()
    if not 2 <= args.seconds <= 1800 or not 0 <= args.warmup < args.seconds:
        parser.error("require 2..1800 seconds and 0 <= warmup < seconds")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = environment(out)
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in (
        SOURCE, Path(__file__), RECEIVER,
        ROOT / "tools/airplay/uxplay/renderers/imouse_frame_pipe.h")}
    flags = subprocess.check_output([str(RUNTIME / "bin/pkgconf.exe"), "--cflags", "--libs",
        "gstreamer-app-1.0", "gstreamer-video-1.0"], env=env, text=True, timeout=30)
    exe = out / "receiver-memory-probe.exe"
    command = [str(RUNTIME / "bin/cc.exe"), "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter",
               str(SOURCE), "-o", str(exe), *shlex.split(flags), "-lpsapi"]
    build = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
    (out / "build.txt").write_text(build.stdout + build.stderr, encoding="utf-8")
    if build.returncode:
        raise RuntimeError(f"compile failed: {build.stderr}")
    packages = [p.name for p in (ROOT / "tools/airplay/msys64/var/lib/pacman/local").iterdir()
                if any(s in p.name for s in ("gstreamer", "gst-", "ffmpeg", "glib2", "gcc-"))]
    provenance = {"source_hashes": hashes, "exe_sha256": sha(exe), "build_command": command,
                  "packages": sorted(packages), "scope": "current local source/dependencies, not installed receiver source attestation"}
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    summaries = {}
    for codec, mode in [("raw", "discard"), ("raw", "bridge"), ("h264", "discard"), ("h264", "bridge")]:
        name = f"{codec}-{mode}"
        print(f"Starting {name} ({args.seconds}s)", flush=True)
        with (out / f"{name}.jsonl").open("x", encoding="utf-8") as stdout, (out / f"{name}.log").open("x", encoding="utf-8") as stderr:
            result = subprocess.run([str(exe), mode, codec, str(args.seconds)], env=env,
                                    stdout=stdout, stderr=stderr, timeout=args.seconds + 30)
        if result.returncode:
            raise RuntimeError(f"{name} failed ({result.returncode}); see log")
        rows = [json.loads(line) for line in (out / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]
        summaries[name] = summarize(rows, args.warmup)
        print(json.dumps({name: summaries[name]}), flush=True)
    module_hashes = {}
    for logfile in out.glob("*.log"):
        for line in logfile.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("module: "):
                p = Path(line[8:])
                if p.is_relative_to(RUNTIME):
                    module_hashes[str(p.relative_to(RUNTIME))] = sha(p)
    (out / "runtime-modules.json").write_text(json.dumps(module_hashes, indent=2), encoding="utf-8")
    summaries["installed_receiver_unchanged"] = sha(RECEIVER) == hashes[str(RECEIVER.relative_to(ROOT))]
    (out / "summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    if not summaries["installed_receiver_unchanged"]:
        raise RuntimeError("installed receiver hash changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Exercise production renderer startup offline with only the selected runtime.

Does not link UxPlay's main/server, discovery, socket service or HID code.
Output is immutable and each child is bounded. This is not AirPlay acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess

from run import ROOT, environment, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("out", "toolchain-runtime", "test-runtime"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--receiver-source", type=Path, default=ROOT / "tools/airplay/uxplay",
                        help="exact saved source tree for the receiver being checked")
    args = parser.parse_args()
    out, toolchain, runtime = (p.resolve() for p in (args.out, args.toolchain_runtime, args.test_runtime))
    if not toolchain.is_dir() or not runtime.is_dir():
        parser.error("both runtime directories must exist")
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name("startup_probe.c")
    native = args.receiver_source.resolve()
    sources = [source, native / "renderers/audio_renderer.c", native / "renderers/video_renderer.c", native / "lib/logger.c"]
    headers = list((native / "renderers").glob("*.h")) + list((native / "lib").glob("*.h"))
    build_env = environment(out, toolchain)
    flags = subprocess.check_output([str(toolchain / "bin/pkgconf.exe"), "--cflags", "--libs",
        "gstreamer-app-1.0", "gstreamer-video-1.0"], env=build_env, text=True, timeout=30)
    exe = out / "renderer-startup-probe.exe"
    command = [str(toolchain / "bin/cc.exe"), "-O2", "-DWIN32", "-Wall", "-Wextra", "-Wno-unused-parameter", "-I" + str(native / "renderers"),
               *map(str, sources), "-o", str(exe), *shlex.split(flags), "-lpsapi", "-lws2_32"]
    build = subprocess.run(command, env=build_env, capture_output=True, timeout=60)
    (out / "build.log").write_bytes(build.stdout + build.stderr)
    if build.returncode:
        raise RuntimeError("Renderer probe compile failed; see build.log")
    env = environment(out, runtime)
    with (out / "stdout.log").open("xb") as stdout, (out / "stderr.log").open("xb") as stderr:
        result = subprocess.run([str(exe)], cwd=out, env=env, stdout=stdout, stderr=stderr, timeout=30)
    loaded, unexpected = {}, []
    windows = Path(env.get("SystemRoot", r"C:\Windows")).resolve()
    for line in (out / "stderr.log").read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("module: "):
            continue
        path = Path(line[8:]).resolve()
        if path.is_relative_to(runtime):
            loaded[str(path)] = sha(path)
        elif path != exe and not path.is_relative_to(windows):
            unexpected.append(str(path))
    report = {"exit_code": result.returncode, "passed": result.returncode == 0 and bool(loaded) and not unexpected,
              "sources": {str(p): sha(p) for p in [*sources, *headers, Path(__file__), Path(__file__).with_name("run.py")]},
              "build_command": command, "probe_sha256": sha(exe), "runtime": str(runtime),
              "loaded_runtime_modules": loaded, "unexpected_modules": unexpected,
              "receiver_started": False, "phone_input": False,
              "scope": "Production renderer initialization/teardown only; no AirPlay transport, decoding workload or physical acceptance."}
    (out / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "exit_code", "unexpected_modules", "scope")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

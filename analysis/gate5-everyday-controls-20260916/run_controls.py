"""Gate 5 navigation capture: one explicitly selected C24C action, no retries.

Default invocation verifies saved preparation only; it makes no network calls.
The original September runner/results remain in Git history. This revision does
not reproduce that two-phone, pre-lease run or overwrite its evidence. It reuses
the current Gate 4 lease transport, not a second input implementation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools"))
import gate4_1000_tap_suite as transport

RECORD = REPO / "analysis/re-improvements-20261014"
LIVE_ROOT = RECORD / "live-navigation"
PHONE = "86:1D:4A:04:2F:F6"
BINDING = {"deviceid": PHONE, "pid": "C24C", "uid": "C24CBFBD", "receiver_name": "iMouse2-C24C"}
CASES = {
    "home-field": ("Home", "Home visible; manually return and compare disposable note with baseline"),
    "home-settings": ("Home", "Home visible from the operator-prepared benign Settings page"),
    "home-idle": ("Home", "Home visible after at least 60 seconds without input"),
    "app-switcher": ("AppSwitch", "App Switcher cards visible; no text mutation"),
    "control-center": ("ControlBar", "Control Centre visible; no text mutation"),
}
FLAGS = ("active", "stopped", "releasing", "release_failed")


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_preparation(record=RECORD):
    """Read-only local validation, before any network access."""
    record = Path(record)
    prep = load(record / "preparation.json")
    saved = prep["kernel_validation"]
    require(saved["allowed"] == ["C24C"] and saved["hid_reply_boards"] == ["C24C"]
            and saved["absolute_probe_board"] is None and saved["home_sequence"] == "command-h"
            and saved["navigation_sequence"] == "direct-fn", "Wrong prepared navigation scope")
    url = saved["address"].rstrip("/")
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == 9913
            and parsed.path == "/api" and not parsed.query and not parsed.fragment
            and not parsed.username and not parsed.password, "Unexpected candidate endpoint")
    run = Path(prep["run_directory"]).resolve()
    inventory = load(record / "run-inventory.json")
    required = {"kernel/bin/iMouse2.Kernel.dll", "kernel/bin/iMouse2.Kernel.pdb",
                "kernel/data/devices.json", "kernel/data/receivers.json", "kernel/data/pointer-calibration.json",
                "console/data/settings.json"}
    require(required <= inventory.keys(), "Incomplete prepared inventory")
    for relative, row in inventory.items():
        target = (run / relative).resolve()
        require(target.is_relative_to(run), "Inventory path escapes the prepared run")
        require(target.is_file() and target.stat().st_size == row["bytes"] and sha(target) == row["sha256"],
                "Prepared file changed: " + relative)
    require(sha(run / "kernel/bin/iMouse2.Kernel.dll") == saved["build"]["sha256"], "Prepared build mismatch")
    devices = load(run / "kernel/data/devices.json")
    require(len(devices) == 1 and all(devices[0].get(k) == BINDING[k] for k in ("deviceid", "pid", "uid")),
            "Prepared board binding mismatch")
    settings = load(run / "console/data/settings.json")
    require(settings.get("trackPointer") is False and settings.get("address", "").rstrip("/") == "http://127.0.0.1:9913",
            "Candidate settings must disable hover tracking and specify port 9913")
    return {"url": url, "kernel_sha256": saved["build"]["sha256"], "run_directory": str(run),
            "preparation_sha256": sha(record / "preparation.json"), "inventory_sha256": sha(record / "run-inventory.json")}


class CaptureKernel(transport.Kernel):
    """Same lease API, with redirects/proxies disabled and bounded captures."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    def _req(self, method, url, body=None, timeout=25):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), self.NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        require(len(raw) <= 16 * 1024 * 1024, "Oversized kernel response")
        return raw

    def devices(self):
        envelope = json.loads(self._req("GET", self.url + "/device/get", timeout=5))
        require(envelope.get("status") == 200 and envelope.get("data", {}).get("code") == 0, "Device query refused")
        return envelope["data"]["list"]


def verify_kernel(status, plan, pid, started=None):
    require(status.get("code") == 0 and status.get("input_leases_required") is True
            and status.get("allowed") == ["C24C"], "Running kernel is not C24C-only with leases")
    process = status.get("process", {})
    require(process.get("pid") == pid and bool(process.get("started_utc")), "Candidate process identity mismatch")
    require(started is None or process["started_utc"] == started, "Candidate restarted during the check")
    require(status.get("build_identity", {}).get("sha256") == plan["kernel_sha256"], "Running kernel hash mismatch")
    config = status.get("input_configuration", {})
    require(config.get("hid_reply_boards") == ["C24C"] and "absolute_probe_board" in config
            and config["absolute_probe_board"] is None, "Unexpected reply or absolute-probe configuration")
    controls = status.get("control_compatibility", {})
    require(controls.get("home_sequence") == "command-h" and controls.get("home_sends_tab") is False
            and controls.get("navigation_sequence") == "direct-fn" and controls.get("navigation_sends_tab") is False,
            "Running shortcuts do not match the prepared navigation profile")
    receivers = status.get("receivers", [])
    require(len(receivers) == 1 and receivers[0].get("deviceid") == PHONE
            and receivers[0].get("name") == "iMouse2-C24C", "Candidate receiver scope mismatch")
    return receivers[0]


def verify_lease(rows, owned):
    require(set(rows) == {PHONE}, "Unexpected enabled input scope")
    row = rows[PHONE]
    require(row.get("owned") is owned and all(row.get(flag) is False for flag in FLAGS),
            "C24C is busy, stopped or recovering; no takeover or Resume attempted")
    if owned:
        require(row.get("lease_remaining_ms", 0) >= 30000, "Insufficient lease time for one bounded action")
    return row


def preflight(kernel, plan, pid, started=None, owned=False, *, confirmed_still=False):
    status = kernel.status()
    receiver = verify_kernel(status, plan, pid, started)
    age = receiver.get("frame_age_ms")
    require(receiver.get("live") is True and receiver.get("frame_pipe_connected") is True
            and isinstance(age, (float, int)) and age >= 0
            and isinstance(receiver.get("frames"), int) and receiver["frames"] > 0
            and (age <= 5000 or confirmed_still), "Fresh C24C video or an explicitly confirmed still baseline required; no input sent")
    devices = kernel.devices()
    matches = [row for row in devices if row.get("deviceid") == PHONE]
    require(len(matches) == 1 and all(matches[0].get(k) == v for k, v in BINDING.items())
            and matches[0].get("state") == 1, "Live C24C board/phone/receiver binding mismatch")
    lease = verify_lease(kernel.input_status(), owned)
    return status, lease


def frame(kernel, destination, name):
    raw = kernel.shot(PHONE)
    transport.grid(raw)
    path = destination / name
    path.write_bytes(raw)
    return {"file": name, "sha256": sha(path), "captured_utc": utc()}


def failure(exc):
    # Transport error text can contain a lease response/token. Keep type only.
    return {"type": type(exc).__name__, "detail": str(exc) if isinstance(exc, ValueError) else
            "Request/capture failed; no retry. Check the bounded kernel diagnostics."}


def run_action(plan, case, pid, fka, destination, *, live=False, kernel=None, sleep=time.sleep,
               confirmed_baseline_sha256=None):
    require(live is True, "Live execution requires an explicitly coordinated window and --live")
    require(case in CASES and fka in ("on", "off") and isinstance(pid, int) and pid > 0, "Explicit case, FKA observation and PID required")
    require(confirmed_baseline_sha256 is None or (len(confirmed_baseline_sha256) == 64
            and all(c in "0123456789abcdef" for c in confirmed_baseline_sha256)),
            "Confirmed baseline must be the SHA-256 of the visually reviewed BMP")
    confirmed_still = confirmed_baseline_sha256 is not None
    destination = Path(destination).resolve()
    require(destination.is_relative_to(LIVE_ROOT.resolve()) and destination != LIVE_ROOT.resolve(),
            "Use a new subfolder of analysis/re-improvements-20261014/live-navigation")
    destination.mkdir(parents=True, exist_ok=False)
    kernel = kernel or CaptureKernel(plan["url"])
    result = {"started_utc": utc(), "case": case, "phone": "C24C", "fka_observed_by_operator": fka,
              "expected": CASES[case][1], "plan": plan, "harness_sha256": sha(HERE),
              "transport_sha256": sha(Path(transport.__file__)), "command_attempted": False,
              "api_success": False, "command_outcome": "not_sent", "visible_acceptance": "not_scored_requires_review",
              "confirmed_baseline_sha256": confirmed_baseline_sha256, "post_command_frames_verified": False,
              "text_preservation": "not_scored_requires_operator_comparison", "frames": [], "errors": [],
              "cleanup": "no_lease_acquired", "timing_scope": "API round-trip only; not Gate 6 console response"}
    tokens = {}
    started = None
    generation = None
    stage = "preflight"
    try:
        status, _ = preflight(kernel, plan, pid, confirmed_still=confirmed_still)
        started = status["process"]["started_utc"]
        result["before"] = status
        if case == "home-idle":
            stage = "idle_preparation"
            result["idle_wait_started_utc"] = utc()
            sleep(60)
            preflight(kernel, plan, pid, started, confirmed_still=confirmed_still)
            result["idle_wait_completed_utc"] = utc()
        stage = "acquire"
        tokens = kernel.acquire([PHONE], lease_ms=120000)
        stage = "owned_preflight"
        _, lease = preflight(kernel, plan, pid, started, owned=True, confirmed_still=confirmed_still)
        generation = lease["generation"]
        stage = "baseline"
        result["frames"].append(frame(kernel, destination, "before.bmp"))
        require(not confirmed_still or result["frames"][-1]["sha256"] == confirmed_baseline_sha256,
                "Still baseline changed since visual review; no input sent")
        # The token remains the authority for the write; status alone cannot
        # guarantee ownership. Recheck after capture, immediately before dispatch.
        current, lease = preflight(kernel, plan, pid, started, owned=True, confirmed_still=confirmed_still)
        require(lease["generation"] == generation, "Lease generation changed before dispatch")
        require(current["receivers"][0].get("frame_session") == result["before"]["receivers"][0].get("frame_session"),
                "Frame session changed during preparation; no input sent")
        result["dispatch_status"] = current
        stage = "command"
        result["command_attempted"] = True
        result["command_outcome"] = "unconfirmed_do_not_retry"
        result["command_started_utc"] = utc()
        reply = kernel.send(PHONE, tokens[PHONE], "/key/sendkey", fn_key=CASES[case][0])
        result["api_success"] = True
        result["command_outcome"] = "completed_by_kernel_not_visually_scored"
        result["api_round_trip_ms"] = reply.get("rtt_ms")
        result["command_completed_utc"] = utc()
        stage = "after_capture"
        # A still baseline does not prove continued video delivery. Require a
        # new frame after dispatch; never retry the input to obtain evidence.
        for attempt in range(11):
            status = kernel.status()
            receiver = verify_kernel(status, plan, pid, started)
            require(receiver.get("frame_session") == current["receivers"][0].get("frame_session")
                    and receiver.get("live") is True and receiver.get("frame_pipe_connected") is True,
                    "Video disconnected or changed session; visual result is unscored")
            if receiver.get("frames", 0) > current["receivers"][0]["frames"]:
                result["post_command_frames_verified"] = True
                break
            if attempt < 10:
                sleep(0.5)
        require(result["post_command_frames_verified"], "No new frame within five seconds; visual result is unscored")
        for i, delay in enumerate((0, 0.5, 1.0)):
            sleep(delay)
            status = kernel.status()
            receiver = verify_kernel(status, plan, pid, started)
            require(receiver.get("frame_session") == current["receivers"][0].get("frame_session"),
                    "Frame session changed; visual result is unscored")
            captured = frame(kernel, destination, f"after-{i + 1}.bmp")
            captured["receiver"] = receiver
            result["frames"].append(captured)
        result["after"] = status
    except Exception as exc:
        result["errors"].append({"stage": stage, **failure(exc)})
        if stage == "acquire":
            result["cleanup"] = "acquisition_unconfirmed_no_token; no takeover; lease may need to expire"
    finally:
        if tokens:
            try:
                status = kernel.status()
                verify_kernel(status, plan, pid, started)
                row = kernel.input_status().get(PHONE, {})
                result["cleanup_input_before"] = {key: row.get(key) for key in ("owned", *FLAGS, "generation")}
                if row.get("owned") is False and row.get("active") is False and row.get("releasing") is False and row.get("release_failed") is False:
                    result["cleanup"] = "already_unowned; no release sent"
                elif generation is None or row.get("generation") == generation:
                    kernel.release(tokens)
                    row = verify_lease(kernel.input_status(), owned=False)
                    result["cleanup_input_after"] = {key: row.get(key) for key in ("owned", *FLAGS, "generation")}
                    result["cleanup"] = "release_confirmed"
                else:
                    raise ValueError("Lease generation changed; no cleanup command sent to a newer owner")
            except Exception as exc:
                result["cleanup"] = "unconfirmed_requires_operator_review"
                result["errors"].append({"stage": "release", **failure(exc)})
        result["finished_utc"] = utc()
        (destination / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send exactly one action in an already-authorized window")
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--kernel-pid", type=int)
    parser.add_argument("--fka", choices=("on", "off"), help="Operator-observed state; this does not change FKA")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--confirmed-baseline-sha256",
                        help="SHA-256 of an operator/visually confirmed current BMP; allows a connected still baseline")
    args = parser.parse_args(argv)
    plan = verify_preparation()
    if not args.live:
        print(json.dumps({"mode": "offline_plan", "rack_contacted": False, "plan": plan, "cases": CASES}, indent=2))
        return 0
    if not args.case or not args.kernel_pid or not args.fka or not args.out:
        parser.error("--live requires --case, --kernel-pid, --fka and a new --out folder")
    result = run_action(plan, args.case, args.kernel_pid, args.fka, args.out, live=True,
                        confirmed_baseline_sha256=args.confirmed_baseline_sha256)
    print(json.dumps({"record": str(args.out / "result.json"), "api_success": result["api_success"],
                      "visible_acceptance": result["visible_acceptance"], "cleanup": result["cleanup"]}, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

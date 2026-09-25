"""Summarize ABAB original vs candidate console telemetry."""
import json, re
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "analysis" / "console-compare-20260915"
summary = {}
fps_re = re.compile(r"(\d+(?:\.\d+)?)\s*fps", re.I)
gap_re = re.compile(r"(\d+)/(\d+)\s*ms")


def parse_frame_status(text: str) -> dict:
    if not text:
        return {}
    fps = fps_re.search(text)
    gap = gap_re.search(text)
    return {
        "displayed_fps": float(fps.group(1)) if fps else None,
        "p50_ms": int(gap.group(1)) if gap else None,
        "p95_ms": int(gap.group(2)) if gap else None,
        "raw": text,
    }


for phase in ("candidate-a", "original-a", "candidate-b", "original-b"):
    rows = [json.loads(s) for s in (root / f"{phase}-telemetry.jsonl").read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    good = [r for r in rows if "error" not in r]
    if not good:
        summary[phase] = {"error": "no samples", "raw_errors": rows}
        continue
    first, last = good[0], good[-1]
    duration = last["elapsed_s"] - first["elapsed_s"]
    result = {
        "start": first["at"],
        "end": last["at"],
        "duration_s": round(duration, 2),
        "samples": len(rows),
        "errors": [r.get("error") for r in rows if "error" in r],
        "console_id": first.get("console_id"),
        "console_path": first.get("console_path"),
        "kernel_id": first.get("kernel_id"),
        "receivers": {},
        "processes": {},
    }
    for initial in first["receivers"]:
        samples = [next(r for r in row["receivers"] if r["name"] == initial["name"]) for row in good]
        final = samples[-1]
        zeros = sum(b["frames"] == a["frames"] for a, b in zip(samples, samples[1:]))
        result["receivers"][initial["name"]] = {
            "received_fps": round((final["frames"] - initial["frames"]) / duration, 2) if duration else None,
            "frame_delta": final["frames"] - initial["frames"],
            "offline_samples": sum(not s["live"] for s in samples),
            "zero_progress_intervals": zeros,
            "restart_delta": final["receiver_restarts"] - initial["receiver_restarts"],
            "pid": sorted({s["receiver_pid"] for s in samples}),
        }
    for initial in first["processes"]:
        samples = [next((p for p in row["processes"] if p["id"] == initial["id"]), None) for row in good]
        samples = [p for p in samples if p]
        if not samples:
            continue
        final = samples[-1]
        cpu = 100 * (final["cpu_s"] - samples[0]["cpu_s"]) / duration / first["logical_cpus"] if duration else 0
        result["processes"][str(initial["id"])] = {
            "name": initial["name"],
            "path": initial.get("path"),
            "cpu_machine_percent": round(cpu, 3),
            "not_responding_samples": sum(not p["responding"] for p in samples),
            "working_set_mib": {
                "start": round(samples[0]["working_set"] / 1048576, 2),
                "end": round(samples[-1]["working_set"] / 1048576, 2),
                "max": round(max(p["working_set"] for p in samples) / 1048576, 2),
            },
            "private_mib": {
                "start": round(samples[0]["private_bytes"] / 1048576, 2),
                "end": round(samples[-1]["private_bytes"] / 1048576, 2),
                "max": round(max(p["private_bytes"] for p in samples) / 1048576, 2),
            },
        }
    result["total_cpu_machine_percent"] = round(sum(p["cpu_machine_percent"] for p in result["processes"].values()), 3)
    ui_path = root / f"{phase}-ui.jsonl"
    displayed = []
    if ui_path.exists():
        for line in ui_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if not line.strip():
                continue
            ui = json.loads(line)
            parsed = parse_frame_status(ui.get("frame") or "")
            if parsed.get("displayed_fps") is not None:
                displayed.append(parsed)
    if displayed:
        result["displayed"] = {
            "samples": len(displayed),
            "fps_mean": round(sum(d["displayed_fps"] for d in displayed) / len(displayed), 2),
            "fps_min": min(d["displayed_fps"] for d in displayed),
            "fps_max": max(d["displayed_fps"] for d in displayed),
            "p95_ms": [d["p95_ms"] for d in displayed],
            "readouts": displayed,
        }
    summary[phase] = result

# C241 repeat question
c241 = {p: summary[p]["receivers"]["iMouse2-C241"]["received_fps"] for p in summary if "receivers" in summary[p]}
c24c = {p: summary[p]["receivers"]["iMouse2-C24C"]["received_fps"] for p in summary if "receivers" in summary[p]}
cand = [c241[p] for p in ("candidate-a", "candidate-b") if p in c241]
orig = [c241[p] for p in ("original-a", "original-b") if p in c241]
summary["c241_received_fps"] = c241
summary["c24c_received_fps"] = c24c
if cand and orig:
    summary["c241_candidate_mean"] = round(sum(cand) / len(cand), 2)
    summary["c241_original_mean"] = round(sum(orig) / len(orig), 2)
    summary["c241_repeat_lower_on_candidate"] = all(c < o for c in cand for o in orig)

(root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "displayed"} if isinstance(v, dict) else v for k, v in summary.items()}, indent=2))

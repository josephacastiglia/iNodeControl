"""Offline tests for gate4_suite.py against mock_kernel.py. No phone, board or kernel needed.

    python tools/gate4_v2/test_gate4_v2.py

Each test checks one claim the harness makes about itself, including the two v1 defects it
exists to fix: the isolation race and the long-move path erased by Home.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

SCALE = 0.05
os.environ["GATE4_TIME_SCALE"] = str(SCALE)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate4_suite as g          # noqa: E402  (must follow the environment variable)
from mock_kernel import MockKernel  # noqa: E402

TARGETS = [{"name": n, "x": x, "y": y} for n, x, y in
           [("t_top_left", 70, 150), ("t_top_right", 430, 150), ("t_mid_a", 190, 420),
            ("t_mid_b", 310, 560), ("t_low", 70, 800), ("t_dock", 250, 1000)]]


def phones(n: int = 2) -> list[dict]:
    return [{"tag": f"P{i}", "id": f"00:00:00:00:00:{i:02d}", "enabled": True, "profile": "XR-default",
             "receiver_name": f"iMouse2-P{i}", "targets": TARGETS} for i in range(n)]


class Rig:
    """A mock kernel, a config file and an output folder for one test."""

    def __init__(self, **faults):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.config_path = self.dir / "config.json"
        self.config_path.write_text(json.dumps({"phones": phones()}), encoding="utf-8")
        self.cfg = g.load_config(self.config_path)
        self.mock = MockKernel(self.cfg["_enabled"], scale=SCALE, **faults)
        self.url = self.mock.start()
        self.k = g.Kernel(self.url)

    def calibrate(self, reviewed: bool = True) -> None:
        g.calibrate(self.k, self.cfg, self.dir)
        path = g.calibration_path(self.dir)
        cal = json.loads(path.read_text(encoding="utf-8"))
        if reviewed:
            cal["reviewed"], cal["reviewed_by"] = True, "unit test"
        path.write_text(json.dumps(cal), encoding="utf-8")

    def run(self, total: int) -> tuple[int, list[dict], dict]:
        args = Namespace(out=str(self.dir), url=self.url, total=total, seed=7, run_id="t")
        code = g.run(args, self.cfg)
        rdir = self.dir / "runs" / "t"
        rows = [json.loads(l) for l in (rdir / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        return code, rows, json.loads((rdir / "status.json").read_text(encoding="utf-8"))

    def close(self) -> None:
        self.mock.stop()
        self.tmp.cleanup()


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.rigs: list[Rig] = []

    def tearDown(self):
        for r in self.rigs:
            r.close()

    def rig(self, **faults) -> Rig:
        r = Rig(**faults)
        self.rigs.append(r)
        return r

    def test_offline_self_check(self):
        g.self_check()

    def test_clean_run_passes_every_trial_and_records_provenance(self):
        r = self.rig()
        r.calibrate()
        total = 2 * len(TARGETS) * len(g.CATEGORIES)
        code, rows, status = r.run(total)
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), total)
        failed = [(x["n"], x["category"], x["target"], x.get("blocking") or x.get("error") or x.get("verdict")) for x in rows if not x["pass"]]
        self.assertEqual(failed, [])
        self.assertEqual(status["state"], "complete")
        self.assertEqual(status["unintended_phone_actions"], 0)
        manifest = json.loads((r.dir / "runs" / "t" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["harness_sha256"], g.HARNESS_SHA256)
        self.assertTrue(all(x["harness_sha256"] == g.HARNESS_SHA256[:16] for x in rows))
        self.assertEqual({x["target"] for x in rows}, {t["name"] for t in TARGETS}, "every target is tapped")
        self.assertTrue(all(x["setup_ok"] for x in rows))

    def test_v1_isolation_race_is_reproduced_and_v2_does_not_fall_for_it(self):
        # The other phone takes 1.5 s to finish dismissing its previous trial.
        r = self.rig(dismiss_ms=1500)
        r.calibrate()
        cal = g.load_calibration(r.dir, r.cfg)
        a, b = r.cfg["_enabled"]
        tokens = r.k.acquire([a["id"], b["id"]])
        thr = cal["phones"][a["tag"]]["isolation_threshold"]

        def open_then_dismiss(p):
            r.k.send(p["id"], tokens[p["id"]], "/mouse/click", x=TARGETS[0]["x"], y=TARGETS[0]["y"], button=1)
            g.nap(1.0)
            r.k.send(p["id"], tokens[p["id"]], "/key/sendkey", fn_key="Home")

        # v1: photograph the other phone 350 ms after its Home, then tap the target phone.
        open_then_dismiss(a)
        g.nap(0.35)
        v1_before = g.grid(r.k.shot(a["id"]))[2]
        sent_to_a = sum(1 for e in r.mock.log if e["phone"] == a["tag"])
        r.k.send(b["id"], tokens[b["id"]], "/mouse/click", x=TARGETS[1]["x"], y=TARGETS[1]["y"], button=1)
        g.nap(2.5)
        v1_distance = g.distance(v1_before, g.grid(r.k.shot(a["id"]))[2])
        self.assertEqual(sum(1 for e in r.mock.log if e["phone"] == a["tag"]), sent_to_a, "nothing was sent to A")
        self.assertGreater(v1_distance, thr, "v1's capture flags A even though A received nothing")

        # v2: the same situation, through the harness's own trial.
        r.k.send(b["id"], tokens[b["id"]], "/key/sendkey", fn_key="Home")
        g.settle_home(r.k, b["id"], b["tag"], cal)
        open_then_dismiss(a)
        spec = {"n": 0, "phone": b["tag"], "id": b["id"], "profile": "XR-default", "category": "after_home",
                "target": TARGETS[2]["name"], "x": TARGETS[2]["x"], "y": TARGETS[2]["y"]}
        row = g.trial(r.k, spec, tokens, cal, r.cfg, r.dir / "shots", "race")
        self.assertTrue(row["target_hit"])
        self.assertTrue(row["isolated"], row["isolation"])

    def test_long_move_really_travels_from_the_start_point(self):
        r = self.rig()
        r.calibrate()
        start = len(r.mock.log)
        code, rows, _ = r.run(2 * len(TARGETS) * len(g.CATEGORIES))
        self.assertEqual(code, 0)
        log = r.mock.log[start:]
        clicks = [e for e in log if e["fun"] == "/mouse/click"]
        by_cat = {}
        for row, click in zip(rows, clicks):
            by_cat.setdefault(row["category"], []).append(click["reset"])
        # After Home the kernel resets to a corner first. v1's off_location always did this.
        self.assertTrue(all(by_cat["after_home"]), "after_home clicks start from a corner reset")
        self.assertFalse(any(by_cat["long_move"]), "long_move clicks must not be preceded by a reset")
        self.assertTrue(all(r_["move_px"] > 300 for r_ in rows if r_["category"] == "long_move"))

    def test_interruption_rotates_the_lease_and_refuses_the_old_token(self):
        r = self.rig()
        r.calibrate()
        _, rows, _ = r.run(2 * len(TARGETS) * len(g.CATEGORIES))
        inter = [x for x in rows if x["category"] == "after_interruption"]
        self.assertTrue(inter)
        self.assertTrue(all(x["old_token_refused"] and x["pass"] for x in inter))

    def test_unwanted_input_on_another_phone_stops_the_run(self):
        r = self.rig(crosstalk=("P0", "P1"))
        r.calibrate()
        code, rows, status = r.run(2 * len(TARGETS) * len(g.CATEGORIES))
        self.assertEqual(code, 2)
        self.assertFalse(rows[-1]["isolated"])
        self.assertEqual(rows[-1]["phone"], "P0")
        self.assertIn("unintended", status["stopped_because"])

    def test_a_miss_is_recorded_once_and_never_retried(self):
        r = self.rig()
        r.calibrate()                       # misses start after calibration, which would rightly refuse a silent target
        r.mock.miss_every = 4
        before = r.mock.clicks
        code, rows, status = r.run(2 * len(TARGETS) * len(g.CATEGORIES))
        self.assertEqual(code, 0)
        self.assertEqual(r.mock.clicks - before, len(rows), "exactly one click per trial")
        misses = [x for x in rows if not x["target_hit"]]
        self.assertTrue(misses)
        self.assertTrue(all(x["clicks_sent"] == 1 and x["verdict"]["at_home"] for x in misses))
        self.assertEqual(status["misses"], len(misses))

    def test_a_possible_double_click_stops_the_run(self):
        r = self.rig()
        r.calibrate()
        r.mock.double_on = {r.mock.clicks + 3}          # the third click of the scored run
        code, rows, status = r.run(2 * len(TARGETS) * len(g.CATEGORIES))
        self.assertEqual(code, 2)
        self.assertTrue(rows[-1]["post_hit_change"])
        self.assertIn("double", status["stopped_because"])

    def test_app_switcher_that_never_appears_is_not_credited(self):
        r = self.rig(appswitch_works=False)             # what FKA Off did on 1 Oct
        r.calibrate()
        _, rows, status = r.run(2 * len(TARGETS) * len(g.CATEGORIES))
        sw = [x for x in rows if x["category"] == "after_app_switch"]
        self.assertTrue(all(x["setup_ok"] is False and "App Switcher did not appear" in x["notes"] for x in sw))
        self.assertEqual(status["per_category"]["after_app_switch"]["setup_failed"], len(sw))

    def test_refuses_an_unreviewed_calibration(self):
        r = self.rig()
        r.calibrate(reviewed=False)
        with self.assertRaises(SystemExit):
            g.load_calibration(r.dir, r.cfg)

    def test_a_target_that_changes_nothing_is_refused(self):
        r = self.rig()
        # The phone has nothing under t_dock: tapping it leaves the Home screen as it was.
        r.mock.stop()
        layout = [dict(p, targets=[t for t in p["targets"] if t["name"] != "t_dock"]) for p in r.cfg["_enabled"]]
        r.mock = MockKernel(layout, scale=SCALE)
        r.url = r.mock.start()
        r.k = g.Kernel(r.url)
        r.calibrate()
        cal = json.loads(g.calibration_path(r.dir).read_text(encoding="utf-8"))
        self.assertFalse(cal["phones"]["P0"]["targets"]["t_dock"]["valid"])
        self.assertTrue(cal["phones"]["P0"]["targets"]["t_low"]["valid"])
        with self.assertRaises(SystemExit):
            g.load_calibration(r.dir, r.cfg)

    def test_calibration_references_are_not_the_home_screen(self):
        r = self.rig(dismiss_ms=900)                    # a slow, frozen-looking dismiss between targets
        r.calibrate()
        cal = json.loads(g.calibration_path(r.dir).read_text(encoding="utf-8"))
        for tag, phone in cal["phones"].items():
            for name, ref in phone["targets"].items():
                self.assertGreater(ref["distance_from_home"], 15, f"{tag} {name} recorded the Home screen")

    def test_refuses_a_scaled_run_against_a_real_kernel(self):
        r = self.rig()
        real = r.k.status

        def no_mock():
            s = dict(real())
            s.pop("mock", None)
            return s
        r.k.status = no_mock
        with self.assertRaises(SystemExit):
            g.preflight(r.k, r.cfg)

    def test_refuses_one_repeated_target(self):
        bad = {"tag": "X", "targets": [{"name": f"s{i}", "x": 250, "y": 900} for i in range(10)]}
        self.assertTrue(g.check_targets(bad))


if __name__ == "__main__":
    unittest.main(verbosity=2)

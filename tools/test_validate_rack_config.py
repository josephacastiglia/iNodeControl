"""Offline configuration failure and readiness checks; no hardware access."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import validate_rack_config as rack


class RackChecks(unittest.TestCase):
    def setUp(self):
        self.receivers = [{"DeviceId": "phone-one", "BoardPid": "ABCD", "Name": "iMouse2-ABCD",
                           "Pipe": "iMouse2-ABCD-frames", "Port": 7110, "Mac": "02:49:4D:32:AB:CD"}]
        self.devices = [{"deviceid": "phone-one", "pid": "ABCD"}]
        self.cals = [{"Pid": "ABCD", "Width": 500, "Height": 1080, "OriginX": 14,
                      "OriginY": 14, "PixelsPerUnitX": 5.1, "PixelsPerUnitY": 5.1}]

    def result(self):
        return rack.validate(self.receivers, self.devices, self.cals)

    def invalid(self):
        result = self.result()
        self.assertFalse(result["configuration_valid"], result)
        self.assertFalse(result["bindings_complete"])

    def test_explicit_binding_is_not_physical_acceptance(self):
        result = self.result()
        self.assertTrue(result["configuration_valid"])
        self.assertTrue(result["bindings_complete"])
        self.assertFalse(result["gate11_acceptance"])
        self.assertFalse(result["hardware_contacted"])
        self.assertEqual(result["physical_readiness"], "not_assessed")

    def test_planned_template_reports_fourteen_unbound(self):
        result = rack.validate(*(rack.read_records(rack.ROOT / name) for name in
                               ("receivers.json", "devices.json", "pointer-calibration.json")), template=True)
        self.assertTrue(result["configuration_valid"], result)
        self.assertEqual(len(result["incomplete_boards"]), 14)
        self.assertEqual(result["explicit_binding_count"], 5)
        self.assertFalse(result["bindings_complete"])

    def test_discovery_and_placeholder_are_incomplete(self):
        for identity in ("*", "", "unbound-ABCD"):
            with self.subTest(identity=identity):
                self.receivers[0]["DeviceId"] = identity
                self.devices[0]["deviceid"] = identity or "phone-one"
                result = self.result()
                self.assertTrue(result["configuration_valid"], result)
                self.assertFalse(result["bindings_complete"])

    def test_duplicate_device_board_not_hidden_by_dictionary(self):
        self.devices.append(dict(self.devices[0], deviceid="phone-two"))
        self.invalid()

    def test_duplicate_calibration_not_hidden_by_dictionary(self):
        self.cals.append(dict(self.cals[0], Pid="abcd"))
        self.invalid()

    def test_missing_calibration(self):
        self.cals.clear()
        self.invalid()

    def test_wrong_binding(self):
        self.devices[0]["deviceid"] = "phone-two"
        self.invalid()

    def test_missing_receiver_fields_report_errors(self):
        original = copy.deepcopy(self.receivers[0])
        for key in original:
            with self.subTest(key=key):
                self.receivers[0] = {k: v for k, v in original.items() if k != key}
                self.invalid()

    def test_invalid_ports_including_boolean(self):
        for port in (True, None, "7110", 7110.0, 1023, 65534, 5352, 5353):
            with self.subTest(port=port):
                self.receivers[0]["Port"] = port
                self.invalid()

    def test_overlapping_port_windows(self):
        self.receivers.append(dict(self.receivers[0], BoardPid="ABCE", DeviceId="phone-two",
                                   Name="iMouse2-ABCE", Pipe="iMouse2-ABCE-frames", Mac="02:49:4D:32:AB:CE", Port=7112))
        self.devices.append({"deviceid": "phone-two", "pid": "ABCE"})
        self.cals.append(dict(self.cals[0], Pid="ABCE"))
        self.invalid()

    def test_nonfinite_and_overflow_calibration(self):
        for key, value in (("OriginX", float("nan")), ("OriginY", float("inf")),
                           ("OriginX", 10 ** 400), ("PixelsPerUnitX", 5e-324),
                           ("PixelsPerUnitY", -1), ("Width", True), ("Height", 2**32)):
            with self.subTest(key=key, value=value):
                saved = self.cals[0][key]
                self.cals[0][key] = value
                self.invalid()
                self.cals[0][key] = saved

    def test_calibrations_need_not_copy_template_values(self):
        self.cals[0].update(Width=720, Height=1600, OriginX=12.5, PixelsPerUnitX=4.9)
        self.assertTrue(self.result()["configuration_valid"])

    def test_invalid_record_shape_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            for text in ('{}', '[null]', '[1]', '[{"Pid":"A","Pid":"B"}]', '[{"Port":NaN}]', '['):
                with self.subTest(text=text):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        rack.read_records(path)

    def test_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text('[{"name":"未分组"}]', encoding="utf-8-sig")
            self.assertEqual(rack.read_records(path)[0]["name"], "未分组")

    def test_cli_template_exit_code_and_explicit_structure_only(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rack.main([]), 2)
            self.assertEqual(rack.main(["--structure-only"]), 0)

    def test_cli_report_never_overwrites_evidence(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            path = Path(tmp) / "report.json"
            self.assertEqual(rack.main(["--report", str(path)]), 2)
            before = path.read_bytes()
            self.assertEqual(rack.main(["--report", str(path)]), 1)
            self.assertEqual(path.read_bytes(), before)

    def test_cli_custom_folder_read_only(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp)
            for name, records in zip(("receivers.json", "devices.json", "pointer-calibration.json"),
                                     (self.receivers, self.devices, self.cals)):
                (folder / name).write_text(json.dumps(records), encoding="utf-8")
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            self.assertEqual(rack.main(["--config-dir", str(folder)]), 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_cli_missing_folder_fails_without_creation(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()):
            folder = Path(tmp) / "missing"
            self.assertEqual(rack.main(["--config-dir", str(folder)]), 1)
            self.assertFalse(folder.exists())


if __name__ == "__main__":
    unittest.main()

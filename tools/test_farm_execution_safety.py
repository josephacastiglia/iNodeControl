"""Offline boundaries of the kernel client and the content store: no sockets, phone input, accounts or media generation."""
from __future__ import annotations

import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import imouse_farm_server as server
import imouse_social_automation as engine


C24C = "86:1D:4A:04:2F:F6"
C241 = "FE:A9:BC:D7:A0:44"


class FarmExecutionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.url_open = self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden in this test")))

    def runtime(self, **kwargs):
        return server.FarmBackendRuntime(db_path=self.root / "farm.db", stage_root=self.root / "stage", **kwargs)

    def live_with_fake_transport(self):
        client = engine.IMouseKernel()
        transport = Mock(side_effect=AssertionError("Unexpected transport call"))
        client._transport = transport
        return client, transport

    def test_a_runtime_holds_no_kernel_client_in_either_mode(self):
        for mode in ("simulate", "live"):
            with self.subTest(mode=mode), patch.object(engine.IMouseKernel, "__init__", side_effect=AssertionError("No kernel client")):
                runtime = server.FarmBackendRuntime(db_path=self.root / mode / "farm.db", stage_root=self.root / mode / "stage", execution_mode=mode)
                self.addCleanup(runtime.transfers.close)
                self.assertEqual(mode, runtime.execution_mode)
                self.assertFalse(any(hasattr(runtime, name) for name in ("kernel_client", "mock_kernel", "get_kernel", "live_kernel_connected")))
                self.assertIsNone(runtime.draft_creations.config)
        self.url_open.assert_not_called()

    def test_unknown_mode_is_rejected_before_creating_database(self):
        with self.assertRaises(ValueError):
            self.runtime(execution_mode="automatic")
        self.assertFalse((self.root / "farm.db").exists())

    def test_database_connection_is_closed_after_read(self):
        db = engine.FarmDatabase(self.root / "farm.db")
        with db._connect() as connection:
            self.assertEqual(1, connection.execute("select 1").fetchone()[0])
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("select 1")

    def test_database_failure_rolls_back_and_closes_connection(self):
        db = engine.FarmDatabase(self.root / "farm.db")
        before = db.get_persona("C24C")["niche"]
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with db._connect() as connection:
                connection.execute("update personas set niche = 'uncommitted' where device_id = 'C24C'")
                raise RuntimeError("abort")
        self.assertEqual(before, db.get_persona("C24C")["niche"])
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("select 1")

    def test_protected_and_unbound_targets_never_become_simulated_live_success(self):
        for target in ("C241", C241, "RACK-03", "unknown", "", "C24C,C241"):
            with self.subTest(target=target):
                client, transport = self.live_with_fake_transport()
                with self.assertRaises(engine.KernelSafetyError):
                    client.preflight_phone(target)
                transport.assert_not_called()

    def test_mixed_group_is_rejected_before_any_transport(self):
        client, transport = self.live_with_fake_transport()
        with self.assertRaises(engine.KernelSafetyError):
            client.acquire([C24C, C241])
        transport.assert_not_called()

    def test_raw_live_post_cannot_bypass_c24c_scope(self):
        for data in ({"id": C241}, {"id": C24C + "," + C241}, {"id": ""}, {}):
            with self.subTest(data=data):
                client, transport = self.live_with_fake_transport()
                with self.assertRaises(engine.KernelSafetyError):
                    client.post("/input/stop", data)
                transport.assert_not_called()

    def test_c24c_post_is_sent_once_and_does_not_rewrite_action(self):
        client, transport = self.live_with_fake_transport()
        transport.side_effect = None
        transport.return_value = (b'{"data":{"code":0}}', {})
        self.assertEqual({"code": 0}, client.post("/input/stop", {"id": C24C}))
        transport.assert_called_once_with("POST", engine.DEFAULT_KERNEL_URL + "/", {"fun": "/input/stop", "data": {"id": C24C}}, 25.0)
        self.assertFalse(client.audit_log[-1]["simulated"])

    def test_live_status_remains_read_only_and_available(self):
        client, transport = self.live_with_fake_transport()
        transport.side_effect = None
        transport.return_value = (b'{"data":{"code":0,"phones":[]}}', {})
        self.assertEqual({}, client.input_status())
        self.assertEqual("/input/status", transport.call_args.args[2]["fun"])

    def test_c24c_alias_cannot_resolve_to_another_phone(self):
        client, transport = self.live_with_fake_transport()
        with patch.object(client, "kernel_status", return_value={"receivers": [{"deviceid": C241, "name": "iMouse2-C24C"}]}):
            with self.assertRaises(engine.KernelSafetyError):
                client.resolve_device_id("C24C")
        transport.assert_not_called()

    def test_send_payload_cannot_override_target_or_lease(self):
        client, transport = self.live_with_fake_transport()
        for data in ({"id": C241}, {"tokens": {C24C: "another-lease"}}):
            with self.subTest(data=data):
                with self.assertRaises(engine.KernelSafetyError):
                    client.send(C24C, "owned-token", "/mouse/click", **data)
        transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()

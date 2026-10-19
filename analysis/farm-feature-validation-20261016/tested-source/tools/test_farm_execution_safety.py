"""Offline farm boundaries: no sockets, phone input, accounts, or media generation."""
from __future__ import annotations

import json
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
        self.enterContext(patch.object(engine.MediaPullOrchestrator, "detect_host_lan_url", return_value="http://127.0.0.1:9914"))

    def runtime(self, **kwargs):
        return server.FarmBackendRuntime(db_path=self.root / "farm.db", stage_root=self.root / "stage", **kwargs)

    def live_with_fake_transport(self):
        client = engine.IMouseKernel()
        transport = Mock(side_effect=AssertionError("Unexpected transport call"))
        client._transport = transport
        return client, transport

    def test_default_runtime_never_probes_or_selects_live_kernel(self):
        runtime = self.runtime()
        kernel = runtime.get_kernel()
        self.assertFalse(kernel._is_live_http)
        self.url_open.assert_not_called()

    def test_explicit_simulation_preserves_mock_phone_work_without_network(self):
        runtime = self.runtime(execution_mode="simulate")
        client = runtime.get_kernel()
        client.preflight_phone("C241")
        tokens = client.acquire(["C241"])
        client.send("C241", tokens["C241"], "/mouse/click", x=10, y=20)
        client.release(tokens)
        self.assertEqual({}, runtime.mock_kernel.leases)
        self.assertTrue(all(entry["simulated"] for entry in client.audit_log))
        self.url_open.assert_not_called()

    def test_live_outage_refuses_instead_of_substituting_simulation(self):
        runtime = self.runtime(execution_mode="live")
        with patch.object(engine.IMouseKernel, "kernel_status", side_effect=OSError("service down")):
            with self.assertRaises(engine.KernelSafetyError):
                runtime.get_kernel()
        self.assertFalse(runtime.live_kernel_connected)
        self.assertEqual({}, runtime.mock_kernel.leases)
        self.url_open.assert_not_called()

    def test_live_requires_ownership_protocol(self):
        runtime = self.runtime(execution_mode="live")
        with patch.object(engine.IMouseKernel, "kernel_status", return_value={"code": 0, "input_leases_required": False}):
            with self.assertRaises(engine.KernelSafetyError):
                runtime.get_kernel()
        self.assertFalse(runtime.live_kernel_connected)

    def test_live_ready_returns_live_transport_and_same_mode(self):
        runtime = self.runtime(execution_mode="live")
        with patch.object(engine.IMouseKernel, "kernel_status", return_value={"code": 0, "input_leases_required": True}):
            self.assertTrue(runtime.get_kernel()._is_live_http)
        self.assertTrue(runtime.live_kernel_connected)

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

    def test_proxy_post_uses_runtime_mode_and_guarded_client(self):
        handler = object.__new__(server.FarmRequestHandler)
        handler._send_json = Mock()
        handler._send_bytes = Mock()
        runtime = self.runtime(execution_mode="simulate")
        payload = {"fun": "/input/acquire", "data": {"id": "C241"}}
        with patch.object(server, "RUNTIME", runtime):
            handler._proxy_to_kernel("POST", server.KERNEL_BASE_URL + "/", json.dumps(payload).encode())
        self.url_open.assert_not_called()
        self.assertEqual(200, handler._send_json.call_args.args[0])
        self.assertIn("C241", runtime.mock_kernel.leases)

    def test_proxy_live_request_cannot_skip_target_guard(self):
        handler = object.__new__(server.FarmRequestHandler)
        handler._send_json = Mock()
        handler._send_bytes = Mock()
        runtime = self.runtime(execution_mode="live")
        client, transport = self.live_with_fake_transport()
        with patch.object(server, "RUNTIME", runtime), patch.object(runtime, "get_kernel", return_value=client):
            handler._proxy_to_kernel("POST", server.KERNEL_BASE_URL + "/", json.dumps({"fun": "/input/stop", "data": {"id": C241}}).encode())
        self.assertEqual(409, handler._send_json.call_args.args[0])
        transport.assert_not_called()
        self.url_open.assert_not_called()


if __name__ == "__main__":
    unittest.main()

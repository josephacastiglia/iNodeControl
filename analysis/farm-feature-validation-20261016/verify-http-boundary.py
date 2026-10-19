"""Reproduce selected handler results through an isolated loopback HTTP server.

Only the exact ephemeral test port is allowed. Real rack ports and other network
destinations are forbidden. Files and databases are disposable test fixtures.
"""
from pathlib import Path
import http.client
import json
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import imouse_farm_server as server

allowed_port = None
def guard(event, args):
    if event == "socket.connect":
        address = args[1]
        if not isinstance(address, tuple) or address[0] != "127.0.0.1" or address[1] != allowed_port:
            raise AssertionError("Only the temporary test server can be contacted")
    if event == "socket.sendto":
        raise AssertionError("Datagrams forbidden")
sys.addaudithook(guard)

handler_errors = []
class QuietServer(server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        handler_errors.append(type(sys.exception()).__name__)

results = []
with tempfile.TemporaryDirectory(prefix="farm-http-validation-") as tmp:
    base = Path(tmp)
    runtime = server.FarmBackendRuntime(base / "farm.db", base / "stage", execution_mode="simulate")
    (base / "outside.txt").write_text("test-marker-outside-stage", encoding="utf-8")
    with patch.object(server, "RUNTIME", runtime):
        srv = QuietServer(("127.0.0.1", 0), server.FarmRequestHandler)
        allowed_port = srv.server_address[1]
        assert allowed_port not in (9911, 9913, 9914)
        worker = threading.Thread(target=srv.serve_forever, daemon=True)
        worker.start()
        def request(label, method, path, body=None, headers=None):
            connection = http.client.HTTPConnection("127.0.0.1", allowed_port, timeout=5)
            try:
                connection.request(method, path, body=body, headers=headers or {})
                response = connection.getresponse()
                payload = response.read()
                result = {"check": label, "status": response.status,
                          "modeHeader": response.getheader("X-Farm-Execution-Mode"),
                          "body": payload.decode("utf-8")}
            except http.client.RemoteDisconnected:
                result = {"check": label, "status": "connection_closed_without_response"}
            finally:
                connection.close()
            results.append(result)
        try:
            request("state", "GET", "/api/farm/state")
            # Keep state result compact; fixture persona data need not be archived.
            state = json.loads(results[-1].pop("body"))
            results[-1]["simulated"] = state["simulated"]
            results[-1]["personaCount"] = len(state["personas"])
            request("console_hardware_id_warmup", "POST", "/api/farm/warmup-wave",
                    json.dumps({"device_id": server.engine.LIVE_TEST_DEVICE_ID, "clips": 1, "time_scale": 0}),
                    {"Content-Type": "application/json"})
            request("stage_parent_traversal", "GET", "/stage/../outside.txt")
            request("invalid_json", "POST", "/api/farm/warmup-wave", "{bad-json", {"Content-Type": "application/json"})
            request("external_origin_refused", "POST", "/api/farm/warmup-wave", "{}", {"Origin": "https://example.invalid"})
        finally:
            srv.shutdown()
            srv.server_close()
            worker.join(timeout=5)
        assert not worker.is_alive()
        assert not runtime.mock_kernel.leases
        assert not runtime.mock_kernel.commands_dispatched
        report = {"offlineOnly": True, "desktopControl": False, "phoneInput": False,
                  "testServerClosed": True, "handlerErrors": handler_errors, "results": results}
        (Path(__file__).parent / "http-boundary-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))

"""Run both built-in self-checks, allowing only their own loopback test listener."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tools'))
from farm_test_network import allowed_ports
import imouse_farm_server as server
import imouse_social_automation as engine


class IsolatedServer(server.ThreadingHTTPServer):
    def __init__(self, address, *args, **kwargs):
        assert address == ('127.0.0.1', 0), 'Only an ephemeral test listener is allowed'
        super().__init__(address, *args, **kwargs)
        allowed_ports.add(self.server_port)

    def server_close(self):
        if hasattr(self, 'server_port'):
            allowed_ports.discard(self.server_port)
        super().server_close()


server.ThreadingHTTPServer = IsolatedServer
engine.self_check()
server.self_check()
assert not allowed_ports, 'Test listener leaked'
print('Both guarded self-checks passed; no live network or hardware access.')

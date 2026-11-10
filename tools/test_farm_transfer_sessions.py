"""Loopback acceptance for the native transfer API; no rack or desktop access."""
import base64
import http.client
import io
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import sys
import threading
import time
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import urlsplit

from PIL import Image
import imouse_farm_server as backend
from farm_drafts import DraftConflict
from farm_transfers import CarouselTransfers, TransferConflict
import farm_test_network as network
from farm_test_network import allowed_ports


class TransferSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='farm-transfer-session-')
        self.root = Path(self.temp.name)
        self.outside = network.mark()
        self.runtime = backend.FarmBackendRuntime(self.root / 'farm.db', self.root / 'stage')
        self.manager = self.runtime.transfers
        self.draft = self.runtime.drafts.create(str(uuid.uuid4()))
        for color in ('red', 'blue'):
            raw = io.BytesIO()
            Image.new('RGB', (20, 25), color).save(raw, 'PNG')
            self.draft = self.runtime.drafts.import_image(self.draft['id'], self.draft['revision'], 'test.png', base64.b64encode(raw.getvalue()).decode())
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            self.port = probe.getsockname()[1]
        allowed_ports.add(self.port)
        self.request = dict(id=str(uuid.uuid4()), draft_id=self.draft['id'], revision=self.draft['revision'],
                            device_id='C24C', account='test.account', bind='127.0.0.1', client='127.0.0.1', port=self.port, minutes=1)
        self.httpd = None

    def tearDown(self):
        self.manager.close()
        if self.httpd:
            self.httpd.shutdown(); self.httpd.server_close(); self.http_thread.join(2)
            allowed_ports.discard(self.httpd.server_port)
            backend.RUNTIME = self.previous
        allowed_ports.discard(self.port)
        self.temp.cleanup()

    def media(self, url, suffix=''):
        parsed = urlsplit(url)
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
        try:
            connection.request('GET', parsed.path + suffix)
            reply = connection.getresponse()
            return reply.status, reply.read()
        finally:
            connection.close()

    def api(self, path, body=None, headers=None):
        if not self.httpd:
            self.previous = backend.RUNTIME
            backend.RUNTIME = self.runtime
            self.httpd = backend.ThreadingHTTPServer(('127.0.0.1', 0), backend.FarmRequestHandler)
            allowed_ports.add(self.httpd.server_port)
            self.http_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.http_thread.start()
        client = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port, timeout=5)
        try:
            client.request('GET' if body is None else 'POST', path, None if body is None else json.dumps(body),
                           headers or {'Content-Type': 'application/json'})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def test_http_start_delivery_recovery_stop_and_no_phone_commands(self):
        code, response = self.api('/api/farm/transfers', self.request)
        self.assertEqual(200, code, response)
        self.assertNotIn('simulated', response)
        session = response['transfer']
        self.assertEqual('real_media_only', session['deliveryMode'])
        self.assertEqual('serving', session['state'])
        self.assertEqual(200, self.media(session['url'], '01.jpg')[0])
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not self.manager.get(session['id'])['imagesDelivered']:
            time.sleep(.01)
        code, recovered = self.api('/api/farm/transfers/current')
        self.assertEqual(['01.jpg'], recovered['transfer']['imagesDelivered'])
        self.assertEqual('unverified', recovered['transfer']['instagramStatus'])
        self.assertEqual('unverified', recovered['transfer']['photosStatus'])
        self.assertFalse(recovered['transfer']['publicationAttempted'])
        self.assertEqual(session['url'], recovered['transfer']['url'])
        code, closed = self.api(f"/api/farm/transfers/{session['id']}/stop", {})
        self.assertEqual('closed', closed['transfer']['state'])
        self.assertIsNone(closed['transfer']['url'])
        with self.assertRaises(OSError): self.media(session['url'])
        self.assertEqual([], network.since(self.outside))

    def test_duplicate_request_never_reopens_or_changes_snapshot(self):
        first = self.manager.start(self.request)
        second = self.manager.start(self.request)
        self.assertEqual(first['url'], second['url'])
        self.assertEqual(first['packageSha256'], second['packageSha256'])
        with self.assertRaises(TransferConflict):
            self.manager.start({**self.request, 'account': 'someone.else'})
        self.manager.stop(first['id'])
        self.assertEqual('closed', self.manager.start(self.request)['state'])
        self.assertIsNone(self.manager.server)

    def test_draft_edits_do_not_mutate_active_media(self):
        first = self.manager.start(self.request)
        before = self.media(first['url'], '01.jpg')[1]
        self.runtime.drafts.save(self.draft['id'], self.draft['revision'], 'New revision', 'new caption', self.draft['slideIds'][::-1])
        self.assertEqual(before, self.media(first['url'], '01.jpg')[1])
        self.assertEqual(b'', self.media(first['url'], 'caption.txt')[1])

    def test_port_collision_is_terminal_and_does_not_kill_other_listener(self):
        with socket.socket() as occupied:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            occupied.bind(('127.0.0.1', self.port)); occupied.listen()
            failed = self.manager.start(self.request)
            self.assertEqual('failed', failed['state'])
            self.assertEqual(self.port, occupied.getsockname()[1])
        self.assertEqual('failed', self.manager.start(self.request)['state'])
        self.assertIsNone(self.manager.server)

    def test_expiry_closes_socket_and_strips_url(self):
        now = [10.0]
        self.manager.clock = lambda: now[0]
        first = self.manager.start(self.request)
        worker = self.manager.thread
        now[0] = 71
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual('expired', self.manager.get(first['id'])['state'])
        self.assertIsNone(self.manager.get(first['id'])['url'])
        with self.assertRaises(OSError): self.media(first['url'])

    def test_restart_keeps_history_but_never_url_or_listener(self):
        first = self.manager.start(self.request)
        token = urlsplit(first['url']).path
        self.manager.stop(first['id'])
        # Emulate a journal left by an abruptly terminated backend, after releasing the test socket.
        with self.manager._db() as db:
            row = json.loads(db.execute('SELECT record FROM transfers').fetchone()[0])
            row['state'] = 'serving'
            db.execute('UPDATE transfers SET record=?', (json.dumps(row),))
        resumed = CarouselTransfers(self.manager.database, self.runtime.drafts)
        self.assertEqual('interrupted', resumed.current()['state'])
        self.assertEqual('interrupted', resumed.start(self.request)['state'])
        self.assertIsNone(resumed.server)
        self.assertNotIn(token.encode(), self.manager.database.read_bytes())

    def test_stale_revision_and_invalid_package_fail_before_listener(self):
        with self.assertRaises(DraftConflict):
            self.manager.start({**self.request, 'revision': 1})
        empty = self.runtime.drafts.create(str(uuid.uuid4()))
        with self.assertRaisesRegex(ValueError, '2–10'):
            self.manager.start({**self.request, 'draft_id': empty['id'], 'revision': empty['revision']})
        self.assertIsNone(self.manager.current())

    def test_concurrent_start_cannot_open_two_sessions(self):
        results = []
        def start(request):
            try: results.append(self.manager.start(request))
            except TransferConflict: results.append('conflict')
        threads = [threading.Thread(target=start, args=({**self.request, 'id': str(uuid.uuid4())},)) for _ in range(2)]
        for worker in threads: worker.start()
        for worker in threads: worker.join(4)
        self.assertEqual(1, results.count('conflict'))
        self.assertEqual(1, sum(isinstance(result, dict) for result in results))

    def test_old_stop_cannot_stop_new_session(self):
        first = self.manager.start(self.request)
        self.manager.stop(first['id'])
        second = self.manager.start({**self.request, 'id': str(uuid.uuid4())})
        self.manager.stop(first['id'])
        self.assertEqual(200, self.media(second['url'])[0])

    def test_second_backend_cannot_interrupt_or_replace_first_transfer(self):
        first = self.manager.start(self.request)
        second = CarouselTransfers(self.manager.database, self.runtime.drafts)
        self.assertEqual('serving', second.current()['state'])
        with self.assertRaises(TransferConflict):
            second.start({**self.request, 'id': str(uuid.uuid4())})
        second.stop(first['id'])
        second.close()
        self.assertEqual(200, self.media(first['url'])[0])
        self.manager.stop(first['id'])
        restarted = second.start({**self.request, 'id': str(uuid.uuid4())})
        try:
            self.assertEqual('serving', restarted['state'])
        finally:
            second.close()

    def test_target_addresses_types_and_control_ports_are_checked(self):
        for changes in ({'device_id': 'C241'}, {'client': '0.0.0.0'}, {'bind': '8.8.8.8'}, {'port': 9913},
                        {'account': ''}, {'account': 'x/../y'}, {'minutes': 0}, {'minutes': True},
                        {'id': None}, {'revision': True}, {'bind': 123}, {'port': '9916'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.start({**self.request, **changes})
        self.assertIsNone(self.manager.current())

    def test_cross_origin_or_wrong_host_cannot_start_or_read_link(self):
        for headers in ({'Origin': 'https://example.com'}, {'Host': 'evil.example'}):
            self.assertEqual(403, self.api('/api/farm/transfers', self.request, headers)[0])
            self.assertEqual(403, self.api('/api/farm/transfers/current', headers=headers)[0])
        self.assertIsNone(self.manager.current())

    def test_stop_still_works_while_other_operation_lock_is_held(self):
        session = self.manager.start(self.request)
        with self.runtime.operation_lock:
            code, body = self.api(f"/api/farm/transfers/{session['id']}/stop", {})
        self.assertEqual(200, code, body)
        self.assertEqual('closed', body['transfer']['state'])

    def test_slow_client_cannot_prevent_stop(self):
        session = self.manager.start(self.request)
        client = socket.create_connection(('127.0.0.1', self.port), timeout=3)
        try:
            client.sendall(b'GET / HTTP/1.1\r\nHost: ')
            deadline = time.monotonic() + 2
            while not self.manager.server.connections and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(self.manager.server.connections)
            start = time.monotonic()
            result = self.manager.stop(session['id'])
            self.assertEqual('closed', result['state'])
            # Windows may finish a blocked receive at its socket timeout. The
            # acceptance boundary is bounded closure, not sub-second UI latency.
            self.assertLess(time.monotonic() - start, 4)
        finally:
            client.close()

    def test_control_server_refuses_lan_binding(self):
        with self.assertRaisesRegex(ValueError, 'loopback'):
            backend.FarmControlServer(('0.0.0.0', 0), backend.FarmRequestHandler)

    def test_taken_control_port_refuses_before_runtime_or_data_changes(self):
        occupied = backend.FarmControlServer(('127.0.0.1', 0), backend.FarmRequestHandler)
        try:
            with patch.object(sys, 'argv', ['farm', '--no-browser', '--port', str(occupied.server_port)]), patch.object(backend, 'FarmBackendRuntime') as runtime:
                with self.assertRaises(OSError):
                    backend.main()
            runtime.assert_not_called()
        finally:
            occupied.server_close()


if __name__ == '__main__':
    unittest.main()

"""Emergency stop in a phone window: the window's own kernel, the window's own phone, and an honest answer.

The kernel here is a loopback stand-in that records what it is sent. No phone, no real kernel.
"""
import http.server
import json
import socket
import threading
import unittest
import uuid
from unittest.mock import patch

from farm_test_network import allowed_ports
from test_farm_draft_runs import Drafts, FixtureRuns, CONFIG
from test_farm_http_jobs import FarmHttpJobsTests

PHONE = dict(board='C214', deviceId='02:00:00:00:00:20', receiver='iMouse2-20', slot=20)   # A fixture phone, not a real one.
STOPPED = dict(status=200, message='ok', data=dict(code=0, message='Input released; previous tokens revoked.'))
RELEASE_FAILED = dict(status=200, message='ok', data=dict(code=33, message='Release failed; input remains stopped. Check the board.'))


class FakeKernel:
    """Answers every POST with `reply` and keeps what it was sent."""
    def __init__(self, reply, order=None, status=200):
        self.reply, self.requests, self.order = reply, [], order if order is not None else []
        kernel = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or b'{}')
                kernel.requests.append((self.path, body)); kernel.order.append('kernel')
                raw = kernel.reply if isinstance(kernel.reply, bytes) else json.dumps(kernel.reply).encode('utf-8')
                self.send_response(status); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def log_message(self, *args): pass
        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.httpd.server_address[1]; allowed_ports.add(self.port)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True); self.thread.start()

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close(); self.thread.join(2); allowed_ports.discard(self.port)


class WindowStopTests(unittest.TestCase):
    setUp = FarmHttpJobsTests.setUp
    tearDown = FarmHttpJobsTests.tearDown
    request = FarmHttpJobsTests.request
    outside_connections = FarmHttpJobsTests.outside_connections

    def window(self, reply=STOPPED, port=None, **kernel_options):
        """Make this backend the window of PHONE on a stand-in kernel (or on `port`, where nothing listens)."""
        kernel = None
        if port is None:
            kernel = FakeKernel(reply, **kernel_options); self.addCleanup(kernel.close); port = kernel.port
        config = dict(version=2, api=f'http://127.0.0.1:{port}/api', kernelSha256='a' * 64, expectedUid='fixture', phone=PHONE,
                      allowed=['C214', 'C24C'], account=None, mediaBind='192.0.2.1', mediaClient='192.0.2.2', mediaPort=9927)
        self.runtime.draft_creations.config = config
        self.runtime.execution_mode = 'live'
        return kernel

    def test_stop_goes_to_the_windows_own_kernel_for_the_windows_own_phone(self):
        kernel = self.window()
        status, body = self.request('/api/farm/emergency-stop', {'device_id': 'C24C'})   # What the console has always sent.
        self.assertEqual(200, status, body)
        self.assertEqual([('/api/', {'fun': '/input/stop', 'data': {'id': PHONE['deviceId']}})], kernel.requests)
        self.assertEqual(('ok', 'C214', True, 'C214', True), (body['status'], body['stopped'], body['phoneStopped'], body['device'],
                                                              body['preparationPaused']))
        self.assertEqual(0, body['kernel_response']['code'])
        self.assertEqual([], self.outside_connections())   # Nothing went to the old single-phone kernel on 9913.

    def test_the_phone_is_stopped_before_the_job_journal_or_the_schedule_store_is_touched(self):
        order = []
        kernel = self.window(order=order)
        cancel, pause = self.runtime.jobs.cancel_active, self.runtime.preparation.pause
        with patch.object(self.runtime.jobs, 'cancel_active', side_effect=lambda: order.append('cancel') or cancel()), \
                patch.object(self.runtime.preparation, 'pause', side_effect=lambda: order.append('pause') or pause()):
            self.assertEqual(200, self.request('/api/farm/emergency-stop', {})[0])
        self.assertEqual(['kernel', 'cancel', 'pause'], order); self.assertEqual(1, len(kernel.requests))

    def test_a_running_window_job_is_cancelled_and_named(self):
        kernel = self.window()
        service = FixtureRuns(self.root / 'runs', Drafts(), self.runtime.jobs, CONFIG); service.wait = True
        self.runtime.reel_creations = service
        spec = dict(id=str(uuid.uuid4()), draft_id=str(uuid.uuid4()), revision=3, store_id=service.store_id)
        self.assertEqual(202, self.request('/api/farm/reel-creations', spec)[0])
        self.assertTrue(service.entered.wait(2))
        status, body = self.request('/api/farm/emergency-stop', {})
        self.assertEqual((200, spec['id'], True), (status, body['cancelledJob'], body['phoneStopped']))
        self.assertTrue(self.runtime.jobs._jobs[spec['id']].done.wait(4))
        self.assertEqual('cancelled', self.request('/api/farm/reel-creations/' + spec['id'])[1]['run']['jobStatus'])
        self.assertEqual(1, len(kernel.requests))

    def test_a_kernel_that_does_not_confirm_is_never_reported_as_stopped(self):
        for name, reply in (('release failed', RELEASE_FAILED), ('no code', dict(status=200, data={})),
                            ('one phone refused', dict(data=dict(code=0, results=[dict(code=0), dict(code=5)]))),
                            ('error envelope', dict(status=500, message='Unknown phone', data=None))):
            with self.subTest(name):
                kernel = self.window(reply)
                status, body = self.request('/api/farm/emergency-stop', {})
                self.assertEqual(502, status, body)
                self.assertEqual(('kernel_refused', None, False, 'C214'), (body['status'], body['stopped'], body['phoneStopped'], body['device']))
                self.assertIn('Input may still be running', body['error'])
                self.assertEqual(1, len(kernel.requests)); self.assertTrue(body['preparationPaused'])   # The rest still happens.

    def test_an_unreachable_or_broken_kernel_is_reported_as_unreachable(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0)); closed = probe.getsockname()[1]
        allowed_ports.add(closed); self.addCleanup(allowed_ports.discard, closed)
        self.window(port=closed)
        status, body = self.request('/api/farm/emergency-stop', {})
        self.assertEqual(502, status, body)
        self.assertEqual(('kernel_unreachable', None, False, 'C214', True), (body['status'], body['stopped'], body['phoneStopped'],
                                                                            body['device'], body['preparationPaused']))
        self.assertIn('did not answer the stop for C214', body['error'])
        for name, options in (('http error', dict(reply=STOPPED, status=500)), ('not json', dict(reply=b'stopped'))):
            with self.subTest(name):
                self.window(**options)
                status, body = self.request('/api/farm/emergency-stop', {})
                self.assertEqual((502, 'kernel_unreachable', False), (status, body['status'], body['phoneStopped']))

    def test_a_failed_schedule_pause_after_a_confirmed_stop_is_partial_and_still_says_the_phone_stopped(self):
        self.window()
        with patch.object(self.runtime.preparation, 'pause', side_effect=OSError('Schedule storage unavailable')):
            status, body = self.request('/api/farm/emergency-stop', {})
        self.assertEqual((500, 'partial', True, 'C214', False), (status, body['status'], body['phoneStopped'], body['stopped'],
                                                               body['preparationPaused']))
        self.assertIn('Phone stop completed', body['error'])

    def test_a_backend_without_a_window_sends_nothing_and_claims_nothing(self):
        status, body = self.request('/api/farm/emergency-stop', {'device_id': 'C24C'})
        self.assertEqual((200, None, False, None), (status, body['stopped'], body['phoneStopped'], body['cancelledJob']))
        self.assertEqual([], self.outside_connections())


del FarmHttpJobsTests


if __name__ == '__main__':
    unittest.main()

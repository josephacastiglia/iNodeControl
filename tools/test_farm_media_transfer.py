"""Real loopback HTTP checks. Never calls the kernel, phones or external hosts."""
import base64
import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
import zipfile

from PIL import Image
from farm_drafts import CarouselDrafts
from farm_media_transfer import TransferPackage, MediaTransferServer, checked_address
from farm_test_network import allowed_ports, network_guard


class MediaTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='farm-transfer-')
        root = Path(cls.temp.name)
        store = CarouselDrafts(root / 'drafts.db', root / 'stage')
        draft = store.create(str(uuid.uuid4()), title='<script>never execute</script>')
        for color in ('red', 'blue', 'green'):
            raw = io.BytesIO()
            Image.new('RGB', (1080, 1350), color).save(raw, 'PNG')
            draft = store.import_image(draft['id'], draft['revision'], color + '.png', base64.b64encode(raw.getvalue()).decode())
        cls.caption = 'Test caption with spaces\nUnicode: café 🎉 </textarea><script>evil()</script>'
        draft = store.save(draft['id'], draft['revision'], draft['title'], cls.caption, draft['slideIds'][::-1])
        cls.raw = store.export(draft['id'], draft['revision'])
        cls.package = TransferPackage(cls.raw)
        cls.hashes = [slide['sha256'] for slide in draft['slides']]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def start(self, **kwargs):
        self.events = []
        self.server = MediaTransferServer(self.package, '127.0.0.1', 0, kwargs.pop('allowed_client', '127.0.0.1'), on_event=self.events.append, **kwargs)
        allowed_ports.add(self.server.server_port)
        thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        def cleanup():
            self.server.shutdown()
            self.server.server_close()
            thread.join(2)
            allowed_ports.discard(self.server.server_port)
        self.addCleanup(cleanup)

    def request(self, path='', method='GET', host=None):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            client.request(method, path or self.server.prefix, headers={'Host': host or self.server.authority})
            response = client.getresponse()
            return response.status, dict(response.headers), response.read()
        finally:
            client.close()

    def test_ordered_image_bytes_and_caption_survive_real_http(self):
        self.start()
        for i, digest in enumerate(self.hashes, 1):
            status, headers, body = self.request(self.server.prefix + f'{i:02}.jpg')
            self.assertEqual(200, status)
            self.assertEqual(digest, hashlib.sha256(body).hexdigest())
            self.assertEqual('image/jpeg', headers['Content-Type'])
            self.assertEqual('no-store', headers['Cache-Control'])
        self.assertEqual(self.caption, self.request(self.server.prefix + 'caption.txt')[2].decode())
        self.assertEqual({'01.jpg', '02.jpg', '03.jpg'}, self.server.served_images)

    def test_page_escapes_user_text_and_has_no_control_or_publish_route(self):
        self.start()
        status, headers, body = self.request()
        self.assertEqual(200, status)
        text = body.decode()
        self.assertIn('&lt;script&gt;never execute&lt;/script&gt;', text)
        self.assertIn('&lt;/textarea&gt;&lt;script&gt;evil()', text)
        self.assertIn('Do not tap Share', text)
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        self.assertEqual('no-referrer', headers['Referrer-Policy'])
        for path in ('/api/farm/state', '/api/farm/drafts', '/api/input/acquire', '/settings.json', '/manifest.json'):
            self.assertEqual(404, self.request(path)[0])

    def test_wrong_token_and_path_traversal_and_query_refused(self):
        self.start()
        for path in ('/t/wrong/01.jpg', self.server.prefix + '../settings.json', self.server.prefix + '%2e%2e/settings.json', self.server.prefix + '01.jpg?next=/api', self.server.prefix + 'slide/0', self.server.prefix + 'slide/99'):
            self.assertEqual(404, self.request(path)[0], path)

    def test_wrong_phone_refused(self):
        self.start(allowed_client='127.0.0.2')
        self.assertEqual(404, self.request()[0])
        self.assertEqual(set(), self.server.served_images)

    def test_wrong_host_refused_and_no_cross_origin_permission(self):
        self.start()
        self.assertEqual(404, self.request(host='attacker.example')[0])
        self.assertNotIn('Access-Control-Allow-Origin', self.request()[1])

    def test_expiration_prevents_more_downloads(self):
        clock = [0]
        self.start(minutes=1, clock=lambda: clock[0])
        self.assertEqual(200, self.request()[0])
        clock[0] = 60
        self.assertEqual(404, self.request()[0])
        self.assertEqual(404, self.request(self.server.prefix + '01.jpg')[0])

    def test_mutations_refused_and_head_does_not_count_as_delivery(self):
        self.start()
        self.assertEqual(b'', self.request(self.server.prefix + '01.jpg', 'HEAD')[2])
        self.assertEqual(set(), self.server.served_images)
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            self.assertEqual(405, self.request(method=method)[0])

    def test_bound_port_collision_is_failure(self):
        self.start()
        with self.assertRaises(OSError):
            MediaTransferServer(self.package, '127.0.0.1', self.server.server_port, '127.0.0.1')

    def test_logs_do_not_contain_secret_url_or_caption(self):
        self.start()
        self.request(self.server.prefix + '01.jpg')
        self.request(self.server.prefix + 'caption.txt')
        serialized = json.dumps(self.events)
        self.assertNotIn(self.server.prefix, serialized)
        self.assertNotIn(self.caption, serialized)
        self.assertNotIn('savedInInstagram', serialized)
        self.assertIn('01.jpg', serialized)

    def modified(self, change):
        with zipfile.ZipFile(io.BytesIO(self.raw)) as original:
            files = {i.filename: original.read(i) for i in original.infolist()}
        change(files)
        result = io.BytesIO()
        with zipfile.ZipFile(result, 'w') as output:
            for name, raw in files.items(): output.writestr(name, raw)
        return result.getvalue()

    def test_corrupt_or_substituted_package_is_refused(self):
        for change in (lambda f: f.update({'01.jpg': b'bad image'}),
                       lambda f: f.update({'caption.txt': b'changed caption'}),
                       lambda f: f.update({'../settings.json': b'bad path'})):
            with self.assertRaises(ValueError): TransferPackage(self.modified(change))

    def test_other_phone_package_refused(self):
        def change(files):
            data = json.loads(files['manifest.json'])
            data['deviceId'] = 'C241'
            files['manifest.json'] = json.dumps(data).encode()
        with self.assertRaisesRegex(ValueError, 'C24C'): TransferPackage(self.modified(change))

    def test_bind_must_be_explicit_private_address_and_time_bounded(self):
        for address in ('0.0.0.0', '8.8.8.8', '224.0.0.1', '169.254.1.2', 'localhost'):
            with self.assertRaises(ValueError): checked_address(address)
        for minutes in (0, 61):
            with self.assertRaises(ValueError): MediaTransferServer(self.package, '127.0.0.1', 0, '127.0.0.1', minutes=minutes)

    def test_test_guard_still_blocks_real_kernel_and_external_connections(self):
        self.start()
        network_guard('socket.connect', (None, ('127.0.0.1', self.server.server_port)))
        for address in (('127.0.0.1', 9913), ('192.168.4.57', 80), ('example.com', 443)):
            with self.assertRaises(AssertionError): network_guard('socket.connect', (None, address))


if __name__ == '__main__':
    unittest.main()

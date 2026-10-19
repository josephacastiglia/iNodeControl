"""Actual codec and HTTP-range tests. No phone, desktop or external network access."""
import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
from unittest.mock import patch

from farm_video import VideoDrafts, VideoTransferPackage, normalize_video, probe_video, run_media
from farm_drafts import DraftConflict
from farm_media_transfer import MediaTransferServer
from farm_test_network import allowed_ports


class VideoDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='farm-video-fixture-')
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'source.mp4'
        run_media('ffmpeg', ['-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'color=c=red:s=320x240:r=15',
                            '-t', '2', '-c:v', 'mpeg4', str(cls.source)])
        cls.raw = cls.source.read_bytes()
        cls.encoded, cls.metadata = normalize_video(cls.raw)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='farm-video-test-'); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.stage = self.root / 'stage/C24C'; self.stage.mkdir(parents=True)
        (self.stage / 'source.mp4').write_bytes(self.raw)
        self.digest = hashlib.sha256(self.raw).hexdigest()
        (self.stage / 'manifest.json').write_text(json.dumps({'deviceId': 'C24C', 'assets': [
            {'url': '/stage/C24C/source.mp4', 'sha256': self.digest, 'bytes': len(self.raw)}]}), encoding='utf-8')
        self.store = VideoDrafts(self.root / 'drafts.db', self.root / 'stage')
        self.request = dict(id=str(uuid.uuid4()), device_id='C24C', format='tt_video', name='source.mp4', sha256=self.digest,
                            title='Draft only', caption='Exact caption with spaces\nand Unicode café 🎉')

    def create(self):
        # Codec acceptance uses the real fixture above. Store tests reuse its bytes.
        with patch('farm_video.normalize_video', return_value=(self.encoded, self.metadata)):
            return self.store.create(self.request)

    def test_normalization_is_h264_vertical_preserves_duration_and_full_frame(self):
        self.assertEqual(('h264', 'yuv420p', 720, 1280), tuple(self.metadata[k] for k in ('codec', 'pixelFormat', 'width', 'height')))
        self.assertAlmostEqual(2, self.metadata['seconds'], delta=.1)
        self.assertTrue(self.metadata['fitted']); self.assertTrue(self.metadata['upscaled'])
        video = self.root / 'encoded.mp4'; video.write_bytes(self.encoded)
        frame = run_media('ffmpeg', ['-v', 'error', '-i', str(video), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'])
        from PIL import Image
        with Image.open(io.BytesIO(frame)) as image:
            self.assertLess(max(image.getpixel((360, 50))), 10)  # margins, not a center crop
            self.assertGreater(image.getpixel((360, 640))[0], 200)
        self.assertEqual(self.raw, self.source.read_bytes())
        self.assertLess(self.encoded.index(b'moov'), self.encoded.index(b'mdat'))

    def test_audio_is_preserved_and_decodes_in_the_normalized_copy(self):
        source = self.root / 'with-audio.mp4'
        run_media('ffmpeg', ['-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'color=c=blue:s=180x320:r=15',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '1.5',
                            '-c:v', 'mpeg4', '-c:a', 'aac', str(source)])
        encoded, metadata = normalize_video(source.read_bytes())
        normalized = self.root / 'with-audio-normalized.mp4'; normalized.write_bytes(encoded)
        self.assertTrue(metadata['audio'])
        pcm = run_media('ffmpeg', ['-v', 'error', '-i', str(normalized), '-map', '0:a:0', '-f', 's16le', '-'])
        self.assertGreater(len(pcm), 48000)
        self.assertGreater(sum(byte != 0 for byte in pcm), 1000)
        self.assertAlmostEqual(1.5, metadata['seconds'], delta=.15)

    def test_immutable_snapshot_duplicate_request_and_restart(self):
        draft = self.create(); first = self.store.export(draft['id'], 1)
        self.assertEqual(draft, self.create())
        self.assertEqual(draft, VideoDrafts(self.root / 'drafts.db', self.root / 'stage').get(draft['id']))
        (self.stage / 'source.mp4').write_bytes(b'new source')
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            self.assertEqual(self.encoded, archive.read('video.mp4'))
            self.assertEqual(self.request['caption'], archive.read('caption.txt').decode())
        self.request['caption'] = 'different'
        with self.assertRaises(DraftConflict): self.create()

    def test_corrupt_staged_bytes_and_traversal_never_encode(self):
        for name in ('../source.mp4', 'missing.mp4'):
            with self.subTest(name=name), patch('farm_video.normalize_video', side_effect=AssertionError('No encode allowed')):
                with self.assertRaises(ValueError): self.store.create({**self.request, 'name': name})
        (self.stage / 'source.mp4').write_bytes(b'x' * len(self.raw))
        with patch('farm_video.normalize_video', side_effect=AssertionError('No encode allowed')):
            with self.assertRaisesRegex(ValueError, 'checksum'): self.store.create(self.request)

    def test_other_phone_and_unsupported_format_refused(self):
        for changes in ({'device_id': 'C241'}, {'format': 'yt_community'}, {'format': 'publish'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.store.create({**self.request, **changes})

    def test_caption_limits_never_silently_truncate(self):
        for changes in ({'caption': 'x' * 281}, {'caption': 'x' * 101, 'format': 'yt_short'}, {'caption': 'bad\0value'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.store.create({**self.request, **changes})
        self.assertEqual(self.request['caption'], self.create()['caption'])

    def test_failed_encoding_does_not_create_draft_or_replace_source(self):
        with patch('farm_video.normalize_video', side_effect=ValueError('encoder failed')):
            with self.assertRaisesRegex(ValueError, 'encoder failed'): self.store.create(self.request)
        with self.assertRaises(KeyError): self.store.get(self.request['id'])
        self.assertEqual(self.raw, (self.stage / 'source.mp4').read_bytes())

    def test_missing_tools_and_long_video_refuse_instead_of_fake_success(self):
        with patch('farm_video.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'ffprobe is required'): normalize_video(self.raw)
        with patch('farm_video.run_media', return_value=json.dumps({'streams': [{'codec_type': 'video'}], 'format': {'duration': '46'}}).encode()):
            with self.assertRaisesRegex(ValueError, '45 seconds'): probe_video(self.source)

    def test_video_package_has_exact_content_and_no_app_completion_claim(self):
        draft = self.create(); package = VideoTransferPackage(self.store.export(draft['id'], 1))
        self.assertEqual(self.encoded, package.video); self.assertEqual(self.request['caption'], package.caption)
        self.assertFalse(draft['savedInApp']); self.assertFalse(draft['published'])
        # tt_video now gets the automated TikTok package page; X and YouTube keep the supervised page.
        page = package.page('/test/', 'nonce').decode()
        self.assertIn('Do not tap Post, Share or Your Story.', page)
        self.assertIn('A download does not prove a Photos save or a TikTok draft.', page)
        with self.assertRaises(DraftConflict): self.store.export(draft['id'], 2)

    def test_corrupt_video_package_refused(self):
        draft = self.create(); raw = self.store.export(draft['id'], 1)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive: files = {n: archive.read(n) for n in archive.namelist()}
        files['video.mp4'] = b'bad'
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name, data in files.items(): archive.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'checksum'): VideoTransferPackage(buffer.getvalue())

    def test_real_http_ranges_head_expiry_and_no_false_save(self):
        draft = self.create(); package = VideoTransferPackage(self.store.export(draft['id'], 1))
        now = [0]; events = []
        server = MediaTransferServer(package, '127.0.0.1', 0, '127.0.0.1', minutes=1, clock=lambda: now[0], on_event=events.append)
        allowed_ports.add(server.server_port)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()
        def call(interval=None, method='GET'):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                connection.request(method, server.prefix + 'video.mp4', headers={'Range': interval} if interval else {})
                response = connection.getresponse(); return response.status, dict(response.headers), response.read()
            finally: connection.close()
        try:
            status, headers, body = call('bytes=0-1'); self.assertEqual((206, self.encoded[:2]), (status, body))
            self.assertEqual(f'bytes 0-1/{len(self.encoded)}', headers['Content-Range'])
            self.assertEqual(self.encoded[-12:], call('bytes=-12')[2])
            self.assertEqual(self.encoded[10:], call('bytes=10-')[2])
            self.assertEqual(self.encoded, call()[2]); self.assertEqual(b'', call(method='HEAD')[2])
            for interval in ('bytes=3-2', 'bytes=999999999-', 'bytes=0-1,3-4', 'bytes=-0', 'items=0-1'):
                self.assertEqual(416, call(interval)[0], interval)
            self.assertEqual(set(), server.served_images)
            self.assertNotIn('savedInApp', json.dumps(events)); self.assertNotIn(server.prefix, json.dumps(events))
            now[0] = 60; self.assertEqual(404, call()[0])
        finally:
            server.shutdown(); server.close_clients(); server.server_close(); thread.join(2); allowed_ports.discard(server.server_port)

    def test_control_api_prepares_recovers_and_stops_video_without_phone_input(self):
        import imouse_farm_server as backend
        import socket
        runtime = backend.FarmBackendRuntime(self.root / 'backend/farm.db', self.root / 'stage')
        httpd = backend.FarmControlServer(('127.0.0.1', 0), backend.FarmRequestHandler)
        allowed_ports.add(httpd.server_port)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0)); media_port = probe.getsockname()[1]
        allowed_ports.add(media_port)
        worker = threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        def request(path, data=None, port=None):
            connection = http.client.HTTPConnection('127.0.0.1', port or httpd.server_port, timeout=5)
            try:
                connection.request('GET' if data is None else 'POST', path, json.dumps(data) if data is not None else None,
                                   {'Content-Type': 'application/json'})
                response = connection.getresponse(); return response.status, response.read()
            finally: connection.close()
        with patch.object(backend, 'RUNTIME', runtime), patch('farm_video.normalize_video', return_value=(self.encoded, self.metadata)):
            worker.start()
            try:
                with runtime.operation_lock:
                    code, body = request('/api/farm/video-drafts', self.request)
                    self.assertEqual(409, code, body)
                    self.assertEqual('preparation_busy', json.loads(body)['status'])
                    self.assertEqual([], runtime.videos.list())
                code, body = request('/api/farm/video-drafts', self.request); self.assertEqual(200, code, body)
                response = json.loads(body); self.assertFalse(response['simulated']); draft = response['draft']
                self.assertEqual(draft, json.loads(request('/api/farm/video-drafts/' + draft['id'])[1])['draft'])
                self.assertEqual(draft, json.loads(request('/api/farm/video-drafts')[1])['drafts'][0])
                transfer_request = dict(id=str(uuid.uuid4()), draft_id=draft['id'], revision=1, kind='video', device_id='C24C',
                                        account='test.account', bind='127.0.0.1', client='127.0.0.1', port=media_port, minutes=1)
                code, body = request('/api/farm/transfers', transfer_request); self.assertEqual(200, code, body)
                transfer = json.loads(body)['transfer']; self.assertEqual('TikTok', transfer['platform'])
                from urllib.parse import urlsplit
                path = urlsplit(transfer['url']).path + 'video.mp4'
                self.assertEqual(self.encoded, request(path, port=media_port)[1])
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and not runtime.transfers.get(transfer['id'])['videoRequests']: time.sleep(.01)
                read = runtime.transfers.get(transfer['id']); self.assertEqual(1, read['videoRequests'])
                self.assertEqual('unverified', read['photosStatus']); self.assertFalse(read['publicationAttempted'])
                self.assertEqual(transfer['url'], json.loads(request('/api/farm/transfers', transfer_request)[1])['transfer']['url'])
                code, body = request('/api/farm/transfers/' + transfer['id'] + '/stop', {})
                self.assertEqual('closed', json.loads(body)['transfer']['state'])
                self.assertEqual([], runtime.mock_kernel.commands_dispatched)
            finally:
                runtime.transfers.close(); httpd.shutdown(); httpd.server_close(); worker.join(2)
                allowed_ports.discard(httpd.server_port); allowed_ports.discard(media_port)


if __name__ == '__main__': unittest.main()

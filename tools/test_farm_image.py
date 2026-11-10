"""Image packages (X image, TikTok photo): drafts, transfer, reference, runs base, routes. No phone access."""
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
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import numpy as np
from PIL import Image

import farm_reel_runs
from farm_draft_workflow import atomic_json
from farm_drafts import DraftConflict
from farm_image import (CANVAS, IMAGE_FORMATS, IMAGE_MODELS, PAGES, SLIDES, ImageDrafts, ImageReference,
                        normalize_image, render_test_images)
from farm_jobs import FarmJobs
from farm_media_transfer import MediaTransferServer, TransferPackage, image_delivery
from farm_reel_layout import FILL, SQUARE, video_match
from farm_reel_runs import ImageCreationRuns, ReelCreationRuns, image_content
from farm_test_network import allowed_ports
from farm_tiktok_layout import MODELS, media_match
import test_farm_http_jobs as http_jobs

BOARD = '724E'
PHONE = dict(board=BOARD, deviceId='02:00:00:00:00:17', receiver='iMouse2-17', slot=17)
CONFIG = dict(version=2, api='http://127.0.0.1:9916/api', kernelSha256='a'*64, expectedUid='test-only', phone=PHONE,
              allowed=[BOARD], account=None, mediaBind='127.0.0.1', mediaClient='127.0.0.1', mediaPort=0)
COLOURS = ((214, 40, 57), (21, 101, 192), (46, 160, 67), (245, 158, 11), (124, 58, 237))


def source_image(index, size=(900, 1200), fmt='PNG'):
    """A distinct, detailed test image: a coloured quadrant pattern per index."""
    image = Image.new('RGB', size, (240, 240, 235))
    width, height = size
    colour = COLOURS[index % len(COLOURS)]
    for row in range(4):
        for column in range(3):
            if (row + column + index) % 2:
                image.paste(colour, (column*width//3, row*height//4, (column+1)*width//3, (row+1)*height//4))
    image.paste((20, 20, 20), (width//3, height//2 - 40 - 30*index, 2*width//3, height//2 + 40))
    raw = io.BytesIO(); image.save(raw, fmt); return raw.getvalue()


def stage(root, fmt, count, board=BOARD, caption='Fresh image test'):
    folder = root/'stage'/board; folder.mkdir(parents=True, exist_ok=True)
    assets, chosen = [], []
    for index in range(count):
        name = f'slide-{index}.png'; raw = source_image(index)
        (folder/name).write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        assets.append({'url': f'/stage/{board}/{name}', 'sha256': digest, 'bytes': len(raw)})
        chosen.append({'name': name, 'sha256': digest})
    (folder/'manifest.json').write_text(json.dumps({'deviceId': board, 'assets': assets}), encoding='utf-8')
    drafts = ImageDrafts(root/'images.db', root/'stage', board)
    draft = drafts.create(dict(id=str(uuid.uuid4()), device_id=board, format=fmt, images=chosen, title='Image test',
                               caption=caption))
    return drafts, draft, chosen


def rewrite(package, change):
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    change(files)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in files.items(): archive.writestr(name, data)
    return output.getvalue()


class ImageDraftTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='farm-image-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_formats_counts_and_canvases(self):
        self.assertEqual({'x_image': 'X', 'tt_photo': 'TikTok'}, IMAGE_FORMATS)
        self.assertEqual((1, 1), SLIDES['x_image']); self.assertEqual((2, 10), SLIDES['tt_photo'])
        self.assertEqual(set(IMAGE_FORMATS), set(PAGES)); self.assertEqual(set(IMAGE_FORMATS), set(CANVAS))

    def test_x_image_is_exactly_one_fitted_jpeg_and_export_is_stable(self):
        drafts, draft, chosen = stage(self.root, 'x_image', 1)
        self.assertEqual(['01.jpg'], [a['file'] for a in draft['assets']])
        asset = draft['assets'][0]
        self.assertEqual((1080, 1350, 900, 1200, True), (asset['width'], asset['height'], asset['sourceWidth'], asset['sourceHeight'], asset['fitted']))
        self.assertEqual((False, False, BOARD, 'X'), (draft['published'], draft['savedInApp'], draft['deviceId'], draft['platform']))
        package = drafts.export(draft['id'], 1)
        self.assertEqual(package, drafts.export(draft['id'], 1))
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            self.assertEqual(['manifest.json', 'caption.txt', '01.jpg'], archive.namelist())
            with Image.open(io.BytesIO(archive.read('01.jpg'))) as image:
                self.assertEqual(('JPEG', (1080, 1350)), (image.format, image.size))
                self.assertEqual((255, 255, 255), image.convert('RGB').getpixel((2, 2)))   # White margin, nothing cropped.
        # The staged source is untouched.
        self.assertEqual(chosen[0]['sha256'], hashlib.sha256((self.root/'stage'/BOARD/'slide-0.png').read_bytes()).hexdigest())
        with self.assertRaises(DraftConflict): drafts.export(draft['id'], 2)

    def test_tiktok_photo_keeps_slide_order_on_a_black_9_16_canvas(self):
        drafts, draft, chosen = stage(self.root, 'tt_photo', 3)
        self.assertEqual(['01.jpg', '02.jpg', '03.jpg'], [a['file'] for a in draft['assets']])
        self.assertEqual([c['name'] for c in chosen], [a['sourceName'] for a in draft['assets']])
        with zipfile.ZipFile(io.BytesIO(drafts.export(draft['id'], 1))) as archive:
            with Image.open(io.BytesIO(archive.read('02.jpg'))) as image:
                self.assertEqual((1080, 1920), image.size)
                self.assertLess(sum(image.convert('RGB').getpixel((540, 3))), 20)   # Black bars above and below.

    def test_counts_duplicates_board_and_format_are_refused(self):
        drafts, draft, chosen = stage(self.root, 'tt_photo', 3)
        base = dict(device_id=BOARD, title='t', caption='c')
        cases = [dict(format='tt_photo', images=chosen[:1]),                       # TikTok photo needs 2-10.
                 dict(format='x_image', images=chosen[:2]),                        # X image is exactly one.
                 dict(format='tt_photo', images=[chosen[0], chosen[0]]),           # Distinct slides only.
                 dict(format='tt_photo', images=chosen, device_id='C24C'),         # Another phone.
                 dict(format='ig_carousel', images=chosen),
                 dict(format='tt_photo', images=[dict(chosen[0], extra=1), chosen[1]])]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                drafts.create(dict(base, id=str(uuid.uuid4()), **case))
        self.assertEqual(1, len(drafts.list()))

    def test_same_id_returns_saved_draft_and_other_content_conflicts(self):
        drafts, draft, chosen = stage(self.root, 'tt_photo', 2)
        request = dict(id=draft['id'], device_id=BOARD, format='tt_photo', images=chosen, title='Image test', caption='Fresh image test')
        self.assertEqual(draft, drafts.create(request))
        with self.assertRaises(DraftConflict): drafts.create(dict(request, images=chosen[::-1]))

    def test_changed_stage_is_refused(self):
        drafts, _, chosen = stage(self.root, 'tt_photo', 2)
        (self.root/'stage'/BOARD/'slide-1.png').write_bytes(source_image(4))
        with self.assertRaises(ValueError):
            drafts.create(dict(id=str(uuid.uuid4()), device_id=BOARD, format='tt_photo', images=chosen, title='t', caption='c'))

    def test_sources_lists_images_in_manifest_order(self):
        drafts, _, chosen = stage(self.root, 'tt_photo', 3)
        self.assertEqual([c['name'] for c in chosen], [s['name'] for s in drafts.sources()])

    def test_normalize_refuses_animation_and_garbage(self):
        frames = [Image.new('RGB', (40, 40), c) for c in COLOURS[:2]]
        animated = io.BytesIO(); frames[0].save(animated, 'GIF', save_all=True, append_images=frames[1:])
        for raw in (b'not an image', animated.getvalue(), b''):
            with self.assertRaises(ValueError): normalize_image(raw, 'x_image')

    def test_render_test_images_are_distinct_slides(self):
        paths = render_test_images('abc123', self.root, 3, 'TIKTOK PHOTO TEST')
        self.assertEqual(3, len({hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))


class ImageTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='farm-image-transfer-')
        root = Path(cls.temp.name)
        cls.x_drafts, cls.x_draft, _ = stage(root/'x', 'x_image', 1)
        cls.t_drafts, cls.t_draft, _ = stage(root/'t', 'tt_photo', 3)
        cls.x_raw = cls.x_drafts.export(cls.x_draft['id'], 1)
        cls.t_raw = cls.t_drafts.export(cls.t_draft['id'], 1)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_image_packages_parse_only_for_their_own_board(self):
        package = TransferPackage(self.t_raw, BOARD)
        self.assertEqual(['01.jpg', '02.jpg', '03.jpg'], list(package.images))
        self.assertEqual(('tt_photo', 'TikTok', BOARD, 'TikTok photo draft'), (package.format, package.app, package.board, package.title))
        self.assertRegex(package.download_name, '^imouse-tp-[a-z]{6}$')
        self.assertRegex(TransferPackage(self.x_raw, BOARD).download_name, '^imouse-xi-[a-z]{6}$')
        for board in ('C24C', 'C214'):
            with self.subTest(board=board), self.assertRaises(ValueError): TransferPackage(self.t_raw, board)
        with self.assertRaises(ValueError): TransferPackage(self.t_raw)   # The C24C default never serves another phone's draft.

    def test_tampered_extra_or_resized_entries_are_refused(self):
        def swap(files): files['01.jpg'], files['02.jpg'] = files['02.jpg'], files['01.jpg']
        def extra(files): files['04.jpg'] = files['03.jpg']
        def published(files):
            manifest = json.loads(files['manifest.json']); manifest['published'] = True; files['manifest.json'] = json.dumps(manifest).encode()
        def resized(files):
            out = io.BytesIO(); Image.new('RGB', (1080, 1350)).save(out, 'JPEG'); files['02.jpg'] = out.getvalue()
            manifest = json.loads(files['manifest.json'])
            manifest['assets'][1].update(sha256=hashlib.sha256(out.getvalue()).hexdigest(), bytes=len(out.getvalue()))
            files['manifest.json'] = json.dumps(manifest).encode()
        def caption(files): files['caption.txt'] = b'other'
        def video(files): files['video.mp4'] = b'x'
        for change in (swap, extra, published, resized, caption, video):
            with self.subTest(change=change.__name__), self.assertRaises(ValueError):
                TransferPackage(rewrite(self.t_raw, change), BOARD)

    def test_carousel_pages_are_byte_identical_and_carousel_stays_c24c(self):
        package = TransferPackage.__new__(TransferPackage)
        package.images = {'01.jpg': b'', '02.jpg': b'', '03.jpg': b''}
        package.title = 'Golden <title> & "x"'
        package.caption = 'Line one\nCafé </textarea><script>x()</script>'
        golden = ['60162457be7f39ad5df2cdbcd65f8727f4fe47c5fa3dfee10c363223db88d739',
                  '05fa8d5291ef7090ea391c2d7141b324c6fe9d9959e466a582293b79b7f11a1f',
                  'fecec7fb8758721285b6d42b5dc47d2dab0dec411bb3f1513450fc4ce8246bf8',
                  'c7c250a4e102d839ce6139878edf7b09f423de4535d6cc8f385f18cb0d146634']
        self.assertEqual(golden, [hashlib.sha256(package.page('/t/abc/', 'NONCE', n)).hexdigest() for n in range(4)])
        package.format, package.app = 'ig_carousel', 'Instagram'
        self.assertEqual(golden[0], hashlib.sha256(package.page('/t/abc/', 'NONCE')).hexdigest())

    def test_image_pages_use_the_carousel_layout_with_their_own_app(self):
        x = TransferPackage(self.x_raw, BOARD)
        index = x.page('/t/a/', 'n').decode('utf-8')
        for text in ('<h1>X image draft</h1>', 'Package ' + x.download_name, '1. Save the image', '>Open slide 1 of 1</a>',
                     'Copy caption', 'Verify the pasted text in X.', '3. Save in X', 'Save to drafts', 'Do not tap Post'):
            self.assertIn(text, index)
        slide = x.page('/t/a/', 'n', 1).decode('utf-8')
        for text in ('Slide 1 of 1', 'Touch and hold the image, then choose Save to Photos.', 'selecting it in X.', '>Back to caption</a>'):
            self.assertIn(text, slide)
        tiktok = TransferPackage(self.t_raw, BOARD)
        pages = [tiktok.page('/t/a/', 'n', n).decode('utf-8') for n in range(4)]
        self.assertIn('1. Save the slides in order', pages[0]); self.assertIn('>Open slide 3 of 3</a>', pages[0])
        self.assertIn('keep the sound', pages[0]); self.assertIn('Next slide →', pages[1]); self.assertIn('Back to caption', pages[3])
        self.assertFalse(any('Instagram' in page for page in pages + [index, slide]))
        with self.assertRaises(KeyError): tiktok.page('/t/a/', 'n', 4)

    def test_each_image_is_served_and_counted(self):
        package = TransferPackage(self.t_raw, BOARD)
        events = []
        server = MediaTransferServer(package, '127.0.0.1', 0, '127.0.0.1', minutes=1, on_event=events.append)
        allowed_ports.add(server.server_port)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()
        try:
            def fetch(route, method='GET'):
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                client.request(method, server.prefix + route, headers={'Host': server.authority})
                response = client.getresponse(); body = response.read(); client.close()
                return response.status, response.headers.get('Content-Type'), body
            self.assertEqual((200, 'image/jpeg', package.images['01.jpg']), fetch('01.jpg'))
            fetch('01.jpg'); fetch('03.jpg'); fetch('02.jpg', 'HEAD')
            self.assertEqual(200, fetch('slide/3')[0]); self.assertEqual(404, fetch('slide/4')[0]); self.assertEqual(404, fetch('video.mp4')[0])
        finally:
            server.shutdown(); server.close_clients(); server.server_close(); thread.join(2); allowed_ports.discard(server.server_port)
        self.assertEqual({'01.jpg': 2, '02.jpg': 0, '03.jpg': 1}, server.image_requests)
        record = image_delivery(events, package.images)
        self.assertEqual(({'01.jpg': 2, '02.jpg': 0, '03.jpg': 1}, ['01.jpg', '03.jpg'], False, False),
                         (record['imageRequests'], record['imagesDelivered'], record['everyImageDelivered'], record['photosSaveProvenByHttp']))
        self.assertFalse(image_delivery([], [])['everyImageDelivered'])


class ImageReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = [normalize_image(source_image(i), 'tt_photo')[0] for i in range(3)]
        cls.reference = ImageReference(cls.images)

    def test_shapes_match_the_video_references(self):
        self.assertEqual(FILL, IMAGE_MODELS['fill'][1]); self.assertEqual(SQUARE, IMAGE_MODELS['square'][1])
        for name, (_, shape) in MODELS.items():
            self.assertEqual(shape, IMAGE_MODELS[name][1], name)
        for name, (shape, targets) in self.reference.models.items():
            self.assertEqual(3, len(targets))
            self.assertEqual((shape[1], shape[0], 3), targets[0].shape, name)
        self.assertIs(self.reference.fill, self.reference.models['fill'][1])
        self.assertIs(self.reference.square, self.reference.models['square'][1])

    def frame(self, raw, box, model):
        """A 500x1080 frame showing one package image in `box` under a crop model."""
        image = np.full((1080, 500, 3), 128, dtype=np.uint8)
        left, top, right, bottom = box
        with Image.open(io.BytesIO(raw)) as source:
            from PIL import ImageOps
            mode, shape = IMAGE_MODELS[model]
            size = (right - left, bottom - top)
            rendered = ImageOps.fit(source.convert('RGB'), size) if mode == 'cover' else ImageOps.pad(source.convert('RGB'), size, color=(0, 0, 0))
            image[top:bottom, left:right] = np.asarray(rendered)
        return image

    def test_media_match_names_the_slide(self):
        box = (20, 300, 200, 480)
        for index in range(3):
            frame = self.frame(self.images[index], box, 'square')
            result = media_match(None, box, self.reference, 'square', image=frame)
            self.assertTrue(result['matched'], result); self.assertEqual(index, result['index'])
            self.assertTrue(video_match(None, box, self.reference, square=True, image=frame)['matched'])
        full = (0, 100, 500, 989)
        result = media_match(None, full, self.reference, 'fit', image=self.frame(self.images[1], full, 'fit'))
        self.assertEqual((True, 1), (result['matched'], result['index']))

    def test_per_slide_reference_rejects_other_slides(self):
        box = (20, 300, 200, 480)
        second = self.reference.slide(1)
        self.assertEqual((1, [self.reference.hashes[1]]), (second.count, second.hashes))
        self.assertTrue(media_match(None, box, second, 'square', image=self.frame(self.images[1], box, 'square'))['matched'])
        self.assertFalse(media_match(None, box, second, 'square', image=self.frame(self.images[0], box, 'square'))['matched'])
        with self.assertRaises(IndexError): self.reference.slide(3)

    def test_invalid_input_is_refused(self):
        for value in ([], [b''], b'raw', [b'not an image']):
            with self.subTest(value=value), self.assertRaises(ValueError): ImageReference(value)


class FakeImageWorkflow:
    """Stands in for a lane workflow: fetches every slide over real loopback HTTP, sends no input."""
    calls = []
    fetch = ('01.jpg', '02.jpg', '03.jpg')

    def __init__(self, folder, kernel, store, images, caption, refs, kernel_sha, uid, **kwargs):
        FakeImageWorkflow.calls.append(dict(images=images, caption=caption, **kwargs))
        self.url, self.package_hash = kwargs['transfer_url'], kwargs['package_hash']

    def run(self):
        parts = urlsplit(self.url)
        allowed_ports.add(parts.port)
        for name in self.fetch:
            client = http.client.HTTPConnection('127.0.0.1', parts.port, timeout=3)
            client.request('GET', parts.path + name, headers={'Host': parts.netloc}); client.getresponse().read(); client.close()
        return dict(packageSha256=self.package_hash, source='candidate_phone_workflow', state='created_unverified', cleanup='confirmed', evidenceExport='confirmed', account='bound-account',
                    actions=[], observations=[], commands=[])


class FakeImageVerification:
    calls = []

    def __init__(self, folder, kernel, store, images, caption, refs, kernel_sha, uid, **kwargs):
        FakeImageVerification.calls.append(dict(images=images, caption=caption, **kwargs))

    def run(self):
        return dict(state='validation_passed', savedDraftVerified=True, cleanup='confirmed', evidenceExport='confirmed',
                    actions=[], observations=[])


class LaneImageRuns(ImageCreationRuns):
    """What a lane adds: its format, workflow, verifier and committing prefixes."""
    action_name = 'create-tiktok-photo-draft'
    FORMAT, LABEL = 'tt_photo', 'TikTok photo'
    workflow, verifier, committing = FakeImageWorkflow, FakeImageVerification, ('save-photo-', 'save-tiktok-draft')
    caption_supported = staticmethod(lambda caption: 0 < len(caption) <= 24)


class ImageRunsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='farm-image-runs-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.drafts, self.draft, _ = stage(self.root, 'tt_photo', 3)
        self.jobs = FarmJobs(journal_path=self.root/'jobs.db'); self.addCleanup(self.jobs.close)
        FakeImageWorkflow.calls, FakeImageVerification.calls, FakeImageWorkflow.fetch = [], [], ('01.jpg', '02.jpg', '03.jpg')

    def spec(self, service):
        return dict(id=str(uuid.uuid4()), draft_id=self.draft['id'], revision=1, store_id=service.store_id)

    def wait(self, service, run_id):
        end = time.monotonic() + 10
        while time.monotonic() < end:
            result = service.get(run_id)
            if result['terminal']: return result
            time.sleep(.02)
        self.fail('Run did not finish.')

    def test_supports_count_board_caption_and_disabled_without_config(self):
        service = LaneImageRuns(self.root/'runs', self.drafts, self.jobs, CONFIG)
        self.assertTrue(service.capability()['enabled'])
        self.assertTrue(service.eligibility(self.draft['id'], 1)['eligible'])
        self.assertFalse(LaneImageRuns(self.root/'off', self.drafts, self.jobs).capability()['enabled'])
        long_root = self.root/'long'; long_root.mkdir()
        drafts, draft, _ = stage(long_root, 'tt_photo', 2, caption='x'*25)
        self.assertFalse(LaneImageRuns(long_root/'runs', drafts, self.jobs, CONFIG).eligibility(draft['id'], 1)['eligible'])
        x_root = self.root/'x'; x_root.mkdir()
        drafts, draft, _ = stage(x_root, 'x_image', 1)
        self.assertFalse(LaneImageRuns(x_root/'runs', drafts, self.jobs, CONFIG).eligibility(draft['id'], 1)['supportedContent'])
        other = dict(CONFIG, phone=dict(PHONE, board='C214'))
        self.assertFalse(LaneImageRuns(self.root/'other', self.drafts, self.jobs, other).supports(self.drafts.export(self.draft['id'], 1)))

    def test_content_identity_covers_caption_and_ordered_images(self):
        manifest, caption, content = image_content(self.drafts.export(self.draft['id'], 1))
        self.assertEqual(('tt_photo', 'Fresh image test'), (manifest['format'], caption))
        other = self.root/'reordered'; other.mkdir()
        drafts, draft, chosen = stage(other, 'tt_photo', 3)
        reordered = drafts.create(dict(id=str(uuid.uuid4()), device_id=BOARD, format='tt_photo', images=chosen[::-1],
                                       title='Image test', caption='Fresh image test'))
        self.assertEqual(content, image_content(drafts.export(draft['id'], 1))[2])
        self.assertNotEqual(content, image_content(drafts.export(reordered['id'], 1))[2])

    def run_once(self):
        service = LaneImageRuns(self.root/'runs', self.drafts, self.jobs, CONFIG)
        spec = self.spec(service)
        with patch.object(farm_reel_runs, 'CreationKernel', MagicMock()), patch.object(farm_reel_runs, 'ObservationStore', MagicMock()), \
                patch.object(farm_reel_runs, 'references', lambda: {}):
            service.start(spec); result = self.wait(service, spec['id'])
        return service, spec, result

    def test_execute_serves_every_slide_then_verifies_with_an_image_reference(self):
        service, spec, result = self.run_once()
        self.assertEqual('verified', result['state']); self.assertTrue(result['savedDraftVerified'])
        call = FakeImageWorkflow.calls[0]
        self.assertEqual(['01.jpg', '02.jpg', '03.jpg'], call['slides']); self.assertEqual('TikTok photo draft', call['transfer_title'])
        self.assertRegex(call['package_name'], '^imouse-tp-[a-z]{6}$'); self.assertIsNone(call['account'])
        self.assertEqual([BOARD], call['allowed']); self.assertIsInstance(call['images'], ImageReference)
        self.assertEqual([a['sha256'] for a in self.draft['assets']], call['images'].hashes)
        self.assertEqual('bound-account', FakeImageVerification.calls[0]['account'])   # Not pinned: the bound account is rechecked.
        delivery = result['workflow']['mediaDelivery']
        self.assertEqual({'01.jpg': 1, '02.jpg': 1, '03.jpg': 1}, delivery['imageRequests'])
        self.assertTrue(delivery['everyImageDelivered']); self.assertTrue(delivery['stopped']); self.assertFalse(delivery['photosSaveProvenByHttp'])
        with self.assertRaises(Exception): service.start(dict(spec, id=str(uuid.uuid4())))   # Held: never a second draft.

    def test_a_slide_never_requested_stops_before_verification(self):
        FakeImageWorkflow.fetch = ('01.jpg', '03.jpg')
        _, _, result = self.run_once()
        self.assertEqual('review_required', result['state']); self.assertFalse(result['savedDraftVerified'])
        self.assertEqual([], FakeImageVerification.calls)
        self.assertEqual(['01.jpg', '03.jpg'], result['workflow']['mediaDelivery']['imagesDelivered'])

    def test_retry_needs_committing_prefixes(self):
        stopped = dict(terminal=True, state='review_required', workflow=dict(source='candidate_phone_workflow', cleanup='confirmed',
                                                                            evidenceExport='confirmed', commands=[]))
        from farm_x_runs import XImageCreationRuns
        self.assertTrue(LaneImageRuns.retry_allowed(stopped))
        self.assertTrue(XImageCreationRuns.retry_allowed(stopped))   # Its own prefixes decide.
        committed = dict(stopped, workflow=dict(stopped['workflow'], commands=[dict(purpose='save-photo-1', state='answered')]))
        self.assertFalse(XImageCreationRuns.retry_allowed(committed)); self.assertFalse(LaneImageRuns.retry_allowed(committed))


class VideoExecuteRegressionTests(unittest.TestCase):
    """The refactored hooks keep the video workflow's arguments and delivery record."""
    def test_video_execute_keeps_its_keywords_and_record(self):
        from test_farm_reel_runs import ReelVideoFixture
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); root = Path(temp.name)
        videos, draft = ReelVideoFixture().stage(root)
        jobs = FarmJobs(journal_path=root/'jobs.db'); self.addCleanup(jobs.close)
        seen = {}

        class Workflow:
            def __init__(self, folder, kernel, store, video, caption, refs, kernel_sha, uid, **kwargs):
                seen.update(kwargs, video=video)
            def run(self):
                return dict(packageSha256=seen['package_hash'], state='review_required', cleanup='confirmed', evidenceExport='confirmed', actions=[], observations=[], commands=[])

        class Runs(ReelCreationRuns):
            workflow = Workflow
            reference = staticmethod(lambda raw: ('reference', len(raw)))

        config = dict(CONFIG, version=1); config.pop('phone'); config.pop('allowed'); config.pop('account')
        service = Runs(root/'runs', videos, jobs, config)
        spec = dict(id=str(uuid.uuid4()), draft_id=draft['id'], revision=1, store_id=service.store_id)
        with patch.object(farm_reel_runs, 'CreationKernel', MagicMock()), patch.object(farm_reel_runs, 'ObservationStore', MagicMock()), \
                patch.object(farm_reel_runs, 'references', lambda: {}):
            service.start(spec)
            end = time.monotonic() + 10
            while not service.get(spec['id'])['terminal'] and time.monotonic() < end: time.sleep(.02)
        result = service.get(spec['id'])
        self.assertEqual({'transfer_url', 'download', 'video_bytes', 'account', 'package_hash', 'cancelled', 'allowed', 'video'}, set(seen))
        self.assertRegex(seen['download'], '^imouse-reel-[a-z]{6}$'); self.assertEqual(('reference', seen['video_bytes']), seen['video'])
        self.assertEqual(['stopped', 'events', 'videoRequests', 'photosSaveProvenByHttp'], list(result['workflow']['mediaDelivery']))
        self.assertEqual('review_required', result['state'])


class ImageHttpTests(unittest.TestCase):
    setUp = http_jobs.FarmHttpJobsTests.setUp
    tearDown = http_jobs.FarmHttpJobsTests.tearDown
    request = http_jobs.FarmHttpJobsTests.request

    def test_default_backend_reports_both_image_routes_disabled_and_sends_nothing(self):
        health = self.request('/health')[1]
        for key, route, fmt in (('xImageCreation', 'x-image-creations', 'x_image'),
                                ('tiktokPhotoCreation', 'tiktok-photo-creations', 'tt_photo')):
            with self.subTest(route=route):
                capability = health[key]
                self.assertEqual((False, fmt, False, False), (capability['enabled'], capability['format'], capability['publishing'], capability['messaging']))
                spec = dict(id=str(uuid.uuid4()), draft_id=str(uuid.uuid4()), revision=1, store_id=capability['storeId'])
                with http_jobs.no_kernel():
                    self.assertEqual(409, self.request('/api/farm/' + route, spec)[0])
                    self.assertEqual(403, self.request('/api/farm/' + route, spec, origin='https://untrusted.invalid')[0])
                    self.assertEqual(403, self.request('/api/farm/' + route + '/' + spec['id'], origin='https://untrusted.invalid')[0])
                self.assertEqual(404, self.request('/api/farm/' + route + '/' + spec['id'])[0])
                self.assertEqual([], self.request('/api/farm/' + route + '?draft_id=' + spec['draft_id'])[1]['runs'])
                self.assertEqual(400, self.request('/api/farm/' + route + '/' + spec['id'] + '/cancel', dict(store_id=str(uuid.uuid4())))[0])

    def test_image_drafts_are_created_and_read_over_http(self):
        _, _, chosen = stage(self.root, 'tt_photo', 2, board='C24C')
        self.assertEqual([c['name'] for c in chosen], [s['name'] for s in self.runtime.images.sources()])
        self.assertEqual(404, self.request('/api/farm/image-sources')[0])   # No client ever asked for this list; creation reads it itself.
        request = dict(id=str(uuid.uuid4()), device_id='C24C', format='tt_photo', images=chosen, title='HTTP', caption='c')
        status, body = self.request('/api/farm/image-drafts', request); self.assertEqual(200, status, body)
        self.assertEqual(body['draft'], self.request('/api/farm/image-drafts/' + request['id'])[1]['draft'])
        self.assertEqual([request['id']], [d['id'] for d in self.request('/api/farm/image-drafts')[1]['drafts']])
        self.assertEqual(400, self.request('/api/farm/image-drafts', dict(request, id=str(uuid.uuid4()), images=chosen[:1]))[0])


if __name__ == '__main__':
    unittest.main()

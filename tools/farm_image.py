"""Immutable, reviewed image drafts (X image, TikTok photo) for one phone. Local encoding only; no phone input.

The image counterpart of farm_video: a window's staged images become one
package (manifest.json, caption.txt, 01.jpg ... NN.jpg) that
farm_media_transfer.TransferPackage serves to that window's own phone, and an
ImageReference that the shared media matchers (farm_reel_layout.video_match,
farm_tiktok_layout.media_match) compare frames with. Each image is fitted whole
onto its format's fixed canvas: nothing is cropped, the source stays untouched.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import threading
import warnings
import zipfile

from PIL import Image, ImageOps

from farm_drafts import checked_text, identifier, DraftConflict, generated_manifest, MAX_IMAGE_BYTES, MAX_PIXELS
from farm_video import download_name

IMAGE_FORMATS = {'x_image': 'X', 'tt_photo': 'TikTok'}
# Inclusive image counts. X image: exactly one. TikTok photo: 2-10 ordered slides.
SLIDES = {'x_image': (1, 1), 'tt_photo': (2, 10)}
# Fixed canvas and margin colour per format, so page, Photos and app renderings are predictable.
# X: 4:5 on white, like the carousel. TikTok photo: 9:16 on black, TikTok's own full-screen photo canvas.
CANVAS = {'x_image': ((1080, 1350), (255, 255, 255)), 'tt_photo': ((1080, 1920), (0, 0, 0))}
CAPTION_LIMITS = {'x_image': 280, 'tt_photo': 2200}
MAX_SOURCE_PIXELS = MAX_PIXELS
SOURCE_SUFFIXES = ('.jpg', '.jpeg', '.png')

# The phone-facing transfer page and steps per format (same layout as the carousel page).
PAGES = {
    'x_image': dict(title='X image draft', app='X', prefix='xi', proof='an X draft',
                    steps='Confirm the signed-in account, start a post, paste the text, add this image from Photos, then '
                          'choose Cancel and Save to drafts. Do not tap Post or Discard.'),
    'tt_photo': dict(title='TikTok photo draft', app='TikTok', prefix='tp', proof='a TikTok draft',
                     steps='Confirm the account, tap + and the gallery, select these photos in numbered order, keep the sound '
                           'TikTok adds, paste the description and choose Drafts. Do not tap Post, Share or Your Story.'),
}

# Crop models: (mode, (width, height)). 'cover' is a centre crop to that aspect (picker tiles, thumbnails,
# drafts covers); 'contain' fits the whole image on black (full-screen viewers). The shapes equal
# farm_reel_layout FILL/SQUARE and farm_tiktok_layout MODELS (a test checks), so one matcher serves both.
IMAGE_MODELS = {'fill': ('cover', (45, 80)), 'square': ('cover', (48, 48)), 'portrait': ('cover', (45, 60)),
                'card': ('cover', (45, 66)), 'fit': ('contain', (45, 80))}


def slide_names(count):
    return [f'{number:02}.jpg' for number in range(1, count + 1)]


def decoded(raw, label='Image'):
    """A complete static JPEG or PNG within the decoding limits, oriented, as RGB."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_IMAGE_BYTES:
        raise ValueError(f'{label} must be nonempty and at most 8 MiB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('JPEG', 'PNG') or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError(f'{label}: choose a static JPEG or PNG image.')
                if source.width * source.height > MAX_SOURCE_PIXELS:
                    raise ValueError(f'{label} exceeds the 40 megapixel editing limit.')
                source.load()   # A header alone does not establish a valid image.
                return ImageOps.exif_transpose(source).convert('RGBA'), source.format
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValueError(f'{label} exceeds safe decoding limits.') from exc
    except (OSError, SyntaxError) as exc:
        raise ValueError(f'{label} could not be decoded as a complete JPEG or PNG.') from exc


def normalize_image(raw, fmt):
    """Fit the whole image on the format's canvas and encode one baseline JPEG without metadata."""
    (width, height), background = CANVAS[fmt]
    image, _ = decoded(raw)
    fitted = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (width, height), background)
    canvas.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2), fitted)
    output = io.BytesIO(); canvas.save(output, 'JPEG', quality=94)
    encoded = output.getvalue()
    check_jpeg(encoded, (width, height))
    return encoded, dict(width=width, height=height, sourceWidth=image.width, sourceHeight=image.height,
                         fitted=image.width * height != image.height * width,
                         upscaled=fitted.width > image.width)


def check_jpeg(data, size):
    """Decode the complete file, not just its signature."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != 'JPEG' or image.size != tuple(size):
                raise ValueError(f'Expected a normalized {size[0]}x{size[1]} JPEG.')
            image.load()
    except (OSError, SyntaxError) as exc:
        raise ValueError('Package image could not be decoded completely.') from exc


class ImageDrafts:
    """Saved image drafts for one board. A saved draft never changes; export is byte-stable."""

    def __init__(self, database, stage_root, board='C24C'):
        self.database, self.stage_root, self.board = Path(database), Path(stage_root), board
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS image_drafts (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, document TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS image_files (draft_id TEXT NOT NULL, file TEXT NOT NULL, image BLOB NOT NULL, '
                       'PRIMARY KEY(draft_id, file))')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db: yield db
        finally: db.close()

    def sources(self, generation=None, checksum=None):
        """Staged JPEG/PNG images in this board's stage manifest, in manifest order."""
        manifest = self.stage_root / self.board / 'manifest.json'
        if generation is None and checksum is None and not manifest.is_file(): return []
        document, digest = generated_manifest(self.stage_root, generation, checksum, self.board)
        if document.get('deviceId') != self.board: raise ValueError(f'Staged manifest is not for {self.board}.')
        result, prefix = [], f'/stage/{self.board}/'
        for item in document.get('assets', []):
            url = item.get('url', '')
            if not url.startswith(prefix) or not url.lower().endswith(SOURCE_SUFFIXES): continue
            name = url.removeprefix(prefix)
            if Path(name).name != name or name in ('.', '..') or any(c in name for c in '/\\:%\x00'):
                raise ValueError('Invalid staged image name.')
            result.append({'name': name, 'sha256': item['sha256'], 'bytes': item['bytes'],
                           'sourceGeneration': document.get('generation'), 'manifestSha256': digest,
                           'caption': document.get('caption', '')})
        return result

    def create(self, request):
        """request: id, device_id, format, images [{name, sha256}, ...] in slide order, title, caption,
        and optionally source_generation + manifest_sha256 for a pinned generated batch."""
        draft_id = identifier(request.get('id'))
        fmt = request.get('format')
        if request.get('device_id') != self.board or fmt not in IMAGE_FORMATS:
            raise ValueError(f'Choose {self.board} and a supported image draft format.')
        chosen = request.get('images')
        low, high = SLIDES[fmt]
        if (not isinstance(chosen, list) or not low <= len(chosen) <= high
                or any(not isinstance(i, dict) or set(i) != {'name', 'sha256'} for i in chosen)):
            count = 'exactly one image' if low == high else f'{low}-{high} images'
            raise ValueError(f'This {IMAGE_FORMATS[fmt]} draft needs {count}, each a staged name and checksum.')
        if len({i['sha256'] for i in chosen}) != len(chosen): raise ValueError('Each slide must be a different image.')
        caption = checked_text(request.get('caption'), 'Caption', CAPTION_LIMITS[fmt])
        title = checked_text(request.get('title'), 'Title', 120, required=True)
        identity = {key: request.get(key) for key in ('device_id', 'format', 'images', 'title', 'caption')}
        generation, checksum = request.get('source_generation'), request.get('manifest_sha256')
        if generation is not None or checksum is not None: identity.update(source_generation=generation, manifest_sha256=checksum)
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        with self.lock, self._connect() as db:
            old = db.execute('SELECT fingerprint,document FROM image_drafts WHERE id=?', (draft_id,)).fetchone()
            if old:
                if old[0] != fingerprint: raise DraftConflict('This image draft ID belongs to different content.')
                return json.loads(old[1])
            staged = self.sources(generation, checksum)
            folder = (self.stage_root / self.board).resolve()
            assets, files = [], []
            for name, choice in zip(slide_names(len(chosen)), chosen):
                asset = next((s for s in staged if s['name'] == choice['name'] and s['sha256'] == choice['sha256']), None)
                if asset is None: raise ValueError('A staged image changed. Refresh and review it again.')
                path = (folder / asset['name']).resolve()
                if path.parent != folder: raise ValueError(f'Image path escapes the {self.board} stage.')
                if path.stat().st_size != asset['bytes'] or path.stat().st_size > MAX_IMAGE_BYTES:
                    raise ValueError('Image size changed or exceeds 8 MiB.')
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != asset['sha256']: raise ValueError('Staged image checksum changed.')
                encoded, metadata = normalize_image(raw, fmt)
                assets.append(dict(file=name, sha256=hashlib.sha256(encoded).hexdigest(), bytes=len(encoded),
                                   sourceName=asset['name'], sourceSha256=asset['sha256'], **metadata))
                files.append((name, encoded))
            if len({a['sha256'] for a in assets}) != len(assets): raise ValueError('Two slides encode to the same image.')
            value = {'id': draft_id, 'revision': 1, 'title': title, 'caption': caption, 'deviceId': self.board,
                     'format': fmt, 'platform': IMAGE_FORMATS[fmt], 'published': False, 'savedInApp': False,
                     'assets': assets}
            if generation is not None: value.update(sourceGeneration=generation, sourceManifestSha256=checksum)
            db.execute('INSERT INTO image_drafts VALUES (?,?,?)', (draft_id, fingerprint, json.dumps(value)))
            db.executemany('INSERT INTO image_files VALUES (?,?,?)', [(draft_id, name, data) for name, data in files])
            return value

    def export(self, draft_id, revision):
        """Deterministic stored zip: manifest.json, caption.txt, 01.jpg ... NN.jpg."""
        with self.lock, self._connect() as db:
            row = db.execute('SELECT document FROM image_drafts WHERE id=?', (identifier(draft_id),)).fetchone()
            if not row: raise KeyError('Image draft not found.')
            document = json.loads(row[0])
            if type(revision) is not int or revision != document['revision']: raise DraftConflict('Image draft revision changed.')
            images = dict(db.execute('SELECT file,image FROM image_files WHERE draft_id=?', (document['id'],)).fetchall())
        files = [('manifest.json', json.dumps(document, ensure_ascii=False).encode('utf-8')),
                 ('caption.txt', document['caption'].encode('utf-8'))]
        for asset in document['assets']:
            data = images.get(asset['file'])
            if data is None or hashlib.sha256(data).hexdigest() != asset['sha256']: raise ValueError('A saved image is damaged.')
            files.append((asset['file'], data))
        result = io.BytesIO()
        with zipfile.ZipFile(result, 'w', zipfile.ZIP_STORED) as archive:
            for name, data in files:
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); entry.external_attr = 0o600 << 16
                archive.writestr(entry, data)
        return result.getvalue()

    def get(self, draft_id):
        with self._connect() as db:
            row = db.execute('SELECT document FROM image_drafts WHERE id=?', (identifier(draft_id),)).fetchone()
        if not row: raise KeyError('Image draft not saved yet. Check again before repeating preparation.')
        return json.loads(row[0])

    def list(self):
        with self._connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT document FROM image_drafts ORDER BY rowid DESC')]


def package_name(package_hash, fmt):
    """Package-bound, OCR-safe label shown on the transfer page and used as the served file name."""
    return download_name(package_hash, PAGES[fmt]['prefix'])


class ImageReference:
    """Package images, decoded once before any lease, under fixed crop models.

    Matches the reference interface of farm_reel_layout.VideoReference / farm_tiktok_layout.TikTokReference:
    `models[name] = (shape, targets)`, `fill`, `square`. Each target is one image in slide order, so a
    matcher's `index` is the 0-based slide. `slide(i)` is a reference holding only slide i, for checking
    that one exact slide is shown. A visual match is evidence, never byte identity.
    """

    def __init__(self, images, models=None):
        if not isinstance(images, (list, tuple)) or not 1 <= len(images) <= 10 or any(not isinstance(i, bytes) or not i for i in images):
            raise ValueError('An image reference needs 1-10 package images.')
        self.spec = dict(IMAGE_MODELS if models is None else models)
        decoded_images = [decoded(raw, f'Slide {n}')[0].convert('RGB') for n, raw in enumerate(images, 1)]
        self.raw = list(images)
        self.hashes = [hashlib.sha256(raw).hexdigest() for raw in images]
        self.sha256 = hashlib.sha256(''.join(self.hashes).encode('ascii')).hexdigest()
        self.count = len(images)
        self.sizes = [image.size for image in decoded_images]
        self.models = {name: (shape, [self._render(image, mode, shape) for image in decoded_images])
                       for name, (mode, shape) in self.spec.items()}
        if 'fill' in self.models: self.fill = self.models['fill'][1]
        if 'square' in self.models: self.square = self.models['square'][1]

    @staticmethod
    def _render(image, mode, shape):
        import numpy as np
        if mode == 'cover': rendered = ImageOps.fit(image, shape, Image.Resampling.LANCZOS)
        elif mode == 'contain': rendered = ImageOps.pad(image, shape, Image.Resampling.LANCZOS, color=(0, 0, 0))
        else: raise ValueError('Unknown image crop model: ' + str(mode))
        return np.asarray(rendered, dtype=float) / 255

    def slide(self, index):
        """A reference to slide `index` (0-based) only."""
        if type(index) is not int or not 0 <= index < self.count: raise IndexError('No such slide.')
        return ImageReference([self.raw[index]], self.spec)


def render_test_images(token, folder, count, label):
    """Labelled acceptance slides (test media, not generated content): one distinct colour code per slide."""
    from PIL import ImageDraw
    from farm_reel_test_media import PALETTE, colour_code, font
    folder = Path(folder); paths = []
    for number in range(1, count + 1):
        image = Image.new('RGB', (1080, 1350), (246, 246, 240))
        draw = ImageDraw.Draw(image)
        draw.text((70, 70), label, font=font(64), fill=(20, 20, 20))
        for n, colour in enumerate(colour_code(f'{token}:{number}')):
            column, row = n % 2, n // 2
            left, top = 70 + column * 480, 260 + row * 300
            draw.rectangle((left, top, left + 460, top + 280), fill=PALETTE[colour])
        draw.rectangle((390, 1170, 690, 1300), fill=(20, 20, 20))
        draw.text((450, 1180), f'{number}/{count}', font=font(96), fill=(250, 250, 250))
        path = folder / f'slide-{token}-{number:02}.png'
        image.save(path, 'PNG'); paths.append(path)
    return paths

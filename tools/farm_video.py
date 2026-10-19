"""Immutable, reviewed C24C video drafts. Local encoding only; no phone input."""
from __future__ import annotations

import hashlib
import html
import io
import json
import math
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import uuid
import zipfile

from farm_drafts import checked_text, identifier, DraftConflict, generated_manifest

FORMATS = {'tt_video': 'TikTok', 'x_video': 'X', 'yt_short': 'YouTube', 'ig_reel': 'Instagram'}
MAX_VIDEO = 64 * 1024 * 1024
# Lowercase letters without I/l/o/b/g/q/j/z, which OCR or a reader can confuse.
NAME_ALPHABET = 'acdefhkmnprtuvwxy'


def download_name(package_hash):
    """Unique Safari download name for one immutable package, never a reused 'imouse-draft'."""
    value, letters = int(package_hash[:16], 16), []
    for _ in range(6):
        value, digit = divmod(value, len(NAME_ALPHABET)); letters.append(NAME_ALPHABET[digit])
    return 'imouse-reel-' + ''.join(letters)


def run_media(tool, arguments, timeout=90):
    binary = shutil.which(tool)
    if not binary:
        raise ValueError(f'{tool} is required for validated video drafts. Install FFmpeg and retry; no transfer started.')
    result = subprocess.run([binary, *arguments], capture_output=True, timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError(f'{tool} could not validate or encode this video. No draft was created.')
    return result.stdout


def probe_video(path):
    data = json.loads(run_media('ffprobe', ['-v', 'error', '-protocol_whitelist', 'file,pipe',
                         '-show_streams', '-show_format', '-of', 'json', str(path)], timeout=20))
    videos = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
    if len(videos) != 1:
        raise ValueError('Choose a video with exactly one video stream.')
    video = videos[0]
    seconds = float(data.get('format', {}).get('duration', 0))
    if not math.isfinite(seconds) or not 0 < seconds <= 45:
        raise ValueError('This draft candidate supports videos longer than zero and no longer than 45 seconds. Nothing is trimmed.')
    return {'width': int(video['width']), 'height': int(video['height']),
            'codec': video['codec_name'], 'pixelFormat': video.get('pix_fmt'), 'seconds': seconds,
            'audio': any(s.get('codec_type') == 'audio' for s in data['streams'])}


def normalize_video(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_VIDEO:
        raise ValueError('Video must be nonempty and at most 64 MiB.')
    with tempfile.TemporaryDirectory(prefix='farm-video-') as directory:
        source, target = Path(directory) / 'source.mp4', Path(directory) / 'draft.mp4'
        source.write_bytes(raw)
        original = probe_video(source)
        if not 1 <= original['width'] <= 4096 or not 1 <= original['height'] <= 4096:
            raise ValueError('Source video dimensions exceed this candidate limit.')
        run_media('ffmpeg', ['-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-i', str(source),
                  '-map', '0:v:0', '-map', '0:a:0?', '-map_metadata', '-1',
                  '-vf', 'scale=720:1280:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1',
                  '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                  '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-threads', '2', str(target)])
        metadata = probe_video(target)
        if metadata['codec'] != 'h264' or metadata['pixelFormat'] != 'yuv420p' or (metadata['width'], metadata['height']) != (720, 1280):
            raise ValueError('Encoded video does not meet the reviewed draft contract.')
        if abs(metadata['seconds'] - original['seconds']) > .15:
            raise ValueError('Encoding changed the video duration; inspect the source before proceeding.')
        # Decode the full file, not just its container header.
        run_media('ffmpeg', ['-v', 'error', '-xerror', '-nostdin', '-protocol_whitelist', 'file,pipe',
                            '-i', str(target), '-map', '0:v:0', '-map', '0:a:0?', '-f', 'null', '-'])
        encoded = target.read_bytes()
        if len(encoded) > MAX_VIDEO:
            raise ValueError('Encoded video exceeds 64 MiB; no draft created.')
    metadata.update(sourceWidth=original['width'], sourceHeight=original['height'],
                    fitted=original['width'] * 16 != original['height'] * 9,
                    upscaled=original['width'] < 720 or original['height'] < 1280)
    return encoded, metadata


class VideoDrafts:
    def __init__(self, database, stage_root):
        self.database, self.stage_root = Path(database), Path(stage_root)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS video_drafts (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, document TEXT NOT NULL, video BLOB NOT NULL)')

    def _connect(self):
        from contextlib import contextmanager
        @contextmanager
        def connection():
            db = sqlite3.connect(self.database, timeout=10)
            try:
                with db: yield db
            finally: db.close()
        return connection()

    def sources(self, generation=None, checksum=None):
        manifest = self.stage_root / 'C24C/manifest.json'
        if generation is None and checksum is None and not manifest.is_file(): return []
        document, digest = generated_manifest(self.stage_root, generation, checksum)
        if document.get('deviceId') != 'C24C': raise ValueError('Staged manifest is not for C24C.')
        result = []
        for item in document.get('assets', []):
            url = item.get('url', '')
            if not url.startswith('/stage/C24C/') or not url.endswith('.mp4'): continue
            name = url.removeprefix('/stage/C24C/')
            if Path(name).name != name or any(c in name for c in '/\\:%\x00'): raise ValueError('Invalid staged video name.')
            result.append({'name': name, 'sha256': item['sha256'], 'bytes': item['bytes'],
                           'sourceGeneration': document.get('generation'), 'manifestSha256': digest, 'caption': document.get('caption', '')})
        return result

    def create(self, request):
        draft_id = identifier(request.get('id'))
        if request.get('device_id') != 'C24C' or request.get('format') not in FORMATS:
            raise ValueError('Choose C24C and a supported video draft format.')
        caption = checked_text(request.get('caption'), 'Caption', 280)
        if request['format'] == 'yt_short' and len(caption) > 100:
            raise ValueError('This Shorts draft supports a title of at most 100 characters.')
        title = checked_text(request.get('title'), 'Title', 120, required=True)
        identity = {key: request.get(key) for key in ('device_id', 'format', 'name', 'sha256', 'title', 'caption')}
        generation, checksum = request.get('source_generation'), request.get('manifest_sha256')
        if generation is not None or checksum is not None: identity.update(source_generation=generation, manifest_sha256=checksum)
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        with self.lock, self._connect() as db:
            old = db.execute('SELECT fingerprint,document FROM video_drafts WHERE id=?', (draft_id,)).fetchone()
            if old:
                if old[0] != fingerprint: raise DraftConflict('This video draft ID belongs to different content.')
                return json.loads(old[1])
            asset = next((v for v in self.sources(generation, checksum) if v['name'] == request.get('name') and v['sha256'] == request.get('sha256')), None)
            if asset is None: raise ValueError('The staged video changed. Refresh and review it again.')
            path = self.stage_root / 'C24C' / asset['name']
            if path.resolve().parent != (self.stage_root / 'C24C').resolve(): raise ValueError('Video path escapes the C24C stage.')
            if path.stat().st_size != asset['bytes'] or path.stat().st_size > MAX_VIDEO: raise ValueError('Video size changed or exceeds 64 MiB.')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != asset['sha256']: raise ValueError('Staged video checksum changed.')
            encoded, metadata = normalize_video(raw)
            value = {'id': draft_id, 'revision': 1, 'title': title, 'caption': caption, 'deviceId': 'C24C',
                     'format': request['format'], 'platform': FORMATS[request['format']], 'published': False,
                     'savedInApp': False, 'sourceSha256': asset['sha256'], 'sha256': hashlib.sha256(encoded).hexdigest(),
                     'bytes': len(encoded), 'video': metadata}
            if generation is not None: value.update(sourceGeneration=generation, sourceManifestSha256=checksum)
            db.execute('INSERT INTO video_drafts VALUES (?,?,?,?)', (draft_id, fingerprint, json.dumps(value), encoded))
            return value

    def export(self, draft_id, revision):
        with self.lock, self._connect() as db:
            row = db.execute('SELECT document,video FROM video_drafts WHERE id=?', (identifier(draft_id),)).fetchone()
            if not row: raise KeyError('Video draft not found.')
            document, video = json.loads(row[0]), row[1]
            if type(revision) is not int or revision != document['revision']: raise DraftConflict('Video revision changed.')
            if hashlib.sha256(video).hexdigest() != document['sha256']: raise ValueError('Saved video is damaged.')
            result = io.BytesIO()
            with zipfile.ZipFile(result, 'w', zipfile.ZIP_STORED) as archive:
                for name, data in (('manifest.json', json.dumps(document, ensure_ascii=False).encode('utf-8')),
                                   ('caption.txt', document['caption'].encode('utf-8')), ('video.mp4', video)):
                    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); entry.external_attr = 0o600 << 16
                    archive.writestr(entry, data)
            return result.getvalue()

    def get(self, draft_id):
        with self._connect() as db:
            row = db.execute('SELECT document FROM video_drafts WHERE id=?', (identifier(draft_id),)).fetchone()
            if not row: raise KeyError('Video draft not saved yet. Check again before repeating preparation.')
            return json.loads(row[0])

    def list(self):
        with self._connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT document FROM video_drafts ORDER BY rowid DESC')]


class VideoTransferPackage:
    def __init__(self, raw):
        if len(raw) > MAX_VIDEO + 65536: raise ValueError('Video package exceeds its limit.')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) != 3 or {e.filename for e in entries} != {'manifest.json', 'caption.txt', 'video.mp4'}:
                raise ValueError('Unexpected video package entries.')
            if sum(e.file_size for e in entries) > MAX_VIDEO + 65536: raise ValueError('Video package expands beyond its limit.')
            doc = json.loads(archive.read('manifest.json'))
            if doc.get('deviceId') != 'C24C' or doc.get('format') not in FORMATS or doc.get('published') is not False or doc.get('savedInApp') is not False:
                raise ValueError('Choose an unpublished C24C video draft.')
            self.video = archive.read('video.mp4')
            if len(self.video) != doc['bytes'] or hashlib.sha256(self.video).hexdigest() != doc['sha256']:
                raise ValueError('Video checksum or size changed.')
            self.caption = archive.read('caption.txt').decode('utf-8')
            checked_text(self.caption, 'Caption', 280)
            if self.caption != doc['caption']: raise ValueError('Caption differs from its reviewed manifest.')
            self.title = checked_text(doc['title'], 'Title', 120, required=True)
            self.draft_id, self.revision = identifier(doc['id']), doc['revision']
            self.platform, self.format = FORMATS[doc['format']], doc['format']
            self.metadata, self.images = doc['video'], {}
            with tempfile.TemporaryDirectory(prefix='farm-video-check-') as directory:
                path = Path(directory) / 'video.mp4'; path.write_bytes(self.video)
                info = probe_video(path)
                if info['codec'] != 'h264' or info['pixelFormat'] != 'yuv420p' or (info['width'], info['height']) != (720, 1280):
                    raise ValueError('Video must be reviewed H.264, 720×1280, yuv420p.')
                run_media('ffmpeg', ['-v', 'error', '-xerror', '-nostdin', '-protocol_whitelist', 'file,pipe', '-i', str(path), '-map', '0:v:0', '-map', '0:a:0?', '-f', 'null', '-'])
        self.package_hash = hashlib.sha256(raw).hexdigest()
        # Reel downloads get a package-bound name so Safari's list can identify
        # this exact file. Other formats keep the supervised 'imouse-draft' route.
        self.download_name = download_name(self.package_hash) if self.format == 'ig_reel' else 'imouse-draft'

    def reel_page(self, prefix, nonce):
        """Short, OCR-readable page: every control is a plain button above the fold."""
        return (f'<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><meta charset="utf-8">'
                f'<title>Reel draft transfer</title><style nonce="{nonce}">body{{font:18px system-ui;padding:20px;max-width:600px;margin:auto;'
                'color:#15243d;background:#f4f7fc}h1{font-size:28px}.file{font-size:20px}.button,button{display:block;border:0;'
                'border-radius:12px;background:#245cd7;color:white;text-decoration:none;padding:16px;margin:14px 0;font:inherit;'
                'text-align:center;width:100%;box-sizing:border-box}textarea{box-sizing:border-box;width:100%;height:70px;'
                'font:16px system-ui;padding:10px}.note{font-size:15px;line-height:1.5}</style></head><body>'
                f'<h1>Reel draft</h1><p class="file">File {html.escape(self.download_name)}</p>'
                f'<a class="button" href="{prefix}video.mp4">Download video</a>'
                f'<textarea id="caption" readonly aria-label="Reel caption">{html.escape(self.caption)}</textarea>'
                '<button id="copy">Copy caption</button><p id="status" role="status"></p>'
                '<p class="note">Touch and hold Download video and choose Download Linked File. In Safari Downloads, open this file, '
                'then Share and Save Video. In Instagram check the account, choose Reel, select this video, paste the caption and '
                'choose Save draft. Do not tap Share.</p><p class="note">A download does not prove a Photos save or an Instagram draft.</p>'
                f'<script nonce="{nonce}">document.getElementById("copy").onclick=async()=>{{const b=document.getElementById("caption");'
                'const s=document.getElementById("status");b.focus();b.select();b.setSelectionRange(0,b.value.length);'
                'try{let ok=false;if(window.isSecureContext&&navigator.clipboard){await navigator.clipboard.writeText(b.value);ok=true;}'
                'else{ok=document.execCommand("copy");}s.textContent=ok?"Caption copied. Verify the pasted text in Instagram.":'
                '"Caption selected. Use the selection menu to copy it.";}catch{s.textContent="Caption selected. Use the selection menu to copy it.";}};'
                '</script></body></html>').encode('utf-8')

    def page(self, prefix, nonce, number=0):
        if self.format == 'ig_reel': return self.reel_page(prefix, nonce)
        return (f'<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><meta charset="utf-8">'
                f'<title>Video draft transfer</title><style nonce="{nonce}">body{{font:18px system-ui;padding:20px;max-width:600px;margin:auto}}'
                'video{width:100%;max-height:55vh;background:#111}textarea{width:100%;height:100px;font:16px system-ui}button,a{display:block;padding:14px;margin:12px 0}</style></head><body>'
                f'<h1>{html.escape(self.title)}</h1><p>Draft only · {html.escape(self.platform)} · C24C</p>'
                f'<video controls playsinline preload="metadata" src="{prefix}video.mp4"></video>'
                f'<a href="{prefix}video.mp4">Open video to save</a><p>On iPhone, press and hold this link and choose Download Linked File. Open Safari Downloads, then imouse-draft. Use its Share menu → Save Video. Verify the video in Photos before selecting it in the app.</p>'
                f'<textarea id="caption" readonly>{html.escape(self.caption)}</textarea><button id="copy">Copy caption</button><p id="status"></p>'
                '<p>Confirm the signed-in account and review the complete video and caption. Remove unwanted suggested sounds: TikTok can attach one automatically. Choose Save draft. Do not tap Post, Share or Upload in the app. Reopen and play the draft and verify its caption.</p>'
                '<p>Wait for menus to settle. If a permission prompt ignores pointer input, stop for a physical tap; do not grant extra access to bypass it.</p>'
                '<p>A download does not prove a Photos save or an app draft. The link expires; the original media stays unchanged.</p>'
                f'<script nonce="{nonce}">document.getElementById("copy").onclick=async()=>{{const b=document.getElementById("caption");b.focus();b.select();b.setSelectionRange(0,b.value.length);'
                'try{let ok=false;if(window.isSecureContext&&navigator.clipboard){await navigator.clipboard.writeText(b.value);ok=true;}else{ok=document.execCommand("copy");}'
                'document.getElementById("status").textContent=ok?"Copied; verify the pasted caption.":"Select and copy manually.";}catch{document.getElementById("status").textContent="Select and copy manually.";}};</script></body></html>').encode('utf-8')

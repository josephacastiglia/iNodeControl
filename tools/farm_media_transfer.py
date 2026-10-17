"""Short-lived media-only delivery of an immutable carousel export.

This server has no farm API, hardware access, filesystem routes, uploads, or
publication capability. HTTP delivery is evidence of a request, not of a save
in Photos or Instagram. Run only for an explicitly selected phone on the LAN.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
from http.server import HTTPServer, BaseHTTPRequestHandler
import io
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import time
from urllib.parse import urlsplit
import zipfile

MAX_PACKAGE = 90 * 1024 * 1024


class TransferPackage:
    def __init__(self, raw: bytes):
        if len(raw) > MAX_PACKAGE:
            raise ValueError('Review package exceeds 90 MiB.')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            items = archive.infolist()
            if len(items) > 20 or sum(i.file_size for i in items) > MAX_PACKAGE:
                raise ValueError('Review package expands beyond its limits.')
            if len({i.filename for i in items}) != len(items):
                raise ValueError('Duplicate package entries.')
            for item in items:
                if '/' in item.filename or '\\' in item.filename or item.file_size > 8 * 1024 * 1024:
                    raise ValueError('Unexpected package entry.')
            manifest = json.loads(archive.read('manifest.json'))
            if (manifest.get('deviceId') != 'C24C' or manifest.get('format') != 'ig_carousel'
                    or manifest.get('savedInInstagram') is not False or manifest.get('published') is not False):
                raise ValueError('Choose an unpublished C24C carousel review package.')
            assets = manifest.get('assets', [])
            if not 2 <= len(assets) <= 10:
                raise ValueError('A transfer requires 2–10 slides.')
            self.images = {}
            for number, asset in enumerate(assets, 1):
                name = f'{number:02}.jpg'
                if asset.get('file') != name:
                    raise ValueError('Slides must be in consecutive numeric order.')
                data = archive.read(name)
                if len(data) != asset.get('bytes') or hashlib.sha256(data).hexdigest() != asset.get('sha256'):
                    raise ValueError('Slide checksum or size does not match its manifest.')
                # Validate complete JPEGs, not merely their signatures.
                from PIL import Image
                with Image.open(io.BytesIO(data)) as image:
                    if image.format != 'JPEG' or image.size != (1080, 1350):
                        raise ValueError('Expected a normalized 1080×1350 JPEG.')
                    image.load()
                self.images[name] = data
            self.caption = archive.read('caption.txt').decode('utf-8')
            if self.caption != manifest.get('caption') or len(self.caption) > 2200:
                raise ValueError('Caption differs from the reviewed manifest.')
            self.title = manifest['title']
            self.draft_id, self.revision = manifest['id'], manifest['revision']
            self.package_hash = hashlib.sha256(raw).hexdigest()

    def page(self, prefix: str, nonce: str, number: int = 0) -> bytes:
        count = len(self.images)
        if number:
            if not 1 <= number <= count:
                raise KeyError('Unknown slide')
            next_link = f'<a class="button" href="{prefix}slide/{number + 1}">Next slide →</a>' if number < count else f'<a class="button" href="{prefix}">Back to caption</a>'
            body = (f'<h1>Slide {number} of {count}</h1><p>Touch and hold the image, then choose Save to Photos. '
                    'Verify it in Photos before selecting it in Instagram.</p>'
                    f'<img class="slide" src="{prefix}{number:02}.jpg" alt="Slide {number}">'
                    f'<nav>{next_link}<a href="{prefix}">All slides</a></nav>')
        else:
            links = ''.join(f'<a class="button" href="{prefix}slide/{n}">Open slide {n} of {count}</a>' for n in range(1, count + 1))
            body = (f'<h1>{html.escape(self.title)}</h1><p>Draft only · nothing published</p>'
                    f'<h2>1. Save the slides in order</h2>{links}'
                    '<h2>2. Copy the caption</h2>'
                    f'<textarea id="caption" readonly aria-label="Full draft caption">{html.escape(self.caption)}</textarea>'
                    '<button id="copy">Copy caption</button><p id="copy-status" role="status"></p>'
                    '<h2>3. Save in Instagram</h2><p>Confirm the account, select these slides in numbered order, '
                    'paste the caption, and choose Save draft. Do not tap Share.</p>'
                    '<p>This page cannot confirm a Photos save or an Instagram draft. Check both in their apps.</p>')
        script = '''document.getElementById('copy')?.addEventListener('click', async () => {
const box = document.getElementById('caption'); const status = document.getElementById('copy-status');
box.focus(); box.select(); box.setSelectionRange(0, box.value.length);
try { let copied = false;
if (window.isSecureContext && navigator.clipboard) { await navigator.clipboard.writeText(box.value); copied = true; }
else { copied = document.execCommand('copy'); }
status.textContent = copied ? 'Caption copied. Verify the pasted text in Instagram.' : 'Caption selected. Use the selection menu to copy it.';
} catch { status.textContent = 'Caption selected. Use the selection menu to copy it.'; }
});'''
        return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Carousel transfer</title>'
                f'<style nonce="{nonce}">body{{font:17px system-ui;margin:20px auto;padding:0 18px;max-width:600px;color:#15243d;background:#f4f7fc}}'
                'h1{font-size:24px}h2{font-size:20px;margin-top:28px}.button,button{display:block;border:0;border-radius:12px;background:#245cd7;'
                'color:white;text-decoration:none;padding:16px;margin:12px 0;font:inherit;text-align:center}textarea{box-sizing:border-box;'
                'width:100%;height:150px;font:16px system-ui;padding:12px}.slide{display:block;max-width:100%;max-height:60vh;margin:auto}'
                'nav{margin:18px 0}p{line-height:1.5}</style></head><body>'
                f'{body}<script nonce="{nonce}">{script}</script></body></html>').encode('utf-8')


def checked_address(value: str) -> str:
    address = ipaddress.IPv4Address(value)
    if address.is_unspecified or address.is_multicast or address.is_link_local or not address.is_private:
        raise ValueError('Use a specific private IPv4 address, not all interfaces or a public address.')
    return str(address)


class MediaTransferServer(HTTPServer):
    allow_reuse_address = False

    def __init__(self, package, bind, port, allowed_client, *, minutes=20, on_event=None, clock=time.monotonic):
        bind, allowed_client = checked_address(bind), checked_address(allowed_client)
        if not 1 <= minutes <= 60:
            raise ValueError('Transfer duration must be 1–60 minutes.')
        self.package, self.allowed_client = package, allowed_client
        self.clock, self.deadline = clock, clock() + minutes * 60
        self.prefix = '/t/' + secrets.token_urlsafe(18) + '/'
        self.nonce = secrets.token_urlsafe(24)
        self.on_event = on_event or (lambda event: None)
        self.served_images = set()
        super().__init__((bind, port), TransferHandler)
        self.timeout = 0.5
        self.authority = f'{bind}:{self.server_port}'
        self.url = f'http://{self.authority}{self.prefix}'

    def server_bind(self):
        # Do not share the port with another listener on Windows.
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address


class TransferHandler(BaseHTTPRequestHandler):
    server_version = 'CarouselTransfer/1'
    sys_version = ''

    def log_message(self, *_):
        pass  # Never log secret URL paths or caption contents.

    def do_GET(self):
        self.deliver(False)

    def do_HEAD(self):
        self.deliver(True)

    def do_POST(self):
        self.reply(405, b'Read-only media service.', 'text/plain')

    do_PUT = do_DELETE = do_PATCH = do_POST

    def reply(self, code, data, content_type, head=False, route='unavailable'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.send_header('Content-Security-Policy', f"default-src 'none'; img-src 'self'; style-src 'nonce-{self.server.nonce}'; script-src 'nonce-{self.server.nonce}'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        try:
            if not head:
                self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            code = 499
        if code == 200 and not head and route in self.server.package.images:
            self.server.served_images.add(route)
        self.server.on_event({'at': datetime.now(timezone.utc).isoformat(), 'method': self.command,
                              'route': route, 'status': code, 'bytes': len(data) if not head else 0})

    def deliver(self, head):
        s = self.server
        parsed = urlsplit(self.path)
        if (self.client_address[0] != s.allowed_client or self.headers.get('Host') != s.authority
                or s.clock() >= s.deadline or parsed.query or parsed.fragment
                or not self.path.startswith(s.prefix)):
            self.reply(404, b'Unavailable or expired.', 'text/plain', head)
            return
        route = self.path[len(s.prefix):]
        if route in s.package.images:
            self.reply(200, s.package.images[route], 'image/jpeg', head, route)
        elif route == 'caption.txt':
            self.reply(200, s.package.caption.encode('utf-8'), 'text/plain; charset=utf-8', head, route)
        elif route == '':
            self.reply(200, s.package.page(s.prefix, s.nonce), 'text/html; charset=utf-8', head, 'index')
        elif route.startswith('slide/') and route[6:].isdigit() and 1 <= int(route[6:]) <= len(s.package.images):
            self.reply(200, s.package.page(s.prefix, s.nonce, int(route[6:])), 'text/html; charset=utf-8', head, route)
        else:
            self.reply(404, b'Unknown media.', 'text/plain', head)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--bind', required=True)
    parser.add_argument('--allow-client', required=True)
    parser.add_argument('--port', type=int, default=9916)
    parser.add_argument('--minutes', type=int, default=20)
    parser.add_argument('--ready-file', type=Path, required=True)
    parser.add_argument('--events-file', type=Path, required=True)
    parser.add_argument('--stop-file', type=Path, required=True)
    args = parser.parse_args()
    if args.ready_file.exists() or args.events_file.exists() or args.stop_file.exists():
        parser.error('Use new state paths; existing evidence is never overwritten.')
    package = TransferPackage(args.package.read_bytes())
    with args.events_file.open('x', encoding='utf-8') as events:
        def event(value):
            events.write(json.dumps(value) + '\n')
            events.flush()
        with MediaTransferServer(package, args.bind, args.port, args.allow_client, minutes=args.minutes, on_event=event) as server:
            state = {'url': server.url, 'draftId': package.draft_id, 'revision': package.revision,
                     'packageSha256': package.package_hash, 'expiresAfterSeconds': args.minutes * 60,
                     'state': 'serving', 'savedInPhotos': False, 'savedInInstagram': False, 'published': False}
            args.ready_file.write_text(json.dumps(state, indent=2), encoding='utf-8')
            print(json.dumps({'state': 'serving', 'readyFile': str(args.ready_file), 'port': server.server_port}), flush=True)
            try:
                while server.clock() < server.deadline and not args.stop_file.exists():
                    server.handle_request()
            finally:
                state.pop('url')
                state.update(state='closed', imagesServed=sorted(server.served_images))
                args.ready_file.write_text(json.dumps(state, indent=2), encoding='utf-8')
                print(json.dumps(state), flush=True)


if __name__ == '__main__':
    main()

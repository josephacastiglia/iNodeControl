"""Labelled Reel acceptance media: a distinctive cover and visible playback.

This is test media, not generated marketing content, and never claims to be AI
output. A token picks six large colour blocks, so separate runs never share a
cover in Photos or Reels drafts. A moving bar and frame number make playback
visible. No words that Instagram uses for publishing appear in the image.
"""
import hashlib
import io
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

PALETTE = ((214, 40, 57), (21, 101, 192), (46, 160, 67), (245, 158, 11), (124, 58, 237), (14, 165, 233), (236, 72, 153),
           (101, 163, 13))
WIDTH, HEIGHT, FPS = 720, 1280, 15


def colour_code(token):
    """Six palette indices; neighbours always differ so the code stays visible."""
    digest = hashlib.sha256(('imouse-reel-test:' + token).encode('utf-8')).digest()
    code = []
    for byte in digest:
        index = byte % len(PALETTE)
        if not code or index != code[-1]: code.append(index)
        if len(code) == 6: return code
    raise ValueError('Could not derive a colour code.')


def font(size):
    for name in ('arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf'):
        try: return ImageFont.truetype(name, size)
        except OSError: continue
    return ImageFont.load_default()


def frame(token, index, count):
    image = Image.new('RGB', (WIDTH, HEIGHT), (246, 246, 240))
    draw = ImageDraw.Draw(image)
    draw.text((60, 120), 'REEL DRAFT TEST', font=font(56), fill=(20, 20, 20))
    # Two columns by three rows, within the square centre crop Instagram uses
    # for the drafts list, so every rendering keeps the code.
    for n, colour in enumerate(colour_code(token)):
        column, row = n % 2, n // 2
        left, top = 60 + column*310, 300 + row*230
        draw.rectangle((left, top, left+290, top+210), fill=PALETTE[colour])
    draw.rectangle((210, 980, 510, 1080), fill=(20, 20, 20))
    draw.text((300, 990), f'{index:02d}', font=font(80), fill=(250, 250, 250))
    progress = round(600 * (index+1) / count)
    draw.rectangle((60, 1100, 660, 1130), outline=(20, 20, 20), width=3)
    draw.rectangle((60, 1100, 60+progress, 1130), fill=(20, 20, 20))
    return image


def render(token, path, seconds=4):
    """Write an H.264 720x1280 MP4 without audio. Requires FFmpeg."""
    binary = shutil.which('ffmpeg')
    if not binary: raise ValueError('ffmpeg is required to render Reel test media.')
    count = seconds * FPS
    stream = io.BytesIO()
    for index in range(count):
        frame(token, index, count).save(stream, 'PNG')
    result = subprocess.run([binary, '-v', 'error', '-nostdin', '-f', 'image2pipe', '-framerate', str(FPS), '-i', '-',
                             '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'veryfast', '-crf', '18', '-an',
                             '-movflags', '+faststart', '-y', str(path)], input=stream.getvalue(), capture_output=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode: raise ValueError('ffmpeg could not render the Reel test media.')
    return Path(path)

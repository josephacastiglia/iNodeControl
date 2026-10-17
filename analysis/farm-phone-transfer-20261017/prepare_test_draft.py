"""Create clearly labelled disposable test content in the candidate draft store."""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import uuid
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_drafts import CarouselDrafts

record = Path(__file__).parent
if (record / 'test-draft.json').exists():
    raise SystemExit('Test draft already prepared; reuse its recorded ID.')
store = CarouselDrafts(ROOT / 'output/farm-data/v2/simulate/carousel-drafts.db', ROOT / 'output/media-stage/v2/simulate')
draft = store.create(str(uuid.uuid4()), 'iMouse transfer test · 17 Oct 2026')
font_path = 'C:/Windows/Fonts/segoeuib.ttf'
for number, color in enumerate(('#203b70', '#116b61', '#6e3574'), 1):
    slide = Image.new('RGB', (1080, 1350), color)
    draw = ImageDraw.Draw(slide)
    draw.text((76, 90), 'iMouse 2.0', font=ImageFont.truetype(font_path, 54), fill='white')
    draw.text((76, 230), 'CAROUSEL TRANSFER TEST', font=ImageFont.truetype(font_path, 48), fill='white')
    draw.text((76, 390), str(number), font=ImageFont.truetype(font_path, 350), fill='white')
    draw.text((76, 900), f'SLIDE {number} OF 3', font=ImageFont.truetype(font_path, 72), fill='white')
    draw.text((76, 1050), 'DRAFT ONLY', font=ImageFont.truetype(font_path, 64), fill='white')
    draw.text((76, 1150), 'DO NOT PUBLISH', font=ImageFont.truetype(font_path, 54), fill='white')
    buffer = io.BytesIO(); slide.save(buffer, 'PNG')
    draft = store.import_image(draft['id'], draft['revision'], f'test-slide-{number}.png', base64.b64encode(buffer.getvalue()).decode())
draft = store.save(draft['id'], draft['revision'], draft['title'],
    'iMouse carousel draft test.\nThree numbered slides in order: 1, 2, 3.\nDRAFT ONLY - do not publish.', draft['slideIds'])
raw = store.export(draft['id'], draft['revision'])
(record / 'test-carousel.zip').write_bytes(raw)
(record / 'test-draft.json').write_text(json.dumps({k:v for k,v in draft.items() if k != 'slides'}, indent=2), encoding='utf-8')
print(json.dumps({'draftId': draft['id'], 'revision': draft['revision'], 'packageSha256': hashlib.sha256(raw).hexdigest()}))

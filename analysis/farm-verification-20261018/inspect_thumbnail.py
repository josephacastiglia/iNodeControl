import io
import json
from pathlib import Path
import zipfile
import numpy as np
from PIL import Image

root = Path(__file__).resolve().parents[2]
prior = root / 'analysis/farm-phone-transfer-20261017'
observed = np.asarray(Image.open(prior / '47-open-drafts-library/after.png').convert('RGB'), dtype=np.float32)
with zipfile.ZipFile(prior / 'test-carousel.zip') as files: source = Image.open(io.BytesIO(files.read('01.jpg'))).convert('RGB')
scores = []
for width in (122, 124, 126):
    scaled = np.asarray(source.resize((width, round(width * 1.25)), Image.Resampling.LANCZOS), dtype=np.float32)
    for y_offset in range(0, 34):
        for top in (110, 111, 112):
            height = min(120, scaled.shape[0] - y_offset)
            a = scaled[y_offset:y_offset + height, 5:width - 5]
            b = observed[top:top + height, 5:width - 5]
            scores.append(dict(width=width, sourceOffset=y_offset, top=top, error=float(np.abs(a - b).mean() / 255)))
print(json.dumps(sorted(scores, key=lambda r: r['error'])[:5]))

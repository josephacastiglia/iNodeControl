import io, json, zipfile
from pathlib import Path
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[2]
PRIOR = ROOT / 'analysis/farm-phone-transfer-20261017'
with zipfile.ZipFile(PRIOR/'test-carousel.zip') as z: raw = z.read('01.jpg')
source = Image.open(io.BytesIO(raw)).convert('RGB').crop((0,135,1080,1215)).resize((124,124), Image.Resampling.LANCZOS)
frame = Image.open(PRIOR/'47-open-drafts-library/after.png').convert('RGB').crop((0,111,124,235))
a,b = [np.asarray(i,dtype=float)/255 for i in (source,frame)]
for y in range(0,124,10):
    x = slice(35,115)
    alpha = float(np.sum(a[y:y+5,x]*b[y:y+5,x])/np.sum(a[y:y+5,x]**2))
    print(y,round(alpha,3),round(float(np.abs(a[y:y+5,x]*alpha-b[y:y+5,x]).mean()),4))
source.save(Path(__file__).parent/'thumb-expected.png')
frame.save(Path(__file__).parent/'thumb-observed.png')

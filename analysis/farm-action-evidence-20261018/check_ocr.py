"""Actual Windows OCR of a generated local image only; no desktop/rack APIs."""
import hashlib,io,json,os,sys,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2]; RUN=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from farm_observations import WindowsOcr
image=Image.new('RGB',(500,1080),'white')
font=ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts/arial.ttf'),32)
ImageDraw.Draw(image).text((40,120),'DRAFT ONLY',font=font,fill='black')
buffer=io.BytesIO();image.save(buffer,'BMP');raw=buffer.getvalue()
started=time.perf_counter();value=WindowsOcr().read(raw);elapsed=(time.perf_counter()-started)*1000
assert value['frameSha256']==hashlib.sha256(raw).hexdigest()
assert any(line['text']=='DRAFT ONLY' for line in value['lines']),value
image.save(RUN/'generated-ocr-fixture.png')
result=dict(elapsedMs=elapsed,ocr=value,phoneInput=False,desktopControl=False)
(RUN/'windows-ocr.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(actualWindowsOcr=True,exactText=True,rawFrameHashVerified=True,elapsedMs=elapsed)))

"""Run Windows OCR on retained evidence only. No network, capture or input."""
import hashlib
import json
from pathlib import Path
import sys
import time

from replay import capture, ROOT, RUN
from farm_observations import WindowsOcr, classify
from farm_screen_layout import next_label


def main():
    rows=[]
    for folder,phase in (('20-reopen-saved-carousel','after'),('21-reopened-slide-two','fresh'),
                         ('22-reopened-slide-two-reviewed','fresh'),('23-reopened-slide-two-verified','fresh'),
                         ('23-reopened-slide-two-verified','after'),('24-reopened-slide-three','fresh'),
                         ('24-reopened-slide-three','after'),('25-reopened-caption','fresh')):
        value,frame=capture(folder,phase)
        started=time.perf_counter(); text=WindowsOcr().read(frame); elapsed=(time.perf_counter()-started)*1000
        result=classify(text,value['expected'],frame); label=next_label(frame,text)
        (RUN/(folder+'-'+phase+'-ocr.json')).write_text(json.dumps(text,indent=2),encoding='utf-8')
        row=dict(folder=folder,phase=phase,frameSha256=hashlib.sha256(frame).hexdigest(),
                 screen=result['screen'],layout=result['layout'],nextLabel=label,
                 cropped='controlOcr' in text,elapsedMs=round(elapsed,2),
                 within1500msProcessingOnly=elapsed<=1500,phoneCalls=0)
        rows.append(row); print(json.dumps(row),flush=True)
    (RUN/'ocr-replay.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')


if __name__=='__main__': main()

"""Labelled test fixture and bounded media session. No phone input, no publishing."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
from imouse_farm_server import FarmBackendRuntime
from imouse_social_automation import IMouseKernel
from farm_video import run_media

p = argparse.ArgumentParser(); p.add_argument('action', choices=['prepare', 'serve']); args = p.parse_args()
runtime = FarmBackendRuntime(RUN / 'video-data/farm.db', RUN / 'video-stage')
if args.action == 'prepare':
    stage = runtime.stage_root / 'C24C'; stage.mkdir(parents=True, exist_ok=True)
    source = stage / 'imouse-draft-only-test.mp4'
    if source.exists(): raise SystemExit('Fixture already exists; never overwrite evidence.')
    runtime.factory.code_animator.compile_code_spec_to_mp4({
        'fps': 15, 'durationSec': 3,
        'scenes': [{'title': 'iMouse VIDEO DRAFT TEST', 'subtitle': 'DRAFT ONLY - DO NOT PUBLISH', 'metricLabel': 'TEST', 'metricTargetPct': 100},
                   {'title': 'END OF TEST VIDEO', 'subtitle': 'DRAFT ONLY - DO NOT PUBLISH', 'metricLabel': 'TEST', 'metricTargetPct': 100}]},
        source, 'C24C', width=720, height=1280)
    raw = source.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    (stage / 'manifest.json').write_text(json.dumps({'deviceId': 'C24C', 'assets': [
        {'url': '/stage/C24C/' + source.name, 'sha256': digest, 'bytes': len(raw)}]}), encoding='utf-8')
    draft = runtime.videos.create(dict(id=str(uuid.uuid4()), device_id='C24C', format='tt_video', name=source.name,
        sha256=digest, title='iMouse video draft test', caption='IMOUSE-VIDEO-DRAFT-TEST-20261017'))
    (RUN / 'video-draft.json').write_text(json.dumps(draft, indent=2), encoding='utf-8')
    (RUN / 'video-package.zip').write_bytes(runtime.videos.export(draft['id'], 1))
    # Inspect the actual normalized transfer bytes.
    import io, zipfile
    with zipfile.ZipFile(io.BytesIO((RUN / 'video-package.zip').read_bytes())) as z:
        normalized = RUN / 'normalized-test.mp4'; normalized.write_bytes(z.read('video.mp4'))
    frame = run_media('ffmpeg', ['-v', 'error', '-ss', '1', '-i', str(normalized), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'])
    (RUN / 'video-preview.png').write_bytes(frame)
    print(json.dumps({'draftId': draft['id'], 'sha256': draft['sha256'], 'video': draft['video']}))
else:
    kernel = IMouseKernel(); kernel.preflight_phone('C24C')
    draft = json.loads((RUN / 'video-draft.json').read_text(encoding='utf-8'))
    ready, stop = RUN / 'video-transfer-ready.json', RUN / 'stop-video-transfer'
    if ready.exists() or stop.exists(): raise SystemExit('Use a new session record; do not overwrite.')
    session = runtime.transfers.start(dict(id=str(uuid.uuid4()), draft_id=draft['id'], revision=1, kind='video',
        device_id='C24C', account='xs.halle.xo', bind='192.168.4.26', client='192.168.4.57', port=9916, minutes=20))
    ready.write_text(json.dumps(session, indent=2), encoding='utf-8')
    print(json.dumps({'state': session['state'], 'ready': str(ready)}), flush=True)
    try:
        while session['state'] == 'serving' and not stop.exists():
            time.sleep(.5); session = runtime.transfers.get(session['id'])
    finally:
        session = runtime.transfers.stop(session['id'])
        ready.write_text(json.dumps(session, indent=2), encoding='utf-8')
        print(json.dumps({'state': session['state'], 'videoRequests': session['videoRequests']}), flush=True)

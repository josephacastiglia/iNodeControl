"""Real local rendering and saved-batch review, with all networking forbidden."""
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
import farm_test_network  # No allowed ports: network is forbidden in this exercise.
from imouse_farm_server import FarmBackendRuntime
from farm_media_transfer import TransferPackage
from farm_video import VideoTransferPackage

label = 'render-exercise-final' if '--final' in sys.argv else 'render-exercise'
folder = RUN / label
folder.mkdir(exist_ok=False)
runtime = FarmBackendRuntime(folder / 'data/farm.db', folder / 'stage')
clock = [time.time()]
runtime.preparation.clock = lambda: clock[0]
runtime.db.update_persona('C24C', niche='Offline workflow review', cta_keyword='REVIEW', offer_url='https://example.invalid/review')
runtime.preparation.configure(dict(id=str(uuid.uuid4()), device_id='C24C', action='create-content', interval_minutes=60, max_runs=2))

def wait_runs(count):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status = runtime.preparation.status()
        if any(run['state'] == 'failed' for run in status['runs']): raise AssertionError(status)
        if status['config']['completedRuns'] == count: return status
        time.sleep(.05)
    raise AssertionError('Local background preparation did not finish in its budget')

with patch.object(runtime, 'get_kernel', side_effect=AssertionError('No kernel access')):
    runtime.preparation.start()
    try:
        first_status = wait_runs(1)
        first = next(item for item in first_status['runs'][0]['contentItems'] if item.get('localDraft'))
        before = runtime.drafts.get(first['localDraft']['id'])
        first_zip = runtime.drafts.export(before['id'], before['revision'])
        clock[0] += 3600
        final_status = wait_runs(2)
        assert final_status['config']['state'] == 'complete' and not final_status['config']['enabled']
    finally: runtime.preparation.close()
    assert runtime.drafts.get(before['id']) == before
    assert runtime.drafts.export(before['id'], before['revision']) == first_zip
    (folder / 'first-carousel.zip').write_bytes(first_zip)
    carousel = TransferPackage(first_zip)
    assert len(carousel.images) == 4
    sources = runtime.videos.sources(first['generation'], first['manifestSha256'])
    assert len(sources) == 1
    videos = []
    for format in ('tt_video', 'x_video', 'yt_short', 'ig_reel'):
        source = sources[0]
        # Editorially short explicit label; never truncate generated copy.
        request = dict(id=str(uuid.uuid4()), device_id='C24C', format=format, title='Offline batch review',
                       caption='Offline saved-batch review. Draft only.', name=source['name'], sha256=source['sha256'],
                       source_generation=first['generation'], manifest_sha256=first['manifestSha256'])
        draft = runtime.videos.create(request)
        archive = runtime.videos.export(draft['id'], draft['revision'])
        package = VideoTransferPackage(archive)  # Decode all frames; no listener or delivery.
        assert package.format == format and draft['sourceGeneration'] == first['generation']
        assert runtime.videos.create(request) == draft
        assert runtime.videos.export(draft['id'], draft['revision']) == archive
        (folder / f'{format}.zip').write_bytes(archive)
        videos.append(dict(format=format, seconds=draft['video']['seconds'], sourceSha256=draft['sourceSha256'],
                           packageSha256=hashlib.sha256(archive).hexdigest(), savedInApp=draft['savedInApp']))
assert not runtime.mock_kernel.commands_dispatched
assert not runtime.preparation.status()['workerRunning']
result = dict(backgroundRuns=2, generatedBatches=len(runtime.drafts.list()), firstBatchSurvivesSecond=True,
              carouselSlides=4, carouselPackageSha256=hashlib.sha256(first_zip).hexdigest(), videos=videos,
              backendSourceHash=runtime.source_hash, workerStopped=True, phoneCommands=0, transferListeners=0,
              networkAllowed=False, published=False, messaged=False)
(RUN / (label + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))

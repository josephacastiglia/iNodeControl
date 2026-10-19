"""One bounded picker-close using unchanged product recognition/dispatch guards."""
import hashlib
import io
import json
from pathlib import Path
import signal
import sys
import threading
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_draft_workflow import Workflow, references
from farm_draft_transport import StepKernel
from farm_observations import ObservationStore, classify
from farm_live_verification import idle
from farm_screen_layout import picker_controls
from imouse_social_automation import LIVE_TEST_DEVICE_ID
from farm_carousel_inspection import InspectionStopped

prep = json.loads((HERE / 'preparation.json').read_text(encoding='utf-8'))
sources = json.loads((HERE / 'validation-sources.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
           for name, digest in sources.items())
raw = (ROOT / 'analysis/farm-phone-transfer-20261017/test-carousel.zip').read_bytes()
package_hash = hashlib.sha256(raw).hexdigest()
assert package_hash == '7f910284d9c7dc26d3c443183fdda33c78bdd4553036dabc75e38d158f48b616'
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    manifest = json.loads(archive.read('manifest.json'))
    assets = [archive.read(asset['file']) for asset in manifest['assets']]
folder = HERE / 'manual-save-picker-return'
folder.mkdir(exist_ok=False)
cancelled = threading.Event()
signal.signal(signal.SIGINT, lambda *_: cancelled.set())
workflow = Workflow(folder, StepKernel(prep['arguments'][0]), ObservationStore(folder / 'observations.sqlite3'),
    assets, manifest['caption'], references(), prep['validation']['build']['sha256'], prep['expectedUid'],
    account='xs.halle.xo', package_hash=package_hash, cancelled=cancelled)
workflow.record['mode'] = 'return_profile_after_operator_saved_draft'
try:
    workflow.identity = workflow.runtime()
    if not idle(workflow.kernel.input_status().get(LIVE_TEST_DEVICE_ID)):
        raise InspectionStopped('C24C is not free.')
    raw, _ = workflow.kernel.shot('C24C')
    text = workflow.store.ocr.read(raw)
    if not picker_controls(raw, text):
        raise InspectionStopped('Only the recognized Post picker may be closed.')
    workflow.record['cleanup'] = 'unconfirmed'; workflow.save()
    workflow.owned.acquire()
    workflow.command('/mouse/reset', purpose='initial_pointer_reset')
    workflow.command('/mouse/move', purpose='park_before_picker_return', x=480, y=300)
    workflow.pause(.65)
    workflow.action('return-profile-only', 'leave_picker', 'picker')
    workflow.observe('profile')
    workflow.record.update(state='profile_restored', savedDraftVerified=False)
except BaseException as error:
    workflow.record.update(state='review_required', error=type(error).__name__ + ': ' + str(error))
finally:
    try:
        if workflow.owned.tokens:
            workflow.owned.release(); workflow.record['cleanup'] = 'confirmed'
        workflow.record['finalInput'] = workflow.kernel.input_status().get(LIVE_TEST_DEVICE_ID)
        if not idle(workflow.record['finalInput']):
            workflow.record.update(state='review_required', cleanup='unconfirmed')
    except Exception as error:
        workflow.record.update(state='review_required', cleanup='unconfirmed', cleanupError=str(error))
    for entry in workflow.record['observations']:
        if entry.get('state') == 'observed':
            value, frame = workflow.store.evidence(entry['observationId'])
            assert hashlib.sha256(frame).hexdigest() == entry['observation']['reviewFrameSha256']
            (folder / entry['frame']).write_bytes(frame)
    workflow.save()
print(json.dumps({key: workflow.record.get(key) for key in ('state', 'error', 'cleanup', 'finalInput')}))
raise SystemExit(0 if workflow.record['state'] == 'profile_restored' else 2)

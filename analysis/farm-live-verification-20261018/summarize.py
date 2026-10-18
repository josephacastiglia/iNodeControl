"""Recheck retained phone evidence offline; never contacts a kernel."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_draft_media import media_comparison
from farm_draft_verification import caption_comparison
from farm_observations import classify


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def observation(folder, name):
    record = read(RUN / folder / 'record.json')
    return next(c['observation'] for c in record['captures'] if c['name'] == name)


def main():
    package = ROOT / 'analysis/farm-phone-transfer-20261017/test-carousel.zip'
    package_hash = hashlib.sha256(package.read_bytes()).hexdigest()
    assert package_hash == '7f910284d9c7dc26d3c443183fdda33c78bdd4553036dabc75e38d158f48b616'
    with zipfile.ZipFile(package) as files:
        manifest = json.loads(files.read('manifest.json'))
        assets = [files.read(a['file']) for a in manifest['assets']]
    caption = 'iMouse carousel draft test.\nThree numbered slides in order: 1, 2, 3.\nDRAFT ONLY - do not publish.'
    slides = []
    for index, folder in enumerate(('20-reopen-saved-carousel', '23-reopened-slide-two-verified', '24-reopened-slide-three'), 1):
        image = (RUN / folder / 'after.png').read_bytes()
        result = media_comparison(image, assets, 'carousel_editor')
        assert result['status'] == 'visual_match' and result['matchedIndex'] == index
        assert result['position']['index'] == index and result['position']['count'] == 3
        value = observation(folder, 'after')
        assert value['freshness'] == 'recent' and value['frameEvidence']['pairedMetadata']
        slides.append(dict(folder=folder, expected=index, comparison=result,
                           frameSha256=hashlib.sha256(image).hexdigest()))
    caption_after = caption_comparison(observation('25-reopened-caption', 'after')['text'], caption)
    assert caption_after['status'] == 'exact_visible_lines'
    account_checks = []
    for folder, phase in (('02-pointer-challenge', 'fresh'), ('31-exit-picker', 'after'), ('32-final-freshness', 'after')):
        value = observation(folder, phase)
        assert value['result']['accountStatus'] == 'exact_text_match'
        assert value['freshness'] == 'recent' and value['frameEvidence']['pairedMetadata']
        account_checks.append(dict(folder=folder, phase=phase, result=value['result']['accountStatus'],
            receiverSession=value['frameEvidence']['session'], generation=value['inputGeneration'],
            ageUpperBoundMs=value['frameEvidence']['ageUpperBoundMs']))
    freshness = read(RUN / '32-final-freshness/record.json')
    assert freshness['retainedExpiry']['freshness'] == 'stale'
    assert freshness['retainedExpiry']['recaptured'] is False
    records = [(p.parent.name, read(p)) for p in sorted(RUN.glob('*/record.json'))]
    commands = [(name, command) for name, value in records for command in value['commands']]
    assert all(c['fun'] in ('/mouse/reset', '/mouse/move', '/mouse/click', '/mouse/swipe') for _, c in commands)
    assert all(c['state'] == 'answered' and c['response']['code'] == 0 for _, c in commands)
    assert all(r['cleanup'] in ('confirmed', 'not_needed') for _, r in records)
    saves = [(name, r) for name, r in records if r['intent'] == 'save_draft']
    assert len(saves) == 2
    assert all(sum(c['fun'] == '/mouse/click' for c in r['commands']) == 1 for _, r in saves)
    restoration = read(RUN / 'restoration.json')
    assert restoration['restoredInitialStoppedState'] is True
    recognition = []
    for case in read(ROOT / 'analysis/farm-recognition-20261017/recognition-replay.json'):
        text = read(ROOT / 'analysis/farm-observations-20261017' / case['file'])
        result = classify(text, dict(platform='instagram', account='unrelated.test.account', caption=''))
        assert result['screen'] == case['expected'], case['file']
        assert result['accountStatus'] != 'exact_text_match' and result['automaticInputAllowed'] is False
        recognition.append(dict(file=case['file'], expected=case['expected'], actual=result['screen']))
    (RUN / 'saved-recognition-replay.json').write_text(json.dumps(recognition, indent=2), encoding='utf-8')
    summary = dict(source='agent_supervised_phone', sourcePackageSha256=package_hash,
        reopenedSlides=slides, captionAfter=caption_after, accountBoundaryChecks=account_checks,
        continuousAccountTracking=False, automaticInputAllowed=False, productSavedDraftVerified=False,
        savedDraftObservation='Existing test carousel saved, returned to library, reopened and inspected; not a newly created draft.',
        saveClicks=[name for name, _ in saves],
        retainedExpiry=freshness['retainedExpiry'],
        savedRecognitionRegressionCases=len(recognition),
        steps=len(records), answeredCommands=len(commands),
        reviewRequired=[dict(folder=name, reason=value['error'],
            semanticCommands=sum(c['fun'] in ('/mouse/click', '/mouse/swipe') for c in value['commands']))
            for name, value in records if value['state'] != 'observed'],
        restorationConfirmed=True)
    (RUN / 'live-evidence-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(dict(reopenedSlides=len(slides), caption=caption_after['status'],
        accountBoundaryChecks=len(account_checks), retainedFrameExpired=True,
        steps=len(records), answeredCommands=len(commands), cleanup='confirmed',
        savedRecognitionRegressionCases=len(recognition),
        automaticInputAllowed=False)))


if __name__ == '__main__':
    main()

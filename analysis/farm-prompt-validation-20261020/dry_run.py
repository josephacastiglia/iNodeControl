"""Offline dry run of the window's command-line steps against the synthetic C24C stand-in.

No socket, phone, kernel or service: tools/farm_prompt_fixture.py replaces the kernel and OCR.
It runs part A in the planned order on a Paste prompt (observe, both class checks, long press,
focus-only, keyboard focus, confirm, promote), then the part B probe on a blank page. The
fixture is told which methods it obeys, so these results show the protocol and the records,
not how iOS behaves. Summaries go to dry-run/; private records to a temporary folder. Promote
refuses every fixture result: only a phone trial can become evidence.
"""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import farm_test_network  # noqa: E402,F401  Refuse every real socket in this process.
import farm_prompt_validation as pv  # noqa: E402
from farm_prompt_fixture import FixtureOcr, PromptPhone  # noqa: E402

OUT = HERE/'dry-run'
PART_A = [
    ('a1-observe', ['observe', '--part', 'A']),
    ('a2-class-tap', ['trial', '--part', 'A', '--method', 'pointer_tap']),
    ('a3-class-escape', ['trial', '--part', 'A', '--method', 'keyboard_escape']),
    ('a4-long-press', ['trial', '--part', 'A', '--method', 'long_press']),
    ('a5-focus-only', ['trial', '--part', 'A', '--method', 'keyboard_focus', '--no-activate']),
    ('a6-keyboard-focus', ['trial', '--part', 'A', '--method', 'keyboard_focus']),
]


def main():
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir()
    results = []
    with tempfile.TemporaryDirectory(prefix='prompt-dry-run-') as directory:
        preparation = Path(directory)/'live/preparation.json'; preparation.parent.mkdir()
        preparation.write_text(json.dumps(dict(root=str(ROOT), windowRecord=str(OUT), runDirectory=str(Path(directory)/'run'),
                                               kernelSha256='a'*64, expectedUid='fixture-uid')), encoding='utf-8')
        # Part A: a Paste prompt; the stand-in obeys only a verified keyboard-focus Space.
        phone = PromptPhone('paste', answers={'keyboard_focus'}, focus_order=('Allow Paste', "Don't Allow Paste"))
        def run(label, argv, device):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = pv.main([argv[0], '--preparation', str(preparation), '--label', label, *argv[1:]],
                               kernel_factory=lambda probe: device, ocr=FixtureOcr(device), clock=device.clock,
                               monotonic=device.clock, pause=device.pause)
            results.append(dict(label=label, exitCode=code, printed=json.loads(output.getvalue())))
        for label, argv in PART_A: run(label, argv, phone)
        for label, argv in (('a6-keyboard-focus', ['confirm', '--declined', '--observed', 'Fixture: the field stayed empty']),
                            ('a6-keyboard-focus', ['promote'])):
            run(label, argv, phone)
        # Part B: the move-only probe on a blank page.
        run('b1-probe', ['probe', '--part', 'B'], PromptPhone(None, probe=True))
        trials = sorted(p.name for p in (Path(directory)/'run/trials').iterdir())
        frames = sum(1 for _ in (Path(directory)/'run/trials').rglob('*.png'))
    report = dict(meaning='Synthetic stand-in. Protocol and record shapes only; no phone, kernel or service was used.',
                  steps=results, privateTrialFolders=trials, privateFramesExported=frames,
                  stateAfterPartA=dict(answered=phone.answered, promptVisible=phone.visible))
    (OUT/'dry-run.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(steps=len(results), exitCodes=[r['exitCode'] for r in results], answered=phone.answered)))


if __name__ == '__main__':
    main()

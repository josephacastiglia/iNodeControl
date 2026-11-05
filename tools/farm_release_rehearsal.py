"""Clean-machine rehearsal of the Marketing Farm release, entirely inside one new temporary folder tree.

  python tools/farm_release_rehearsal.py --kernel DIR --console DIR --receiver-exe FILE --receiver-runtime DIR
         [--work DIR] [--keep]

Steps: build package A from this checkout and package B from a temporary copy with one changed farm
file; make a fake per-machine data folder with fake rack state; install A; run installed code under the
runtime guard (all farm modules imported, the farm server's offline --self-check) with the data folder
as the working directory; run the launcher (status, preflight, a blocked command's refusal); update to B;
roll back to A; check a tampered version is refused; uninstall; prove the data folder is unchanged.

Never starts the kernel, a receiver or a farm backend; the guard refuses every process start and every
connection except to the self-check's own port. Runs at below-normal priority.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import farm_install as fi  # noqa: E402
import farm_release as fr  # noqa: E402

FAKE_PREPARATION = {'note': 'rehearsal fake: no real device', 'receivers': [{'board': 'FAKE', 'name': 'iMouse2-FAKE', 'port': 7110}]}


def below_normal():
    try:
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    except (AttributeError, OSError):
        pass


def tree_hash(root, skip=()):
    digest = hashlib.sha256()
    for p in sorted(Path(root).rglob('*')):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and rel not in skip:
            digest.update(rel.encode() + b'\0' + fr.sha256(p).encode() + b'\n')
    return digest.hexdigest()


def run(cmd, cwd, timeout=300):
    started = time.monotonic()
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                          creationflags=getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0))
    return {'exit': done.returncode, 'seconds': round(time.monotonic() - started, 1),
            'stdout': done.stdout[-40000:], 'stderr': done.stderr[-4000:]}


def copy_sources(dest):
    """A throwaway copy of the farm sources (tools/ and the rack scripts), with one changed file."""
    for rel in ('tools', fr.RACK_DIR):
        shutil.copytree(REPO / rel, dest / rel, ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', 'slots', 'held', 'windows', 'windows-archive', 'rack-a', 'rack-b', 'identify', 'autoconnect',
            'measure', 'look', 'card-survey', 'airplay', 'protocol-deps', '*.png', '*.jpg', '*.bmp', '*.log', '*.jsonl'))
    marker = dest / 'tools' / 'mdns_goodbye.py'
    marker.write_text(marker.read_text(encoding='utf-8') + '\n# rehearsal B: this line marks the updated version\n', encoding='utf-8')
    return dest


def guarded(python, guard, forbid, report, cwd, script=None, import_all=None, args=()):
    cmd = [python, '-E', str(guard), '--forbid', str(forbid), '--report', str(report)]
    if import_all:
        cmd += ['--import-all', str(import_all)]
    if script:
        cmd += ['--', str(script), *args]
    outcome = run(cmd, cwd)
    outcome['report'] = json.loads(Path(report).read_text(encoding='utf-8'))
    return outcome


def powershell(script, *args, cwd):
    return run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script), *args], cwd)


def rehearse(kernel, console, receiver_exe, receiver_runtime, work):
    below_normal()
    work = Path(work)
    pc = work / 'clean-pc'
    packages, root, data, scratch = pc / 'packages', pc / 'LocalAppData/Programs/iMouseFarm', pc / 'LocalAppData/iMouseFarm', pc / 'scratch'
    for p in (packages, scratch):
        p.mkdir(parents=True)
    steps, checks = [], {}

    def step(name, value):
        steps.append({'step': name, 'utc': datetime.now(timezone.utc).isoformat(), **value})
        return value

    tokens = fr.privacy_tokens()
    a = fr.build(REPO, packages / 'farm-A', kernel, console, receiver_exe, receiver_runtime, version='rehearsal-a', tokens=tokens or ())
    b_src = copy_sources(work / 'source-copy-B')
    b = fr.build(b_src, packages / 'farm-B', kernel, console, receiver_exe, receiver_runtime, version='rehearsal-b', tokens=tokens or ())
    step('build', {'A': {'files': len(a['files']), 'bytes': sum(r['bytes'] for r in a['files'].values())},
                   'B': {'files': len(b['files'])}, 'privacy_lists_used': tokens is not None,
                   'dev_path_blockers': a['dev_path_findings'], 'ready': [c for c, s in a['commands'].items() if s['ready']],
                   'blocked': [c for c, s in a['commands'].items() if not s['ready']]})
    shutil.rmtree(b_src)
    checks['packages verify'] = not fr.verify(packages / 'farm-A') and not fr.verify(packages / 'farm-B')

    # Fake per-machine data folder, with fake rack state the release must never carry or touch.
    fi.init_data(data)
    (data / f'{fr.RACK_DIR}/slots/preparation.json').write_text(json.dumps(FAKE_PREPARATION), encoding='utf-8')
    (data / f'{fr.RACK_DIR}/phone-slots.json').write_text('{"slots": {"1": {"board": "FAKE"}}}', encoding='utf-8')
    (data / 'evidence-archive/privacy/withheld-candidates.txt').write_text('# fake\n', encoding='utf-8')
    data_before = tree_hash(data, skip={'data.json'})

    step('install A', fi.install(packages / 'farm-A', root, data, python=sys.executable))
    version_a = root / 'versions/rehearsal-a'
    guard = scratch / 'runtime_guard.py'
    shutil.copyfile(HERE / 'release/runtime_guard.py', guard)
    dev = REPO.parent.parent if REPO.parent.name.endswith('.worktrees') else REPO.parent  # ...\Desktop\Claude Code

    imports = guarded(sys.executable, guard, dev, scratch / 'imports-A.json', cwd=data, import_all=version_a / 'farm/tools')
    step('import every installed farm module (guarded)', {k: imports[k] for k in ('exit', 'seconds')} | {
        k: imports['report'].get(k) for k in ('imported', 'import_errors', 'forbidden_opened', 'forbidden_modules', 'forbidden_sys_path', 'refused', 'opened_count')})
    selfcheck = guarded(sys.executable, guard, dev, scratch / 'selfcheck-A.json', cwd=data,
                        script=version_a / 'farm/tools/imouse_farm_server.py', args=['--self-check'])
    step('farm server --self-check from the install (guarded)', {k: selfcheck[k] for k in ('exit', 'seconds')} | {
        'stdout_tail': selfcheck['stdout'][-300:], 'stderr_tail': selfcheck['stderr'][-600:]} | {
        k: selfcheck['report'].get(k) for k in ('exit', 'error', 'forbidden_opened', 'forbidden_modules', 'forbidden_sys_path', 'refused', 'opened_count')})
    paths = guarded(sys.executable, guard, dev, scratch / 'paths-A.json', cwd=data,
                    script=_paths_probe(scratch, version_a / 'farm/tools'))
    step('farm_paths as installed (guarded)', {'stdout': paths['stdout'].strip()[-800:], 'exit': paths['exit']})
    checks['dev folder not read (imports)'] = not any(imports['report'][k] for k in ('forbidden_opened', 'forbidden_modules', 'forbidden_sys_path'))
    checks['dev folder not read (self-check)'] = not any(selfcheck['report'][k] for k in ('forbidden_opened', 'forbidden_modules', 'forbidden_sys_path'))
    checks['self-check passed'] = selfcheck['report'].get('exit') == 0 and 'OK' in selfcheck['stdout']
    checks['guard refused nothing'] = not selfcheck['report']['refused'] and not imports['report']['refused']

    launcher = root / 'Farm.ps1'
    status = powershell(launcher, 'status', cwd=scratch)
    step('Farm.ps1 status', {'exit': status['exit'], 'stdout': status['stdout'].strip()[-1200:]})
    preflight = powershell(launcher, 'preflight', '-Json', cwd=scratch)
    try:
        pf = json.loads(preflight['stdout'][preflight['stdout'].index('{'):])
        step('Farm.ps1 preflight (read-only)', {'exit': preflight['exit'], 'seconds': preflight['seconds'],
                                               'not_ok': [(c['id'], c['status']) for c in pf['checks'] if c['status'] != 'ok']})
    except (json.JSONDecodeError, ValueError):
        step('Farm.ps1 preflight (read-only)', {'exit': preflight['exit'], 'stdout': preflight['stdout'][-800:], 'stderr': preflight['stderr'][-400:]})
    blocked = [c for c, s in a['commands'].items() if not s['ready'] and c == 'start-rack']
    if blocked:  # only ever call a command the manifest marks NOT ready: the launcher must refuse it
        refusal = powershell(launcher, 'start-rack', cwd=scratch)
        step('Farm.ps1 start-rack (blocked: must refuse, start nothing)', {'exit': refusal['exit'], 'stderr': refusal['stderr'].strip()[-500:]})
        checks['launcher refuses a blocked command'] = refusal['exit'] != 0 and 'not ready' in refusal['stderr']

    step('update to B', fi.update(packages / 'farm-B', root))
    checks['update switched'] = fi.status(root)['version'] == 'rehearsal-b' and fi.status(root)['previous'] == 'rehearsal-a'
    checks['B has its change'] = 'rehearsal B' in (root / 'versions/rehearsal-b/farm/tools/mdns_goodbye.py').read_text(encoding='utf-8')
    imports_b = guarded(sys.executable, guard, dev, scratch / 'imports-B.json', cwd=data, import_all=root / 'versions/rehearsal-b/farm/tools')
    checks['dev folder not read (B imports)'] = not any(imports_b['report'][k] for k in ('forbidden_opened', 'forbidden_modules', 'forbidden_sys_path'))
    status_b = powershell(launcher, 'status', cwd=scratch)
    checks['launcher follows the switch'] = 'rehearsal-b' in status_b['stdout']

    (version_a / 'console/startup-state.json').write_text('{"written by": "the console beside itself"}', encoding='utf-8')
    step('roll back to A', fi.rollback(root))
    checks['rollback switched'] = fi.status(root)['version'] == 'rehearsal-a' and fi.status(root)['previous'] == 'rehearsal-b'
    checks['launcher follows the rollback'] = 'rehearsal-a' in powershell(launcher, 'status', cwd=scratch)['stdout']

    tampered = root / 'versions/rehearsal-b/farm/tools/farm_jobs.py'
    tampered.write_bytes(tampered.read_bytes() + b'\n# tampered\n')
    try:
        fi.rollback(root)
        checks['tampered version refused'] = False
    except fi.Refused as error:
        step('roll back to a tampered B (must refuse)', {'refused': str(error)[:200]})
        checks['tampered version refused'] = fi.status(root)['version'] == 'rehearsal-a'

    state = fi.read_json(data / 'data.json')
    step('uninstall', fi.uninstall(root))
    checks['install root removed'] = not root.exists()
    checks['data folder kept and unchanged'] = tree_hash(data, skip={'data.json'}) == data_before and state['last_version'] == 'rehearsal-a'
    checks['package carries no private state'] = not [n for n in a['files'] if fr.is_private(n) and not n.startswith('receiver/runtime/')]
    return {'utc': datetime.now(timezone.utc).isoformat(), 'source': a['source'], 'passed': all(checks.values()),
            'checks': checks, 'steps': steps}


def _paths_probe(scratch, tools):
    probe = Path(scratch) / 'paths_probe.py'
    probe.write_text(
        'import sys\nsys.path.insert(0, %r)\nimport farm_paths as p\n'
        'print("MAIN", p.MAIN)\nprint("ARCHIVE", p.ARCHIVE)\nprint("RACK", p.RACK)\n' % str(tools), encoding='utf-8')
    return probe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for key in ('kernel', 'console', 'receiver-exe', 'receiver-runtime'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--work', type=Path, help='a new folder (default: a new temporary folder)')
    parser.add_argument('--report', type=Path, help='write the JSON report here (default: output/release-rehearsal-<utc>.json)')
    parser.add_argument('--keep', action='store_true', help='keep the temporary tree for inspection')
    args = parser.parse_args(argv)
    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix='farm-clean-pc-'))
    if args.work:
        work.mkdir(parents=True, exist_ok=False)
    try:
        result = rehearse(args.kernel, args.console, args.receiver_exe, args.receiver_runtime, work)
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
    report = args.report or REPO / 'output' / f"release-rehearsal-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=1), encoding='utf-8')
    for name, ok in result['checks'].items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"Rehearsal {'passed' if result['passed'] else 'FAILED'}; report {report}")
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

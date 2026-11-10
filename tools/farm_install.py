"""Install, update, roll back and uninstall a Marketing Farm release in a versioned folder.

Standard library only; runs from a package's install/ folder or from tools/. Changes nothing outside the
install root and the data folder it is given: no services, drivers, firewall rules, registry, PATH or
shortcuts. The operator does those (Preflight-Farm.ps1 prints the steps).

  <root>/install.json          data folder, Python, created; written once by install
  <root>/current.json          {"version", "previous", "history"}; replaced in one step (os.replace)
  <root>/versions/<version>/   a verified, never-modified copy of one package
  <root>/Farm.ps1              launcher: reads current.json, runs a command from that version

  <data>/data.json             data schema and the last version that used this folder
  <data>/...                   private per-machine state (DATA_DIRS); never inside the install root

  python farm_install.py init-data --data DIR
  python farm_install.py install   --package PKG --root DIR --data DIR [--python EXE]
  python farm_install.py update    --package PKG --root DIR
  python farm_install.py rollback  --root DIR
  python farm_install.py status    --root DIR
  python farm_install.py prune     --root DIR            # remove versions other than current and previous
  python farm_install.py uninstall --root DIR            # the data folder is kept
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import farm_release as fr  # noqa: E402

SCHEMA = 1
# Private state, laid out as the farm tools expect it relative to their state root (farm_paths.MAIN once
# IMOUSE_FARM_DATA is honoured). Created empty by init-data; filled by the operator's own preparations.
DATA_DIRS = (
    'analysis/farm-multiphone-20261020/slots',    # the kernel's preparation, process record, logs and ledgers
    'analysis/farm-multiphone-20261020/windows',  # per-window preparations, backend data, run logs
    'output/candidate-runs',                      # kernel run directories: devices, receivers, calibration
    'output/farm-data',                           # backend databases
    'output/media-stage',
    'output/farm-schedule',                       # review queue and slot state
    'evidence-archive/privacy',                   # withheld-value lists for the privacy scan
    'logs',
)


class Refused(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json_atomic(path, value):
    """Write beside the target, flush to disk, then replace in one step: readers see old or new, never half."""
    path = Path(path)
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex[:8]}.tmp')
    with temp.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _inside(a, b):
    a, b = Path(a).resolve(), Path(b).resolve()
    return a == b or a.is_relative_to(b)


def _in_checkout(path):
    for folder in [Path(path).resolve(), *Path(path).resolve().parents]:
        if (folder / '.git').exists():
            return folder
    return None


def check_roots(root, data, package=None):
    root, data = Path(root).resolve(), Path(data).resolve()
    if _inside(root, data) or _inside(data, root):
        raise Refused('the data folder and the install root must not contain each other')
    for label, path in (('install root', root), ('data folder', data)):
        checkout = _in_checkout(path)
        if checkout:
            raise Refused(f'the {label} is inside a source checkout ({checkout}); install outside the dev folder')
        if package and (_inside(path, package) or _inside(package, path)):
            raise Refused(f'the {label} and the package folder overlap')


# ---------------------------------------------------------------- data folder

def init_data(data, package_schema=fr.DATA_SCHEMA):
    data = Path(data)
    marker = data / 'data.json'
    if marker.exists():
        info = read_json(marker)
        if info.get('schema_version') != SCHEMA:
            raise Refused('data.json is not a Marketing Farm data folder marker')
        created = False
    else:
        if data.exists() and any(data.iterdir()):
            raise Refused(f'{data} exists, is not empty and has no data.json; choose an empty or new folder')
        data.mkdir(parents=True, exist_ok=True)
        info = {'schema_version': SCHEMA, 'data_schema': package_schema, 'created_utc': now(), 'last_version': None}
        created = True
    for d in DATA_DIRS:
        (data / d).mkdir(parents=True, exist_ok=True)
    if created:
        write_json_atomic(marker, info)
    return info


def _claim_data(data, manifest):
    marker = Path(data) / 'data.json'
    info = read_json(marker)
    if info.get('data_schema', 0) > manifest['data_schema']:
        raise Refused(f"version {manifest['version']} reads data schema {manifest['data_schema']}, "
                      f"but this data folder is at schema {info['data_schema']}: an older version must not open newer data")
    info.update(data_schema=max(info.get('data_schema', 0), manifest['data_schema']), last_version=manifest['version'], last_used_utc=now())
    write_json_atomic(marker, info)


# ---------------------------------------------------------------- processes

def farm_processes(root):
    """Processes whose executable or command line is under the install root (read-only CIM query)."""
    script = ("Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath,CommandLine | "
              "ConvertTo-Json -Compress")
    try:
        out = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                             capture_output=True, text=True, timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise Refused(f'could not list processes to check nothing runs from the install: {error}') from error
    rows = json.loads(out or '[]')
    rows = rows if isinstance(rows, list) else [rows]
    needle = str(Path(root).resolve()).casefold()
    return [r for r in rows if needle in (r.get('ExecutablePath') or '').casefold() or needle in (r.get('CommandLine') or '').casefold()]


def _require_idle(root, processes):
    running = processes(root)
    if running:
        names = ', '.join(sorted({f"{r.get('Name')} (pid {r.get('ProcessId')})" for r in running}))
        raise Refused(f'farm processes run from this install: {names}. Stop the farm (Stop-Window, Stop-Multiphone) first')


# ---------------------------------------------------------------- versions

def _versions(root):
    return Path(root) / 'versions'


def _verified_manifest(folder, installed=False):
    # An installed version may hold files its apps wrote beside themselves; recorded bytes must match.
    issues = fr.verify(folder, allow_unrecorded=installed)
    if issues:
        raise Refused(f'{folder.name} failed verification: ' + '; '.join(issues[:5]))
    return fr.load_json(Path(folder) / 'release.json')


def _copy_version(root, package):
    manifest = _verified_manifest(Path(package))
    target = _versions(root) / manifest['version']
    if target.exists():
        if _verified_manifest(target, installed=True)['files'] != manifest['files']:
            raise Refused(f"version {manifest['version']} is already installed with different files")
        return manifest, target, False
    partial = _versions(root) / f".{manifest['version']}.partial-{uuid.uuid4().hex[:8]}"
    partial.mkdir(parents=True)
    try:
        for name in manifest['files']:
            dest = partial.joinpath(*fr.safe_name(name).split('/'))
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(package).joinpath(*name.split('/')), dest)
        shutil.copyfile(Path(package) / 'release.json', partial / 'release.json')
        _verified_manifest(partial)
        os.replace(partial, target)  # the version appears complete or not at all
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return manifest, target, True


def _install_launcher(root, version_dir):
    src = version_dir / 'install' / 'Farm.ps1'
    temp = Path(root) / f'.Farm.ps1.{uuid.uuid4().hex[:8]}.tmp'
    shutil.copyfile(src, temp)
    os.replace(temp, Path(root) / 'Farm.ps1')


def _switch(root, version, previous, action):
    state_path = Path(root) / 'current.json'
    history = read_json(state_path).get('history', []) if state_path.exists() else []
    history = (history + [{'utc': now(), 'action': action, 'version': version, 'from': previous}])[-50:]
    write_json_atomic(state_path, {'schema_version': SCHEMA, 'version': version, 'previous': previous, 'history': history})


def status(root):
    root = Path(root)
    if not (root / 'install.json').exists():
        return {'installed': False}
    current = read_json(root / 'current.json')
    versions = sorted(p.name for p in _versions(root).iterdir() if p.is_dir() and not p.name.startswith('.'))
    partials = sorted(p.name for p in _versions(root).iterdir() if p.name.startswith('.'))
    return {'installed': True, **read_json(root / 'install.json'), 'version': current['version'],
            'previous': current.get('previous'), 'versions': versions, 'leftover_partials': partials}


def install(package, root, data, python=None, processes=farm_processes):
    root, data, package = Path(root).resolve(), Path(data).resolve(), Path(package).resolve()
    check_roots(root, data, package)
    if (root / 'install.json').exists():
        raise Refused('already installed here; use update')
    if root.exists() and any(root.iterdir()):
        raise Refused(f'{root} exists and is not empty; choose an empty or new folder')
    manifest = fr.load_json(package / 'release.json')
    init_data(data, manifest.get('data_schema', fr.DATA_SCHEMA))
    root.mkdir(parents=True, exist_ok=True)
    manifest, target, _ = _copy_version(root, package)
    _claim_data(data, manifest)
    write_json_atomic(root / 'install.json', {'schema_version': SCHEMA, 'data_root': str(data),
                                              'python': str(python) if python else None, 'created_utc': now()})
    _install_launcher(root, target)
    _switch(root, manifest['version'], None, 'install')
    return status(root)


def update(package, root, processes=farm_processes):
    root, package = Path(root).resolve(), Path(package).resolve()
    if not (root / 'install.json').exists():
        raise Refused('nothing installed here; use install')
    info = read_json(root / 'install.json')
    check_roots(root, info['data_root'], package)
    current = read_json(root / 'current.json')
    incoming = fr.load_json(package / 'release.json')
    if incoming.get('version') == current['version']:
        raise Refused(f"version {current['version']} is already current")
    _require_idle(root, processes)
    manifest, target, _ = _copy_version(root, package)
    _claim_data(info['data_root'], manifest)
    _install_launcher(root, target)
    _switch(root, manifest['version'], current['version'], 'update')
    return status(root)


def rollback(root, processes=farm_processes):
    root = Path(root).resolve()
    if not (root / 'install.json').exists():
        raise Refused('nothing installed here')
    info, current = read_json(root / 'install.json'), read_json(root / 'current.json')
    previous = current.get('previous')
    if not previous:
        raise Refused('there is no previous version to roll back to')
    target = _versions(root) / previous
    if not target.is_dir():
        raise Refused(f'previous version {previous} is no longer installed')
    _require_idle(root, processes)
    manifest = _verified_manifest(target, installed=True)
    _claim_data(info['data_root'], manifest)
    _install_launcher(root, target)
    _switch(root, previous, current['version'], 'rollback')
    return status(root)


def prune(root, processes=farm_processes):
    root = Path(root).resolve()
    current = read_json(root / 'current.json')
    keep = {current['version'], current.get('previous')}
    _require_idle(root, processes)
    removed = []
    for p in sorted(_versions(root).iterdir()):
        if p.is_dir() and (p.name not in keep or p.name.startswith('.')):
            shutil.rmtree(p)
            removed.append(p.name)
    return removed


def uninstall(root, processes=farm_processes):
    root = Path(root).resolve()
    if not (root / 'install.json').exists():
        raise Refused('nothing installed here')
    info = read_json(root / 'install.json')
    _require_idle(root, processes)
    known = {'versions', 'current.json', 'install.json', 'Farm.ps1'}
    extra = sorted(p.name for p in root.iterdir() if p.name not in known and not p.name.startswith('.'))
    if extra:
        raise Refused('the install root holds files the installer did not write: ' + ', '.join(extra))
    shutil.rmtree(_versions(root))
    for name in ('Farm.ps1', 'current.json', 'install.json'):
        (root / name).unlink(missing_ok=True)
    for leftover in root.iterdir():
        if leftover.name.startswith('.') and leftover.suffix == '.tmp':
            leftover.unlink()
    root.rmdir()
    return {'removed': str(root), 'data_kept': info['data_root']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='mode', required=True)
    d = sub.add_parser('init-data'); d.add_argument('--data', type=Path, required=True)
    i = sub.add_parser('install')
    for p in (i, sub.add_parser('update')):
        p.add_argument('--package', type=Path, required=True)
        p.add_argument('--root', type=Path, required=True)
    i.add_argument('--data', type=Path, required=True)
    i.add_argument('--python', type=Path)
    for name in ('rollback', 'status', 'prune', 'uninstall'):
        sub.add_parser(name).add_argument('--root', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'init-data': result = init_data(args.data)
        elif args.mode == 'install': result = install(args.package, args.root, args.data, args.python)
        elif args.mode == 'update': result = update(args.package, args.root)
        elif args.mode == 'rollback': result = rollback(args.root)
        elif args.mode == 'status': result = status(args.root)
        elif args.mode == 'prune': result = {'removed': prune(args.root)}
        else: result = uninstall(args.root)
    except (Refused, ValueError, OSError) as error:
        print(json.dumps({'refused': str(error)}))
        return 2
    print(json.dumps(result, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

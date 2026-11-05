"""Build, verify and lint a Marketing Farm release package. Never starts, installs or stops anything.

A package is a folder (and optionally a zip of it) with this layout:

  release.json                         manifest: version, components, prerequisites, every file's SHA-256
  Install-Farm.ps1                     operator entry: preflight, then install/update via the pinned Python
  install/                             farm_install.py, farm_release.py (verify), Preflight-Farm.ps1, Farm.ps1
  kernel/                              iMouse2.Kernel.{exe,dll,deps.json,runtimeconfig.json,pdb}
  console/                             iMouse2.{exe,dll,deps.json,runtimeconfig.json,pdb}
  receiver/uxplay.exe, receiver/runtime/**   patched UxPlay and its GStreamer/MSYS2 runtime
  farm/tools/**, farm/analysis/farm-multiphone-20261020/**   the farm's Python/PowerShell, same relative layout

Private, per-machine state is never packaged: rack preparations and process records, phone-slot and
board maps, window folders, receiver/device/calibration data, run output, databases, logs, captures,
evidence and accounts. It lives in the per-machine data folder (farm_install.py init-data).

  python tools/farm_release.py build --out output/release/<name> --kernel DIR --console DIR \
         --receiver-exe FILE --receiver-runtime DIR [--version V] [--zip]
  python tools/farm_release.py verify --package DIR
  python tools/farm_release.py lint [--json]          # dev-folder assumptions in the runtime set
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
SCHEMA = 1
DATA_SCHEMA = 1
KIND = 'imouse-marketing-farm'
RACK_DIR = 'analysis/farm-multiphone-20261020'

KERNEL_FILES = tuple('iMouse2.Kernel' + s for s in ('.exe', '.dll', '.deps.json', '.runtimeconfig.json', '.pdb'))
CONSOLE_FILES = tuple('iMouse2' + s for s in ('.exe', '.dll', '.deps.json', '.runtimeconfig.json', '.pdb'))
FRAMEWORKS = {'kernel': {'Microsoft.NETCore.App'}, 'console': {'Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App'}}
RECEIVER_RUNTIME_REQUIRED = ('libexec/gstreamer-1.0/gst-plugin-scanner.exe',)

# Farm entry points. Their local imports and every tools/ or rack file they name are added too.
ENTRIES = ('tools/imouse_farm_server.py', 'tools/farm_schedule_cli.py', 'tools/farm_schedule_runner.py',
           'tools/farm_photos_cleanup.py', 'tools/mdns_goodbye.py', 'tools/requirements-farm.txt')
RACK_SCRIPT_GLOBS = ('*.py', '*.ps1')
# One-off rack probes and bring-up helpers with machine-specific values (phone IPs, a fixed path): not
# packaged unless an operator script names them.
DEV_ONLY = {'identify_rack_b.py', 'connect_xr.ps1', 'connect_small.ps1', 'learn_rack_b.ps1', 'board_probe.py',
            'one_tap.py', 'switcher_probe.py', 'open_app_look.py',
            # 20 Oct one-shot preparations: fixed run names, they refuse to run again (superseded by prepare_rack_a/b, rack_kernels).
            'prepare_multiphone.py', 'prepare_slots.py'}

# Never packaged, whatever references them. Matched against the package-relative path (case-insensitive).
PRIVATE_PATTERNS = (
    '*/preparation*.json', 'preparation*.json', '*/processes*.json', '*/receivers-ready.json',
    '*/phone-slots.json', '*/rack-b-boards.json', '*/rack-b-slots.json', '*/rack-*-slots.json',
    '*/slots/*', '*/held/*', '*/windows/*', '*/windows-archive/*', '*/rack-a/*', '*/rack-b/*',
    '*/identify/*', '*/autoconnect/*', '*/measure/*', '*/look/*', '*/data/*', '*/output/*',
    '*devices.json', '*receivers.json', '*pointer-calibration.json', '*settings.json', '*startup-state.json',
    '*ui-boxes.json', '*imservice.json', '*.db', '*.db-*', '*.sqlite*', '*.log', '*.jsonl', '*.etl',
    '*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif', '*.mp4', '*.mov', '*.webm', '*.heic',
    '*.pfx', '*.p12', '*.key', '*.pem', '*.token', '*.env', '*.env.*', '*/__pycache__/*', '*.pyc',
    '*kernel*.txt', '*evidence-archive*', '*/privacy/*', '*withheld*', '*handles*',
)
TEST_PATTERNS = ('test_*.py', '*_test.py', '*/offrack/*')

# Content that must never ship: device identifiers and absolute dev/user paths.
PRIVATE_CONTENT = (
    ('device id (UDID)', re.compile(rb'\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}\b')),
    ('device id (40-hex UDID)', re.compile(rb'(?<![0-9A-Fa-f])[0-9A-Fa-f]{40}(?![0-9A-Fa-f])')),
)
TEXT_SUFFIXES = {'.py', '.ps1', '.psm1', '.json', '.txt', '.md', '.cmd', '.bat', '.cfg', '.ini', '.xml', '.config'}

# Dev-folder assumptions. 'blocker' = the installed copy would read or write the dev folder (or keep
# state inside the install); 'info' = works when installed but is worth a review.
LINT_RULES = (
    ('blocker', 'absolute user path', re.compile(r'[A-Za-z]:[\\/]+Users[\\/]', re.I)),
    ('blocker', 'dev folder name', re.compile(r'Desktop[\\/]+Claude Code|iMouseXP-2\.0(?:-combined-candidate|-evidence-archive)?(?![\w-])', re.I)),
    ('blocker', 'lane worktree discovery (.worktrees)', re.compile(r'\.worktrees')),
    ('blocker', 'pinned interpreter path', re.compile(r'Python3\d+[\\/]+python\.exe', re.I)),
    ('blocker', 'state under the code folder (output/)', re.compile(r'''(?:ROOT|REPO|HERE|taskRoot|taskMain|parents\[\d\])[^\n]{0,40}['"]output(?:[\\/]|['"])''')),
    ('info', 'cwd-relative state (lands in the data folder: Farm.ps1 runs there)', re.compile(r'''^[^#\n]*Path\(\s*['"](?:output|config)[\\/]''')),
    ('blocker', 'state beside the rack scripts ($PSScriptRoot)', re.compile(r'''Join-Path\s+\$PSScriptRoot\s+(?:\$Stage|\$Rack|\(?['"](?:windows|slots|held|rack-|processes|preparation|receivers-ready|identify|autoconnect|measure|look))''', re.I)),
    ('blocker', 'state beside the rack scripts (__file__)', re.compile(r'''(?:HERE|ROOT|FOLDER|folder)\s*/\s*f?['"](?:windows|slots|held|rack-|identify|autoconnect|card-survey|measure|look|phone-slots)''')),
    ('blocker', 'rack folder via repo layout', re.compile(r'''(?:ROOT|REPO|HERE)[^\n]{0,10}['"]analysis[\\/]+farm-multiphone-20261020['"]''')),
    ('blocker', 'rack state via repo layout', re.compile(r'''['"]analysis[\\/]+farm-multiphone-20261020[\\/]+(?:slots|held|windows|rack-)''', re.I)),
    ('info', 'hard-coded kernel port', re.compile(r'127\.0\.0\.1:99(?:13|16|26)')),
    ('info', 'repo-relative root (parents[N] / ..\\..)', re.compile(r'''parents\[[1-9]\]|Join-Path\s+\$PSScriptRoot\s+['"]\.\.[\\/]\.\.''')),
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def row(path):
    return {'sha256': sha256(path), 'bytes': Path(path).stat().st_size}


def safe_name(name):
    """A package-relative POSIX path that cannot escape the package or name a device."""
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError(f'unsafe package path: {name!r}')
    parts = PurePosixPath(name).parts
    if PurePosixPath(name).is_absolute() or any(p in ('', '.', '..') or p.endswith((' ', '.')) or
            re.match(r'^(CON|PRN|AUX|NUL|COM\d|LPT\d)(\.|$)', p, re.I) for p in parts):
        raise ValueError(f'unsafe package path: {name!r}')
    return name


def is_private(name):
    low = name.casefold()
    return any(fnmatch.fnmatchcase(low, p) for p in PRIVATE_PATTERNS)


def is_test(name):
    base = PurePosixPath(name).name
    return any(fnmatch.fnmatchcase(base, p) or fnmatch.fnmatchcase(name, p) for p in TEST_PATTERNS)


def load_json(path):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f'duplicate JSON key: {k}')
            out[k] = v
        return out
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique)


# ---------------------------------------------------------------- farm file set

def _named_files(text, folders):
    """Every existing file in `folders` (or one folder below) that the text names ('x.py', 'kernel-window/y.ps1')."""
    found = set()
    for match in re.finditer(r'''(?:([A-Za-z0-9_.-]+)[\\/]+)?([A-Za-z0-9_.-]+\.(?:py|ps1|json|txt))\b''', text):
        sub, base = match.groups()
        for folder in folders:
            candidates = ([folder / sub / base] if sub else []) + [folder / base]
            hit = next((c for c in candidates if c.is_file()), None)
            if hit is not None:
                found.add(hit.resolve())
                break
    return found


def references(path, folders):
    """Files a script pulls in. Python: its imports and the string constants it holds (module names for
    importlib, file names it opens or launches); comments and docstring-only mentions do not count.
    PowerShell: file names on non-comment lines."""
    path = Path(path)
    if path.suffix == '.ps1':
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        return _named_files('\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#')), folders)
    if path.suffix != '.py':
        return set()
    try:
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as error:
        raise ValueError(f'cannot parse {path.name}: {error}') from error
    docstrings = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                  and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    names, strings = set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split('.')[0])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            strings.append(node.value)
            if re.fullmatch(r'[A-Za-z_]\w*', node.value):
                names.add(node.value)  # importlib.import_module('farm_tiktok_photo_runs'), lane tables of module names
    out = _named_files('\n'.join(strings), folders)
    for name in names:
        for folder in folders:
            if (folder / f'{name}.py').is_file():
                out.add((folder / f'{name}.py').resolve())
    return out


def farm_files(repo):
    """{package name: source path} for the farm, plus the private files the code names (for the report)."""
    repo = Path(repo).resolve()
    tools, rack = repo / 'tools', repo / RACK_DIR
    folders = (tools, rack)
    pending = [repo / e for e in ENTRIES if (repo / e).is_file()]
    for pattern in RACK_SCRIPT_GLOBS:
        pending += sorted(p for p in rack.glob(pattern) if p.name not in DEV_ONLY)
    missing = [e for e in ENTRIES if not (repo / e).is_file()]
    if missing:
        raise ValueError('farm entry points missing: ' + ', '.join(missing))
    seen, private_refs, files = set(), set(), {}
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        seen.add(path)
        name = 'farm/' + path.relative_to(repo).as_posix()
        if is_test(name[5:]):
            continue
        if is_private(name):
            private_refs.add(name[5:])
            continue
        files[name] = path
        pending += sorted(references(path, folders) - seen)
    return dict(sorted(files.items())), sorted(private_refs)


def server_hash_names(server_source):
    """The file names the farm server hashes into its sourceHash (Start-Window.ps1 compares it)."""
    match = re.search(r'for name in \(((?:\s*"[^"]+",?)+)\s*\)\)\)\.hexdigest', server_source)
    return re.findall(r'"([^"]+)"', match.group(1)) if match else []


# ---------------------------------------------------------------- lint

def lint_text(name, text):
    """Per-line findings. Comment and docstring lines are marked 'comment' (never block). A line marked
    '# release-lint: dev-fallback' is today's dev-checkout path, used only while IMOUSE_FARM_DATA is unset
    (Farm.ps1 always sets it); '# release-lint: code' names code, not state. Both are reported as info."""
    findings = []
    docs = _docstring_lines(text) if name.endswith('.py') else set()
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        marker = re.search(r'release-lint: (dev-fallback|code)\b', line)
        for level, rule, pattern in LINT_RULES:
            if pattern.search(line):
                findings.append({'file': name, 'line': number, 'level': 'info' if marker else level,
                                 'rule': rule + (f' ({marker.group(1)})' if marker else ''),
                                 'comment': number in docs or stripped.startswith(('#', '"""', "'''"))})
    return findings


def _docstring_lines(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def lint(files):
    """Findings for {package name: source path}. Comment-only lines are kept but marked."""
    out = []
    for name, path in files.items():
        if Path(path).suffix.lower() in ('.py', '.ps1', '.cmd', '.bat'):
            out += lint_text(name, Path(path).read_text(encoding='utf-8-sig', errors='replace'))
    return out


def blockers(findings):
    return [f for f in findings if f['level'] == 'blocker' and not f['comment']]


def command_readiness(commands, findings, files):
    """A launcher command is ready when its entry and the files it pulls in have no blocker."""
    blocked_files = {f['file'] for f in blockers(findings)}
    out = {}
    for command, spec in commands.items():
        closure = _closure_of(spec['entry'], files)
        hits = sorted(blocked_files & closure) + MANUAL_BLOCKERS.get(command, [])
        out[command] = {'ready': not hits, 'blocked_by': hits}
    return out


def _closure_of(entry, files):
    by_path = {Path(p).resolve(): n for n, p in files.items()}
    farm = [(n, Path(p).resolve()) for n, p in files.items() if n.startswith('farm/')]
    if not farm:
        return {entry}
    name, path = farm[0]
    repo = path.parents[len(PurePosixPath(name).parts) - 2]  # the source checkout the farm files came from
    folders = (repo / 'tools', repo / RACK_DIR)
    pending, seen = [entry], set()
    while pending:
        name = pending.pop()
        if name in seen or name not in files:
            continue
        seen.add(name)
        pending += [by_path[r] for r in references(files[name], folders) if r in by_path]
    return seen


# Blockers the text lint cannot see (compiled code), as {command: [reason]}. Cleared by hand once the
# source changes. Console cleared 5 Nov: src/iMouse.Console/InstallLayout.cs (run files in <data>\console,
# the farm server from IMOUSE_FARM_HOME; its self-tests cover both layouts).
MANUAL_BLOCKERS = {}


# Launcher commands (install/Farm.ps1). 'kind' says how Farm.ps1 runs the entry.
COMMANDS = {
    'server': {'entry': 'farm/tools/imouse_farm_server.py', 'kind': 'python'},
    'server-self-check': {'entry': 'farm/tools/imouse_farm_server.py', 'kind': 'python', 'args': ['--self-check'], 'offline': True},
    'schedule': {'entry': 'farm/tools/farm_schedule_cli.py', 'kind': 'python'},
    'start-rack': {'entry': f'farm/{RACK_DIR}/Start-Multiphone.ps1', 'kind': 'powershell'},
    'stop-rack': {'entry': f'farm/{RACK_DIR}/Stop-Multiphone.ps1', 'kind': 'powershell'},
    'release-receiver': {'entry': f'farm/{RACK_DIR}/Release-Receiver.ps1', 'kind': 'powershell'},
    'restart-receiver': {'entry': f'farm/{RACK_DIR}/Restart-Receiver.ps1', 'kind': 'powershell'},
    'start-window': {'entry': f'farm/{RACK_DIR}/Start-Window.ps1', 'kind': 'powershell'},
    'stop-window': {'entry': f'farm/{RACK_DIR}/Stop-Window.ps1', 'kind': 'powershell'},
    'prepare-window': {'entry': f'farm/{RACK_DIR}/prepare_window.py', 'kind': 'python'},
    'run-window': {'entry': f'farm/{RACK_DIR}/run_window.py', 'kind': 'python'},
    'verify-window': {'entry': f'farm/{RACK_DIR}/verify_window.py', 'kind': 'python'},
    'console': {'entry': 'console/iMouse2.exe', 'kind': 'exe'},
}


# ---------------------------------------------------------------- build

def _framework_check(component, config_path):
    config = load_json(config_path)
    opts = config.get('runtimeOptions', {})
    frameworks = opts.get('frameworks', []) + ([opts['framework']] if 'framework' in opts else [])
    names = {f.get('name') for f in frameworks if str(f.get('version', '')).startswith('8.')}
    if not FRAMEWORKS[component] <= names:
        raise ValueError(f'{component}: runtimeconfig does not ask for .NET 8 {sorted(FRAMEWORKS[component])}')
    return sorted(f"{f['name']} {f['version']}" for f in frameworks)


def _requirements(path):
    pins = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)', line)
        if not m:
            raise ValueError(f'requirement not pinned with ==: {line}')
        pins[m.group(1)] = m.group(2)
    return pins


def scan_private_content(path, tokens=()):
    if Path(path).suffix.lower() not in TEXT_SUFFIXES:
        return []
    blob = Path(path).read_bytes()
    hits = [kind for kind, pattern in PRIVATE_CONTENT if pattern.search(blob)]
    low = blob.decode('utf-8', errors='replace').casefold()
    hits += ['withheld value' for t in tokens if t.casefold() in low][:1]
    return hits


def privacy_tokens(archive=None):
    """Withheld serial-shaped tokens from the evidence archive, when this PC has it. Values never printed."""
    if archive is None:
        try:
            sys.path.insert(0, str(REPO / 'tools'))
            from farm_paths import ARCHIVE as archive  # noqa: N811
        except Exception:
            return None
    path = Path(archive) / 'privacy' / 'withheld-candidates.txt'
    handles = Path(archive) / 'privacy' / 'extra-handles.txt'
    if not path.is_file() or not handles.is_file():
        return None

    def lines(p):
        return [t.strip() for t in p.read_text(encoding='utf-8').splitlines() if t.strip() and not t.strip().startswith('#')]
    return ([t for t in lines(path) if len(t) >= 12 and not t.isalpha()] +
            [h.lstrip('@') for h in lines(handles) if len(h.lstrip('@')) >= 4])


def account_labels(archive=None):
    """Account labels kept in per-machine private data (<archive>/privacy/farm-accounts.json). Values never printed."""
    if archive is None:
        try:
            sys.path.insert(0, str(REPO / 'tools'))
            from farm_paths import ARCHIVE as archive  # noqa: N811
        except Exception:
            return []
    path = Path(archive) / 'privacy' / 'farm-accounts.json'
    try:
        values = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [v for k, v in values.items() if k != 'note' and isinstance(v, str) and len(v) >= 4]


def git_identity(repo):
    try:
        head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        dirty = bool(subprocess.run(['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=no'],
                                    capture_output=True, text=True, timeout=20, check=True).stdout.strip())
        return {'head': head, 'tracked_changes': dirty}
    except (OSError, subprocess.SubprocessError):
        return {'head': None, 'tracked_changes': None}


def plan(repo, kernel, console, receiver_exe, receiver_runtime):
    """Every file the package will hold, as {package name: source path}, before anything is written."""
    repo = Path(repo).resolve()
    copies = {}
    for component, folder, names in (('kernel', kernel, KERNEL_FILES), ('console', console, CONSOLE_FILES)):
        folder = Path(folder)
        for n in names:
            if not (folder / n).is_file():
                raise ValueError(f'{component}: missing {n} in {folder}')
            copies[f'{component}/{n}'] = folder / n
    receiver_exe, receiver_runtime = Path(receiver_exe), Path(receiver_runtime)
    if receiver_exe.name.lower() != 'uxplay.exe' or not receiver_exe.is_file():
        raise ValueError('receiver: --receiver-exe must be an existing uxplay.exe')
    copies['receiver/uxplay.exe'] = receiver_exe
    for need in RECEIVER_RUNTIME_REQUIRED:
        if not (receiver_runtime / need).is_file():
            raise ValueError(f'receiver runtime: missing {need}')
    for path in sorted(receiver_runtime.rglob('*')):
        if path.is_file():
            copies['receiver/runtime/' + path.relative_to(receiver_runtime).as_posix()] = path
    farm, _ = farm_files(repo)
    copies.update(farm)
    here = Path(__file__).resolve().parent
    for name in ('farm_install.py', 'farm_release.py'):
        copies[f'install/{name}'] = here / name
    for name in ('Preflight-Farm.ps1', 'Farm.ps1'):
        copies[f'install/{name}'] = here / 'release' / name
    copies['Install-Farm.ps1'] = here / 'release' / 'Install-Farm.ps1'
    for name in copies:
        safe_name(name)
        if is_private(name) and not name.startswith('receiver/runtime/'):
            raise ValueError(f'private path refused: {name}')
    if len({n.casefold() for n in copies}) != len(copies):
        raise ValueError('case-colliding package paths')
    return copies


def build(repo, out, kernel, console, receiver_exe, receiver_runtime, version=None, make_zip=False, tokens=None, now=None, accounts=None):
    """accounts: account labels from private data; packaged files still naming one are listed in the
    manifest's 'account_labels_in' for review (not refused while a lane's file still names one)."""
    repo, out = Path(repo).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('output already exists; packages are never overwritten')
    for src in (repo, Path(kernel).resolve(), Path(console).resolve(), Path(receiver_runtime).resolve()):
        if out.is_relative_to(src) and src != repo:
            raise ValueError('output may not be inside an input folder')
    if out.is_relative_to(repo) and not out.is_relative_to(repo / 'output'):
        raise ValueError('inside the checkout, packages go under output/ only')
    copies = plan(repo, kernel, console, receiver_exe, receiver_runtime)
    rows = {name: row(src) for name, src in copies.items()}
    problems = []
    for name, src in copies.items():
        if name.startswith('receiver/runtime/'):
            continue  # third-party runtime: binaries and upstream data, scanned only for our private paths
        for hit in scan_private_content(src, tokens or ()):
            problems.append(f'{hit}: {name}')
    if problems:
        raise ValueError('private content refused: ' + '; '.join(problems))
    labels = [a.casefold() for a in (accounts or ())]
    account_hits = sorted(n for n, src in copies.items() if labels and not n.startswith('receiver/') and Path(src).suffix.lower() in TEXT_SUFFIXES
                          and any(a in Path(src).read_text(encoding='utf-8', errors='replace').casefold() for a in labels))
    frameworks = {c: _framework_check(c, copies[f'{c}/{n}']) for c, n in
                  (('kernel', 'iMouse2.Kernel.runtimeconfig.json'), ('console', 'iMouse2.runtimeconfig.json'))}
    pins = _requirements(copies['farm/tools/requirements-farm.txt'])
    server = copies['farm/tools/imouse_farm_server.py'].read_text(encoding='utf-8-sig')
    hashed = server_hash_names(server)
    absent = [n for n in hashed if f'farm/tools/{n}' not in copies]
    if not hashed or absent:
        raise ValueError('farm server source-hash files missing from the package: ' + (', '.join(absent) or 'list not found'))
    farm = {n: p for n, p in copies.items() if n.startswith('farm/')}
    _, private_refs = farm_files(repo)
    findings = lint(farm)
    identity = git_identity(repo)
    now = now or datetime.now(timezone.utc)
    version = version or now.strftime('%Y.%m.%d.%H%M') + (f"-{identity['head'][:7]}" if identity['head'] else '')
    if not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z._-]{0,63}', version):
        raise ValueError(f'invalid version: {version!r}')
    manifest = {
        'schema_version': SCHEMA, 'kind': KIND, 'version': version, 'data_schema': DATA_SCHEMA,
        'created_utc': now.isoformat(), 'source': identity,
        'components': {
            'kernel': {'entry': 'kernel/iMouse2.Kernel.exe', 'frameworks': frameworks['kernel'], 'sha256': rows['kernel/iMouse2.Kernel.dll']['sha256']},
            'console': {'entry': 'console/iMouse2.exe', 'frameworks': frameworks['console']},
            'receiver': {'entry': 'receiver/uxplay.exe', 'runtime': 'receiver/runtime',
                         'redistribution_cleared': False, 'note': 'GStreamer/MSYS2 runtime for this operator\'s own PCs; not cleared for redistribution.'},
            'farm': {'root': 'farm', 'python': '3.11', 'requirements': 'farm/tools/requirements-farm.txt', 'pins': pins,
                     'server_hash_files': len(hashed), 'external_tools': ['ffmpeg', 'ffprobe (libx264)']},
        },
        'commands': {c: dict(spec, **command_readiness({c: spec}, findings, farm)[c]) for c, spec in COMMANDS.items()},
        'prerequisites': ['Windows 10/11 x64', '.NET 8 runtime + .NET 8 Desktop runtime (x64)', 'Python 3.11 x64 with the pinned packages',
                          'ffmpeg and ffprobe on PATH (libx264)', 'Bonjour (mDNSResponder) service running', 'WCH HID boards (VID_720A) on the built-in HID driver',
                          'inbound firewall rule for the receiver ports (TCP and UDP 7100-7599)', 'vendor iMouseService stopped'],
        'data_layout': 'farm_install.py DATA_DIRS; private state stays in the per-machine data folder',
        'excluded': {'patterns': list(PRIVATE_PATTERNS), 'referenced_private_files': private_refs},
        'dev_path_findings': {'blockers': len(blockers(findings)), 'total': len(findings)},
        'account_labels_in': account_hits,
        'files': dict(sorted(rows.items())),
    }
    partial = out.with_name(out.name + '.partial')
    if partial.exists():
        raise ValueError(f'an earlier failed build left {partial}; inspect and remove it first')
    partial.mkdir(parents=True)
    import shutil
    for name, src in copies.items():
        target = partial.joinpath(*name.split('/'))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        if row(target) != rows[name]:
            raise ValueError(f'file changed while packaging: {name}')
    with (partial / 'release.json').open('x', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2)
    issues = verify(partial)
    if issues:
        raise ValueError('package failed its own verification: ' + '; '.join(issues))
    os.replace(partial, out)  # the complete package appears in one step
    if make_zip:
        archive = out.with_suffix('.zip')
        with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(out.rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(out).as_posix())
    return manifest


def inventory(root):
    root = Path(root)
    out, names = {}, set()
    for p in sorted(root.rglob('*')):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
            raise ValueError(f'linked path refused: {rel}')
        if not p.is_file() or rel == 'release.json':
            continue
        if rel.casefold() in names:
            raise ValueError(f'case-colliding path: {rel}')
        names.add(rel.casefold())
        out[rel] = row(p)
    return out


def verify(package, allow_unrecorded=False):
    """Issues with a package folder (empty list = intact). Raises on a malformed manifest.
    allow_unrecorded: an installed version may gain files its apps write beside themselves (the console's
    startup-state.json); every recorded file must still be byte-identical."""
    package = Path(package)
    manifest = load_json(package / 'release.json')
    if manifest.get('schema_version') != SCHEMA or manifest.get('kind') != KIND:
        raise ValueError('not a Marketing Farm release manifest')
    if not isinstance(manifest.get('version'), str) or not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z._-]{0,63}', manifest['version']):
        raise ValueError('invalid version in manifest')
    expected = manifest.get('files')
    if not isinstance(expected, dict) or not expected:
        raise ValueError('empty package inventory')
    for name in expected:
        safe_name(name)
    actual = inventory(package)
    issues = []
    for name, data in expected.items():
        if name not in actual:
            issues.append(f'missing: {name}')
        elif actual[name] != data:
            issues.append(f'changed: {name}')
    if not allow_unrecorded:
        issues += [f'unrecorded: {n}' for n in sorted(actual.keys() - expected.keys())]
    required = {f'kernel/{n}' for n in KERNEL_FILES} | {f'console/{n}' for n in CONSOLE_FILES} | {
        'receiver/uxplay.exe', 'farm/tools/imouse_farm_server.py', 'farm/tools/requirements-farm.txt',
        'install/farm_install.py', 'install/farm_release.py', 'install/Preflight-Farm.ps1', 'install/Farm.ps1', 'Install-Farm.ps1'}
    required |= {f'receiver/runtime/{n}' for n in RECEIVER_RUNTIME_REQUIRED}
    issues += [f'required file absent: {n}' for n in sorted(required - expected.keys())]
    issues += [f'private path in package: {n}' for n in expected if is_private(n) and not n.startswith('receiver/runtime/')]
    if manifest.get('components', {}).get('kernel', {}).get('sha256') != expected.get('kernel/iMouse2.Kernel.dll', {}).get('sha256'):
        issues.append('kernel identity does not match its DLL')
    return issues


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='mode', required=True)
    b = sub.add_parser('build')
    b.add_argument('--repo', type=Path, default=REPO)
    for key in ('out', 'kernel', 'console', 'receiver-exe', 'receiver-runtime'):
        b.add_argument('--' + key, type=Path, required=True)
    b.add_argument('--version')
    b.add_argument('--zip', action='store_true')
    b.add_argument('--no-privacy-lists', action='store_true', help='skip the evidence-archive withheld list (CI/synthetic)')
    v = sub.add_parser('verify')
    v.add_argument('--package', type=Path, required=True)
    li = sub.add_parser('lint')
    li.add_argument('--repo', type=Path, default=REPO)
    li.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.mode == 'verify':
            issues = verify(args.package)
            print(*issues, sep='\n') if issues else None
            print('Package FAILED verification' if issues else 'Package verified: every file matches release.json.')
            return 1 if issues else 0
        if args.mode == 'lint':
            files, private_refs = farm_files(args.repo)
            findings = lint(files)
            if args.json:
                json.dump({'findings': findings, 'referenced_private_files': private_refs,
                           'commands': command_readiness(COMMANDS, findings, files)}, sys.stdout, indent=1)
                print()
            else:
                for f in findings:
                    print(f"{f['level']:7} {f['file'][5:]}:{f['line']}  {f['rule']}{'  (comment)' if f['comment'] else ''}")
                print(f'{len(files)} farm files; {len(blockers(findings))} blocker line(s), {len(findings)} finding(s).')
            return 1 if blockers(findings) else 0
        tokens = None if args.no_privacy_lists else privacy_tokens()
        if tokens is None and not args.no_privacy_lists:
            print('Refused: the withheld-value list was not found; pass --no-privacy-lists only for synthetic builds.')
            return 2
        m = build(args.repo, args.out, args.kernel, args.console, args.receiver_exe, args.receiver_runtime, args.version, args.zip, tokens,
                  accounts=None if args.no_privacy_lists else account_labels())
        print(f"Built {m['version']}: {len(m['files'])} files; dev-path blockers {m['dev_path_findings']['blockers']}. Nothing was started.")
        if m['account_labels_in']:
            print('REVIEW: an account label from private data is still in: ' + ', '.join(m['account_labels_in']))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(f'Refused: {error}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

"""The complete Python farm suite (every tools/test_farm*.py module) in parallel shards. No socket or phone.

Each shard is `python -m unittest <modules>` in tools/, logged to python-shard-[<label>-]<name>.txt
with its exit code. The slow retained-frame protocol suites get their own shards.
"""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[1] / 'tools'
modules = sorted(p.stem for p in TOOLS.glob('test_farm*.py'))
SLOW = {'x': ['test_farm_x_creation'], 'tiktok': ['test_farm_tiktok_creation'], 'reel': ['test_farm_reel_creation'],
        'carousel': ['test_farm_creation', 'test_farm_draft_runs', 'test_farm_draft_runs_http']}
assigned = {m for group in SLOW.values() for m in group}
assert assigned <= set(modules), assigned - set(modules)
shards = dict(SLOW, rest=[m for m in modules if m not in assigned])
assert sorted(m for group in shards.values() for m in group) == modules
processes = {}
for name, group in shards.items():
    label = (sys.argv[1] + '-') if len(sys.argv) > 1 else ''
    path = HERE / f'python-shard-{label}{name}.txt'
    if path.exists(): raise SystemExit('Shard log exists; never overwrite a recorded run: ' + path.name)
    log = open(path, 'w', encoding='utf-8')
    processes[name] = (subprocess.Popen([sys.executable, '-m', 'unittest', *group], cwd=TOOLS, stdout=log, stderr=subprocess.STDOUT), log)
codes = {}
for name, (process, log) in processes.items():
    codes[name] = process.wait(); log.write(f'exit {codes[name]}\n'); log.close()
print(dict(modules=len(modules), shards={k: len(v) for k, v in shards.items()}, exitCodes=codes))
sys.exit(1 if any(codes.values()) else 0)

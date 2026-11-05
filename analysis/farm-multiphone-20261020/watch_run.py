"""Prints each new phone action of a window's latest run, then the driver's final line. Read-only.

  python watch_run.py --window reel-slot18 --driver-output <file>
"""
import argparse
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
import sys  # noqa: E402
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
import farm_paths  # noqa: E402
STATE = farm_paths.rack_state(HERE)  # windows/, identify/ ...: beside this script in a checkout, the data folder when installed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--window', required=True)
    parser.add_argument('--driver-output', required=True, type=Path)
    args = parser.parse_args()
    prep = json.loads((STATE / 'windows' / args.window / 'preparation.json').read_text(encoding='utf-8'))
    runs = Path(prep['backendData']) / prep['route']
    seen = 0
    while True:
        folders = sorted((p for p in runs.glob('*') if p.is_dir() and (p / 'record.json').exists()), key=lambda p: p.stat().st_mtime)
        if folders:
            try: record = json.loads((folders[-1] / 'record.json').read_text(encoding='utf-8'))
            except ValueError: record = {}
            actions = [c for c in record.get('commands', []) if c.get('purpose') != 'fresh_frame_challenge'
                       and not str(c.get('purpose', '')).startswith('park')]
            for index, command in enumerate(actions[seen:], start=seen + 1):
                print(f"{index:02d} {command.get('purpose')} {command.get('state')}", flush=True)
            seen = max(seen, len(actions))
        if args.driver_output.exists():
            final = [line for line in args.driver_output.read_text(encoding='utf-8', errors='replace').splitlines() if '"state"' in line]
            if final: print(final[-1], flush=True); return
        time.sleep(3)


if __name__ == '__main__':
    main()

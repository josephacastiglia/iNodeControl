"""Summarize the two recorded, read-only comparison windows."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'analysis' / 'candidate-validation-20260915'
summary = {}
for phase in ('baseline', 'candidate'):
    rows = [json.loads(s) for s in (root / f'{phase}-telemetry.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    good = [r for r in rows if 'error' not in r]
    first, last = good[0], good[-1]
    duration = last['elapsed_s'] - first['elapsed_s']
    result = {'start': first['at'], 'end': last['at'], 'duration_s': duration, 'samples': len(rows), 'errors': [r for r in rows if 'error' in r], 'receivers': {}, 'processes': {}}
    for initial in first['receivers']:
        samples = [next(r for r in row['receivers'] if r['name'] == initial['name']) for row in good]
        final = samples[-1]
        result['receivers'][initial['name']] = {
            'received_fps': (final['frames'] - initial['frames']) / duration,
            'frame_delta': final['frames'] - initial['frames'],
            'offline_samples': sum(not s['live'] for s in samples),
            'zero_progress_intervals': sum(b['frames'] == a['frames'] for a,b in zip(samples,samples[1:])),
            'restart_delta': final['receiver_restarts'] - initial['receiver_restarts'],
            'pids': sorted({s['receiver_pid'] for s in samples})}
    for initial in first['processes']:
        samples = [next(p for p in row['processes'] if p['id'] == initial['id']) for row in good]
        final = samples[-1]
        result['processes'][str(initial['id'])] = {
            'name': initial['name'],
            'cpu_machine_percent': 100 * (final['cpu_s'] - initial['cpu_s']) / duration / first['logical_cpus'],
            'not_responding_samples': sum(not p['responding'] for p in samples),
            **{field+'_mib': {'start': samples[0][field]/1048576, 'end': samples[-1][field]/1048576, 'min': min(p[field] for p in samples)/1048576, 'max': max(p[field] for p in samples)/1048576} for field in ('working_set','private_bytes')}}
    result['total_cpu_machine_percent'] = sum(p['cpu_machine_percent'] for p in result['processes'].values())
    summary[phase] = result
(root / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))

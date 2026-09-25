import json, statistics
from pathlib import Path

out=Path(__file__).resolve().parents[1]/'analysis'/'two-phone-live-test-20260914'
rows=[json.loads(s) for s in (out/'telemetry.jsonl').read_text(encoding='utf-8-sig').splitlines()]
good=[r for r in rows if 'error' not in r]
def percentile(v,p):
    v=sorted(v);return v[min(len(v)-1,round((len(v)-1)*p))]
def mb(n):return round(n/1048576,2)
result={'start':good[0]['at'],'end':good[-1]['at'],'duration_s':round(good[-1]['elapsed_s']-good[0]['elapsed_s'],2),'samples':len(rows),'telemetry_errors':[r for r in rows if 'error' in r],'receivers':{},'processes':{}}
for identity in [r['deviceid'] for r in good[0]['receivers']]:
    seq=[(r['elapsed_s'],next(x for x in r['receivers'] if x['deviceid']==identity)) for r in good]
    rates=[(b['frames']-a['frames'])/(tb-ta) for (ta,a),(tb,b) in zip(seq,seq[1:])]
    result['receivers'][seq[0][1]['name']]={'pid_start':seq[0][1]['receiver_pid'],'pid_end':seq[-1][1]['receiver_pid'],'restart_delta':seq[-1][1]['receiver_restarts']-seq[0][1]['receiver_restarts'],'offline_samples':sum(not r['live'] for _,r in seq),'no_frame_progress_intervals':sum(r<=0 for r in rates),'frames_received':seq[-1][1]['frames']-seq[0][1]['frames'],'average_received_fps':round((seq[-1][1]['frames']-seq[0][1]['frames'])/(seq[-1][0]-seq[0][0]),2),'interval_fps_min':round(min(rates),2),'interval_fps_p50':round(statistics.median(rates),2),'interval_fps_p95':round(percentile(rates,.95),2),'zero_progress_intervals':[{'from':good[i]['at'],'to':good[i+1]['at']} for i,r in enumerate(rates) if r<=0]}
for pid in [p['id'] for p in good[0]['processes']]:
    seq=[(r['elapsed_s'],p) for r in good for p in r['processes'] if p['id']==pid]
    a,b=seq[0][1],seq[-1][1];duration=seq[-1][0]-seq[0][0]
    rates=[100*(b['cpu_s']-a['cpu_s'])/(tb-ta)/good[0]['logical_cpus'] for (ta,a),(tb,b) in zip(seq,seq[1:])]
    result['processes'][str(pid)]={'name':a['name'],'samples_present':len(seq),'not_responding_samples':sum(not p['responding'] for _,p in seq),'working_set_start_mib':mb(a['working_set']),'working_set_end_mib':mb(b['working_set']),'working_set_peak_mib':mb(max(p['working_set'] for _,p in seq)),'private_start_mib':mb(a['private_bytes']),'private_end_mib':mb(b['private_bytes']),'private_peak_mib':mb(max(p['private_bytes'] for _,p in seq)),'cpu_machine_average_percent':round(100*(b['cpu_s']-a['cpu_s'])/duration/good[0]['logical_cpus'],2),'cpu_machine_interval_p95_percent':round(percentile(rates,.95),2)}
actions=[json.loads(s) for s in (out/'actions.jsonl').read_text().splitlines()]
result['api_actions']={}
for action in sorted({a['action'] for a in actions if a['action']}):
    selected=[a for a in actions if a['action']==action]
    result['api_actions'][action]={'count':len(selected),'response_ms_min':min(a['api_ms'] for a in selected),'response_ms_median':statistics.median(a['api_ms'] for a in selected),'response_ms_max':max(a['api_ms'] for a in selected),'nonzero_result_count':sum(a['response']['data']['code']!=0 for a in selected)}
(out/'summary.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))

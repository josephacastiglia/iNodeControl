from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'tools/farm_draft_verification.py'
s=p.read_text(encoding='utf-8')
s=s.replace('import numpy as np\nfrom PIL import Image\n','')
s=s.replace('from farm_observations import classify, expectations, image_size','from farm_observations import classify, expectations\nfrom farm_draft_media import media_comparison')
s=s.replace('maximum = 10 if', 'maximum = 11 if')
a=s.index('def media_comparison('); b=s.index('\ndef assess(',a)
s=s[:a]+s[b+1:]
s=s.replace('def assess(spec, draft, assets, captures):','def assess(spec, draft, assets, captures, timeline=None):')
s=s.replace("                titles = [line['text'].casefold() for line in value['text'].get('lines', []) if line.get('words')\n                          and .04 < min(w['y'] for w in line['words']) / value['text']['height'] < .12]\n                candidate = result['screen'] == 'unknown' and 'drafts' in titles and 'select' in titles", "                candidate = library_candidate(value['text'], result)")
a=s.index("    for role in ('prepared', 'reopened'):",s.index('def assess(')); b=s.index("    source = 'phone'",a)
s=s[:a]+'''    coverage = {}
    for role in ('prepared', 'reopened'):
        rows = details[role]
        editors = [r for r in rows if 'position' in r.get('media', {})]
        indices = [r['media'].get('matchedIndex') for r in editors]
        full = (indices == list(range(1, len(assets)+1)) and all(
            r['media']['position'] == dict(status='visible_position', index=n, count=len(assets))
            for n,r in enumerate(editors,1)))
        captions = [r['caption']['status'] for r in rows if r.get('caption', {}).get('status') != 'unsupported_layout']
        caption_ok = bool(captions) and all(c == 'exact_visible_lines' for c in captions)
        # Details previews must also match, even though only editor dots establish count/order.
        other_ok = all(r.get('media', {}).get('matchedIndex') is not None for r in rows)
        coverage[role] = dict(expectedCount=len(assets), observedIndices=indices,
                              fullSizeAndPositionMatch=full, captionMatches=caption_ok)
        if not full or not other_ok:
            blockers.append(role.title() + ' needs every full-size slide in order with its matching position and total count.')
        if not caption_ok: blockers.append(role.title() + ' full visible caption does not match exactly.')
    continuity = account_history(spec, timeline, expected)
    blockers.extend(continuity['blockers'])
''' +s[b:]
s=s.replace("blockers=list(dict.fromkeys(blockers)), stages=details, automaticInputAllowed=False,", "blockers=list(dict.fromkeys(blockers)), stages=details, slideCoverage=coverage, accountHistory=continuity, automaticInputAllowed=False,")
s=s.replace("'Similar pixels are not byte identity, and observation sequence does not prove carousel navigation order.',", "'Full-size pixels and page dots check visible slide order/count, not media byte identity.',")
s=s.replace("'Account observations bracket the run; actions between frames are not witnessed.',", "'All stored observations in the interval are checked; actions between captures are not witnessed.',")
s=s.replace("        if observation_id not in sum(record['request']['observations'].values(), []):", "        if observation_id not in sum(record['request']['observations'].values(), []) + record.get('intervalObservationIds', []):")
s=s.replace("            assessment = assess(spec, draft, assets, captures)", '''            timeline, timeline_error = None, None
            if spec['observations']['account_before'] and spec['observations']['account_after']:
                try:
                    timeline = self.observations.interval(spec['observations']['account_before'][0], spec['observations']['account_after'][0])
                except ValueError as error: timeline_error = str(error)
            for value, frame in timeline or []:
                if value['id'] not in captures:
                    size += len(frame or b'') + len(json.dumps(value, ensure_ascii=False).encode('utf-8'))
                    if size > MAX_EVIDENCE_BYTES: raise ValueError('Selected review evidence exceeds 32 MiB; no partial review stored.')
            assessment = assess(spec, draft, assets, captures, timeline)
            if timeline_error: assessment['blockers'].append(timeline_error)''')
s=s.replace("                    archive.writestr(observation_id + '.png', frame)", "                    archive.writestr(observation_id + '.png', frame)\n                for value, frame in timeline or []:\n                    if value['id'] in captures: continue\n                    archive.writestr(value['id'] + '.json', json.dumps(value, ensure_ascii=False))\n                    if frame is not None: archive.writestr(value['id'] + '.png', frame)")
s=s.replace("document = dict(id=spec['id'], createdAt=time.time(), request=spec,", "document = dict(id=spec['id'], createdAt=time.time(), request=spec, verificationVersion=2,\n                            intervalObservationIds=[v['id'] for v, _ in timeline or []],")
p.write_text(s,encoding='utf-8')

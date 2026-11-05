"""Local review queue and planned run slots within per-account daily budgets.

Prepared packages wait for the operator's approve or reject. Approved ones get a planned slot
(day, time) within each account's daily cap and spacing. Nothing here starts a run, opens a
window, touches a phone or the kernel, or posts. The slot runner (farm_schedule_runner.py) claims
a due slot here (planned -> running), runs it, and records its one outcome (finish): verified ->
done, stopped -> stopped (never retried by itself), phone not ready -> approved again, slot dropped
(a new slot needs another `plan --commit`). Slots used by a run keep counting toward daily caps.
Accounts are opaque labels ('acct-1'), never handles or device IDs.

Storage is one JSON file, replaced atomically under an OS lock, so the backend and the operator's
command line can both use it, and a restart only reads it back. A slot that passes unrun is never
run late: it lapses and the package goes back to approved for a fresh slot.
"""
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

PENDING, APPROVED, REJECTED, PLANNED = 'pending', 'approved', 'rejected', 'planned'
RUNNING, DONE, STOPPED = 'running', 'done', 'stopped'        # set only through claim/finish/abandon
VERIFIED, STOPPED_SAFELY, NOT_READY = 'verified', 'stopped', 'not_ready'   # slot run outcomes
USED = (PLANNED, RUNNING, DONE, STOPPED)   # states whose slot counts toward caps and spacing
MAX_DAILY = 10            # hard ceiling whatever the queue file says
GRACE_SECONDS = 600       # a planned slot older than this lapses; no late or catch-up runs
LEAD_SECONDS = 300        # a new slot is never sooner than this from now
LABEL = re.compile(r'^[a-z][a-z0-9-]{0,31}$')
PACKAGE_ID = re.compile(r'^[a-z0-9][a-z0-9._-]{0,63}$')
HEXISH = re.compile(r'^[0-9a-f-]{4,}$')
DEFAULT_SETTINGS = {'window': [9, 21], 'rackGapMinutes': 10, 'utcOffsetHours': None,
                    'defaultDailyCap': 1, 'defaultGapMinutes': 120, 'platformAccounts': {}}
SAFETY = {'startsRuns': False, 'phoneInput': False, 'publishing': False, 'messaging': False}


def check_label(value, what):
    if not isinstance(value, str) or not LABEL.match(value) or HEXISH.match(value):
        raise ValueError(f'{what} must be an opaque lowercase label like acct-1 (no handles or device IDs).')
    return value


def package_key(package_id):
    if type(package_id) is int and package_id > 0: return str(package_id)
    if isinstance(package_id, str) and PACKAGE_ID.match(package_id): return package_id
    raise ValueError('Package ID must be a positive integer or a short lowercase label.')


def fingerprint(item):
    """What the operator approves: the exact copy and files. Changed content is a new package."""
    keep = {k: item.get(k) for k in ('platform', 'format', 'caption', 'stagedFiles', 'manifestSha256')}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()


class _FileLock:
    """Exclusive OS lock on a side file; waits (up to ~10 s) for the other holder."""
    def __init__(self, path): self.path, self.file = path, None

    def __enter__(self):
        self.file = open(self.path, 'a+b')
        if self.file.tell() == 0: self.file.write(b'\0'); self.file.flush()
        self.file.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        self.file.close(); self.file = None


class ReviewQueue:
    def __init__(self, path, clock=time.time):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock; self.lock = _FileLock(self.path.with_suffix('.lock'))
        self.state = self._load()

    # --- storage ---
    def _load(self):
        state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        state.setdefault('settings', {}); state.setdefault('accounts', {}); state.setdefault('packages', {})
        for key, value in DEFAULT_SETTINGS.items(): state['settings'].setdefault(key, value)
        for account, caps in state.pop('budgets', {}).items():      # first-commit format
            state['accounts'].setdefault(account, {}).setdefault('platformCaps', {}).update(caps)
        return state

    def _save(self):
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(self.state, handle, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True); raise

    @contextmanager
    def _change(self):
        """Re-read under the lock, change, write back: another writer's work is never lost."""
        with self.lock:
            self.state = self._load(); yield self.state; self._save()

    def reload(self):
        with self.lock: self.state = self._load()
        return self

    # --- settings and per-account budgets ---
    def settings(self): return dict(self.state['settings'])

    def set_settings(self, window=None, rack_gap_minutes=None, utc_offset_hours=None, platform_accounts=None,
                     default_daily_cap=None, default_gap_minutes=None):
        if window is not None and (len(window) != 2 or any(type(h) is not int for h in window) or not 0 <= window[0] < window[1] <= 24):
            raise ValueError('Run window is two whole hours, start < end, within 0-24.')
        if rack_gap_minutes is not None and (type(rack_gap_minutes) is not int or not 0 <= rack_gap_minutes <= 720):
            raise ValueError('Rack gap is 0-720 minutes.')
        if utc_offset_hours is not None and (not isinstance(utc_offset_hours, (int, float)) or isinstance(utc_offset_hours, bool) or not -12 <= utc_offset_hours <= 14):
            raise ValueError('UTC offset is -12 to 14 hours.')
        if default_daily_cap is not None: self._check_cap(default_daily_cap)
        if default_gap_minutes is not None: self._check_gap(default_gap_minutes)
        for platform, account in (platform_accounts or {}).items():
            check_label(platform, 'Platform'); check_label(account, 'Account')
        with self._change() as state:
            s = state['settings']
            if window is not None: s['window'] = list(window)
            if rack_gap_minutes is not None: s['rackGapMinutes'] = rack_gap_minutes
            if utc_offset_hours is not None: s['utcOffsetHours'] = utc_offset_hours
            if default_daily_cap is not None: s['defaultDailyCap'] = default_daily_cap
            if default_gap_minutes is not None: s['defaultGapMinutes'] = default_gap_minutes
            if platform_accounts: s['platformAccounts'].update(platform_accounts)
        return self.settings()

    @staticmethod
    def _check_cap(value):
        if type(value) is not int or not 0 <= value <= MAX_DAILY:
            raise ValueError(f'Daily cap must be a whole number 0-{MAX_DAILY}.')

    @staticmethod
    def _check_gap(value):
        if type(value) is not int or not 1 <= value <= 1440:
            raise ValueError('Spacing is 1-1440 minutes.')

    def set_account(self, account, daily_cap=None, gap_minutes=None, platform_caps=None, first_day=None, ramp=None):
        """Per-account budget. ramp[i] caps the account's day i counted from first_day (warmup)."""
        check_label(account, 'Account')
        if daily_cap is not None: self._check_cap(daily_cap)
        if gap_minutes is not None: self._check_gap(gap_minutes)
        for platform, cap in (platform_caps or {}).items(): check_label(platform, 'Platform'); self._check_cap(cap)
        if first_day is not None: dt.date.fromisoformat(first_day)
        if ramp is not None:
            if not isinstance(ramp, list) or len(ramp) > 60: raise ValueError('Ramp is a list of at most 60 daily caps.')
            for cap in ramp: self._check_cap(cap)
        with self._change() as state:
            if ramp is not None and first_day is None and 'firstDay' not in state['accounts'].get(account, {}):
                raise ValueError('A ramp needs the first day it counts from.')
            a = state['accounts'].setdefault(account, {})
            if daily_cap is not None: a['dailyCap'] = daily_cap
            if gap_minutes is not None: a['gapMinutes'] = gap_minutes
            if platform_caps: a.setdefault('platformCaps', {}).update(platform_caps)
            if first_day is not None: a['firstDay'] = first_day
            if ramp is not None: a['ramp'] = list(ramp)
        return self.account(account)

    def set_budget(self, account, platform, per_day):
        """Cap one platform for one account (also limited by the account's daily cap)."""
        return self.set_account(account, platform_caps={check_label(platform, 'Platform'): per_day})

    def account(self, account):
        a, s = self.state['accounts'].get(account, {}), self.state['settings']
        return {'dailyCap': a.get('dailyCap', s['defaultDailyCap']), 'gapMinutes': a.get('gapMinutes', s['defaultGapMinutes']),
                'platformCaps': dict(a.get('platformCaps', {})), 'firstDay': a.get('firstDay'), 'ramp': a.get('ramp')}

    def cap_on(self, account, day, platform=None):
        a = self.account(account); cap = a['dailyCap']
        if a['firstDay']:
            index = (day - dt.date.fromisoformat(a['firstDay'])).days
            if index < 0: return 0
            if a['ramp'] and index < len(a['ramp']): cap = min(cap, a['ramp'][index])
        if platform is not None and platform in a['platformCaps']: cap = min(cap, a['platformCaps'][platform])
        return cap

    # --- review ---
    def submit(self, package_id, platform, format, account=None, caption='', source=None):
        """A prepared package enters as pending. Same ID and same content is a no-op;
        same ID with different content is refused, so an approval never carries to new content."""
        key = package_key(package_id); check_label(platform, 'Platform')
        if account is None: account = self.state['settings']['platformAccounts'].get(platform)
        if account is not None: check_label(account, 'Account')
        if not isinstance(format, str) or not format: raise ValueError('Package needs a format.')
        source = dict(source or {})
        print_ = fingerprint({'platform': platform, 'format': format, 'caption': str(caption), **source})
        with self._change() as state:
            existing = state['packages'].get(key)
            if existing:
                if existing['fingerprint'] != print_:
                    raise ValueError(f'Package {key} is already queued with different content; it was not replaced.')
                return existing
            state['packages'][key] = {'id': package_id, 'platform': platform, 'format': format, 'account': account,
                                      'caption': str(caption), 'source': source, 'fingerprint': print_,
                                      'state': PENDING, 'submittedAt': self.clock()}
            return state['packages'][key]

    def intake(self, prepared):
        """Queue the content items of succeeded local preparation runs (see
        farm_preparation_schedule.read_prepared_packages). Returns added, known and refused IDs."""
        report = {'added': [], 'known': [], 'refused': []}
        for item in prepared:
            source = {k: item[k] for k in ('runId', 'stagedFiles', 'manifest', 'manifestSha256', 'generation', 'localDraft') if k in item}
            try:
                before = package_key(item['id']) in self.reload().state['packages']
                self.submit(item['id'], item['platform'], item['format'], item.get('account'), item.get('caption', ''), source)
                report['known' if before else 'added'].append(item['id'])
            except (KeyError, ValueError) as exc:
                report['refused'].append({'id': item.get('id'), 'reason': str(exc)})
        return report

    def approve(self, package_id, account=None):
        key = package_key(package_id)
        if account is not None: check_label(account, 'Account')
        with self._change() as state:
            pkg = self._get(state, key)
            if pkg['state'] == REJECTED: raise ValueError('Rejected package; submit a new package instead.')
            if account is not None and account != pkg['account']:
                if pkg['state'] != PENDING: raise ValueError('Account can only be set while the package is pending.')
                pkg['account'] = account
            if pkg['account'] is None: raise ValueError(f'Package {key} has no account; approve it with an account label.')
            if pkg['state'] == PENDING: pkg.update(state=APPROVED, decidedAt=self.clock())
            return pkg

    def reject(self, package_id, reason=''):
        """Rejecting a pending, approved or planned package cancels any planned slot."""
        key = package_key(package_id)
        with self._change() as state:
            pkg = self._get(state, key)
            if pkg['state'] == RUNNING: raise ValueError(f'Package {key} is running on a phone; let the run end first.')
            if pkg['state'] in (DONE, STOPPED): raise ValueError(f'Package {key} already ran ({pkg["state"]}); its record stays.')
            if pkg['state'] != REJECTED:
                pkg.pop('slot', None); pkg.update(state=REJECTED, decidedAt=self.clock(), reason=str(reason))
            return pkg

    def unplan(self, package_id):
        """Take a planned package off its slot (back to approved) without rejecting it."""
        with self._change() as state:
            pkg = self._get(state, package_key(package_id))
            if pkg['state'] == PLANNED: pkg['state'] = APPROVED; pkg.pop('slot')
            return pkg

    @staticmethod
    def _get(state, key):
        try: return state['packages'][key]
        except KeyError: raise ValueError(f'No package {key} in the queue.') from None

    def pending(self): return [p for p in self._ordered() if p['state'] == PENDING]

    def _ordered(self, state=None):
        return sorted((state or self.state)['packages'].values(), key=lambda p: (p['submittedAt'], str(p['id'])))

    # --- time ---
    def _tz(self):
        offset = self.state['settings']['utcOffsetHours']
        return None if offset is None else dt.timezone(dt.timedelta(hours=offset))

    def _local(self, ts):
        tz = self._tz()
        return dt.datetime.fromtimestamp(ts, tz) if tz else dt.datetime.fromtimestamp(ts).astimezone()

    def _day(self, ts): return self._local(ts).date()

    def _at(self, day, hour):
        naive = dt.datetime.combine(day, dt.time()) + dt.timedelta(hours=hour)
        tz = self._tz()
        return (naive.replace(tzinfo=tz) if tz else naive).timestamp()

    def bind_window(self, package_id, window, slot, package_sha256):
        """An approved real package gets the prepared window that holds its exact files and caption
        (farm_schedule_content.py). What was approved does not change: its fingerprint stays. Refused
        once a slot is planned or a run happened, and for a package already bound."""
        key = package_key(package_id)
        with self._change() as state:
            pkg = self._get(state, key)
            if pkg['state'] != APPROVED: raise ValueError(f'Package {key} is {pkg["state"]}; approve it first, and bind before planning.')
            if pkg['source'].get('kind') == 'window': raise ValueError(f'Package {key} already has a window.')
            pkg['source'].update(kind='window', window=window, slot=slot, windowPackageSha256=package_sha256, testPackage=False)
            return pkg

    # --- slot runs (the runner's side; the queue itself never touches a phone) ---
    def due(self, phone):
        """Planned slots for this phone that may start now: at or after their time, within the grace."""
        now = self.clock(); self.reload()
        return sorted((p for p in self.state['packages'].values() if p['state'] == PLANNED
                       and p.get('source', {}).get('slot') == phone and 0 <= now - p['slot'] <= GRACE_SECONDS),
                      key=lambda p: p['slot'])

    def next_slot(self, phone):
        self.reload()
        slots = [p['slot'] for p in self.state['packages'].values()
                 if p['state'] == PLANNED and p.get('source', {}).get('slot') == phone]
        return min(slots) if slots else None

    def in_progress(self, phone=None):
        self.reload()
        return [p for p in self._ordered() if p['state'] == RUNNING and (phone is None or p['run']['phone'] == phone)]

    def claim(self, package_id, phone):
        """planned -> running, once. Refused when early, past the grace (it lapses instead) or while this
        phone has a run without a recorded end: one slot at a time per phone."""
        key = package_key(package_id); now = self.clock()
        with self._change() as state:
            self._lapse(state, now)
            pkg = self._get(state, key)
            if pkg['state'] != PLANNED:
                raise ValueError(f'Package {key} is {pkg["state"]}, not planned (a passed slot lapses; never run late).')
            if pkg.get('source', {}).get('slot') != phone: raise ValueError(f'Package {key} is not for phone {phone}.')
            if now < pkg['slot']: raise ValueError(f'Package {key} is not due yet.')
            busy = [p['id'] for p in state['packages'].values() if p['state'] == RUNNING and p['run']['phone'] == phone]
            if busy:
                raise ValueError(f'Phone {phone} has a run without a recorded end (package {busy[0]}); review it, then `abandon` it.')
            pkg.update(state=RUNNING, run={'phone': phone, 'slot': pkg['slot'], 'startedAt': now})
            return pkg

    def finish(self, package_id, outcome, reason='', **details):
        """Record a running package's one outcome. verified -> done; stopped -> stopped (the operator
        decides what next; nothing retries it); not_ready (no phone input sent) -> approved, slot dropped."""
        if outcome not in (VERIFIED, STOPPED_SAFELY, NOT_READY): raise ValueError(f'Unknown outcome {outcome!r}.')
        key = package_key(package_id)
        with self._change() as state:
            pkg = self._get(state, key)
            if pkg['state'] != RUNNING: raise ValueError(f'Package {key} is not running.')
            record = {**pkg.pop('run'), 'outcome': outcome, 'reason': str(reason), 'finishedAt': self.clock(), **details}
            pkg.setdefault('runs', []).append(record)
            if outcome == VERIFIED: pkg['state'] = DONE
            elif outcome == STOPPED_SAFELY: pkg['state'] = STOPPED
            else: pkg['state'] = APPROVED; pkg.setdefault('notReadySlots', []).append(pkg.pop('slot'))
            return pkg

    def abandon(self, package_id, reason):
        """Operator only: a run whose end was never recorded (the runner died) becomes stopped, after review."""
        if not str(reason).strip(): raise ValueError('Say what the review found.')
        key = package_key(package_id)
        with self._change() as state:
            pkg = self._get(state, key)
            if pkg['state'] != RUNNING: raise ValueError(f'Package {key} is not running.')
            pkg.setdefault('runs', []).append({**pkg.pop('run'), 'outcome': STOPPED_SAFELY, 'finishedAt': self.clock(),
                                               'reason': 'run end not recorded; operator reviewed: ' + str(reason)})
            pkg['state'] = STOPPED
            return pkg

    # --- planning ---
    def _lapse(self, state, now):
        changed = []
        for pkg in self._ordered(state):
            if pkg['state'] == PLANNED and now - pkg['slot'] > GRACE_SECONDS:
                pkg['state'] = APPROVED; pkg.setdefault('lapsedSlots', []).append(pkg.pop('slot')); changed.append(pkg['id'])
        return changed

    def lapse_stale(self):
        """Planned slots past their grace go back to approved: no late run, no catch-up burst."""
        with self._change() as state: return self._lapse(state, self.clock())

    def _propose(self, state, now, horizon_days):
        """Slots for approved packages, keeping every existing planned slot. Pure: no writes."""
        taken = [(p['slot'], p['account'], p['platform']) for p in state['packages'].values() if p['state'] in USED and 'slot' in p]
        rack_gap = state['settings']['rackGapMinutes'] * 60
        start_h, end_h = state['settings']['window']
        first = self._day(now); proposed, unplaced = [], []
        for pkg in self._ordered(state):
            if pkg['state'] != APPROVED: continue
            account, platform = pkg['account'], pkg['platform']
            if pkg['source'].get('stagedFiles') and pkg['source'].get('kind') != 'window':
                # Real content runs only from its window; a slot without one would lapse and spend the day's cap.
                unplaced.append({'id': pkg['id'], 'account': account, 'platform': platform, 'reason': 'no window yet: run `convert` first'})
                continue
            gap = self.account(account)['gapMinutes'] * 60; slot, why = None, 'no free time in the window'
            for offset in range(horizon_days):
                day = first + dt.timedelta(days=offset)
                mine = [s for s, a, p in taken if a == account and self._day(s) == day]
                if len(mine) >= self.cap_on(account, day):
                    why = 'account daily cap'; continue
                if sum(1 for s, a, p in taken if a == account and p == platform and self._day(s) == day) >= self.cap_on(account, day, platform):
                    why = f'{platform} daily cap'; continue
                slot = self._free(day, start_h, end_h, now, [(s, gap if a == account else rack_gap) for s, a, p in taken])
                if slot is not None: break
                why = 'no free time in the window'
            if slot is None:
                unplaced.append({'id': pkg['id'], 'account': account, 'platform': platform,
                                 'reason': f'{why} through {(first + dt.timedelta(days=horizon_days - 1)).isoformat()}'})
                continue
            taken.append((slot, account, platform)); proposed.append({'id': pkg['id'], 'slot': slot})
        return proposed, unplaced

    def _free(self, day, start_h, end_h, now, others):
        """Earliest time in the day's window, LEAD from now, each other slot at least its gap away."""
        t, end = max(self._at(day, start_h), now + LEAD_SECONDS), self._at(day, end_h)
        while t < end:
            clash = [s + g for s, g in others if g and abs(s - t) < g]
            if not clash: return t
            t = max(clash)
        return None

    def plan(self, horizon_days=7, commit=False):
        """Dry run by default: what would be planned. commit=True records the new slots."""
        if type(horizon_days) is not int or not 1 <= horizon_days <= 30: raise ValueError('Horizon is 1-30 days.')
        now = self.clock()
        if not commit:
            self.reload(); state = json.loads(json.dumps(self.state)); lapsing = self._lapse(state, now)
            proposed, unplaced = self._propose(state, now, horizon_days)
            return {'dryRun': True, 'lapsing': lapsing, 'proposed': proposed, 'unplaced': unplaced, **SAFETY}
        with self._change() as state:
            lapsing = self._lapse(state, now); proposed, unplaced = self._propose(state, now, horizon_days)
            for item in proposed:
                state['packages'][package_key(item['id'])].update(state=PLANNED, slot=item['slot'], plannedAt=now)
        return {'dryRun': False, 'lapsing': lapsing, 'proposed': proposed, 'unplaced': unplaced, **SAFETY}

    def schedule(self):
        """Read-only view: planned slots in time order, then the waiting lists."""
        self.reload()
        slots = sorted((p for p in self.state['packages'].values() if p['state'] == PLANNED), key=lambda p: p['slot'])
        by_state = lambda s: [p['id'] for p in self._ordered() if p['state'] == s]
        return {'slots': [{'id': p['id'], 'platform': p['platform'], 'format': p['format'], 'account': p['account'],
                           'at': p['slot'], 'day': self._day(p['slot']).isoformat()} for p in slots],
                'pending': by_state(PENDING), 'approved': by_state(APPROVED), 'rejected': by_state(REJECTED),
                'running': by_state(RUNNING), 'done': by_state(DONE), 'stopped': by_state(STOPPED),
                'runs': self.history(), **SAFETY}

    def history(self):
        """Every recorded slot run, oldest first."""
        return sorted(({'id': p['id'], **r} for p in self.state['packages'].values() for r in p.get('runs', [])),
                      key=lambda r: r['startedAt'])

    def render(self, horizon_days=7):
        """The operator's plain-text plan: committed slots plus what a commit would add."""
        dry = self.plan(horizon_days); now = self.clock()
        packages = self.state['packages']; s = self.state['settings']
        new = {package_key(i['id']): i['slot'] for i in dry['proposed']}
        lapsing = {package_key(i) for i in dry['lapsing']}
        rows = [(p['slot'], p, '') for p in packages.values() if p['state'] == PLANNED and package_key(p['id']) not in lapsing]
        rows += [(slot, packages[key], 'NEW') for key, slot in new.items()]
        stamp = lambda ts: self._local(ts).strftime('%a %Y-%m-%d %H:%M')
        short = lambda text: (text[:48] + '...') if len(text) > 51 else text
        out = [f'Run plan, {stamp(now)} (UTC{self._local(now).strftime("%z")}). DRY RUN: nothing runs on a phone, nothing posts.',
               f'Window {s["window"][0]:02d}:00-{s["window"][1]:02d}:00, at least {s["rackGapMinutes"]} min between any two runs.']
        accounts = sorted({p['account'] for p in packages.values() if p['account']} | set(self.state['accounts']))
        for account in accounts:
            a = self.account(account); caps = ', '.join(f'{k} {v}/day' for k, v in sorted(a['platformCaps'].items()))
            today = self.cap_on(account, self._day(now))
            warm = f', warmup from {a["firstDay"]} (today {today}/day)' if a['firstDay'] else ''
            out.append(f'  {account}: {a["dailyCap"]}/day, {a["gapMinutes"]} min apart' + (f' ({caps})' if caps else '') + warm)
        out.append('')
        out.append(f'Planned ({len(rows)}; NEW = added by `plan --commit`):' if rows else 'Planned: none.')
        for slot, p, mark in sorted(rows, key=lambda r: r[0]):
            out.append(f'  {stamp(slot)}  {p["account"]:<10} {p["platform"] + "/" + p["format"]:<22} pkg {p["id"]:<6} {mark:<3} "{short(p["caption"])}"')
        waiting = [p for p in self._ordered() if p['state'] == PENDING]
        out.append(''); out.append(f'Waiting for review ({len(waiting)}):' if waiting else 'Waiting for review: none.')
        for p in waiting:
            files = len(p['source'].get('stagedFiles', []))
            out.append(f'  pkg {p["id"]:<6} {p["platform"]}/{p["format"]}  account {p["account"] or "(set at approve)"}  {files} file(s)  "{short(p["caption"])}"')
        if dry['unplaced']:
            out.append(''); out.append('Approved, no slot yet:')
            out += [f'  pkg {u["id"]:<6} {u["account"]} {u["platform"]}: {u["reason"]}' for u in dry['unplaced']]
        if lapsing:
            out.append(''); out.append('Lapsed (slot passed unrun; replanned, never run late): ' + ', '.join(sorted(lapsing)))
        running = [p for p in self._ordered() if p['state'] == RUNNING]
        if running:
            out.append(''); out.append('Running now (one per phone):')
            out += [f'  pkg {p["id"]:<6} phone {p["run"]["phone"]} since {stamp(p["run"]["startedAt"])}' for p in running]
        runs = self.history()
        if runs:
            out.append(''); out.append(f'Slot runs ({len(runs)}):')
            out += [f'  {stamp(r["slot"])}  pkg {r["id"]:<6} phone {r["phone"]}  {r["outcome"]:<9} {short(r["reason"])}' for r in runs]
        rejected = [p for p in self._ordered() if p['state'] == REJECTED]
        if rejected: out.append(''); out.append('Rejected: ' + ', '.join(str(p['id']) for p in rejected))
        return '\n'.join(out) + '\n'

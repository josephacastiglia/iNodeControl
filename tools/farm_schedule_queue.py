"""Local review queue and planned run slots with daily budgets. Planning only.

Prepared packages wait for the operator's approve or reject. Approved ones get a planned slot
(day, time) within per-account, per-platform daily budgets. Nothing here starts a run, opens a
window, touches a phone or the kernel, or posts: a slot is a record the operator's tooling may
later read. Accounts are opaque labels ('acct-1'), never handles or device IDs.
"""
import datetime as dt
import json
import os
from pathlib import Path
import re
import tempfile
import time

PENDING, APPROVED, REJECTED, PLANNED, LAPSED = 'pending', 'approved', 'rejected', 'planned', 'lapsed'
MAX_DAILY = 10          # hard ceiling whatever the budget file says
DEFAULT_DAILY = 1
GRACE_SECONDS = 600     # a slot older than this is lapsed, never run late or in a burst
LABEL = re.compile(r'^[a-z][a-z0-9-]{0,31}$')
BOARD_ID = re.compile(r'^[0-9a-f]{4}$')
PACKAGE_KEYS = ('platform', 'format', 'account')


def check_label(value, what):
    if not isinstance(value, str) or not LABEL.match(value) or BOARD_ID.match(value):
        raise ValueError(f'{what} must be an opaque lowercase label (no handles or device IDs).')
    return value


class ReviewQueue:
    def __init__(self, path, clock=time.time, utc_offset_hours=0, window=(9, 21), min_gap_minutes=45):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock; self.tz = dt.timezone(dt.timedelta(hours=utc_offset_hours))
        if not (0 <= window[0] < window[1] <= 24) or min_gap_minutes < 1:
            raise ValueError('Bad run window or gap.')
        self.window, self.gap = window, min_gap_minutes * 60
        self.state = self._load()

    # --- storage: one JSON file, replaced atomically; a restart only reads it back ---
    def _load(self):
        if not self.path.exists():
            return {'budgets': {}, 'packages': {}}
        return json.loads(self.path.read_text(encoding='utf-8'))

    def _save(self):
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(self.state, handle, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    # --- budgets ---
    def set_budget(self, account, platform, per_day):
        check_label(account, 'Account'); check_label(platform, 'Platform')
        if type(per_day) is not int or not 0 <= per_day <= MAX_DAILY:
            raise ValueError(f'Daily budget must be a whole number 0-{MAX_DAILY}.')
        self.state['budgets'].setdefault(account, {})[platform] = per_day; self._save()

    def budget(self, account, platform):
        return self.state['budgets'].get(account, {}).get(platform, DEFAULT_DAILY)

    # --- review ---
    def submit(self, package_id, platform, format, account, caption=''):
        """A prepared package enters the queue as pending. Resubmitting the same ID is a no-op."""
        if type(package_id) is not int or package_id <= 0:
            raise ValueError('Package ID must be a positive integer.')
        check_label(platform, 'Platform'); check_label(account, 'Account')
        if not isinstance(format, str) or not format:
            raise ValueError('Package needs a format.')
        key = str(package_id)
        if key not in self.state['packages']:
            self.state['packages'][key] = {'id': package_id, 'platform': platform, 'format': format,
                                           'account': account, 'caption': str(caption), 'state': PENDING,
                                           'submittedAt': self.clock()}
            self._save()
        return self.state['packages'][key]

    def _get(self, package_id):
        try: return self.state['packages'][str(package_id)]
        except KeyError: raise ValueError(f'No package {package_id} in the queue.') from None

    def approve(self, package_id):
        pkg = self._get(package_id)
        if pkg['state'] == PENDING:
            pkg.update(state=APPROVED, decidedAt=self.clock()); self._save()
        elif pkg['state'] == REJECTED:
            raise ValueError('Rejected package; submit a new package instead.')
        return pkg

    def reject(self, package_id):
        """Rejecting a pending, approved or planned package cancels any planned slot."""
        pkg = self._get(package_id)
        if pkg['state'] != REJECTED:
            pkg.pop('slot', None); pkg.update(state=REJECTED, decidedAt=self.clock()); self._save()
        return pkg

    def pending(self):
        return [p for p in self._ordered() if p['state'] == PENDING]

    def _ordered(self):
        return sorted(self.state['packages'].values(), key=lambda p: (p['submittedAt'], p['id']))

    # --- planning ---
    def _day(self, ts): return dt.datetime.fromtimestamp(ts, self.tz).date()

    def _at_hour(self, day, hour):
        return dt.datetime.combine(day, dt.time(hour), self.tz).timestamp()

    def lapse_stale(self):
        """Planned slots past their grace become lapsed and return to approved: no catch-up run."""
        now, changed = self.clock(), []
        for pkg in self._ordered():
            if pkg['state'] == PLANNED and now - pkg['slot'] > GRACE_SECONDS:
                pkg.update(state=APPROVED, lapsedSlot=pkg.pop('slot')); changed.append(pkg['id'])
        if changed: self._save()
        return changed

    def plan(self, horizon_days=7):
        """Give each approved package a slot within its budget; return newly planned packages."""
        if not 1 <= horizon_days <= 30:
            raise ValueError('Horizon is 1-30 days.')
        self.lapse_stale()
        now = self.clock(); first = self._day(now); newly = []
        taken = [p['slot'] for p in self.state['packages'].values() if p['state'] == PLANNED]
        for pkg in self._ordered():
            if pkg['state'] != APPROVED: continue
            limit = self.budget(pkg['account'], pkg['platform'])
            for offset in range(horizon_days):
                day = first + dt.timedelta(days=offset)
                used = sum(1 for p in self.state['packages'].values()
                           if p['state'] == PLANNED and p['account'] == pkg['account'] and
                           p['platform'] == pkg['platform'] and self._day(p['slot']) == day)
                if used >= limit: continue
                slot = self._free_slot(day, now, taken)
                if slot is None: continue
                pkg.update(state=PLANNED, slot=slot, plannedAt=now); taken.append(slot); newly.append(pkg)
                break
        if newly: self._save()
        return newly

    def _free_slot(self, day, now, taken):
        """Earliest time in the day's window at least one gap from every other slot and from now."""
        start, end = self._at_hour(day, self.window[0]), self._at_hour(day, self.window[1]) if self.window[1] < 24 else self._at_hour(day, 0) + 86400
        t = max(start, now + self.gap)
        while t < end:
            clash = [s for s in taken if abs(s - t) < self.gap]
            if not clash: return t
            t = max(clash) + self.gap
        return None

    def schedule(self):
        """Read-only view for the operator: slots in time order, then the waiting lists."""
        slots = sorted((p for p in self.state['packages'].values() if p['state'] == PLANNED), key=lambda p: p['slot'])
        by_state = lambda s: [p['id'] for p in self._ordered() if p['state'] == s]
        return {'slots': [{'id': p['id'], 'platform': p['platform'], 'account': p['account'], 'at': p['slot'],
                           'day': self._day(p['slot']).isoformat()} for p in slots],
                'pending': by_state(PENDING), 'approved': by_state(APPROVED), 'rejected': by_state(REJECTED),
                'startsRuns': False, 'phoneInput': False, 'publishing': False, 'messaging': False}

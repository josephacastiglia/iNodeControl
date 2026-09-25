import { h, replace, pill } from '../lib/dom.js';
import { get } from '../lib/api.js';
import { state, formatTime, timezoneLabel } from '../lib/state.js';
import { stopAllButton } from '../lib/stopall.js';
import { describeEntry } from './activity.js';

export function overviewView({ setActions, setBanner }) {
  setActions(stopAllButton());
  const stats = h('div', { class: 'stats' });
  const attention = h('div', { class: 'list' });
  const active = h('div', { class: 'list' });
  const recent = h('div', { class: 'list' });
  const planNote = h('p', { class: 'muted small' });
  const el = h('div', { style: 'display:grid;gap:24px' },
    stats, planNote,
    h('div', { class: 'two-col' },
      h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Needs attention'), h('a', { href: '#/phones', class: 'small' }, 'All phones →')), attention),
      h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Active now')), active)),
    h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Recent activity'), h('span', { class: 'muted small' }, `Times in ${timezoneLabel()}`)), recent,
      h('a', { href: '#/activity', class: 'small' }, 'Full activity log →')));

  const stat = (value, label) => h('div', { class: 'stat' }, h('strong', {}, String(value)), h('span', {}, label));

  async function refresh() {
    let phones, activity;
    try { [{ phones }, activity] = await Promise.all([get('/api/phones'), get('/api/activity')]); }
    catch { return; }
    state.phones = phones;
    const live = phones.filter(p => p.video.state === 'live').length;
    const ready = phones.filter(p => ['ready', 'yours'].includes(p.input.state)).length;
    const controlled = phones.filter(p => ['yours', 'teammate'].includes(p.input.state)).length;
    const rackOnline = phones.length === 0 || phones.some(p => p.rack.online);
    setBanner(phones.some(p => p.rack.simulated) ? 'Simulated rack — for development and testing only. These are not real phones.' : null);
    replace(stats,
      stat(phones.length, 'Phones assigned to you'),
      stat(`${live}/${phones.length}`, 'Screens live'),
      stat(`${ready}/${phones.length}`, 'Ready for control'),
      stat(controlled, 'Controlled right now'));
    const plan = state.me.planPhones;
    planNote.textContent = [
      !rackOnline ? 'We can’t reach the rack hosting your phones right now; we’re on it.' : '',
      plan && plan > phones.length ? `Your plan includes ${plan} phones and ${phones.length} ${phones.length === 1 ? 'is' : 'are'} assigned so far. We assign each phone once it has been checked and verified working.` : '',
    ].filter(Boolean).join(' ');

    const issues = phones.filter(p => !['live'].includes(p.video.state) || ['stopped', 'unavailable', 'unknown'].includes(p.input.state));
    replace(attention, issues.length ? issues.map(p => h('a', { class: 'list-row', href: `#/phones/${p.id}` },
      h('div', { class: 'label-row' }, h('b', {}, p.name), h('small', { class: 'muted' }, p.input.state === 'stopped' ? p.input.detail : p.video.state !== 'live' ? p.video.detail : p.input.detail ?? '')),
      h('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;justify-content:end' }, pill(p.input.state, p.input.label, 'Control'), pill(p.video.state, p.video.label, 'Video'))))
      : h('p', { class: 'empty' }, 'Everything looks good.'));

    const busy = phones.filter(p => ['yours', 'teammate', 'operator'].includes(p.input.state));
    replace(active, busy.length ? busy.map(p => h('a', { class: 'list-row', href: `#/phones/${p.id}` }, h('b', {}, p.name), pill(p.input.state, p.input.label)))
      : h('p', { class: 'empty' }, 'No one is controlling a phone right now. Scheduled jobs and automations will appear here once they’re available.'));

    replace(recent, activity.entries.slice(0, 8).map(e => h('div', { class: 'list-row' },
      h('div', { class: 'label-row' }, h('span', {}, describeEntry(e)), h('small', { class: 'muted' }, [e.actor_label || (e.actor_type === 'system' ? 'NodeTheory' : ''), e.phone_name].filter(Boolean).join(' · '))),
      h('span', { class: 'muted small' }, formatTime(e.at)))));
    if (!activity.entries.length) replace(recent, h('p', { class: 'empty' }, 'No activity yet.'));
  }

  refresh();
  const timer = setInterval(refresh, 3000);
  const onRefresh = () => refresh();
  window.addEventListener('nt:refresh', onRefresh);
  return { el, destroy() { clearInterval(timer); window.removeEventListener('nt:refresh', onRefresh); } };
}

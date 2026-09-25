import { h, replace } from '../lib/dom.js';
import { get } from '../lib/api.js';
import { formatTime, timezoneLabel } from '../lib/state.js';
import { stopAllButton } from '../lib/stopall.js';

const LABELS = {
  'auth.login': 'Signed in', 'auth.logout': 'Signed out',
  'control.acquire': 'Took control', 'control.release': 'Released control', 'control.lost': 'Control ended',
  'input.tap': 'Tap', 'input.drag': 'Swipe', 'input.longPress': 'Long press', 'input.key': 'Key press', 'input.text': 'Typed text',
  'input.resetPointer': 'Reset pointer', 'input.stop': 'Stopped phone', 'input.resume': 'Resumed input',
  'phone.rename': 'Renamed phone', 'phone.allocate': 'Phone assigned to your account', 'phone.unallocate': 'Phone removed from your account',
  'customer.create': 'Account created', 'customer.status': 'Account status changed', 'user.create': 'User added', 'user.disable': 'User disabled',
};
const OUTCOMES = {
  ok: '', succeeded: '', failed: 'failed', refused: 'refused', unconfirmed: 'not confirmed', unknown: 'outcome uncertain', cancelled: 'cancelled',
  rejected: 'not sent', stopped: 'stopped', lease_lost: 'timed out', released: '', timeout: 'browser stopped responding', rack_disconnected: 'rack connection lost',
};

export function describeEntry(e) {
  let text = e.action.startsWith('group.') ? `Group action: ${e.detail?.summary ?? e.action.slice(6)}` : (LABELS[e.action] ?? e.action);
  if (e.detail?.summary && e.action.startsWith('input.') && e.action !== 'input.stop') text = e.detail.summary;
  const outcome = e.action.startsWith('group.') ? e.outcome : (OUTCOMES[e.outcome] ?? e.outcome);
  return outcome ? `${text} — ${outcome}` : text;
}

export function activityView({ setActions }) {
  setActions(stopAllButton());
  const body = h('tbody');
  const more = h('button', { class: 'btn btn-ghost', type: 'button', hidden: true }, 'Load older');
  let oldest = null;
  const el = h('div', { style: 'display:grid;gap:14px' },
    h('p', { class: 'muted small' }, `Every sign-in, control change and remote action on your phones. Typed text is never recorded — only its length. Times in ${timezoneLabel()}.`),
    h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'When'), h('th', {}, 'Who'), h('th', {}, 'Phone'), h('th', {}, 'What'), h('th', {}, 'Detail'))), body)),
    more);
  async function load() {
    const { entries } = await get(`/api/activity${oldest ? `?before=${oldest}` : ''}`);
    for (const e of entries) body.append(h('tr', {},
      h('td', { class: 'mono' }, formatTime(e.at, { date: true })),
      h('td', {}, e.actor_label || (e.actor_type === 'agent' ? 'Rack' : 'NodeTheory')),
      h('td', {}, e.phone_name ?? (e.phone_id ? 'Former phone' : '—')),
      h('td', {}, describeEntry(e)),
      h('td', { class: 'muted small' }, e.detail?.message ?? '')));
    if (entries.length) oldest = entries.at(-1).id;
    more.hidden = entries.length < 100;
    if (!body.children.length) replace(body, h('tr', {}, h('td', { colspan: 5, class: 'empty' }, 'No activity yet.')));
  }
  more.addEventListener('click', load);
  load();
  return { el };
}

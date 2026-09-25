import { h, replace, pill, toast, showDialog } from '../lib/dom.js';
import { get, post } from '../lib/api.js';
import { state } from '../lib/state.js';
import { gridPreview } from '../lib/frames.js';
import { presetSwipe, textProblem } from '../lib/coords.js';
import { stopAllButton } from '../lib/stopall.js';

const STATUS_WORDS = { succeeded: 'Done', failed: 'Failed', cancelled: 'Cancelled', unknown: 'Uncertain — check this phone', rejected: 'Not sent', skipped: 'Skipped' };

export function phonesView({ setActions, setBanner }) {
  const selectToggle = h('button', { class: 'btn btn-ghost', type: 'button', 'aria-pressed': 'false' }, 'Select phones for a group action');
  setActions(selectToggle, stopAllButton());
  const grid = h('div', { class: 'phone-grid' });
  const bar = h('div', { class: 'group-bar', hidden: true, role: 'region', 'aria-label': 'Group actions' });
  const note = h('p', { class: 'muted small' }, 'Open a phone to see it live and control it. Each phone has one controller at a time.');
  const el = h('div', { style: 'display:grid;gap:16px' }, note, grid, bar);
  const tiles = new Map();
  const selected = new Set();
  let selecting = false;
  let phones = [];

  selectToggle.addEventListener('click', () => {
    selecting = !selecting;
    selectToggle.setAttribute('aria-pressed', String(selecting));
    selectToggle.textContent = selecting ? 'Done selecting' : 'Select phones for a group action';
    if (!selecting) selected.clear();
    note.textContent = selecting ? 'Group mode: tick the phones you want. Actions below go only to the ticked phones.' : 'Open a phone to see it live and control it. Each phone has one controller at a time.';
    render();
  });

  function tileFor(p) {
    let t = tiles.get(p.id);
    if (!t) {
      const img = h('img', { alt: `${p.name} screen` });
      const placeholder = h('div', { class: 'placeholder' }, 'Loading preview…');
      const screen = h('div', { class: 'screen' }, img, placeholder);
      const name = h('h3');
      const chips = h('div', { class: 'chips' });
      const check = h('span', { class: 'check', 'aria-hidden': 'true' });
      const el = h('button', { class: 'tile', type: 'button' }, check, screen, h('div', { class: 'label-row' }, name, h('small', {}, p.model)), chips);
      el.addEventListener('click', () => {
        if (!selecting) { location.hash = `#/phones/${p.id}`; return; }
        selected.has(p.id) ? selected.delete(p.id) : selected.add(p.id);
        render();
      });
      const preview = gridPreview(`/api/phones/${p.id}/frame`, img, { onFrame: () => { placeholder.hidden = true; } });
      t = { el, name, chips, check, placeholder, img, preview };
      tiles.set(p.id, t);
    }
    t.name.textContent = p.name;
    replace(t.chips, pill(p.input.state, p.input.label, 'Control'), pill(p.video.state, p.video.label, 'Video'));
    t.check.hidden = !selecting;
    t.el.classList.toggle('selected', selecting && selected.has(p.id));
    t.el.setAttribute('aria-label', selecting ? `${selected.has(p.id) ? 'Deselect' : 'Select'} ${p.name}` : `Open ${p.name}`);
    if (p.video.state !== 'live') { t.placeholder.hidden = false; t.placeholder.textContent = p.video.label; }
    return t.el;
  }

  function render() {
    for (const id of [...selected]) if (!phones.some(p => p.id === id)) selected.delete(id);
    if (!phones.length) replace(grid, h('div', { class: 'card', style: 'grid-column:1/-1' }, h('h2', {}, 'No phones assigned yet'),
      h('p', { class: 'muted' }, 'Your NodeTheory team assigns phones once each one is verified working. They’ll appear here automatically.')));
    else replace(grid, phones.map(tileFor));
    for (const [id, t] of tiles) if (!phones.some(p => p.id === id)) { t.preview.stop(); tiles.delete(id); }
    renderBar();
  }

  function renderBar() {
    bar.hidden = !selecting;
    if (!selecting) return;
    const ids = [...selected];
    const n = ids.length;
    const disabled = n === 0;
    const btn = (label, fn, cls = 'btn-ghost') => h('button', { class: `btn btn-sm ${cls}`, type: 'button', disabled, onclick: fn }, label);
    const inControl = phones.filter(p => selected.has(p.id) && p.input.state === 'yours').length;
    replace(bar,
      h('div', { class: 'group-warning' }, `Group mode — actions go to ${n} selected phone${n === 1 ? '' : 's'}`),
      h('span', { class: 'count' }, `${n} selected · ${inControl} in your control`),
      btn('Take control', () => groupCall('/api/groups/control', 'Take control')),
      btn('Home', () => groupAction({ type: 'key', key: 'Home' })),
      btn('Swipe ←', () => groupSwipe('left')), btn('Swipe →', () => groupSwipe('right')),
      btn('Swipe ↑', () => groupSwipe('up')), btn('Swipe ↓', () => groupSwipe('down')),
      btn('Type text…', groupType),
      btn('Release', () => groupCall('/api/groups/release', 'Release')),
      h('span', { class: 'spacer' }),
      btn('Stop selected', () => groupCall('/api/groups/stop', 'Stop'), 'btn-stop'),
      h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => { selected.clear(); render(); } }, 'Clear'));
  }

  async function groupCall(path, label) {
    try {
      const r = await post(path, { phoneIds: [...selected] });
      if (r.results) showResults(label, r.results.map(x => ({ ...x, status: x.ok ? 'succeeded' : 'failed' })));
      else toast(`${label}: done.`);
    } catch (err) { toast(err.message, 'bad'); }
    refresh();
  }

  function groupSwipe(direction) {
    const sizes = new Set(phones.filter(p => selected.has(p.id)).map(p => `${p.screen.width}x${p.screen.height}`));
    if (sizes.size !== 1) return toast('Swipes need phones with the same screen size.', 'warn');
    const [w, hgt] = [...sizes][0].split('x').map(Number);
    groupAction(presetSwipe(direction, { width: w, height: hgt }));
  }

  function groupType() {
    const input = h('input', { type: 'text', maxlength: 200, 'aria-label': 'Text to type' });
    const err = h('p', { class: 'error-text' });
    const send = h('button', { class: 'btn btn-dark', type: 'button' }, `Type on ${selected.size} phones`);
    const dlg = showDialog('Type on selected phones', h('p', { class: 'muted small' }, 'The text goes to whatever field is focused on each selected phone. English (US) keyboard characters only.'), input, err, send);
    send.addEventListener('click', () => {
      const problem = textProblem(input.value);
      if (problem) { err.textContent = problem; return; }
      dlg.close();
      groupAction({ type: 'text', text: input.value });
    });
    input.focus();
  }

  async function groupAction(action, retryOf, ids = [...selected]) {
    try {
      const r = await post('/api/groups/actions', { phoneIds: ids, action, ...(retryOf ? { retryOf } : {}) });
      showResults(actionLabel(action), r.results, { action, groupId: r.groupId });
    } catch (err) { toast(err.message, 'bad'); }
    refresh();
  }

  function showResults(label, results, retry) {
    const retryable = results.filter(r => ['failed', 'cancelled', 'rejected'].includes(r.status));
    const ok = results.filter(r => r.status === 'succeeded').length;
    const rows = results.map(r => h('tr', {}, h('td', {}, r.name), h('td', { class: `st st-${r.status}` }, STATUS_WORDS[r.status] ?? r.status), h('td', { class: 'muted small' }, r.message ?? '')));
    const content = [
      h('p', {}, `${ok} of ${results.length} succeeded.`),
      h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Phone'), h('th', {}, 'Result'), h('th', {}, 'Detail'))), h('tbody', {}, rows))),
    ];
    if (results.some(r => r.status === 'unknown'))
      content.push(h('p', { class: 'small muted' }, 'Uncertain results are never retried automatically: the action may already have happened. Check those phones first.'));
    if (retry && retryable.length) {
      const btn = h('button', { class: 'btn btn-primary', type: 'button' }, `Retry on the ${retryable.length} phone${retryable.length === 1 ? '' : 's'} that didn’t succeed`);
      btn.addEventListener('click', () => { dlg.close(); groupAction(retry.action, retry.groupId, retryable.map(r => r.phoneId)); });
      content.push(h('p', { class: 'small muted' }, 'Phones that succeeded will not receive the action again.'), btn);
    }
    const dlg = showDialog(`${label}: results`, ...content);
  }

  async function refresh() {
    try {
      ({ phones } = await get('/api/phones'));
      state.phones = phones;
      setBanner(phones.some(p => p.rack.simulated) ? 'Simulated rack — for development and testing only. These are not real phones.' : null);
      render();
    } catch { /* retry next tick */ }
  }
  refresh();
  const timer = setInterval(refresh, 2500);
  const onRefresh = () => refresh();
  window.addEventListener('nt:refresh', onRefresh);
  return { el, destroy() { clearInterval(timer); window.removeEventListener('nt:refresh', onRefresh); for (const t of tiles.values()) t.preview.stop(); } };
}

export function actionLabel(a) {
  switch (a.type) {
    case 'key': return { Home: 'Home', AppSwitch: 'App switcher', ControlBar: 'Control Centre', Enter: 'Return', Backspace: 'Delete', Tab: 'Tab', Escape: 'Escape' }[a.key] ?? a.key;
    case 'text': return 'Type text';
    case 'drag': return 'Swipe';
    case 'tap': return 'Tap';
    case 'longPress': return 'Long press';
    case 'resetPointer': return 'Reset pointer';
    default: return 'Action';
  }
}

import { h, replace, pill, toast, showDialog } from '../lib/dom.js';
import { get, post, ApiError } from '../lib/api.js';
import { state, formatTime, isCustomerAdmin } from '../lib/state.js';
import { focusPreview } from '../lib/frames.js';
import { toSource, fromSource, classifyGesture, presetSwipe, textProblem } from '../lib/coords.js';
import { stopAllButton } from '../lib/stopall.js';
import { actionLabel } from './phones.js';
import { OUTCOME_WORDS, OUTCOME_KIND, progressNote } from '../lib/outcomes.js';
import { LatencyRecorder, summarize } from '../lib/measure.js';


export function phoneView({ params: [phoneId], setTitle, setActions, setBanner }) {
  let phone = null;
  let destroyed = false;
  let inflight = 0;
  // Measurement state (see measurePanel); declared first because the panel is built early.
  const fpsNow = () => shown.length > 1 ? (shown.length - 1) / ((shown.at(-1) - shown[0]) / 1000) : 0;
  const shown = [], frameLog = [], receiverFpsSamples = [];
  const recorder = new LatencyRecorder();
  const canvas = document.createElement('canvas');
  const ctx2d = canvas.getContext('2d', { willReadFrequently: true });
  let measuring = false, recordStart = null, measureRender = () => {};

  // ---- stage (live screen) ------------------------------------------------------------
  const img = h('img', { alt: '', draggable: 'false' });
  const placeholder = h('div', { class: 'placeholder' }, 'Connecting to the screen…');
  const overlay = h('div', { class: 'touch-overlay', 'aria-hidden': 'true' });
  const screen = h('div', { class: 'screen', role: 'application', tabindex: '0', 'aria-label': 'Phone screen. When you are in control: click to tap, drag to swipe, press and hold to long-press.' }, img, placeholder, overlay);
  const fpsText = h('span', {}, '—');
  const hint = h('span', {}, '');
  const stage = h('div', { class: 'stage dark' }, screen, h('div', { class: 'stage-meta' }, fpsText, hint));

  // ---- panel -------------------------------------------------------------------------
  const controlCard = h('div', { class: 'status-card' });
  const videoCard = h('div', { class: 'status-card' });
  const endedNote = h('p', { class: 'small', role: 'status' });
  const controls = h('div', { class: 'card' });
  const history = h('div', { class: 'list history' });
  const diagBody = h('div', {}, h('p', { class: 'muted small' }, 'Loading…'));
  const diag = h('details', { class: 'disclosure' }, h('summary', {}, 'Diagnostics'), diagBody);
  diag.addEventListener('toggle', () => { if (diag.open) loadDiagnostics(); });
  const stopBtn = h('button', { class: 'btn btn-stop', type: 'button', onclick: stopPhone }, 'Stop this phone');
  const panel = h('div', { class: 'panel' },
    h('div', { class: 'status-grid' }, controlCard, videoCard), endedNote, controls,
    h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Recent actions'), h('span', { class: 'muted small' }, '“Sent” means the rack delivered the input — check the screen for the result.')), history),
    unavailableList(), diag, measurePanel());
  const el = h('div', { class: 'focus' }, stage, panel);
  setActions(stopBtn, stopAllButton());

  const inControl = () => phone?.input.state === 'yours';

  // ---- actions -------------------------------------------------------------------------
  async function send(action, { feedbackAt } = {}) {
    if (!inControl()) { toast('Take control of this phone first.', 'warn'); return; }
    inflight++; renderHint();
    let pending = null;
    if (feedbackAt) pending = marker(feedbackAt, 'pending-dot');
    if (measuring && !recorder.baseline) captureBaseline();
    const m = measuring ? recorder.start({ label: actionLabel(action), point: action.type === 'tap' || action.type === 'longPress' ? { x: action.x, y: action.y } : null, source: phone.screen }) : null;
    try {
      const r = await post(`/api/phones/${phoneId}/actions`, { action });
      const c = r.command;
      if (m) recorder.ack(m, c.status);
      if (c.status !== 'succeeded' || action.type === 'text') toast(`${actionLabel(action)}: ${OUTCOME_WORDS[c.status] ?? c.status}. ${c.message}`, OUTCOME_KIND[c.status] ?? 'bad', c.status === 'uncertain' ? 12000 : 7000);
      applyPhone(r.phone);
    } catch (err) {
      toast(err.message, 'bad');
    } finally {
      pending?.remove();
      inflight--; renderHint();
      loadHistory();
    }
  }

  function marker(pt, cls) {
    const box = screen.getBoundingClientRect();
    const pos = fromSource(pt.x, pt.y, box, { width: img.naturalWidth || phone.screen.width, height: img.naturalHeight || phone.screen.height }, phone.screen);
    if (!pos) return null;
    const m = h('span', { class: cls, style: `left:${pos.x}px;top:${pos.y}px` });
    overlay.append(m);
    if (cls === 'ripple') setTimeout(() => m.remove(), 650);
    return m;
  }

  // Pointer gestures become exactly one action when the pointer is released.
  let gesture = null;
  function mapPoint(e, clamp) {
    const box = screen.getBoundingClientRect();
    return toSource(e.clientX - box.left, e.clientY - box.top, box,
      { width: img.naturalWidth || phone.screen.width, height: img.naturalHeight || phone.screen.height }, phone.screen, clamp);
  }
  screen.addEventListener('pointerdown', e => {
    if (!inControl() || e.button !== 0 || !phone?.screen.width) return;
    const p = mapPoint(e, false);
    if (!p) return;
    e.preventDefault();
    screen.setPointerCapture(e.pointerId);
    gesture = { id: e.pointerId, start: performance.now(), points: [[p.x, p.y]] };
  });
  screen.addEventListener('pointermove', e => {
    if (!gesture || e.pointerId !== gesture.id) return;
    const p = mapPoint(e, true);
    const last = gesture.points.at(-1);
    if (p && (Math.abs(p.x - last[0]) > 2 || Math.abs(p.y - last[1]) > 2)) gesture.points.push([p.x, p.y]);
  });
  screen.addEventListener('pointerup', e => {
    if (!gesture || e.pointerId !== gesture.id) return;
    const g = gesture; gesture = null;
    const action = classifyGesture(g.points, performance.now() - g.start);
    if (!action) return;
    const at = action.type === 'drag' ? { x: action.points.at(-1)[0], y: action.points.at(-1)[1] } : { x: action.x, y: action.y };
    marker(at, 'ripple');
    send(action, { feedbackAt: at });
  });
  screen.addEventListener('pointercancel', () => { gesture = null; });
  screen.addEventListener('contextmenu', e => e.preventDefault());

  // ---- control lifecycle ------------------------------------------------------------------
  async function takeControl() {
    try { applyPhone((await post(`/api/phones/${phoneId}/control`)).phone); toast('You’re in control.'); }
    catch (err) { toast(err.message, 'bad', 6000); refresh(); }
  }
  async function releaseControl() {
    try { applyPhone((await post(`/api/phones/${phoneId}/control/release`)).phone); toast('Control released.'); }
    catch (err) { toast(err.message, 'bad'); }
  }
  async function resume() {
    try {
      applyPhone((await post(`/api/phones/${phoneId}/resume`, { generation: phone.input.generation })).phone);
      toast('Input resumed. Take control when you’re ready.');
    } catch (err) { toast(err.message, 'bad', 7000); refresh(); }
  }
  async function stopPhone() {
    try {
      const r = await post(`/api/phones/${phoneId}/stop`);
      toast(r.result.ok ? 'Stopped. Queued actions were cancelled. Resume when you’re ready.' : `Stop not confirmed: ${r.result.message}`, r.result.ok ? 'ok' : 'bad', 7000);
      applyPhone(r.phone);
    } catch (err) { toast(err.message, 'bad'); }
  }
  async function rename() {
    const input = h('input', { type: 'text', maxlength: 40, value: phone.name, 'aria-label': 'Phone name' });
    const save = h('button', { class: 'btn btn-dark', type: 'button' }, 'Save name');
    const dlg = showDialog('Rename phone', input, save);
    save.addEventListener('click', async () => {
      try { await post(`/api/phones/${phoneId}/name`, { name: input.value }); dlg.close(); refresh(); }
      catch (err) { toast(err.message, 'bad'); }
    });
  }

  // ---- rendering ------------------------------------------------------------------------
  function renderControlCard() {
    const i = phone.input;
    const buttons = [];
    if (i.state === 'ready') buttons.push(h('button', { class: 'btn btn-dark', type: 'button', onclick: takeControl }, 'Take control'));
    if (i.state === 'yours') buttons.push(h('button', { class: 'btn btn-ghost', type: 'button', onclick: releaseControl }, 'Release control'));
    if (i.state === 'stopped') buttons.push(h('button', { class: 'btn btn-dark', type: 'button', onclick: resume }, 'Resume input'));
    replace(controlCard, h('span', { class: 'eyebrow' }, 'Control'), h('div', {}, pill(i.state, i.label)),
      i.detail ? h('p', {}, i.detail) : h('p', {}, i.state === 'yours' ? 'Only you can send input to this phone until you release it.' : i.state === 'ready' ? 'Take control to tap, swipe and type.' : ''),
      buttons.length ? h('div', { class: 'control-row' }, buttons) : null);
  }
  function renderVideoCard(stats) {
    const v = phone.video;
    replace(videoCard, h('span', { class: 'eyebrow' }, 'Video'), h('div', {}, pill(v.state, v.label)),
      h('p', {}, v.detail || (v.state === 'live' ? 'The picture updates whenever the screen changes.' : '')),
      stats ? h('p', { class: 'mono' }, `${stats.fps.toFixed(1)} fps shown · frame ${(stats.ageMs / 1000).toFixed(1)} s old at arrival`) : null);
  }
  function renderHint() {
    hint.textContent = inControl() ? (inflight ? `Sending… (${inflight})` : 'Click · drag · hold') : 'View only';
    screen.classList.toggle('interactive', inControl());
  }
  function renderControls() {
    const on = inControl();
    const b = (label, action, extra = {}) => h('button', { class: 'btn btn-ghost btn-sm', type: 'button', disabled: !on, onclick: () => send(action), ...extra }, label);
    const text = h('input', { type: 'text', maxlength: 200, placeholder: 'Text to type on the phone', disabled: !on, 'aria-label': 'Text to type', autocomplete: 'off' });
    const counter = h('span', { class: 'counter' }, '0 / 200');
    const textErr = h('p', { class: 'error-text' });
    const sendText = h('button', { class: 'btn btn-dark', type: 'button', disabled: !on }, 'Type');
    text.addEventListener('input', () => { counter.textContent = `${text.value.length} / 200`; textErr.textContent = text.value ? textProblem(text.value) ?? '' : ''; });
    const submitText = () => {
      const problem = textProblem(text.value);
      if (problem) { textErr.textContent = problem; return; }
      send({ type: 'text', text: text.value });
      text.value = ''; counter.textContent = '0 / 200';
    };
    sendText.addEventListener('click', submitText);
    text.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); submitText(); } });
    const swipe = dir => presetSwipe(dir, phone.screen);
    replace(controls,
      h('div', { class: 'card-head' }, h('h2', {}, 'Controls'), on ? h('span', { class: 'muted small' }, 'Actions run one at a time, in order.') : h('span', { class: 'muted small' }, 'Take control to use these.')),
      h('div', { class: 'control-row' }, b('Home', { type: 'key', key: 'Home' }), b('App switcher', { type: 'key', key: 'AppSwitch' }), b('Control Centre', { type: 'key', key: 'ControlBar' })),
      h('div', { style: 'display:flex;gap:18px;align-items:center;flex-wrap:wrap' },
        h('div', { class: 'pad', role: 'group', 'aria-label': 'Swipe' },
          h('button', { class: 'up', type: 'button', disabled: !on, 'aria-label': 'Swipe up', onclick: () => send(swipe('up')) }, '↑'),
          h('button', { class: 'left', type: 'button', disabled: !on, 'aria-label': 'Swipe left', onclick: () => send(swipe('left')) }, '←'),
          h('button', { class: 'right', type: 'button', disabled: !on, 'aria-label': 'Swipe right', onclick: () => send(swipe('right')) }, '→'),
          h('button', { class: 'down', type: 'button', disabled: !on, 'aria-label': 'Swipe down', onclick: () => send(swipe('down')) }, '↓')),
        h('p', { class: 'muted small', style: 'max-width:26em' }, 'Swipes travel across the middle of the screen. For a precise swipe, drag on the screen itself.')),
      h('div', { style: 'display:grid;gap:6px' },
        h('div', { class: 'textbox' }, text, sendText),
        h('div', { style: 'display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap' }, counter,
          h('span', { class: 'counter' }, 'English (US) keyboard characters only · the phone needs a text field selected')),
        textErr),
      h('div', { class: 'control-row' }, b('Return', { type: 'key', key: 'Enter' }), b('Delete', { type: 'key', key: 'Backspace' }), b('Tab', { type: 'key', key: 'Tab' }), b('Esc', { type: 'key', key: 'Escape' }),
        b('Reset pointer', { type: 'resetPointer' }, { title: 'Use this if taps stop registering.' })));
  }

  let lastRendered = '';
  function applyPhone(p) {
    if (!p || destroyed) return;
    const firstLoad = !phone;
    phone = p;
    const i = state.phones.findIndex(x => x.id === p.id);
    if (i >= 0) state.phones[i] = p; else state.phones.push(p);
    setTitle(p.name);
    setBanner(p.rack.simulated ? 'Simulated rack — for development and testing only. This is not a real phone.' : null);
    const key = JSON.stringify([p.input, p.video.state, p.video.label, p.video.detail]);
    if (key !== lastRendered || firstLoad) {
      lastRendered = key;
      renderControlCard(); renderVideoCard(preview?.stats.fps ? preview.stats : null); renderControls(); renderHint();
    }
    endedNote.textContent = p.lastEnded && p.input.state !== 'yours' ? `Control ended: ${p.lastEnded.message}` : '';
    if (p.video.state !== 'live' && !img.dataset.url) { placeholder.hidden = false; placeholder.textContent = p.video.detail || p.video.label; }
    if (firstLoad && isCustomerAdmin()) setActions(h('button', { class: 'btn btn-ghost', type: 'button', onclick: rename }, 'Rename'), stopBtn, stopAllButton());
  }

  async function refresh() {
    try { applyPhone((await get(`/api/phones/${phoneId}`)).phone); }
    catch (err) {
      if (err instanceof ApiError && err.status === 404) replace(el, h('div', { class: 'card' }, h('h2', {}, 'Phone not found'), h('p', { class: 'muted' }, 'It may have been removed from your account.'), h('a', { href: '#/phones' }, '← Back to phones')));
    }
  }

  async function loadHistory() {
    try {
      const { commands } = await get(`/api/phones/${phoneId}/commands`);
      replace(history, commands.length ? commands.slice(0, 12).map(c => h('div', { class: 'list-row' },
        h('div', { class: 'label-row' }, h('span', {}, c.summary),
          h('small', { class: 'muted' }, [c.user_name, formatTime(c.created_at), c.elapsed_ms ? `${c.elapsed_ms} ms` : '', progressNote(c)].filter(Boolean).join(' · ')),
          c.status !== 'succeeded' && c.message ? h('small', { class: 'muted' }, c.message) : null),
        h('span', { class: `st st-${c.status}` }, OUTCOME_WORDS[c.status] ?? c.status))) : h('p', { class: 'empty' }, 'No actions yet.'));
    } catch { /* keep previous */ }
  }

  async function loadDiagnostics() {
    try {
      const { diagnostics: d } = await get(`/api/phones/${phoneId}/diagnostics`);
      const p = d.phone;
      const rows = p.reported === false ? [['Device ID', p.deviceId], ['Reported by rack', 'No']] : [
        ['Device ID', p.deviceId], ['Model / iOS', `${p.model} · ${p.os}`], ['Screen image', p.image], ['Control board', `${p.board} · ${p.boardPresent === null ? 'unknown' : p.boardPresent ? 'present' : 'missing'}`],
        ['Input enabled', p.inputEnabled ? 'yes' : 'no'], ['Input state', `owned=${p.input.owned} stopped=${p.input.stopped} releasing=${p.input.releasing} generation=${p.input.generation}`],
        ['Input message', p.input.message || '—'], ['Receiver', `${p.video.receiver} · ${p.video.receiverState} · restarts ${p.video.receiverRestarts}`],
        ['Frames received', String(p.video.frames)], ['Last new frame', p.video.lastFrameAt ? formatTime(p.video.lastFrameAt) : 'not yet seen changing'], ['Simulated rack', d.rack.simulated ? 'yes' : 'no'],
      ];
      replace(diagBody, h('p', { class: 'muted small' }, 'Technical details for NodeTheory support.'), h('dl', { class: 'kv' }, rows.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])));
    } catch (err) { replace(diagBody, h('p', { class: 'error-text' }, err.message)); }
  }

  const preview = focusPreview(`/api/phones/${phoneId}/frame`, img, {
    onDisplayed: (f, perf, wall) => onDisplayed(f, perf, wall),
    onFrame: (f, stats) => {
      placeholder.hidden = true;
      fpsText.textContent = `${stats.fps.toFixed(1)} fps`;
      if (phone && (f.source.width !== phone.screen.width || f.source.height !== phone.screen.height)) phone.screen = f.source;
      if (phone) renderVideoCard(stats);
    },
    onIdle: stats => { fpsText.textContent = stats.fps ? `${stats.fps.toFixed(1)} fps` : 'Waiting for the screen to change'; },
  });

  // ---- measurements (validation aid) -------------------------------------------------------
  /** Pixels of the frame currently on screen, as the comparison point for the next action. */
  function captureBaseline() {
    try {
      const w = img.naturalWidth, hgt = img.naturalHeight;
      if (!w || !hgt) return;
      if (canvas.width !== w || canvas.height !== hgt) { canvas.width = w; canvas.height = hgt; }
      ctx2d.drawImage(img, 0, 0);
      recorder.setBaseline(ctx2d.getImageData(0, 0, w, hgt).data, w, hgt);
    } catch { /* image not decoded yet */ }
  }

  function onDisplayed(f, perf, wall) {
    shown.push(perf);
    while (shown.length && perf - shown[0] > 3000) shown.shift();
    if (!measuring) return;
    frameLog.push({ at: wall, seq: f.seq, captureToDisplayMs: f.capturedAt ? wall - f.capturedAt : null, portalHeldMs: f.ageMs });
    if (frameLog.length > 5000) frameLog.shift();
    try {
      const w = img.naturalWidth, hgt = img.naturalHeight;
      if (canvas.width !== w || canvas.height !== hgt) { canvas.width = w; canvas.height = hgt; }
      ctx2d.drawImage(img, 0, 0);
      recorder.onFrame(ctx2d.getImageData(0, 0, w, hgt).data, w, hgt, perf, { seq: f.seq });
    } catch { /* decoding raced with navigation */ }
  }

  function measurePanel() {
    const threshold = h('input', { type: 'number', min: 1, max: 60, step: 1, value: 8, 'aria-label': 'Change threshold', style: 'width:5.5em;min-height:32px' });
    threshold.addEventListener('change', () => { recorder.threshold = Math.min(60, Math.max(1, Number(threshold.value) || 8)); });
    const toggle = h('button', { class: 'btn btn-dark btn-sm', type: 'button' }, 'Start recording');
    toggle.addEventListener('click', () => {
      measuring = !measuring;
      toggle.textContent = measuring ? 'Stop recording' : 'Start recording';
      if (measuring && !recordStart) recordStart = Date.now();
      if (measuring) captureBaseline();
    });
    const download = h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => {
      const data = { phoneId, phoneName: phone?.name, recordedFrom: recordStart, exportedAt: Date.now(), userAgent: navigator.userAgent,
        method: { latency: 'first displayed frame whose mean pixel difference (0-255) vs the last frame before the click reaches the threshold; tap/long press: box of ±24 source px around the point; other actions: largest 1/12 x 1/24 block', threshold: recorder.threshold, timeoutMs: recorder.timeoutMs,
          captureToDisplay: 'browser Date.now() at image load minus rack agent capture time; valid only when both clocks are the same PC' },
        summary: { latency: recorder.summary(), displayedFps: fpsNow(), receiverFpsSamples, captureToDisplayMs: summarize(frameLog.map(x => x.captureToDisplayMs)), portalHeldMs: summarize(frameLog.map(x => x.portalHeldMs)) },
        latency: recorder.results, frames: frameLog };
      const a = h('a', { href: URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })), download: `measurements-${(phone?.name ?? 'phone').replace(/\W+/g, '-')}-${new Date().toISOString().replace(/[:.]/g, '-')}.json` });
      document.body.append(a); a.click(); a.remove();
    } }, 'Download JSON');
    const clear = h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => { recorder.results = []; recorder.pending = []; frameLog.length = 0; receiverFpsSamples.length = 0; recordStart = measuring ? Date.now() : null; render(); } }, 'Clear');
    const live = h('div', { class: 'mono small', style: 'display:grid;gap:4px' });
    const table = h('div', { class: 'table-wrap' });
    const render = () => {
      const lat = recorder.summary();
      const cd = summarize(frameLog.map(x => x.captureToDisplayMs)), held = summarize(frameLog.map(x => x.portalHeldMs));
      const fmt = s => s.count ? `median ${Math.round(s.median)} ms · p95 ${Math.round(s.p95)} ms (n=${s.count})` : '—';
      replace(live,
        h('div', {}, `Displayed: ${fpsNow().toFixed(1)} fps (last 3 s) · ${frameLog.length} frames recorded`),
        h('div', {}, `Receiver (kernel frame counter): ${receiverFpsSamples.length ? receiverFpsSamples.at(-1).fps : '—'} new frames/s`),
        h('div', {}, `Capture → display: ${fmt(cd)} [same-PC clocks only]`),
        h('div', {}, `Waited in portal before sending: ${fmt(held)}`),
        h('div', {}, `Action confirmed sent: ${fmt(lat.ack)}`),
        h('div', {}, `Click → first visible change: ${fmt(lat.visible)} · no visible change: ${lat.noVisibleChange} of ${lat.attempts}`));
      replace(table, h('table', {}, h('thead', {}, h('tr', {}, ['#', 'Action', 'Sent (ms)', 'Visible (ms)', 'Diff', 'Note'].map(t => h('th', {}, t)))),
        h('tbody', {}, recorder.results.slice(-12).reverse().map(r => h('tr', {}, h('td', {}, String(r.id)), h('td', {}, r.label), h('td', {}, r.ackMs ?? '—'),
          h('td', {}, r.visibleMs ?? '—'), h('td', {}, r.diff ?? '—'), h('td', { class: 'small muted' }, r.note ?? (r.status && r.status !== 'succeeded' ? r.status : '')))))));
    };
    measureRender = render;
    return h('details', { class: 'disclosure' }, h('summary', {}, 'Measurements (for validation)'), h('div', {},
      h('p', { class: 'muted small' }, 'Records what this browser displays. Start recording, then use the phone normally. Latency is measured from your click to the first displayed frame that visibly changes (see Download JSON for the exact method).'),
      h('div', { class: 'control-row', style: 'align-items:center' }, toggle, download, clear, h('label', { class: 'small' }, 'Change threshold ', threshold)),
      live, table));
  }
  const measureTimer = setInterval(async () => {
    recorder.tick();
    if (measuring) {
      try {
        const { diagnostics: d } = await get(`/api/phones/${phoneId}/diagnostics`);
        if (d.phone?.video?.receiverFps !== undefined) receiverFpsSamples.push({ at: Date.now(), fps: d.phone.video.receiverFps, frames: d.phone.video.frames });
        if (receiverFpsSamples.length > 2000) receiverFpsSamples.shift();
      } catch { /* next tick */ }
    }
    measureRender();
  }, 2000);

  refresh(); loadHistory();
  const timer = setInterval(refresh, 1500);
  const historyTimer = setInterval(loadHistory, 6000);
  const onRefresh = () => refresh();
  window.addEventListener('nt:refresh', onRefresh);
  return { el, destroy() { destroyed = true; preview.stop(); clearInterval(timer); clearInterval(historyTimer); clearInterval(measureTimer); window.removeEventListener('nt:refresh', onRefresh); } };
}

function unavailableList() {
  return h('details', { class: 'disclosure' }, h('summary', {}, 'Not available remotely yet'), h('div', {},
    h('ul', { class: 'unavailable', style: 'margin:0;padding-left:18px' },
      h('li', {}, h('b', {}, 'Reconnecting screen mirroring.'), ' If video stops, our team reconnects it at the rack. Controls may still work meanwhile.'),
      h('li', {}, h('b', {}, 'Restarting the phone’s USB connection or rebinding it.'), ' Our team handles this at the rack.'),
      h('li', {}, h('b', {}, 'Right-click, scroll wheel, pinch and multi-finger gestures.')),
      h('li', {}, h('b', {}, 'Emoji and non-English characters, copy and paste.'), ' Typing uses an English (US) keyboard.'),
      h('li', {}, h('b', {}, 'Uploading videos to the phone, posting and account analytics.'), ' Coming in later releases.')),
    h('p', { class: 'muted small' }, 'Some apps handle keyboard input differently — for example, the Search field can drop spaces.')));
}

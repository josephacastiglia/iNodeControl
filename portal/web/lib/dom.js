// Tiny DOM builder. Text is always set as textContent, never parsed as HTML.
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs ?? {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    // CSSOM, not a style attribute: the portal's CSP forbids inline style attributes.
    else if (k === 'style') el.style.cssText = v;
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value') el.value = v;
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, String(v));
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function replace(el, ...children) { el.replaceChildren(); append(el, children); return el; }

export function toast(message, kind = 'ok', ms = 4200) {
  const box = document.getElementById('toasts');
  const t = h('div', { class: `toast ${kind === 'ok' ? '' : kind}` }, message);
  box.append(t);
  setTimeout(() => t.remove(), ms);
}

const PILL = {
  live: 'ok', ready: 'ok', yours: 'mine', teammate: 'warn', operator: 'warn', recovering: 'warn', reconnecting: 'warn',
  stopped: 'bad', unavailable: 'bad', unknown: '',
};
export function pill(state, label, prefix) {
  return h('span', { class: `pill ${PILL[state] ?? ''}`, title: prefix ? `${prefix}: ${label}` : label }, prefix ? `${prefix} · ${label}` : label);
}

export function confirmDialog({ title, body, confirmLabel = 'Confirm', danger = false, requireText = null }) {
  return new Promise(resolve => {
    const input = requireText ? h('input', { type: 'text', 'aria-label': `Type ${requireText} to confirm`, autocomplete: 'off' }) : null;
    const ok = h('button', { class: `btn ${danger ? 'btn-stop' : 'btn-dark'}`, type: 'button', disabled: !!requireText }, confirmLabel);
    const cancel = h('button', { class: 'btn btn-ghost', type: 'button' }, 'Cancel');
    const dlg = h('dialog', {}, h('div', { class: 'dialog-body' }, h('h2', {}, title), typeof body === 'string' ? h('p', {}, body) : body,
      input ? h('label', { class: 'field' }, `Type ${requireText} to confirm`, input) : null, h('div', { class: 'dialog-actions' }, cancel, ok)));
    input?.addEventListener('input', () => { ok.disabled = input.value.trim() !== requireText; });
    const done = v => { dlg.close(); dlg.remove(); resolve(v); };
    ok.addEventListener('click', () => done(requireText ? input.value.trim() : true));
    cancel.addEventListener('click', () => done(false));
    dlg.addEventListener('cancel', e => { e.preventDefault(); done(false); });
    document.body.append(dlg);
    dlg.showModal();
    (input ?? ok).focus();
  });
}

export function showDialog(title, ...content) {
  const close = h('button', { class: 'btn btn-dark', type: 'button' }, 'Close');
  const dlg = h('dialog', {}, h('div', { class: 'dialog-body' }, h('h2', {}, title), ...content, h('div', { class: 'dialog-actions' }, close)));
  close.addEventListener('click', () => { dlg.close(); dlg.remove(); });
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  return dlg;
}

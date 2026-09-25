import { h, toast, confirmDialog } from './dom.js';
import { post } from './api.js';

/** Customer "Stop all": only this customer's phones. Always reachable from the top bar. */
export function stopAllButton() {
  return h('button', { class: 'btn btn-stop', type: 'button', onclick: async () => {
    const ok = await confirmDialog({ title: 'Stop all your phones?', body: 'This immediately cancels queued actions and releases held input on every phone assigned to your account. Each phone then needs Resume before it can be controlled again.', confirmLabel: 'Stop all phones', danger: true });
    if (!ok) return;
    try {
      const r = await post('/api/stop-all');
      const bad = r.results.filter(x => !x.ok);
      toast(bad.length ? `Stopped ${r.results.length - bad.length} of ${r.results.length} phones. ${bad.map(b => `${b.name}: ${b.message}`).join(' ')}` : `Stopped all ${r.results.length} phones.`, bad.length ? 'bad' : 'ok', 7000);
      window.dispatchEvent(new Event('nt:refresh'));
    } catch (err) { toast(err.message, 'bad'); }
  } }, 'Stop all phones');
}


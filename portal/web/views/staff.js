import { h, replace, pill, toast, confirmDialog, showDialog } from '../lib/dom.js';
import { get, post } from '../lib/api.js';
import { formatTime } from '../lib/state.js';
import { gridPreview } from '../lib/frames.js';

const SERVICE_LABEL = { unverified: 'Unverified', in_service: 'In service', maintenance: 'Maintenance', retired: 'Retired' };

export function staffView({ params: [tab = 'racks'], setTitle, setActions, setBanner }) {
  const el = h('div', { style: 'display:grid;gap:18px' });
  const titles = { racks: 'Racks', phones: 'Phones', customers: 'Customers', emergency: 'Emergency stop', audit: 'Audit log' };
  setTitle(titles[tab] ?? 'Staff console');
  setActions(h('a', { class: 'btn btn-danger', href: '#/staff/emergency' }, 'Emergency stop'));
  let timer = null;
  const views = { racks, phones, customers, emergency, audit };
  const cleanup = (views[tab] ?? racks)();
  return { el, destroy() { clearInterval(timer); cleanup?.(); } };

  // ---- racks -----------------------------------------------------------------------
  function racks() {
    const list = h('div', { class: 'table-wrap' });
    const name = h('input', { type: 'text', placeholder: 'e.g. Rack 1 — main office', 'aria-label': 'Rack name', maxlength: 60 });
    const add = h('button', { class: 'btn btn-dark', type: 'button' }, 'Create rack credential');
    add.addEventListener('click', async () => {
      try {
        const r = await post('/api/admin/agents', { name: name.value });
        name.value = '';
        showDialog('Rack credential created',
          h('p', {}, 'Copy this credential into the rack agent’s credential file now. It is shown only once and cannot be recovered; if it is lost, revoke it and create a new one.'),
          h('div', { class: 'secret-box' }, r.credential),
          h('p', { class: 'muted small' }, 'Store it with restricted file permissions on the rack PC. Never paste it into chat or email.'));
        load();
      } catch (err) { toast(err.message, 'bad'); }
    });
    el.append(h('section', { class: 'card' }, h('h2', {}, 'Rack agents'),
      h('p', { class: 'muted small' }, 'Each rack PC runs the NodeTheory rack agent, which connects out to this portal. Revoking a credential disconnects that rack immediately.'),
      h('div', { class: 'form-row' }, name, add)), list);
    const portalLine = h('p', { class: 'muted small mono' });
    el.append(portalLine);
    async function load() {
      const { agents, portalProcess: pp, previews } = await get('/api/admin/summary');
      portalLine.textContent = `Portal PID ${pp.pid} · ${pp.rssMB} MB resident · ${pp.heapMB} MB heap · preview cache ${previews.frames} frames / ${Math.round(previews.bytes / 1024)} KB · ${previews.waiters} waiting viewers`;
      replace(list, h('table', {}, h('thead', {}, h('tr', {}, ['Rack', 'Connection', 'Kernel', 'Phones reported', 'Previews', 'Agent process', 'Last connected', ''].map(t => h('th', {}, t)))),
        h('tbody', {}, agents.length ? agents.map(a => h('tr', {},
          h('td', {}, h('b', {}, a.name), h('div', { class: 'mono muted' }, a.id)),
          h('td', {}, a.revoked_at ? pill('stopped', 'Revoked') : a.online ? pill('live', 'Connected') : pill('unknown', 'Offline')),
          h('td', {}, !a.kernel ? '—' : !a.kernel.reachable ? pill('unavailable', 'Not responding') : a.kernel.simulated ? pill('teammate', 'SIMULATOR') : a.kernel.compatible ? pill('live', 'Compatible') : pill('unavailable', 'Incompatible'),
            a.kernel?.reason ? h('div', { class: 'muted small' }, a.kernel.reason) : null),
          h('td', {}, String(a.phonesReported)),
          h('td', { class: 'mono small' }, a.previewStats ? `sent ${a.previewStats.sent} · dropped ${a.previewStats.droppedBackpressure} · avg ${(a.previewStats.encodeMsTotal / Math.max(1, a.previewStats.encoded)).toFixed(0)} ms` : '—'),
          h('td', { class: 'mono small' }, a.agentProcess ? `PID ${a.agentProcess.pid} · CPU ${a.agentProcess.cpuPercentOfOneCore ?? '—'}% of 1 core · ${a.agentProcess.rssMB} MB` : '—'),
          h('td', { class: 'small' }, a.last_connected_at ? formatTime(a.last_connected_at, { date: true }) : 'never'),
          h('td', {}, a.revoked_at ? '' : h('button', { class: 'btn btn-danger btn-sm', type: 'button', onclick: async () => {
            if (!(await confirmDialog({ title: `Revoke ${a.name}?`, body: 'The rack disconnects immediately and every phone on it stops accepting remote control until a new credential is installed.', confirmLabel: 'Revoke credential', danger: true }))) return;
            await post(`/api/admin/agents/${a.id}/revoke`); toast('Credential revoked.'); load();
          } }, 'Revoke'))))
          : [h('tr', {}, h('td', { colspan: 8, class: 'empty' }, 'No racks yet. Create a credential to connect the first rack agent.'))])));
    }
    load(); timer = setInterval(load, 4000);
  }

  // ---- phones ----------------------------------------------------------------------
  function phones() {
    const wrap = h('div', { class: 'table-wrap' });
    el.append(h('p', { class: 'muted small' }, 'Phones appear here when a rack reports them. Only phones marked “In service” — verified working at the rack — can be assigned to customers. A plan size is not inventory.'), wrap);
    let customersList = [];
    async function load() {
      const [{ phones: list }, { customers: cs }] = await Promise.all([get('/api/admin/phones'), get('/api/admin/customers')]);
      customersList = cs;
      setBanner(list.some(p => p.simulated) ? 'Some racks are SIMULATED. Their phones are not real.' : null);
      replace(wrap, h('table', {}, h('thead', {}, h('tr', {}, ['Phone', 'Rack report', 'Control', 'Video', 'Service', 'Assigned to', ''].map(t => h('th', {}, t)))),
        h('tbody', {}, list.length ? list.map(row) : [h('tr', {}, h('td', { colspan: 7, class: 'empty' }, 'No phones reported yet.'))])));
    }
    function row(p) {
      const service = h('select', { 'aria-label': 'Service state' }, Object.entries(SERVICE_LABEL).map(([v, l]) => h('option', { value: v, selected: v === p.serviceState }, l)));
      service.addEventListener('change', async () => {
        try { await post(`/api/admin/phones/${p.id}/service`, { state: service.value }); toast('Service state updated.'); }
        catch (err) { toast(err.message, 'bad'); }
        load();
      });
      return h('tr', {},
        h('td', {}, h('b', {}, p.rackName || p.model), h('div', { class: 'mono muted' }, p.deviceId), p.simulated ? pill('teammate', 'SIMULATED') : null),
        h('td', { class: 'small' }, !p.rackOnline ? 'Rack offline' : p.reported ? `Board ${p.board}` : 'Not reported'),
        h('td', {}, !p.reported ? '—' : !p.inputEnabled ? pill('unavailable', 'Not enabled') : p.inputStopped ? pill('stopped', 'Stopped') : p.controlledBy ? pill('teammate', p.controlledBy) : pill('ready', 'Ready')),
        h('td', {}, !p.reported ? '—' : p.videoLive ? pill('live', `Live · ${p.frames} frames`) : pill('unavailable', p.videoState ?? 'offline')),
        h('td', {}, service),
        h('td', {}, p.customerName ? h('div', {}, h('b', {}, p.customerName), h('div', { class: 'small muted' }, p.friendlyName)) : h('span', { class: 'muted' }, 'Unassigned')),
        h('td', {},
          h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => viewPhone(p) }, 'View'),
          p.customerId
            ? h('button', { class: 'btn btn-danger btn-sm', type: 'button', onclick: async () => {
                if (!(await confirmDialog({ title: 'Unassign phone?', body: `${p.customerName} loses access immediately. Any control session ends and queued actions are cancelled.`, confirmLabel: 'Unassign', danger: true }))) return;
                try { await post(`/api/admin/phones/${p.id}/unallocate`); toast('Unassigned.'); } catch (err) { toast(err.message, 'bad'); }
                load();
              } }, 'Unassign')
            : h('button', { class: 'btn btn-dark btn-sm', type: 'button', disabled: p.serviceState !== 'in_service', title: p.serviceState !== 'in_service' ? 'Mark in service first' : null, onclick: () => assign(p) }, 'Assign')));
    }
    function assign(p) {
      const customer = h('select', { 'aria-label': 'Customer' }, customersList.map(c => h('option', { value: c.id }, `${c.name} (${c.allocated}${c.plan_phones ? ` of ${c.plan_phones}` : ''} assigned)`)));
      const name = h('input', { type: 'text', maxlength: 40, placeholder: 'Friendly name, e.g. Studio phone 4', 'aria-label': 'Friendly name' });
      const save = h('button', { class: 'btn btn-dark', type: 'button' }, 'Assign phone');
      const dlg = showDialog('Assign phone to customer', h('label', { class: 'field' }, 'Customer', customer), h('label', { class: 'field' }, 'Name customers see', name), save);
      save.addEventListener('click', async () => {
        try { await post(`/api/admin/phones/${p.id}/allocate`, { customerId: customer.value, friendlyName: name.value }); dlg.close(); toast('Phone assigned.'); load(); }
        catch (err) { toast(err.message, 'bad'); }
      });
    }
    function viewPhone(p) {
      const img = h('img', { alt: 'Phone screen' });
      const kv = h('dl', { class: 'kv' });
      const dlg = showDialog(p.rackName || 'Phone', h('p', { class: 'muted small' }, 'Support view (read-only, low rate).'),
        h('div', { class: 'screen', style: 'aspect-ratio:500/1080;max-height:420px;max-width:200px' }, img), kv);
      const stream = gridPreview(`/api/admin/phones/${p.id}/frame`, img, { intervalMs: 1000 });
      dlg.addEventListener('close', () => stream.stop());
      get(`/api/admin/phones/${p.id}/diagnostics`).then(({ diagnostics: d }) => {
        const rows = [['Rack', `${d.rack.agentId} · ${d.rack.online ? 'online' : 'offline'} · agent ${d.rack.version ?? '?'}`], ...Object.entries(d.phone).map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : String(v)])];
        replace(kv, rows.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)]));
      }).catch(() => {});
    }
    load(); timer = setInterval(load, 5000);
  }

  // ---- customers -------------------------------------------------------------------
  function customers() {
    const list = h('div', { class: 'table-wrap' });
    const cName = h('input', { type: 'text', placeholder: 'Customer name', 'aria-label': 'Customer name', maxlength: 80 });
    const plan = h('select', { 'aria-label': 'Plan' }, h('option', { value: '' }, 'No plan'), h('option', { value: '1' }, 'Pilot · 1 phone'), h('option', { value: '10' }, 'Half box · 10 phones'), h('option', { value: '20' }, 'Full box · 20 phones'));
    const tz = h('input', { type: 'text', value: 'UTC', 'aria-label': 'Time zone', placeholder: 'e.g. America/New_York' });
    const addC = h('button', { class: 'btn btn-dark', type: 'button' }, 'Add customer');
    addC.addEventListener('click', async () => {
      try { await post('/api/admin/customers', { name: cName.value, planPhones: plan.value ? Number(plan.value) : null, timezone: tz.value }); cName.value = ''; toast('Customer added.'); load(); }
      catch (err) { toast(err.message, 'bad'); }
    });
    el.append(h('section', { class: 'card' }, h('h2', {}, 'Add a customer'), h('div', { class: 'form-row' }, cName, plan, tz, addC)), list);
    async function load() {
      const { customers: cs, users } = await get('/api/admin/customers');
      replace(list, h('table', {}, h('thead', {}, h('tr', {}, ['Customer', 'Plan', 'Phones assigned', 'Status', 'Users', ''].map(t => h('th', {}, t)))),
        h('tbody', {}, cs.length ? cs.map(c => h('tr', {},
          h('td', {}, h('b', {}, c.name), h('div', { class: 'small muted' }, c.timezone)),
          h('td', {}, c.plan_phones ? `${c.plan_phones} phones` : '—'),
          h('td', {}, `${c.allocated}${c.plan_phones ? ` of ${c.plan_phones}` : ''}`, c.plan_phones && c.allocated < c.plan_phones ? h('div', { class: 'small muted' }, `${c.plan_phones - c.allocated} still to assign from verified inventory`) : null),
          h('td', {}, c.status === 'active' ? pill('live', 'Active') : pill('stopped', 'Suspended')),
          h('td', { class: 'small' }, users.filter(u => u.customer_id === c.id).map(u => h('div', {}, `${u.name} · ${u.email} · ${u.role === 'customer_admin' ? 'admin' : 'member'}${u.disabled_at ? ' (disabled)' : ''}`))),
          h('td', {},
            h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => addUser(c) }, 'Add user'),
            h('button', { class: 'btn btn-danger btn-sm', type: 'button', onclick: async () => {
              const next = c.status === 'active' ? 'suspended' : 'active';
              if (next === 'suspended' && !(await confirmDialog({ title: `Suspend ${c.name}?`, body: 'Their users are signed out and all control sessions end.', confirmLabel: 'Suspend', danger: true }))) return;
              await post(`/api/admin/customers/${c.id}/status`, { status: next }); load();
            } }, c.status === 'active' ? 'Suspend' : 'Reactivate'))))
          : [h('tr', {}, h('td', { colspan: 6, class: 'empty' }, 'No customers yet.'))])));
    }
    function addUser(c) {
      const email = h('input', { type: 'email', 'aria-label': 'Email' });
      const name = h('input', { type: 'text', 'aria-label': 'Name' });
      const role = h('select', { 'aria-label': 'Role' }, h('option', { value: 'customer_admin' }, 'Account admin'), h('option', { value: 'customer_member' }, 'Member'));
      const pw = h('input', { type: 'password', autocomplete: 'new-password', 'aria-label': 'Temporary password' });
      const save = h('button', { class: 'btn btn-dark', type: 'button' }, 'Create user');
      const dlg = showDialog(`Add user to ${c.name}`, h('label', { class: 'field' }, 'Email', email), h('label', { class: 'field' }, 'Name', name), h('label', { class: 'field' }, 'Role', role),
        h('label', { class: 'field' }, 'Temporary password (10+ characters, share securely)', pw), save);
      save.addEventListener('click', async () => {
        try { await post('/api/admin/users', { customerId: c.id, email: email.value, name: name.value, role: role.value, password: pw.value }); pw.value = ''; dlg.close(); toast('User created.'); load(); }
        catch (err) { toast(err.message, 'bad'); }
      });
    }
    load();
  }

  // ---- emergency stop --------------------------------------------------------------------
  function emergency() {
    const scope = h('select', { 'aria-label': 'Scope' }, h('option', { value: '' }, 'All connected racks'));
    get('/api/admin/agents').then(({ agents }) => agents.filter(a => a.online).forEach(a => scope.append(h('option', { value: a.id }, a.name))));
    const out = h('div');
    const go = h('button', { class: 'btn btn-stop', type: 'button' }, 'Emergency stop');
    go.addEventListener('click', async () => {
      const typed = await confirmDialog({ title: 'Emergency stop', body: 'Stops input on every enabled phone in scope — every customer, and the rack operators’ own consoles. Queued actions are cancelled and held input is released. Each phone then needs Resume.', confirmLabel: 'Stop everything', danger: true, requireText: 'STOP' });
      if (!typed) return;
      try {
        const r = await post('/api/admin/emergency-stop', { confirm: typed, ...(scope.value ? { agentId: scope.value } : {}) });
        replace(out, h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Rack'), h('th', {}, 'Result'))),
          h('tbody', {}, r.results.map(x => h('tr', {}, h('td', { class: 'mono' }, x.agentId), h('td', {}, x.ok ? `${x.phones.filter(p => p.ok).length}/${x.phones.length} phones stopped` : `Not delivered: ${x.message}`)))))));
        toast('Emergency stop sent.', 'warn');
      } catch (err) { toast(err.message, 'bad'); }
    });
    el.append(h('section', { class: 'card danger-zone' }, h('h2', {}, 'Emergency stop'),
      h('p', {}, 'Use this when phones must stop immediately, regardless of who controls them. Customers’ own “Stop all” only affects their own phones; this affects everyone.'),
      h('div', { class: 'form-row' }, scope, go), out));
  }

  // ---- audit -------------------------------------------------------------------------
  function audit() {
    const wrap = h('div', { class: 'table-wrap' });
    el.append(wrap);
    const row = e => h('tr', {},
      h('td', { class: 'mono' }, formatTime(e.at, { date: true })),
      h('td', {}, `${e.actor_type}${e.actor_label ? ` · ${e.actor_label}` : e.actor_id ? ` · ${e.actor_id}` : ''}`),
      h('td', {}, e.action), h('td', {}, e.outcome),
      h('td', { class: 'mono small' }, e.customer_id?.slice(0, 8) ?? ''),
      h('td', { class: 'mono small' }, e.phone_id?.slice(0, 8) ?? ''),
      h('td', { class: 'small muted' }, JSON.stringify(e.detail)));
    get('/api/admin/audit')
      .then(({ entries }) => replace(wrap, h('table', {},
        h('thead', {}, h('tr', {}, ['When', 'Actor', 'Action', 'Outcome', 'Customer', 'Phone', 'Detail'].map(t => h('th', {}, t)))),
        h('tbody', {}, entries.map(row)))))
      .catch(err => toast(err.message, 'bad'));
  }
}

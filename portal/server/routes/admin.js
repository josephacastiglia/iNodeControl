import { HttpError, sendJson } from '../http.js';
import { newId, hashPassword, newAgentCredential } from '../security.js';
import { AuditLog } from '../audit.js';
import { phoneDiagnostics } from '../phones.js';
import { frameHandler } from './customer.js';

const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,20}$/;
const SERVICE_STATES = ['unverified', 'in_service', 'maintenance', 'retired'];

export function registerAdminRoutes(router, ctx) {
  const { db, hub, control, directory, audit, auth } = ctx;
  const actor = user => AuditLog.actorFor(user);

  router.add('GET', '/api/admin/summary', 'staff', ({ res }) => {
    const agents = db.prepare('SELECT id, name, created_at, revoked_at, last_connected_at, last_ip FROM agents ORDER BY created_at').all()
      .map(a => { const c = hub.connection(a.id); return { ...a, online: !!c, version: c?.hello?.version ?? null, kernel: c?.kernel ?? null, phonesReported: c?.phones.size ?? 0, previewStats: c?.previewStats ?? null }; });
    const phoneCounts = db.prepare(`SELECT p.service_state AS state, COUNT(*) AS n, SUM(CASE WHEN a.id IS NULL THEN 0 ELSE 1 END) AS allocated
      FROM phones p LEFT JOIN allocations a ON a.phone_id = p.id AND a.ended_at IS NULL GROUP BY p.service_state`).all();
    sendJson(res, 200, { agents, phoneCounts, activeControl: control.sessions.size, previews: ctx.previews.stats() });
  });

  // ---- customers & users --------------------------------------------------------
  router.add('GET', '/api/admin/customers', 'staff', ({ res }) => {
    const customers = db.prepare(`SELECT c.*, (SELECT COUNT(*) FROM allocations a WHERE a.customer_id = c.id AND a.ended_at IS NULL) AS allocated,
      (SELECT COUNT(*) FROM users u WHERE u.customer_id = c.id) AS users FROM customers c ORDER BY c.name COLLATE NOCASE`).all();
    const users = db.prepare("SELECT id, customer_id, email, name, role, disabled_at FROM users WHERE role != 'staff' ORDER BY name").all();
    sendJson(res, 200, { customers, users });
  });

  router.add('POST', '/api/admin/customers', 'staff', ({ res, user, body, ip }) => {
    const name = String(body.name ?? '').trim();
    const plan = body.planPhones === null || body.planPhones === undefined ? null : Number(body.planPhones);
    const timezone = String(body.timezone ?? 'UTC');
    if (!name || name.length > 80) throw new HttpError(400, 'bad_name', 'Customer name is required.');
    if (plan !== null && ![1, 10, 20].includes(plan)) throw new HttpError(400, 'bad_plan', 'Plans are 1, 10 or 20 phones.');
    try { new Intl.DateTimeFormat('en', { timeZone: timezone }); } catch { throw new HttpError(400, 'bad_timezone', 'Unknown time zone.'); }
    const id = newId();
    db.prepare('INSERT INTO customers (id, name, plan_phones, timezone, created_at) VALUES (?, ?, ?, ?, ?)').run(id, name, plan, timezone, Date.now());
    audit.record({ actor: actor(user), customerId: id, action: 'customer.create', outcome: 'ok', detail: { name, plan }, ip });
    sendJson(res, 201, { id });
  });

  router.add('POST', '/api/admin/customers/:id/status', 'staff', async ({ res, user, params, body, ip }) => {
    const status = body.status === 'suspended' ? 'suspended' : body.status === 'active' ? 'active' : null;
    if (!status) throw new HttpError(400, 'bad_status', 'Status must be active or suspended.');
    const c = db.prepare('SELECT id FROM customers WHERE id = ?').get(params.id);
    if (!c) throw new HttpError(404, 'not_found', 'Customer not found.');
    db.prepare('UPDATE customers SET status = ? WHERE id = ?').run(status, c.id);
    if (status === 'suspended') {
      for (const u of db.prepare('SELECT id FROM users WHERE customer_id = ?').all(c.id)) auth.revokeUserSessions(u.id);
      for (const row of directory.listFor(c.id)) await control.release(row.id, { reason: 'suspended', message: 'Account suspended.', actor: actor(user) });
    }
    audit.record({ actor: actor(user), customerId: c.id, action: 'customer.status', outcome: status, ip });
    sendJson(res, 200, { ok: true });
  });

  router.add('POST', '/api/admin/users', 'staff', async ({ res, user, body, ip }) => {
    const email = String(body.email ?? '').trim().toLowerCase();
    const name = String(body.name ?? '').trim();
    const role = String(body.role ?? '');
    if (!EMAIL.test(email)) throw new HttpError(400, 'bad_email', 'Enter a valid email.');
    if (!name || name.length > 80) throw new HttpError(400, 'bad_name', 'Name is required.');
    if (!['customer_admin', 'customer_member', 'staff'].includes(role)) throw new HttpError(400, 'bad_role', 'Unknown role.');
    const customerId = role === 'staff' ? null : String(body.customerId ?? '');
    if (role !== 'staff' && !db.prepare('SELECT 1 FROM customers WHERE id = ?').get(customerId)) throw new HttpError(404, 'not_found', 'Customer not found.');
    let hash;
    try { hash = await hashPassword(String(body.password ?? '')); } catch (err) { throw new HttpError(400, 'weak_password', err.message); }
    const id = newId();
    try {
      db.prepare('INSERT INTO users (id, customer_id, email, name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)').run(id, customerId, email, name, role, hash, Date.now());
    } catch (err) {
      if (/UNIQUE/.test(err.message)) throw new HttpError(409, 'exists', 'That email already has an account.');
      throw err;
    }
    audit.record({ actor: actor(user), customerId, action: 'user.create', outcome: 'ok', detail: { email, role }, ip });
    sendJson(res, 201, { id });
  });

  router.add('POST', '/api/admin/users/:id/disable', 'staff', ({ res, user, params, ip }) => {
    const target = db.prepare('SELECT id, customer_id FROM users WHERE id = ?').get(params.id);
    if (!target) throw new HttpError(404, 'not_found', 'User not found.');
    if (target.id === user.id) throw new HttpError(400, 'self', 'You cannot disable your own account.');
    db.prepare('UPDATE users SET disabled_at = ? WHERE id = ?').run(Date.now(), target.id);
    auth.revokeUserSessions(target.id);
    for (const s of [...control.sessions.values()]) if (s.userId === target.id) control.release(s.phoneId, { reason: 'user_disabled', message: 'Account disabled.', actor: actor(user) });
    audit.record({ actor: actor(user), customerId: target.customer_id, action: 'user.disable', outcome: 'ok', ip });
    sendJson(res, 200, { ok: true });
  });

  // ---- rack agents ----------------------------------------------------------------
  router.add('GET', '/api/admin/agents', 'staff', ({ res }) => {
    const agents = db.prepare('SELECT id, name, created_at, revoked_at, last_connected_at, last_ip FROM agents ORDER BY created_at').all()
      .map(a => ({ ...a, online: hub.isOnline(a.id), kernel: hub.connection(a.id)?.kernel ?? null }));
    sendJson(res, 200, { agents });
  });

  router.add('POST', '/api/admin/agents', 'staff', ({ res, user, body, ip }) => {
    const name = String(body.name ?? '').trim();
    if (!name || name.length > 60) throw new HttpError(400, 'bad_name', 'Give the rack a name.');
    const cred = newAgentCredential();
    db.prepare('INSERT INTO agents (id, name, secret_hash, created_at, created_by) VALUES (?, ?, ?, ?, ?)').run(cred.id, name, cred.secretHash, Date.now(), user.id);
    audit.record({ actor: actor(user), action: 'agent.create', outcome: 'ok', detail: { agentId: cred.id, name }, ip });
    // The credential is returned exactly once and never stored in plain form.
    sendJson(res, 201, { id: cred.id, credential: cred.credential });
  });

  router.add('POST', '/api/admin/agents/:id/revoke', 'staff', ({ res, user, params, ip }) => {
    const a = db.prepare('SELECT id, revoked_at FROM agents WHERE id = ?').get(params.id);
    if (!a) throw new HttpError(404, 'not_found', 'Rack agent not found.');
    if (!a.revoked_at) db.prepare('UPDATE agents SET revoked_at = ?, revoked_by = ? WHERE id = ?').run(Date.now(), user.id, a.id);
    hub.revoke(a.id);
    audit.record({ actor: actor(user), action: 'agent.revoke', outcome: 'ok', detail: { agentId: a.id }, ip });
    sendJson(res, 200, { ok: true });
  });

  // ---- phones & allocation ----------------------------------------------------------
  router.add('GET', '/api/admin/phones', 'staff', ({ res }) => {
    const phones = directory.all().map(row => {
      const conn = hub.connection(row.agent_id);
      const inv = conn?.phones.get(row.kernel_device_id);
      return {
        id: row.id, agentId: row.agent_id, deviceId: row.kernel_device_id, rackName: row.rack_name, model: row.model,
        serviceState: row.service_state, customerId: row.customer_id, customerName: row.customer_name, friendlyName: row.friendly_name,
        reported: !!inv, rackOnline: !!conn, simulated: !!conn?.kernel?.simulated,
        board: inv?.input.boardPid ?? null, inputEnabled: inv?.input.enabled ?? false, inputStopped: inv?.input.stopped ?? false,
        videoState: inv?.video.state ?? null, videoLive: inv?.video.live ?? false, frames: inv?.video.frames ?? 0,
        controlledBy: control.get(row.id)?.userName ?? null,
      };
    });
    sendJson(res, 200, { phones });
  });

  router.add('GET', '/api/admin/phones/:id/diagnostics', 'staff', ({ res, params }) => {
    sendJson(res, 200, { diagnostics: phoneDiagnostics(directory.any(params.id), hub) });
  });

  router.add('GET', '/api/admin/phones/:id/frame', 'staff', frameHandler(ctx, (_user, id) => directory.any(id)));

  router.add('POST', '/api/admin/phones/:id/service', 'staff', ({ res, user, params, body, ip }) => {
    const row = directory.any(params.id);
    const state = String(body.state ?? '');
    if (!SERVICE_STATES.includes(state)) throw new HttpError(400, 'bad_state', 'Unknown service state.');
    if (state !== 'in_service' && row.allocation_id) throw new HttpError(409, 'allocated', 'Unassign the phone before taking it out of service.');
    db.prepare('UPDATE phones SET service_state = ?, service_note = ? WHERE id = ?').run(state, String(body.note ?? '').slice(0, 200), row.id);
    audit.record({ actor: actor(user), phoneId: row.id, action: 'phone.service', outcome: state, detail: { note: body.note }, ip });
    sendJson(res, 200, { ok: true });
  });

  router.add('POST', '/api/admin/phones/:id/allocate', 'staff', ({ res, user, params, body, ip }) => {
    const row = directory.any(params.id);
    if (row.service_state !== 'in_service') throw new HttpError(409, 'not_in_service', 'Only phones verified as in service can be assigned to customers.');
    if (row.allocation_id) throw new HttpError(409, 'allocated', 'This phone is already assigned.');
    const customer = db.prepare('SELECT id, plan_phones FROM customers WHERE id = ?').get(String(body.customerId ?? ''));
    if (!customer) throw new HttpError(404, 'not_found', 'Customer not found.');
    const name = String(body.friendlyName ?? '').trim() || `Phone ${db.prepare('SELECT COUNT(*) AS n FROM allocations WHERE customer_id = ? AND ended_at IS NULL').get(customer.id).n + 1}`;
    const id = newId();
    try {
      db.prepare('INSERT INTO allocations (id, phone_id, customer_id, friendly_name, started_at, started_by) VALUES (?, ?, ?, ?, ?, ?)').run(id, row.id, customer.id, name.slice(0, 40), Date.now(), user.id);
    } catch (err) { if (/UNIQUE/.test(err.message)) throw new HttpError(409, 'allocated', 'This phone is already assigned.'); throw err; }
    audit.record({ actor: actor(user), customerId: customer.id, phoneId: row.id, action: 'phone.allocate', outcome: 'ok', detail: { name }, ip });
    sendJson(res, 201, { id });
  });

  router.add('POST', '/api/admin/phones/:id/unallocate', 'staff', async ({ res, user, params, ip }) => {
    const row = directory.any(params.id);
    if (!row.allocation_id) throw new HttpError(409, 'not_allocated', 'This phone is not assigned.');
    // End control first so queued work for the previous customer is cancelled at the rack.
    await control.release(row.id, { reason: 'unallocated', message: 'This phone was reassigned.', actor: actor(user), ip });
    db.prepare('UPDATE allocations SET ended_at = ?, ended_by = ? WHERE id = ?').run(Date.now(), user.id, row.allocation_id);
    ctx.previews.dropPhone(row.id);
    audit.record({ actor: actor(user), customerId: row.customer_id, phoneId: row.id, action: 'phone.unallocate', outcome: 'ok', ip });
    sendJson(res, 200, { ok: true });
  });

  // ---- emergency stop (staff only; separate from customers' Stop all) -------------------
  router.add('POST', '/api/admin/emergency-stop', 'staff', async ({ res, user, body, ip }) => {
    if (body.confirm !== 'STOP') throw new HttpError(400, 'confirm', 'Type STOP to confirm an emergency stop.');
    const agentIds = body.agentId ? [String(body.agentId)] : [...hub.conns.keys()];
    const results = [];
    for (const s of [...control.sessions.values()]) if (agentIds.includes(s.agentId)) control.end(s.phoneId, 'emergency', 'Emergency stop by NodeTheory staff.');
    await Promise.all(agentIds.map(async agentId => {
      try { const r = await hub.request(agentId, 'emergencyStop', {}, 20_000); results.push({ agentId, ok: true, phones: r.results }); }
      catch (err) { results.push({ agentId, ok: false, message: err.message }); }
    }));
    audit.record({ actor: actor(user), action: 'emergency_stop', outcome: results.every(r => r.ok) ? 'ok' : 'partial', detail: { agents: agentIds.length }, ip });
    sendJson(res, 200, { results });
  });

  router.add('GET', '/api/admin/audit', 'staff', ({ res, query }) => {
    const customerId = query.get('customer');
    const rows = db.prepare(`SELECT * FROM audit_log WHERE (? IS NULL OR customer_id = ?) ORDER BY id DESC LIMIT 200`).all(customerId ?? null, customerId ?? null);
    sendJson(res, 200, { entries: rows.map(r => ({ ...r, detail: JSON.parse(r.detail) })) });
  });
}

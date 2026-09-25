import { HttpError, sendJson } from '../http.js';
import { newId } from '../security.js';
import { AuditLog } from '../audit.js';
import { AgentNoAnswerError, AgentUnavailableError, AgentRequestError } from '../agent-hub.js';
import { validateAction, ActionError, describeAction, commandTimeoutMs, isCoordinateAction } from '../actions.js';
import { phoneStatus, phoneDiagnostics } from '../phones.js';

const MAX_GROUP = 20;
const MAX_INFLIGHT_PER_PHONE = 4;

function phoneIdList(value) {
  if (!Array.isArray(value) || value.length === 0) throw new HttpError(400, 'bad_request', 'Choose at least one phone.');
  const ids = [...new Set(value)];
  if (ids.length > MAX_GROUP || ids.some(id => typeof id !== 'string')) throw new HttpError(400, 'bad_request', `Choose up to ${MAX_GROUP} phones.`);
  return ids;
}

export function registerCustomerRoutes(router, ctx) {
  const { db, hub, control, previews, directory, audit } = ctx;
  const insertCommand = db.prepare(`INSERT INTO commands (id, customer_id, user_id, phone_id, group_id, kind, summary, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`);
  const finishCommand = db.prepare('UPDATE commands SET status = ?, message = ?, finished_at = ?, elapsed_ms = ? WHERE id = ?');
  const status = (row, user) => phoneStatus(row, { hub, control, previews, user });

  /**
   * Runs one validated action on one phone for its controller. Ownership and control are
   * checked again here, immediately before dispatch, and again by the agent when the
   * command reaches the front of the phone's queue.
   */
  async function runCommand(user, row, action, { groupId = null, ip } = {}) {
    const id = newId();
    const now = Date.now();
    const summary = describeAction(action);
    const reject = message => {
      insertCommand.run(id, user.customerId, user.id, row.id, groupId, action.type, summary, 'rejected', now);
      finishCommand.run('rejected', message, Date.now(), 0, id);
      return { id, status: 'rejected', message };
    };
    try { row = directory.owned(user.customerId, row.id); } catch { return reject('This phone is no longer assigned to your account.'); }
    const session = control.get(row.id);
    if (!session || session.userId !== user.id || session.allocationId !== row.allocation_id) return reject('Take control of this phone first.');
    if (session.inflight >= MAX_INFLIGHT_PER_PHONE) return reject('This phone is still working through earlier actions.');
    insertCommand.run(id, user.customerId, user.id, row.id, groupId, action.type, summary, 'sent', now);
    session.inflight++;
    session.heartbeatAt = Date.now();
    let result;
    try {
      const res = await hub.request(row.agent_id, 'command', { kernelId: row.kernel_device_id, sessionId: session.sessionId, commandId: id, action }, commandTimeoutMs(action));
      result = { status: ['succeeded', 'failed', 'cancelled', 'unknown', 'rejected'].includes(res?.status) ? res.status : 'unknown', message: String(res?.message ?? '') };
    } catch (err) {
      if (err instanceof AgentUnavailableError) result = { status: 'failed', message: 'The rack is offline; nothing was sent.' };
      else if (err instanceof AgentRequestError) result = { status: 'rejected', message: err.message };
      else {
        result = { status: 'unknown', message: 'The rack did not confirm this action. It may have happened — check the screen before repeating it.' };
        if (err instanceof AgentNoAnswerError && hub.isOnline(row.agent_id)) {
          // Never retry. Stop the phone so nothing stale follows an uncertain action.
          control.end(row.id, 'unknown', 'Control ended because an action was not confirmed.');
          hub.request(row.agent_id, 'stop', { kernelIds: [row.kernel_device_id], reason: 'Action not confirmed by the rack.' }).catch(() => {});
        }
      }
    } finally {
      session.inflight--;
    }
    finishCommand.run(result.status, result.message.slice(0, 300), Date.now(), Date.now() - now, id);
    audit.record({ actor: AuditLog.actorFor(user), customerId: user.customerId, phoneId: row.id, action: 'input.' + action.type,
      outcome: result.status, detail: { summary, groupId, message: result.status === 'succeeded' ? undefined : result.message }, ip });
    return { id, ...result, elapsedMs: Date.now() - now };
  }

  async function stopPhones(user, rows, reason, ip) {
    const byAgent = new Map();
    for (const row of rows) {
      control.end(row.id, 'stopped', 'Stopped.');
      if (!byAgent.has(row.agent_id)) byAgent.set(row.agent_id, []);
      byAgent.get(row.agent_id).push(row);
    }
    const results = [];
    await Promise.all([...byAgent].map(async ([agentId, list]) => {
      let res;
      try { res = await hub.request(agentId, 'stop', { kernelIds: list.map(r => r.kernel_device_id), reason }, 15_000); }
      catch (err) { res = { error: err instanceof AgentUnavailableError ? 'The rack is offline, so Stop could not be delivered.' : 'The rack did not confirm Stop.' }; }
      for (const row of list) {
        const r = res.results?.find(x => x.kernelId === row.kernel_device_id);
        const ok = !!r?.ok;
        const message = res.error ?? (ok ? 'Stopped.' : r?.message || 'Stop could not be confirmed.');
        results.push({ phoneId: row.id, name: row.friendly_name, ok, message });
        audit.record({ actor: AuditLog.actorFor(user), customerId: user.customerId, phoneId: row.id, action: 'input.stop', outcome: ok ? 'ok' : 'unconfirmed', detail: { reason, message }, ip });
      }
    }));
    return results;
  }

  // ---- phones ------------------------------------------------------------------
  router.add('GET', '/api/phones', 'customer', ({ res, user }) => {
    const rows = directory.listFor(user.customerId);
    sendJson(res, 200, { phones: rows.map(r => status(r, user)), timezone: user.timezone });
  });

  router.add('GET', '/api/phones/:id', 'customer', ({ res, user, params }) => {
    sendJson(res, 200, { phone: status(directory.owned(user.customerId, params.id), user) });
  });

  router.add('GET', '/api/phones/:id/diagnostics', 'customer', ({ res, user, params }) => {
    const row = directory.owned(user.customerId, params.id);
    const d = phoneDiagnostics(row, hub);
    // Customers see their phone's technical detail, not other rack internals.
    sendJson(res, 200, { diagnostics: { phone: d.phone, rack: { online: d.rack.online, simulated: !!d.rack.kernel?.simulated } } });
  });

  router.add('POST', '/api/phones/:id/name', 'customer_admin', ({ res, user, params, body, ip }) => {
    const row = directory.owned(user.customerId, params.id);
    const name = String(body.name ?? '').trim();
    if (!name || name.length > 40) throw new HttpError(400, 'bad_name', 'Use a name of 1–40 characters.');
    db.prepare('UPDATE allocations SET friendly_name = ? WHERE id = ?').run(name, row.allocation_id);
    audit.record({ actor: AuditLog.actorFor(user), customerId: user.customerId, phoneId: row.id, action: 'phone.rename', outcome: 'ok', detail: { name }, ip });
    sendJson(res, 200, { ok: true });
  });

  router.add('GET', '/api/phones/:id/frame', 'customer', frameHandler(ctx, (user, id) => directory.owned(user.customerId, id)));

  router.add('GET', '/api/phones/:id/commands', 'customer', ({ res, user, params }) => {
    const row = directory.owned(user.customerId, params.id);
    const list = db.prepare(`SELECT c.id, c.kind, c.summary, c.status, c.message, c.created_at, c.elapsed_ms, c.group_id, u.name AS user_name
      FROM commands c JOIN users u ON u.id = c.user_id WHERE c.phone_id = ? AND c.customer_id = ? ORDER BY c.created_at DESC LIMIT 50`).all(row.id, user.customerId);
    sendJson(res, 200, { commands: list });
  });

  // ---- control -----------------------------------------------------------------
  router.add('POST', '/api/phones/:id/control', 'customer', async ({ res, user, params, ip }) => {
    const row = directory.owned(user.customerId, params.id);
    await control.acquire(user, row, ip);
    sendJson(res, 200, { phone: status(row, user) });
  });

  router.add('POST', '/api/phones/:id/control/heartbeat', 'customer', ({ res, user, params }) => {
    const row = directory.owned(user.customerId, params.id);
    const s = control.heartbeat(user, row.id);
    sendJson(res, 200, { inControl: !!s, phone: status(row, user) });
  });

  router.add('POST', '/api/phones/:id/control/release', 'customer', async ({ res, user, params, ip }) => {
    const row = directory.owned(user.customerId, params.id);
    const s = control.get(row.id);
    if (s && s.userId !== user.id) throw new HttpError(409, 'not_yours', 'Someone else is controlling this phone.');
    await control.release(row.id, { reason: 'released', message: 'You released control.', actor: AuditLog.actorFor(user), ip });
    sendJson(res, 200, { phone: status(row, user) });
  });

  router.add('POST', '/api/phones/:id/actions', 'customer', async ({ res, user, params, body, ip }) => {
    const row = directory.owned(user.customerId, params.id);
    let action;
    try { action = validateAction(body.action, directory.size(row)); }
    catch (err) { if (err instanceof ActionError) throw new HttpError(400, 'bad_action', err.message); throw err; }
    const result = await runCommand(user, row, action, { ip });
    sendJson(res, 200, { command: result, phone: status(row, user) });
  });

  router.add('POST', '/api/phones/:id/stop', 'customer', async ({ res, user, params, ip }) => {
    const row = directory.owned(user.customerId, params.id);
    const [result] = await stopPhones(user, [row], 'Stopped by customer.', ip);
    sendJson(res, 200, { result, phone: status(row, user) });
  });

  router.add('POST', '/api/phones/:id/resume', 'customer', async ({ res, user, params, body, ip }) => {
    const row = directory.owned(user.customerId, params.id);
    if (!Number.isInteger(body.generation)) throw new HttpError(400, 'bad_request', 'Refresh and try again.');
    let r;
    try { r = await hub.request(row.agent_id, 'resume', { kernelId: row.kernel_device_id, generation: body.generation }); }
    catch (err) { throw new HttpError(503, 'rack_unavailable', err instanceof AgentRequestError ? err.message : 'The rack is not responding.'); }
    audit.record({ actor: AuditLog.actorFor(user), customerId: user.customerId, phoneId: row.id, action: 'input.resume', outcome: r?.ok ? 'ok' : 'refused', detail: { message: r?.message }, ip });
    if (!r?.ok) {
      const changed = /state changed/i.test(r?.message ?? '');
      throw new HttpError(409, changed ? 'state_changed' : 'cannot_resume', changed
        ? 'This phone’s state changed since you looked at it. Check the screen, then resume again.'
        : 'The phone can’t resume yet. If this continues, contact support.');
    }
    sendJson(res, 200, { phone: status(row, user) });
  });

  router.add('POST', '/api/stop-all', 'customer', async ({ res, user, ip }) => {
    const rows = directory.listFor(user.customerId);
    const results = await stopPhones(user, rows, 'Stop all by customer.', ip);
    sendJson(res, 200, { results });
  });

  // ---- groups (explicit selection, individual outcomes) ----------------------------
  router.add('POST', '/api/groups/control', 'customer', async ({ res, user, body, ip }) => {
    const rows = phoneIdList(body.phoneIds).map(id => directory.owned(user.customerId, id));
    const results = await Promise.all(rows.map(async row => {
      try { await control.acquire(user, row, ip); return { phoneId: row.id, name: row.friendly_name, ok: true, message: 'In control.' }; }
      catch (err) { return { phoneId: row.id, name: row.friendly_name, ok: false, message: err.message }; }
    }));
    sendJson(res, 200, { results });
  });

  router.add('POST', '/api/groups/release', 'customer', async ({ res, user, body, ip }) => {
    const rows = phoneIdList(body.phoneIds).map(id => directory.owned(user.customerId, id));
    await Promise.all(rows.map(row => {
      const s = control.get(row.id);
      return s && s.userId === user.id ? control.release(row.id, { reason: 'released', message: 'You released control.', actor: AuditLog.actorFor(user), ip }) : null;
    }));
    sendJson(res, 200, { ok: true });
  });

  router.add('POST', '/api/groups/stop', 'customer', async ({ res, user, body, ip }) => {
    const rows = phoneIdList(body.phoneIds).map(id => directory.owned(user.customerId, id));
    sendJson(res, 200, { results: await stopPhones(user, rows, 'Group stop by customer.', ip) });
  });

  router.add('POST', '/api/groups/actions', 'customer', async ({ res, user, body, ip }) => {
    let rows = phoneIdList(body.phoneIds).map(id => directory.owned(user.customerId, id));
    const skipped = [];
    let retryOf = null;
    if (body.retryOf !== undefined) {
      const original = db.prepare('SELECT id, kind FROM group_actions WHERE id = ? AND customer_id = ?').get(String(body.retryOf), user.customerId);
      if (!original) throw new HttpError(404, 'not_found', 'Original group action not found.');
      if (body.action?.type !== original.kind) throw new HttpError(400, 'bad_retry', 'A retry must repeat the same kind of action.');
      const outcomes = new Map(db.prepare('SELECT phone_id, status FROM commands WHERE group_id = ? AND customer_id = ?').all(original.id, user.customerId).map(c => [c.phone_id, c.status]));
      if (rows.some(r => !outcomes.has(r.id))) throw new HttpError(400, 'bad_retry', 'A retry can only include phones from the original action.');
      // Phones that already succeeded, or whose outcome is uncertain, never receive it again.
      rows = rows.filter(r => {
        const s = outcomes.get(r.id);
        if (s === 'succeeded' || s === 'unknown' || s === 'sent') { skipped.push({ phoneId: r.id, name: r.friendly_name, status: 'skipped', message: s === 'succeeded' ? 'Already succeeded; not sent again.' : 'Outcome was uncertain; check this phone before repeating.' }); return false; }
        return true;
      });
      retryOf = original.id;
    }
    const sizes = rows.map(r => directory.size(r));
    let action;
    try {
      if (!body.action || typeof body.action !== 'object') throw new ActionError('Missing action.');
      if (isCoordinateAction(body.action) && new Set(sizes.map(s => `${s.width}x${s.height}`)).size > 1)
        throw new ActionError('Tap and swipe need phones with the same screen size. Use keys or text for mixed groups.');
      action = validateAction(body.action, sizes[0] ?? { width: 2, height: 2 });
    } catch (err) { if (err instanceof ActionError) throw new HttpError(400, 'bad_action', err.message); throw err; }
    const groupId = newId();
    db.prepare('INSERT INTO group_actions (id, customer_id, user_id, kind, summary, retry_of, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)')
      .run(groupId, user.customerId, user.id, action.type, describeAction(action), retryOf, Date.now());
    const results = await Promise.all(rows.map(async row => ({ phoneId: row.id, name: row.friendly_name, ...(await runCommand(user, row, action, { groupId, ip })) })));
    audit.record({ actor: AuditLog.actorFor(user), customerId: user.customerId, action: 'group.' + action.type, outcome: `${results.filter(r => r.status === 'succeeded').length}/${results.length} succeeded`,
      detail: { groupId, retryOf, summary: describeAction(action) }, ip });
    sendJson(res, 200, { groupId, results: [...results, ...skipped] });
  });

  // ---- activity ------------------------------------------------------------------
  router.add('GET', '/api/activity', 'customer', ({ res, user, query }) => {
    const before = Number.parseInt(query.get('before') ?? '', 10);
    const phoneId = query.get('phone');
    const rows = db.prepare(`SELECT l.id, l.at, l.actor_type, l.actor_label, l.phone_id, l.action, l.outcome, l.detail, a.friendly_name AS phone_name
      FROM audit_log l LEFT JOIN allocations a ON a.phone_id = l.phone_id AND a.customer_id = l.customer_id AND a.ended_at IS NULL
      WHERE l.customer_id = ? AND (? IS NULL OR l.id < ?) AND (? IS NULL OR l.phone_id = ?)
      ORDER BY l.id DESC LIMIT 100`).all(user.customerId, Number.isFinite(before) ? before : null, Number.isFinite(before) ? before : null, phoneId ?? null, phoneId ?? null);
    sendJson(res, 200, { entries: rows.map(r => ({ ...r, detail: JSON.parse(r.detail) })) });
  });
}

/** Shared by customers (own phones) and staff (support view). */
export function frameHandler(ctx, resolveRow) {
  const { hub, previews } = ctx;
  return async ({ req, res, user, params, query }) => {
    const row = resolveRow(user, params.id);
    const tier = query.get('tier') === 'focus' ? 'focus' : 'grid';
    if (hub.isOnline(row.agent_id) && previews.shouldRenewWatch(row.id, tier))
      hub.notify(row.agent_id, 'watch', { kernelId: row.kernel_device_id, tier, ttlMs: 8000 });
    const after = Number.parseInt(query.get('after') ?? '', 10);
    let frame;
    if (Number.isFinite(after) && after >= 0 && query.get('wait') === '0') {
      // Short poll (grid tiles): newer frame or nothing, immediately. Keeps browser
      // connections free for control requests on HTTP/1.1.
      const latest = previews.latest(row.id, tier);
      frame = latest && latest.seq > after ? latest : null;
    } else if (Number.isFinite(after) && after >= 0) {
      const abort = new AbortController();
      req.on('close', () => abort.abort());
      frame = await previews.waitNewer(row.id, tier, after, abort.signal);
      if (frame === 'busy') throw new HttpError(429, 'busy', 'Too many viewers; slow down.');
    } else frame = previews.latest(row.id, tier);
    if (res.destroyed) return;
    if (!frame) { res.writeHead(204, { 'cache-control': 'no-store', 'x-frame-seq': String(Number.isFinite(after) ? after : 0) }); return res.end(); }
    const h = frame.header;
    res.writeHead(200, {
      'content-type': 'image/jpeg', 'content-length': frame.jpeg.length, 'cache-control': 'no-store, private',
      'x-frame-seq': String(frame.seq), 'x-source-width': String(h.srcWidth), 'x-source-height': String(h.srcHeight),
      'x-frame-age-ms': String(Date.now() - frame.receivedAt), 'x-captured-at': String(h.capturedAt),
    });
    res.end(frame.jpeg);
  };
}

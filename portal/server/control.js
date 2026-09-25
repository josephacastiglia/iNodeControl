import { HttpError } from './http.js';
import { newId } from './security.js';
import { AgentUnavailableError, AgentRequestError } from './agent-hub.js';
import { AuditLog } from './audit.js';

const HEARTBEAT_TIMEOUT_MS = 35_000;

const ACQUIRE_REFUSALS = {
  owned_elsewhere: [409, 'operator_control', 'Our operators are using this phone at the rack right now. Try again shortly.'],
  busy: [409, 'in_use', 'This phone is already being controlled.'],
  stopped: [409, 'stopped', 'This phone is stopped. Resume it before taking control.'],
  recovering: [409, 'recovering', 'This phone is finishing a previous action. Try again in a moment.'],
  release_failed: [409, 'needs_support', 'This phone needs our team to check it before it can be controlled.'],
  input_unavailable: [409, 'input_unavailable', 'Remote control is not available for this phone right now. Our team has been notified.'],
  kernel_incompatible: [409, 'input_unavailable', 'Remote control is not available on this rack yet.'],
  kernel_unreachable: [503, 'rack_unavailable', 'The rack is not responding. Try again shortly.'],
};

/**
 * One portal controller per phone, mirroring the kernel's one-lease-per-phone rule.
 * A session exists only while the browser keeps sending heartbeats; the rack agent
 * holds the actual kernel lease on the session's behalf.
 */
export class ControlManager {
  constructor({ hub, audit }) {
    this.hub = hub; this.audit = audit;
    this.sessions = new Map();   // phoneId -> session
    this.byId = new Map();       // sessionId -> session
    this.pending = new Set();
    this.lastEnded = new Map();  // phoneId -> { reason, message, at }
    this.sweepTimer = setInterval(() => this.sweep(), 5_000);
    this.sweepTimer.unref();
    hub.on('event', (agentId, evt) => this.#onAgentEvent(agentId, evt));
    hub.on('disconnected', agentId => this.#onAgentDisconnected(agentId));
  }

  get(phoneId) { return this.sessions.get(phoneId) ?? null; }

  #remove(session, reason, message) {
    if (this.sessions.get(session.phoneId) === session) this.sessions.delete(session.phoneId);
    this.byId.delete(session.sessionId);
    this.lastEnded.set(session.phoneId, { reason, message, at: Date.now(), userId: session.userId });
  }

  async acquire(user, phone, ip) {
    const existing = this.sessions.get(phone.id);
    if (existing) {
      if (existing.userId === user.id && existing.allocationId === phone.allocation_id) { existing.heartbeatAt = Date.now(); return existing; }
      throw new HttpError(409, 'in_use', `${existing.userName} is controlling this phone.`, { holder: existing.userName });
    }
    if (this.pending.has(phone.id)) throw new HttpError(409, 'in_use', 'Control of this phone is already being requested.');
    if (!this.hub.isOnline(phone.agent_id)) throw new HttpError(503, 'rack_offline', 'The rack is offline. Try again shortly.');
    this.pending.add(phone.id);
    const session = {
      sessionId: newId(), phoneId: phone.id, userId: user.id, userName: user.name, customerId: user.customerId,
      allocationId: phone.allocation_id, agentId: phone.agent_id, kernelId: phone.kernel_device_id,
      startedAt: Date.now(), heartbeatAt: Date.now(), inflight: 0,
    };
    let result;
    try {
      result = await this.hub.request(phone.agent_id, 'acquire', { kernelId: phone.kernel_device_id, sessionId: session.sessionId });
    } catch (err) {
      const reason = err instanceof AgentRequestError ? err.reason : err instanceof AgentUnavailableError ? 'kernel_unreachable' : 'kernel_unreachable';
      this.audit.record({ actor: AuditLog.actorFor(user), customerId: user.customerId, phoneId: phone.id, action: 'control.acquire', outcome: 'failed', detail: { reason }, ip });
      const [status, code, message] = ACQUIRE_REFUSALS[reason] ?? [503, 'rack_unavailable', err.message];
      throw new HttpError(status, code, message);
    } finally {
      this.pending.delete(phone.id);
    }
    if (!result?.ok) {
      this.audit.record({ actor: AuditLog.actorFor(user), customerId: user.customerId, phoneId: phone.id, action: 'control.acquire', outcome: 'refused', detail: { reason: result?.reason }, ip });
      const [status, code, message] = ACQUIRE_REFUSALS[result?.reason] ?? [409, 'refused', result?.message || 'The rack declined control.'];
      throw new HttpError(status, code, message);
    }
    this.sessions.set(phone.id, session);
    this.byId.set(session.sessionId, session);
    this.lastEnded.delete(phone.id);
    this.audit.record({ actor: AuditLog.actorFor(user), customerId: user.customerId, phoneId: phone.id, action: 'control.acquire', outcome: 'ok', ip });
    return session;
  }

  heartbeat(user, phoneId) {
    const s = this.sessions.get(phoneId);
    if (!s || s.userId !== user.id) return null;
    s.heartbeatAt = Date.now();
    return s;
  }

  /** Normal hand-back (release): cancels queued work and releases held input at the rack. */
  async release(phoneId, { reason = 'released', message = 'Control released.', actor = { type: 'system' }, ip } = {}) {
    const s = this.sessions.get(phoneId);
    if (!s) return { ok: true, already: true };
    this.#remove(s, reason, message);
    let result;
    try { result = await this.hub.request(s.agentId, 'release', { kernelId: s.kernelId, sessionId: s.sessionId }); }
    catch (err) { result = { ok: false, message: err.message }; }
    this.audit.record({ actor, customerId: s.customerId, phoneId, action: 'control.release', outcome: result?.ok ? 'ok' : 'unconfirmed', detail: { reason, message: result?.message }, ip });
    return result;
  }

  /** Local end without contacting the rack (the rack already ended it, or Stop is being sent). */
  end(phoneId, reason, message) {
    const s = this.sessions.get(phoneId);
    if (s) this.#remove(s, reason, message);
    return s;
  }

  sweep() {
    const now = Date.now();
    for (const s of [...this.sessions.values()]) {
      if (now - s.heartbeatAt > HEARTBEAT_TIMEOUT_MS && s.inflight === 0)
        this.release(s.phoneId, { reason: 'timeout', message: 'Control ended because the browser stopped responding.' });
    }
  }

  #onAgentEvent(agentId, evt) {
    if (evt.type !== 'control_lost') return;
    const s = this.byId.get(evt.sessionId);
    if (!s || s.agentId !== agentId) return;
    this.#remove(s, evt.reason, evt.message);
    this.audit.record({ actor: { type: 'agent', id: agentId }, customerId: s.customerId, phoneId: s.phoneId, action: 'control.lost', outcome: String(evt.reason ?? 'lost'), detail: { message: evt.message } });
  }

  #onAgentDisconnected(agentId) {
    for (const s of [...this.sessions.values()]) {
      if (s.agentId !== agentId) continue;
      this.#remove(s, 'rack_disconnected', 'The connection to the rack was lost. Take control again when it is back.');
      this.audit.record({ actor: { type: 'system' }, customerId: s.customerId, phoneId: s.phoneId, action: 'control.lost', outcome: 'rack_disconnected' });
    }
  }

  close() { clearInterval(this.sweepTimer); }
}

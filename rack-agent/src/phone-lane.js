import { planFor } from './actions.js';
import { KernelAmbiguousError, KernelUnreachableError } from './kernel/http-kernel.js';

// One lane per phone. It is the phone's single controller on behalf of the portal:
//  - holds the private kernel lease token (never sent to the portal or browser),
//  - renews it on its own timer, independent of the command queue,
//  - runs commands strictly one at a time,
//  - lets Stop bypass the queue, cancel pending work and latch the kernel's Stop,
//  - never retries a command whose outcome is unknown, and never re-acquires by itself.
// Accounts sharing a phone share this lane, so they share its execution order.

const sleep = (ms, signal) => new Promise(resolve => {
  if (signal?.aborted) return resolve(false);
  const timer = setTimeout(() => { signal?.removeEventListener('abort', onAbort); resolve(true); }, ms);
  const onAbort = () => { clearTimeout(timer); resolve(false); };
  signal?.addEventListener('abort', onAbort, { once: true });
});

export const LaneOutcome = Object.freeze({
  succeeded: 'succeeded', failed: 'failed', cancelled: 'cancelled', unknown: 'unknown', rejected: 'rejected',
});

export class PhoneLane {
  #kernel; #token = null; #renewTimer = null; #renewFailures = 0; #queue = []; #running = null;
  #stopSeq = 0; #acquiring = false; #acquiredAt = 0; #recent = new Set(); #closed = false;

  constructor(kernelId, kernel, { leaseMs = 30_000, renewMs = 10_000, maxQueue = 8, onEvent = () => {} } = {}) {
    this.kernelId = kernelId;
    this.#kernel = kernel;
    this.leaseMs = leaseMs;
    this.renewMs = renewMs;
    this.maxQueue = maxQueue;
    this.onEvent = onEvent;
    /** @type {{sessionId: string} | null} */
    this.owner = null;
  }

  get hasControl() { return this.#token !== null; }
  get queued() { return this.#queue.length + (this.#running ? 1 : 0); }
  #matches(owner) { return !!owner && !!this.owner && this.owner.sessionId === owner.sessionId && this.#token !== null; }

  #clearOwnership() {
    this.#token = null;
    this.owner = null;
    this.#renewFailures = 0;
    if (this.#renewTimer) { clearInterval(this.#renewTimer); this.#renewTimer = null; }
  }

  #cancelWork(message) {
    const pending = this.#queue.splice(0);
    for (const job of pending) { job.cancelled = true; job.abort.abort(); job.resolve({ status: LaneOutcome.cancelled, message }); }
    if (this.#running) { this.#running.cancelled = true; this.#running.cancelMessage = message; this.#running.abort.abort(); }
  }

  #lost(reason, message) {
    const owner = this.owner;
    this.#clearOwnership();
    this.#cancelWork('Control ended before this action ran.');
    if (owner) this.onEvent({ type: 'control_lost', kernelId: this.kernelId, sessionId: owner.sessionId, reason, message });
  }

  async #reasonFromStatus() {
    try {
      const status = await this.#kernel.inputStatus();
      const phone = status.phones?.find(p => p.id === this.kernelId);
      if (!phone) return { reason: 'input_unavailable', message: 'This phone is not enabled for input at the rack.' };
      if (phone.release_failed) return { reason: 'release_failed', message: phone.message || 'Input release failed; support must check the board.' };
      if (phone.releasing) return { reason: 'recovering', message: 'Input is finishing a previous release. Try again shortly.' };
      if (phone.stopped) return { reason: 'stopped', message: phone.message || 'Input is stopped.', generation: phone.generation };
      if (phone.owned || phone.active) return { reason: 'owned_elsewhere', message: 'Another controller at the rack is using this phone.' };
      return { reason: 'rejected', message: 'The rack declined control.' };
    } catch (err) {
      return { reason: 'kernel_unreachable', message: err.message };
    }
  }

  async acquire(owner) {
    if (this.#closed) return { ok: false, reason: 'closed', message: 'Rack agent is shutting down.' };
    if (this.owner) {
      if (this.owner.sessionId === owner.sessionId && this.#token) return { ok: true, already: true };
      return { ok: false, reason: 'busy', message: 'Another portal session controls this phone.' };
    }
    if (this.#acquiring) return { ok: false, reason: 'busy', message: 'Control is already being requested.' };
    this.#acquiring = true;
    const stopSeq = this.#stopSeq;
    let data;
    try {
      data = await this.#kernel.command('/input/acquire', { id: this.kernelId, lease_ms: this.leaseMs });
    } catch (err) {
      this.#acquiring = false;
      // An ambiguous acquire could leave an orphan lease; it has no token here, so it
      // simply expires in the kernel (which then latches Stop and requires Resume).
      return { ok: false, reason: 'kernel_unreachable', message: err.message };
    }
    this.#acquiring = false;
    if (data.code !== 0) {
      if (data.code === 36) return { ok: false, reason: 'input_unavailable', message: data.message || 'Input is not available for this phone.' };
      return { ok: false, ...(await this.#reasonFromStatus()) };
    }
    const token = data.leases?.find(l => l.id === this.kernelId)?.token;
    if (typeof token !== 'string' || !token) return { ok: false, reason: 'protocol', message: 'Kernel returned no lease.' };
    if (stopSeq !== this.#stopSeq || this.#closed) {
      // Stop arrived while acquiring: give the new lease straight back.
      try { await this.#kernel.command('/input/release', { id: this.kernelId, token }); } catch { /* expires on its own */ }
      return { ok: false, reason: 'stopped', message: 'Stopped while control was being requested.' };
    }
    this.#token = token;
    this.owner = { sessionId: owner.sessionId };
    this.#acquiredAt = Date.now();
    this.#renewTimer = setInterval(() => this.#renew(token), this.renewMs);
    this.#renewTimer.unref?.();
    return { ok: true };
  }

  async #renew(token) {
    if (this.#token !== token) return;
    try {
      const data = await this.#kernel.command('/input/renew', { id: this.kernelId, token }, { timeoutMs: 5000 });
      if (this.#token !== token) return;
      if (data.code === 0) { this.#renewFailures = 0; return; }
      this.#lost('lease_lost', data.message || 'Control lease could not be renewed.');
    } catch (err) {
      if (this.#token !== token) return;
      // One missed renewal still leaves ~20 s on a 30 s lease. Two means it is gone.
      if (++this.#renewFailures >= 2) this.#lost('lease_lost', 'Lost contact with the kernel; control ended.');
    }
  }

  /** Called by the inventory poller with a status snapshot taken at `observedAt`. */
  observe(statusPhone, observedAt) {
    if (!this.#token || this.#acquiring || observedAt <= this.#acquiredAt) return;
    if (!statusPhone || !statusPhone.owned || statusPhone.stopped)
      this.#lost('stopped', statusPhone?.message || 'Input was stopped at the rack.');
  }

  enqueue(owner, commandId, action) {
    if (!this.#matches(owner)) return Promise.resolve({ status: LaneOutcome.rejected, message: 'You no longer control this phone.' });
    if (this.#recent.has(commandId)) return Promise.resolve({ status: LaneOutcome.rejected, message: 'Duplicate command ignored.' });
    if (this.#queue.length + (this.#running ? 1 : 0) >= this.maxQueue)
      return Promise.resolve({ status: LaneOutcome.rejected, message: 'This phone is still working through earlier actions.' });
    this.#recent.add(commandId);
    if (this.#recent.size > 512) this.#recent.delete(this.#recent.values().next().value);
    const plan = planFor(action);
    return new Promise(resolve => {
      this.#queue.push({ commandId, plan, owner: { sessionId: owner.sessionId }, resolve, cancelled: false, abort: new AbortController() });
      this.#pump();
    });
  }

  #pump() {
    if (this.#running || this.#queue.length === 0) return;
    const job = this.#queue.shift();
    this.#running = job;
    this.#execute(job)
      .catch(err => ({ status: LaneOutcome.failed, message: err.message }))
      .then(result => job.resolve(result))
      .finally(() => { this.#running = null; this.#pump(); });
  }

  async #send(step, token) {
    const data = await this.#kernel.command(step.fun, { ...step.data, id: this.kernelId, token });
    const own = Array.isArray(data.results) ? data.results.find(r => r.id === this.kernelId) : null;
    const code = own ? own.code : data.code;
    return { ok: code === 0, code, message: own?.message ?? data.message ?? '' };
  }

  async #execute(job) {
    // Ownership is checked again at execution time, not only when the job was queued.
    if (job.cancelled) return { status: LaneOutcome.cancelled, message: job.cancelMessage || 'Cancelled before it ran.' };
    if (!this.#matches(job.owner)) return { status: LaneOutcome.rejected, message: 'Control ended before this action ran.' };
    const token = this.#token;
    const { plan } = job;
    let delivered = 0, outcome = null;
    try {
      for (const step of plan.steps) {
        if (job.cancelled || this.#token !== token) { outcome = { status: LaneOutcome.cancelled, message: job.cancelMessage || 'Stopped.' }; break; }
        if (step.sleep) { await sleep(step.sleep, job.abort.signal); continue; }
        const r = await this.#send(step, token);
        delivered++;
        if (!r.ok) {
          outcome = { status: r.code === 499 ? LaneOutcome.cancelled : LaneOutcome.failed, message: r.message || `Kernel code ${r.code}.`, kernelCode: r.code };
          break;
        }
      }
    } catch (err) {
      if (err instanceof KernelAmbiguousError) outcome = { status: LaneOutcome.unknown, message: 'The rack did not confirm this action. It may have happened; check the screen before repeating it.' };
      else if (err instanceof KernelUnreachableError) outcome = { status: delivered ? LaneOutcome.unknown : LaneOutcome.failed, message: 'The rack kernel is not reachable.' };
      else outcome = { status: LaneOutcome.failed, message: err.message };
    }
    // Release a held button if the button went down and this lease is still ours.
    if (plan.finally && delivered > (plan.finallyAfter ?? 0) && this.#token === token && outcome?.status !== LaneOutcome.unknown) {
      for (const step of plan.finally) {
        try { const r = await this.#send(step, token); if (!r.ok && !outcome) outcome = { status: LaneOutcome.failed, message: r.message, kernelCode: r.code }; }
        catch (err) { outcome = { status: LaneOutcome.unknown, message: 'The rack did not confirm the button release.' }; break; }
      }
    }
    if (outcome && delivered < plan.steps.filter(s => !s.sleep).length && delivered > 0 && outcome.status !== LaneOutcome.unknown)
      outcome.message += ` (${delivered} of ${plan.steps.filter(s => !s.sleep).length} steps ran)`;
    if (outcome?.status === LaneOutcome.unknown) {
      // Never replay; stop the phone so nothing stale can follow an uncertain action.
      await this.stop('Stopped automatically because an action was not confirmed.');
    } else if (outcome && (outcome.status === LaneOutcome.failed || outcome.status === LaneOutcome.cancelled) && this.#token === token) {
      // A failed or cancelled kernel command latches Stop in the kernel. Confirm and hand back.
      const status = await this.#reasonFromStatus();
      if (status.reason !== 'owned_elsewhere') this.#lost(status.reason === 'rejected' ? 'lease_lost' : status.reason, status.message);
    }
    return outcome ?? { status: LaneOutcome.succeeded, message: 'Done.' };
  }

  /** Bypasses the queue. Cancels queued and running work, then latches the kernel's Stop. */
  async stop(reason = 'Stopped.') {
    this.#stopSeq++;
    const owner = this.owner;
    this.#clearOwnership();
    this.#cancelWork('Stopped before it ran.');
    let result;
    try {
      const data = await this.#kernel.command('/input/stop', { id: this.kernelId }, { timeoutMs: 10_000 });
      result = { ok: data.code === 0, code: data.code, message: data.message ?? '' };
    } catch (err) {
      result = { ok: false, code: -1, message: err.message, uncertain: err instanceof KernelAmbiguousError };
    }
    if (owner) this.onEvent({ type: 'control_lost', kernelId: this.kernelId, sessionId: owner.sessionId, reason: 'stopped', message: reason });
    return result;
  }

  /** Normal hand-back: cancels pending work and releases held input. Does not latch Stop. */
  async release(owner, message = 'Control released.') {
    if (owner && !this.#matches(owner)) return { ok: false, message: 'This session does not control the phone.' };
    const token = this.#token;
    const prior = this.owner;
    this.#clearOwnership();
    this.#cancelWork('Control was released before this action ran.');
    if (!token) return { ok: true };
    let result;
    try {
      const data = await this.#kernel.command('/input/release', { id: this.kernelId, token }, { timeoutMs: 10_000 });
      result = { ok: data.code === 0, code: data.code, message: data.message ?? '' };
    } catch (err) {
      result = { ok: false, code: -1, message: err.message };
    }
    if (prior && !owner) this.onEvent({ type: 'control_lost', kernelId: this.kernelId, sessionId: prior.sessionId, reason: 'released', message });
    return result;
  }

  /** Explicit Resume after Stop. Refuses when the generation the user saw has changed. */
  async resume(expectedGeneration) {
    if (this.#token) return { ok: false, message: 'Release control before resuming.' };
    const expected = { [this.kernelId]: expectedGeneration };
    try {
      const data = await this.#kernel.command('/input/resume', { id: this.kernelId, expected_generations: expected });
      return { ok: data.code === 0, code: data.code, message: data.message ?? '' };
    } catch (err) {
      return { ok: false, code: -1, message: err.message };
    }
  }

  async close() {
    this.#closed = true;
    if (this.#token) await this.release(null, 'Rack agent shutting down.');
  }
}

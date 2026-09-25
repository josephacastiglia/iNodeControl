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

/**
 * Every action ends in exactly one of three states:
 *  - succeeded: the kernel confirmed every step (code 0). This proves the HID reports were
 *    written, not that iOS showed the expected result.
 *  - not_sent:  confirmed that nothing reached the phone (refused before execution, stopped
 *    while queued, kernel not reachable). Only this state is safe for a person to retry.
 *  - uncertain: no reply, a failure or cancellation during execution, or a partly completed
 *    multi-step action. Never retried automatically; the phone is stopped or handed back.
 */
export const Outcome = Object.freeze({ succeeded: 'succeeded', notSent: 'not_sent', uncertain: 'uncertain' });

// Kernel codes returned at the top level (no per-phone `results`) before any HID output:
// InputSessions.DispatchAsync rejects ownership/busy (409), arguments (36), unknown ids (1)
// and unsupported functions (41) before ExecuteAsync. Anything else is treated as uncertain.
const REFUSED_BEFORE_EXECUTION = new Set([409, 36, 1, 41]);

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
    for (const job of pending) { job.cancelled = true; job.abort.abort(); job.resolve(this.#outcome(job, Outcome.notSent, 'stopped_before_start', message)); }
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
    if (!this.#matches(owner)) return Promise.resolve(this.#outcome({ plan: planFor(action) }, Outcome.notSent, 'not_in_control', 'This session does not control the phone.'));
    if (this.#recent.has(commandId)) return Promise.resolve(this.#outcome({ plan: planFor(action) }, Outcome.notSent, 'duplicate', 'Duplicate command ignored.'));
    if (this.#queue.length + (this.#running ? 1 : 0) >= this.maxQueue)
      return Promise.resolve(this.#outcome({ plan: planFor(action) }, Outcome.notSent, 'queue_full', 'Earlier actions are still running on this phone.'));
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
      .catch(err => this.#outcome(job, Outcome.uncertain, 'agent_error', err.message))
      .then(result => job.resolve(result))
      .finally(() => { this.#running = null; this.#pump(); });
  }

  async #send(step, token) {
    const data = await this.#kernel.command(step.fun, { ...step.data, id: this.kernelId, token });
    const own = Array.isArray(data.results) ? data.results.find(r => r.id === this.kernelId) : null;
    // With per-phone results the command reached ExecuteAsync (HID may have been written).
    return { executed: !!own, code: own ? own.code : data.code, message: own?.message ?? data.message ?? '' };
  }

  /**
   * Builds a result with step-level progress. For text, `text` reports characters:
   * confirmed (kernel code 0 for their chunk), uncertain (the chunk in flight when the
   * outcome became unknown) and not sent. Confirmed keystrokes do not prove the text
   * appeared on the phone (focus, Typing Mode or autocorrect decide that).
   */
  #outcome(job, status, reason, detail = '', track = null, kernelCode) {
    const steps = [...job.plan.steps.filter(st => !st.sleep), ...(job.plan.finally ?? [])];
    const confirmed = track?.confirmed ?? new Set();
    const uncertain = track?.uncertain ?? null;
    const progress = { total: steps.length, confirmed: confirmed.size, uncertain: uncertain === null ? 0 : 1, notSent: steps.length - confirmed.size - (uncertain === null ? 0 : 1) };
    const out = { status, retrySafe: status === Outcome.notSent, reason, detail, progress };
    if (kernelCode !== undefined) out.kernelCode = kernelCode;
    const chunks = steps.map((st, i) => (st.fun === '/key/sendkey' && typeof st.data.key === 'string' ? [i, st.data.key.length] : null)).filter(Boolean);
    if (chunks.length) {
      const total = chunks.reduce((n, [, len]) => n + len, 0);
      const ok = chunks.filter(([i]) => confirmed.has(i)).reduce((n, [, len]) => n + len, 0);
      const unsure = chunks.filter(([i]) => i === uncertain).reduce((n, [, len]) => n + len, 0);
      out.text = { total, confirmed: ok, uncertain: unsure, notSent: total - ok - unsure };
    }
    return out;
  }

  async #execute(job) {
    // Ownership is checked again at execution time, not only when the job was queued.
    if (job.cancelled) return this.#outcome(job, Outcome.notSent, 'stopped_before_start', job.cancelMessage || 'Cancelled before it ran.');
    if (!this.#matches(job.owner)) return this.#outcome(job, Outcome.notSent, 'not_in_control', 'Control ended before this action ran.');
    const token = this.#token;
    const { plan } = job;
    const track = { confirmed: new Set(), uncertain: null };
    let index = -1, verdict = null, buttonDown = false;
    const settle = (status, reason, detail, code) => { verdict = { status, reason, detail, code }; };
    const interrupted = reason => track.confirmed.size === 0
      ? settle(Outcome.notSent, reason === 'kernel_unreachable' ? reason : 'stopped_before_start', job.cancelMessage || 'Nothing was sent.')
      : settle(Outcome.uncertain, 'interrupted', job.cancelMessage || 'Stopped partway; the remaining steps were not sent.');

    const run = async step => {
      index++;
      let r;
      try { r = await this.#send(step, token); }
      catch (err) {
        if (err instanceof KernelUnreachableError) { interrupted('kernel_unreachable'); return false; }
        track.uncertain = index;
        settle(Outcome.uncertain, 'no_reply', err.message);
        return false;
      }
      if (r.code === 0) {
        track.confirmed.add(index);
        if (step.fun === '/mouse/down') buttonDown = true;
        if (step.fun === '/mouse/up') buttonDown = false;
        return true;
      }
      if (!r.executed && REFUSED_BEFORE_EXECUTION.has(r.code)) {
        if (track.confirmed.size === 0) settle(Outcome.notSent, 'kernel_refused', r.message, r.code);
        else settle(Outcome.uncertain, 'interrupted', r.message, r.code);
        return false;
      }
      track.uncertain = index;
      if (step.fun === '/mouse/down') buttonDown = true; // may be down; Stop/release clears it
      settle(Outcome.uncertain, r.code === 499 ? 'cancelled_during' : 'kernel_failed', r.message, r.code);
      return false;
    };

    for (const step of plan.steps) {
      if (job.cancelled || this.#token !== token) { interrupted('stopped'); break; }
      if (step.sleep) { await sleep(step.sleep, job.abort.signal); continue; }
      if (!(await run(step))) break;
    }
    // Stopped after every main step was confirmed: only a gesture still holding the button is unfinished.
    if (!verdict && buttonDown && plan.finally && (job.cancelled || this.#token !== token)) interrupted('stopped');
    // Finish a gesture that pressed the button, if this lease is still ours. After Stop,
    // release or lease loss the kernel has already released every held input.
    if (plan.finally && buttonDown && this.#token === token && verdict?.reason !== 'no_reply') {
      index = plan.steps.filter(st => !st.sleep).length - 1;
      for (const step of plan.finally) {
        const before = verdict;
        const ok = await run(step);
        if (before && ok) verdict = before; // a successful release does not undo an earlier failure
        if (!ok) break;
      }
    }

    if (verdict?.reason === 'no_reply') {
      // Never replay; stop the phone so nothing stale can follow an uncertain action.
      await this.stop('Stopped automatically because an action was not confirmed.');
    } else if (verdict?.reason === 'kernel_unreachable') {
      if (this.#token === token) this.#lost('kernel_unreachable', 'The rack kernel is not reachable; control ended.');
    } else if (verdict && this.#token === token && (verdict.status === Outcome.uncertain || verdict.code === 409)) {
      // A failed or cancelled command latches Stop in the kernel; 409 means the lease is gone.
      const status = await this.#reasonFromStatus();
      if (status.reason !== 'owned_elsewhere') this.#lost(status.reason === 'rejected' ? 'lease_lost' : status.reason, status.message);
    }
    return verdict
      ? this.#outcome(job, verdict.status, verdict.reason, verdict.detail, track, verdict.code)
      : this.#outcome(job, Outcome.succeeded, 'done', '', track);
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

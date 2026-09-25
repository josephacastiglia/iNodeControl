// Latest-frame cache for remote previews. Memory is bounded: one JPEG per phone per tier.
// Browsers pull frames; a request with ?after=<seq> waits (long-poll) for a newer frame,
// so a slow client simply asks less often and never builds a backlog of old frames.

export class PreviewCache {
  constructor({ maxWaitersPerKey = 32, maxWaiters = 2000, waitMs = 8000 } = {}) {
    this.frames = new Map();    // key -> { seq, jpeg, header, receivedAt }
    this.waiters = new Map();   // key -> Set<fn>
    this.totalWaiters = 0;
    this.seq = 0;
    this.maxWaitersPerKey = maxWaitersPerKey;
    this.maxWaiters = maxWaiters;
    this.waitMs = waitMs;
    this.watchSentAt = new Map();
  }

  static key(phoneId, tier) { return `${phoneId}:${tier}`; }

  put(phoneId, tier, jpeg, header) {
    const key = PreviewCache.key(phoneId, tier);
    const frame = { seq: ++this.seq, jpeg: Buffer.from(jpeg), header, receivedAt: Date.now() };
    this.frames.set(key, frame);
    const set = this.waiters.get(key);
    if (set) { this.waiters.delete(key); this.totalWaiters -= set.size; for (const fn of set) fn(frame); }
  }

  latest(phoneId, tier) { return this.frames.get(PreviewCache.key(phoneId, tier)) ?? null; }

  /** Resolves with a frame newer than `after`, or null after the wait (caller answers 204). */
  waitNewer(phoneId, tier, after, signal) {
    const key = PreviewCache.key(phoneId, tier);
    const current = this.frames.get(key);
    if (current && current.seq > after) return Promise.resolve(current);
    let set = this.waiters.get(key);
    if ((set?.size ?? 0) >= this.maxWaitersPerKey || this.totalWaiters >= this.maxWaiters) return Promise.resolve('busy');
    if (!set) { set = new Set(); this.waiters.set(key, set); }
    return new Promise(resolve => {
      const done = frame => { clearTimeout(timer); signal?.removeEventListener('abort', abort); resolve(frame); };
      const remove = () => { if (set.delete(done)) this.totalWaiters--; if (set.size === 0 && this.waiters.get(key) === set) this.waiters.delete(key); };
      const timer = setTimeout(() => { remove(); done(null); }, this.waitMs);
      const abort = () => { remove(); done(null); };
      signal?.addEventListener('abort', abort, { once: true });
      set.add(done);
      this.totalWaiters++;
    });
  }

  /** True when a watch renewal should be sent to the agent (throttled per phone/tier). */
  shouldRenewWatch(phoneId, tier, everyMs = 2500) {
    const key = PreviewCache.key(phoneId, tier);
    const now = Date.now();
    if (now - (this.watchSentAt.get(key) ?? 0) < everyMs) return false;
    this.watchSentAt.set(key, now);
    return true;
  }

  dropPhone(phoneId) {
    for (const tier of ['grid', 'focus']) this.frames.delete(PreviewCache.key(phoneId, tier));
  }

  stats() { return { frames: this.frames.size, waiters: this.totalWaiters, bytes: [...this.frames.values()].reduce((n, f) => n + f.jpeg.length, 0) }; }
}

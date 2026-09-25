import { Worker } from 'node:worker_threads';
import os from 'node:os';

/**
 * JPEG encoding runs off the main thread so lease renewals, Stop and the portal link
 * are never delayed by preview work. Callers keep at most one job in flight per phone,
 * so the pool queue is bounded by the number of watched phones, not by frame rate.
 */
export class EncoderPool {
  constructor({ size = Math.max(1, Math.min(4, os.availableParallelism() - 1)) } = {}) {
    this.workers = [];
    this.idle = [];
    this.queue = [];
    this.pending = new Map();
    this.nextId = 1;
    this.closed = false;
    for (let i = 0; i < size; i++) this.#spawn();
  }

  #spawn() {
    const worker = new Worker(new URL('./encode-worker.js', import.meta.url));
    worker.unref();
    worker.on('message', msg => {
      const job = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      this.idle.push(worker);
      this.#pump();
      if (!job) return;
      if (msg.ok) job.resolve(msg); else job.reject(new Error(msg.error));
    });
    worker.on('error', err => {
      for (const [id, job] of this.pending) if (job.worker === worker) { this.pending.delete(id); job.reject(err); }
      this.workers = this.workers.filter(w => w !== worker);
      this.idle = this.idle.filter(w => w !== worker);
      if (!this.closed) this.#spawn();
    });
    this.workers.push(worker);
    this.idle.push(worker);
  }

  get backlog() { return this.queue.length; }

  encode(bmpArrayBuffer, tiers) {
    if (this.closed) return Promise.reject(new Error('Encoder closed.'));
    return new Promise((resolve, reject) => {
      this.queue.push({ id: this.nextId++, bmp: bmpArrayBuffer, tiers, resolve, reject });
      this.#pump();
    });
  }

  #pump() {
    while (this.idle.length && this.queue.length) {
      const worker = this.idle.pop();
      const job = this.queue.shift();
      job.worker = worker;
      this.pending.set(job.id, job);
      worker.postMessage({ id: job.id, bmp: job.bmp, tiers: job.tiers }, [job.bmp]);
    }
  }

  async close() {
    this.closed = true;
    for (const job of this.queue) job.reject(new Error('Encoder closed.'));
    this.queue = [];
    await Promise.all(this.workers.map(w => w.terminate()));
  }
}

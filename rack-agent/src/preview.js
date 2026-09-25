import { parseBmp, frameSignature, BmpError } from './bmp.js';

// Preview bridge. The kernel's raw BMP path is untouched: this reads the same
// /pic/screenshot endpoint the desktop console uses and turns frames into small JPEGs
// for remote viewers.
//
// Bounded by construction:
//  - one capture loop per watched phone, shared by every viewer and both tiers;
//  - at most one screenshot request and one encode in flight per phone;
//  - frames are dropped, never queued, when the portal link is backed up;
//  - watches expire unless the portal keeps renewing them.
//
// Measured on the development container (synthetic noisy 500x1080 frame, one core):
// 150 px ≈ 18 ms, 360 px ≈ 42 ms, 500 px ≈ 85 ms per JPEG. Real screens compress
// better. Grid tiles therefore run at ~1 fps and the focused view at up to ~8 fps,
// with encoding on worker threads so leases and Stop never wait behind previews.

export const DEFAULT_TIERS = Object.freeze({
  grid: Object.freeze({ width: 144, quality: 55, intervalMs: 1000 }),
  focus: Object.freeze({ width: 360, quality: 65, intervalMs: 125 }),
});

const sleep = ms => new Promise(r => setTimeout(r, ms));

export class PreviewManager {
  /**
   * @param {object} deps
   * @param {import('./kernel/http-kernel.js').HttpKernel} deps.kernel
   * @param {{encode(buf: ArrayBuffer, tiers: object[]): Promise<any>}} deps.encoder
   * @param {{canSend(): boolean, sendFrame(header: object, jpeg: ArrayBuffer): void, sendVideoStatus(status: object): void}} deps.sink
   * @param {(kernelId: string) => number} [deps.framesOf] receiver frame counter from inventory
   */
  constructor({ kernel, encoder, sink, framesOf = () => 0, tiers = DEFAULT_TIERS, now = () => Date.now() }) {
    this.kernel = kernel; this.encoder = encoder; this.sink = sink; this.framesOf = framesOf;
    this.tiers = tiers; this.now = now;
    this.phones = new Map();
    this.closed = false;
    this.stats = { captured: 0, encoded: 0, sent: 0, droppedBackpressure: 0, unchangedSkipped: 0, unavailable: 0, encodeMsTotal: 0 };
  }

  watch(kernelId, tier, ttlMs = 8000) {
    if (!this.tiers[tier] || this.closed) return false;
    let st = this.phones.get(kernelId);
    if (!st) { st = { watches: {}, last: {}, seq: 0, running: false }; this.phones.set(kernelId, st); }
    st.watches[tier] = this.now() + Math.min(Math.max(ttlMs, 1000), 30_000);
    if (!st.running) { st.running = true; this.#run(kernelId, st).finally(() => { st.running = false; }); }
    return true;
  }

  unwatchAll() { for (const st of this.phones.values()) { st.watches = {}; st.last = {}; } }

  #active(st) {
    const t = this.now();
    return Object.keys(st.watches).filter(k => st.watches[k] > t);
  }

  async #run(kernelId, st) {
    while (!this.closed) {
      const active = this.#active(st);
      if (active.length === 0) { this.phones.delete(kernelId); return; }
      const started = this.now();
      const interval = Math.min(...active.map(t => this.tiers[t].intervalMs));
      const shot = await this.kernel.screenshot(kernelId);
      if (!shot.ok) {
        this.stats.unavailable++;
        this.sink.sendVideoStatus({ kernelId, available: false, code: shot.code, message: shot.message, at: this.now() });
        st.last = {};
        await sleep(Math.max(interval, 1000));
        continue;
      }
      this.stats.captured++;
      let parsed;
      try { parsed = parseBmp(shot.bmp); }
      catch (err) {
        this.sink.sendVideoStatus({ kernelId, available: false, code: -2, message: err instanceof BmpError ? err.message : 'Bad frame.', at: this.now() });
        await sleep(interval);
        continue;
      }
      const sig = frameSignature(parsed);
      const due = active.filter(t => {
        const last = st.last[t];
        if (!last) return true;
        if (this.now() - last.sentAt < this.tiers[t].intervalMs) return false;
        if (last.sig === sig) { this.stats.unchangedSkipped++; return false; }
        return true;
      });
      if (due.length) {
        if (!this.sink.canSend()) {
          this.stats.droppedBackpressure++;
        } else {
          const t0 = performance.now();
          let res;
          try {
            const ab = shot.bmp.byteOffset === 0 && shot.bmp.byteLength === shot.bmp.buffer.byteLength
              ? shot.bmp.buffer : shot.bmp.buffer.slice(shot.bmp.byteOffset, shot.bmp.byteOffset + shot.bmp.byteLength);
            res = await this.encoder.encode(ab, due.map(name => ({ name, width: this.tiers[name].width, quality: this.tiers[name].quality })));
          } catch (err) {
            res = null;
          }
          this.stats.encodeMsTotal += performance.now() - t0;
          if (res) {
            this.stats.encoded++;
            const capturedAt = started;
            for (const o of res.out) {
              if (!this.sink.canSend()) { this.stats.droppedBackpressure++; continue; }
              st.seq++;
              this.sink.sendFrame({
                kernelId, tier: o.tier, seq: st.seq, width: o.width, height: o.height,
                srcWidth: res.srcWidth, srcHeight: res.srcHeight, capturedAt, kernelFrames: this.framesOf(kernelId),
              }, o.jpeg);
              st.last[o.tier] = { sig, sentAt: this.now() };
              this.stats.sent++;
            }
          }
        }
      }
      const elapsed = this.now() - started;
      await sleep(Math.max(15, interval - elapsed));
    }
  }

  close() { this.closed = true; this.phones.clear(); }
}

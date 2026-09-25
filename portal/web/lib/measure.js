// Measurements for rack validation, computed in the browser from what the viewer is shown.
//
// Input-to-visible latency follows the method used elsewhere in this project (HANDOFF.md):
// mean absolute pixel difference in a small box around the tap, compared with the last
// frame displayed before the click. Actions without a point (keys, text, swipes) use the
// largest per-block difference across the whole frame. A change must reach `threshold`
// (0–255 scale) within `timeoutMs`, otherwise the attempt is recorded as "no visible change".
//
// Times use the browser clock. "Capture → display" also uses the rack agent's capture
// timestamp, so it is only meaningful when browser and rack PC share a clock (same PC).
// Pure functions: unit-tested in Node (portal/test/units.test.mjs).

export function regionMeanDiff(a, b, width, height, box) {
  const x0 = Math.max(0, Math.floor(box.x0)), y0 = Math.max(0, Math.floor(box.y0));
  const x1 = Math.min(width, Math.ceil(box.x1)), y1 = Math.min(height, Math.ceil(box.y1));
  let sum = 0, n = 0;
  for (let y = y0; y < y1; y++) {
    let i = (y * width + x0) * 4;
    for (let x = x0; x < x1; x++, i += 4) {
      sum += Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]);
      n += 3;
    }
  }
  return n ? sum / n : 0;
}

/**
 * Largest mean difference of any block in a blocksX × blocksY grid (sampled every 2nd pixel).
 * The top `skipTop` fraction (the iOS status bar: clock, battery) is ignored so a clock tick
 * is not mistaken for a response. Other unrelated changes (notifications) can still count.
 */
export function maxBlockDiff(a, b, width, height, blocksX = 12, blocksY = 24, skipTop = 0.06) {
  const bw = width / blocksX, bh = height / blocksY;
  let max = 0;
  for (let by = Math.ceil(skipTop * blocksY); by < blocksY; by++) for (let bx = 0; bx < blocksX; bx++) {
    let sum = 0, n = 0;
    for (let y = Math.floor(by * bh); y < Math.floor((by + 1) * bh); y += 2) {
      let i = (y * width + Math.floor(bx * bw)) * 4;
      for (let x = Math.floor(bx * bw); x < Math.floor((bx + 1) * bw); x += 2, i += 8) {
        sum += Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]);
        n += 3;
      }
    }
    if (n && sum / n > max) max = sum / n;
  }
  return max;
}

export function summarize(values) {
  const v = values.filter(Number.isFinite).sort((x, y) => x - y);
  if (!v.length) return { count: 0, median: null, p95: null, min: null, max: null };
  const pick = p => v[Math.min(v.length - 1, Math.ceil(p * v.length) - 1)];
  return { count: v.length, median: pick(0.5), p95: pick(0.95), min: v[0], max: v.at(-1) };
}

/** Box around a source-image point, in displayed-JPEG pixels. `half` is in source pixels. */
export function tapBox(point, source, picture, half = 24) {
  const sx = picture.width / source.width, sy = picture.height / source.height;
  return { x0: (point.x - half) * sx, y0: (point.y - half) * sy, x1: (point.x + half) * sx, y1: (point.y + half) * sy };
}

export class LatencyRecorder {
  constructor({ threshold = 8, timeoutMs = 5000, now = () => performance.now() } = {}) {
    this.threshold = threshold; this.timeoutMs = timeoutMs; this.now = now;
    this.baseline = null;   // { data, width, height }
    this.pending = [];
    this.results = [];
    this.nextId = 1;
  }

  /** Call when a new frame has been displayed. `data` is RGBA of the displayed JPEG. */
  onFrame(data, width, height, displayedAt, meta = {}) {
    for (const m of [...this.pending]) {
      if (displayedAt <= m.startedAt) continue;
      if (!m.baseline || m.baseline.width !== width || m.baseline.height !== height) continue;
      const diff = m.point
        ? regionMeanDiff(m.baseline.data, data, width, height, tapBox(m.point, m.source, { width, height }))
        : maxBlockDiff(m.baseline.data, data, width, height);
      m.maxDiff = Math.max(m.maxDiff, diff);
      if (diff >= this.threshold) this.#finish(m, { visibleMs: Math.round(displayedAt - m.startedAt), diff: Math.round(diff * 10) / 10, frameSeq: meta.seq ?? null });
    }
    this.baseline = { data, width, height };
    this.tick();
  }

  /** Starts a measurement for an action sent now. `point` (source pixels) selects the tap box. */
  start({ label, point = null, source = null }) {
    const m = { id: this.nextId++, label, point, source, startedAt: this.now(), wallStart: Date.now(), baseline: this.baseline, maxDiff: 0, ackMs: null, status: null };
    this.pending.push(m);
    return m;
  }

  /** Records when the rack confirmed the outcome. May arrive after the change was seen (text). */
  ack(m, status) {
    m.ackMs = Math.round(this.now() - m.startedAt); m.status = status;
    const done = this.results.find(r => r.id === m.id);
    if (done) { done.ackMs = m.ackMs; done.status = status; return; }
    if (status !== 'succeeded') this.#finish(m, { visibleMs: null, diff: null, note: 'action not confirmed sent' });
  }

  tick() {
    const t = this.now();
    for (const m of [...this.pending]) if (t - m.startedAt > this.timeoutMs) this.#finish(m, { visibleMs: null, diff: Math.round(m.maxDiff * 10) / 10, note: `no visible change within ${this.timeoutMs} ms` });
  }

  #finish(m, outcome) {
    const i = this.pending.indexOf(m);
    if (i < 0) return;
    this.pending.splice(i, 1);
    this.results.push({ id: m.id, label: m.label, at: m.wallStart, point: m.point, ackMs: m.ackMs, status: m.status, ...outcome });
    this.results.sort((x, y) => x.id - y.id);
    if (this.results.length > 500) this.results.shift();
  }

  /** Uses the frame on screen now as the comparison point (call when recording starts). */
  setBaseline(data, width, height) { this.baseline = { data, width, height }; }

  summary() {
    return {
      attempts: this.results.length,
      ack: summarize(this.results.map(r => r.ackMs)),
      visible: summarize(this.results.map(r => r.visibleMs)),
      noVisibleChange: this.results.filter(r => r.visibleMs === null && r.status === 'succeeded').length,
    };
  }
}

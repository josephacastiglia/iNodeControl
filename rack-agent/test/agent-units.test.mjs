// Rack agent unit/contract tests against the SIMULATED kernel (rack-agent/sim).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { KernelSim, defaultPhones } from '../sim/kernel-sim.js';
import { HttpKernel, KernelUnreachableError } from '../src/kernel/http-kernel.js';
import { PhoneLane } from '../src/phone-lane.js';
import { PreviewManager } from '../src/preview.js';
import { EncoderPool } from '../src/encoder-pool.js';
import { validateAction, planFor, ActionError, TEXT_CHUNK } from '../src/actions.js';
import { parseBmp, bmpToRgba, makeBmp, BmpError } from '../src/bmp.js';

const size = { width: 500, height: 1080 };
const ID = '5E:11:00:00:00:01', ID2 = '5E:11:00:00:00:02';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function withSim(fn, opts = {}) {
  const sim = new KernelSim({ phones: defaultPhones(2), speed: 0.05, ...opts });
  const url = await sim.listen();
  try { await fn(sim, new HttpKernel({ baseUrl: url, ...(opts.kernel ?? {}) })); } finally { await sim.close(); }
}

test('kernel address must stay on the rack PC', () => {
  assert.throws(() => new HttpKernel({ baseUrl: 'http://192.168.4.10:9913/api/' }), /local/);
  assert.throws(() => new HttpKernel({ baseUrl: 'https://127.0.0.1:9913/api/' }));
  assert.doesNotThrow(() => new HttpKernel({ baseUrl: 'http://127.0.0.1:9913/api/' }));
});

test('HTTP 200 with a non-zero data.code is surfaced, not treated as success', () => {
  const data = HttpKernel.readEnvelope(JSON.stringify({ status: 200, message: 'ok', data: { code: 409, message: 'busy' } }));
  assert.equal(data.code, 409);
  assert.throws(() => HttpKernel.readEnvelope(JSON.stringify({ status: 500, data: { code: 33 } })));
  assert.throws(() => HttpKernel.readEnvelope('<html>'));
});

test('capability check refuses a kernel without the ownership protocol', () => withSim(async (_sim, kernel) => {
  const cap = await kernel.capability();
  assert.equal(cap.compatible, false);
  assert.match(cap.reason, /input_protocol/);
}, { advertiseProtocol: false }));

test('unreachable kernel is distinguished from an ambiguous one', async () => {
  const net = await import('node:net');
  const port = await new Promise(r => { const s = net.createServer().listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => r(p)); }); });
  const kernel = new HttpKernel({ baseUrl: `http://127.0.0.1:${port}/api/` });
  await assert.rejects(kernel.command('/mouse/click', {}), KernelUnreachableError);
});

test('screenshot checks content type: BMP when live, code 25 JSON when video is off', () => withSim(async (sim, kernel) => {
  assert.equal((await kernel.screenshot(ID)).ok, true);
  sim.setVideo(ID, false);
  const off = await kernel.screenshot(ID);
  assert.deepEqual([off.ok, off.code], [false, 25]);
}));

test('actions: allowlist, bounds, keyboard alphabet and text chunking', () => {
  assert.throws(() => validateAction({ type: 'raw', fun: '/device/set' }, size), ActionError);
  assert.throws(() => validateAction({ type: 'tap', x: 500, y: 10 }, size), /outside/);
  assert.throws(() => validateAction({ type: 'tap', x: 1.5, y: 10 }, size), /whole-pixel/);
  assert.throws(() => validateAction({ type: 'key', key: 'WIN+v' }, size), /not supported/);
  assert.throws(() => validateAction({ type: 'text', text: 'héllo' }, size), /English/);
  assert.throws(() => validateAction({ type: 'text', text: 'a\nb' }, size), /English/);
  const plan = planFor(validateAction({ type: 'text', text: 'x'.repeat(100) }, size));
  assert.equal(plan.steps.length, Math.ceil(100 / TEXT_CHUNK));
  assert.ok(plan.steps.every(s => s.data.key.length <= TEXT_CHUNK));
  assert.equal(planFor(validateAction({ type: 'drag', points: [[1, 1], [2, 2], [3, 3]] }, size)).steps.length, 4);
});

test('bmp: validates the kernel layout and downsamples to the requested width', () => {
  const rgb = Buffer.alloc(10 * 20 * 3, 200);
  const bmp = parseBmp(makeBmp(10, 20, rgb));
  assert.deepEqual([bmp.width, bmp.height], [10, 20]);
  const small = bmpToRgba(bmp, 5);
  assert.deepEqual([small.width, small.height], [5, 10]);
  assert.equal(small.data[0], 200);
  const bad = makeBmp(10, 20, rgb); bad.writeInt16LE(32, 28);
  assert.throws(() => parseBmp(bad), BmpError);
});

test('lane serializes commands: never two active on one phone, no kernel "busy" rejections', () => withSim(async (sim, kernel) => {
  const lane = new PhoneLane(ID, kernel);
  await lane.acquire({ sessionId: 's' });
  const results = await Promise.all([1, 2, 3, 4].map(i => lane.enqueue({ sessionId: 's' }, 'c' + i, validateAction({ type: 'tap', x: 10 * i, y: 10 }, size))));
  assert.deepEqual(results.map(r => r.status), ['succeeded', 'succeeded', 'succeeded', 'succeeded']);
  const clicks = sim.delivered(ID).filter(e => e.fun === '/mouse/click');
  assert.deepEqual(clicks.map(c => c.data.x), [10, 20, 30, 40], 'executed in submission order');
  await lane.release({ sessionId: 's' });
}));

test('Stop bypasses the queue, cancels pending work and nothing runs afterwards', () => withSim(async (sim, kernel) => {
  sim.faults(ID).commandDelayMs = 600;
  const events = [];
  const lane = new PhoneLane(ID, kernel, { onEvent: e => events.push(e) });
  await lane.acquire({ sessionId: 's' });
  const pending = [1, 2, 3].map(i => lane.enqueue({ sessionId: 's' }, 'c' + i, validateAction({ type: 'tap', x: i, y: 1 }, size)));
  await sleep(100);
  const stoppedAt = Date.now();
  const stop = await lane.stop('user pressed stop');
  assert.equal(stop.ok, true);
  const results = await Promise.all(pending);
  assert.deepEqual(results.map(r => r.status), ['cancelled', 'cancelled', 'cancelled']);
  assert.equal(sim.delivered(ID, stoppedAt).filter(e => e.fun.startsWith('/mouse/')).length, 0, 'no input after Stop');
  assert.equal(events.at(-1).reason, 'stopped');
  const status = (await kernel.inputStatus()).phones.find(p => p.id === ID);
  assert.equal(status.stopped, true);
}));

test('an unconfirmed command is never retried and stops the phone', () => withSim(async (sim, kernel) => {
  sim.faults(ID).hangMs = 1500;
  const lane = new PhoneLane(ID, kernel);
  await lane.acquire({ sessionId: 's' });
  const r = await lane.enqueue({ sessionId: 's' }, 'c1', validateAction({ type: 'tap', x: 5, y: 5 }, size));
  assert.equal(r.status, 'unknown');
  sim.faults(ID).hangMs = 0;
  await sleep(1600);
  assert.equal(sim.delivered(ID).filter(e => e.fun === '/mouse/click').length, 1, 'executed exactly once');
  assert.equal((await kernel.inputStatus()).phones.find(p => p.id === ID).stopped, true);
  assert.equal(lane.hasControl, false);
}, { kernel: { commandTimeoutMs: 500 } }));

test('a failed command drops control (kernel latched Stop) and reports it', () => withSim(async (sim, kernel) => {
  const events = [];
  const lane = new PhoneLane(ID, kernel, { onEvent: e => events.push(e) });
  await lane.acquire({ sessionId: 's' });
  sim.faults(ID).failNext = 1;
  const r = await lane.enqueue({ sessionId: 's' }, 'c1', validateAction({ type: 'key', key: 'Home' }, size));
  assert.equal(r.status, 'failed');
  assert.equal(lane.hasControl, false);
  assert.equal(events[0].reason, 'stopped');
}));

test('operator-held phone is refused; external Stop is noticed by observe()', () => withSim(async (_sim, kernel) => {
  const desktop = await kernel.command('/input/acquire', { id: ID2 });
  const lane2 = new PhoneLane(ID2, kernel);
  assert.equal((await lane2.acquire({ sessionId: 's' })).reason, 'owned_elsewhere');
  await kernel.command('/input/release', { id: ID2, token: desktop.leases[0].token });

  const events = [];
  const lane = new PhoneLane(ID, kernel, { onEvent: e => events.push(e) });
  await lane.acquire({ sessionId: 's' });
  await sleep(5);
  await kernel.command('/input/stop', { id: ID }); // the rack operator presses Stop
  const st = (await kernel.inputStatus()).phones.find(p => p.id === ID);
  lane.observe(st, Date.now());
  assert.equal(lane.hasControl, false);
  assert.equal(events[0].reason, 'stopped');
}));

test('the kernel-side 8 s deadline (scaled) cancels an over-long sendkey; chunked text passes', () => withSim(async (sim, kernel) => {
  const text = 'y'.repeat(100);
  const desktop = await kernel.command('/input/acquire', { id: ID2 });
  const whole = await kernel.command('/key/sendkey', { id: ID2, token: desktop.leases[0].token, key: text });
  assert.equal(whole.results[0].code, 499);
  const lane = new PhoneLane(ID, kernel);
  await lane.acquire({ sessionId: 's' });
  const r = await lane.enqueue({ sessionId: 's' }, 't', validateAction({ type: 'text', text }, size));
  assert.equal(r.status, 'succeeded');
}, { deadlineMs: 300, speed: 0.05 }));

test('previews: backpressure drops frames instead of queueing; unchanged frames are not re-encoded', () => withSim(async (_sim, kernel) => {
  const encoder = new EncoderPool({ size: 1 });
  let open = false, sent = 0;
  const sink = { canSend: () => open, sendFrame: () => { sent++; }, sendVideoStatus: () => {} };
  const tiers = { grid: { width: 60, quality: 50, intervalMs: 40 }, focus: { width: 120, quality: 50, intervalMs: 40 } };
  const pm = new PreviewManager({ kernel, encoder, sink, tiers });
  pm.watch(ID, 'focus', 3000);
  await sleep(500);
  assert.equal(sent, 0);
  assert.ok(pm.stats.droppedBackpressure > 3, 'frames were dropped while the link was blocked');
  assert.equal(encoder.backlog, 0, 'nothing queued in the encoder');
  assert.equal(pm.stats.encoded, 0, 'no encode work while the link was blocked');
  open = true;
  await sleep(500);
  assert.ok(sent >= 1);
  assert.ok(pm.stats.unchangedSkipped >= 1, 'identical frames skipped');
  pm.close();
  await encoder.close();
}));

test('previews: watches expire, stopping capture', () => withSim(async (_sim, kernel) => {
  const encoder = new EncoderPool({ size: 1 });
  const sink = { canSend: () => true, sendFrame: () => {}, sendVideoStatus: () => {} };
  const pm = new PreviewManager({ kernel, encoder, sink, tiers: { grid: { width: 60, quality: 50, intervalMs: 50 } } });
  pm.watch(ID, 'grid', 1000);
  await sleep(1300);
  const captured = pm.stats.captured;
  await sleep(300);
  assert.equal(pm.stats.captured, captured, 'no more screenshots after the watch expired');
  pm.close();
  await encoder.close();
}));

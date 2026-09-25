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
  // In flight when Stop arrived: may have run partly. Still queued: confirmed not sent.
  assert.deepEqual(results.map(r => r.status), ['uncertain', 'not_sent', 'not_sent']);
  assert.deepEqual(results.map(r => r.retrySafe), [false, true, true]);
  assert.equal(results[0].reason, 'cancelled_during');
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
  assert.deepEqual([r.status, r.reason, r.retrySafe], ['uncertain', 'no_reply', false]);
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
  assert.deepEqual([r.status, r.reason, r.retrySafe], ['uncertain', 'kernel_failed', false], 'a failure during execution may have been partial');
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

// ---- outcome classification and long text ------------------------------------------

test('a kernel refusal before execution is "not sent" and safe to retry; nothing reached HID', () => withSim(async (sim, kernel) => {
  const lane = new PhoneLane(ID, kernel);
  await lane.acquire({ sessionId: 's' });
  await kernel.command('/input/stop', { id: ID }); // operator stops it; the lane has not noticed yet
  const before = sim.log.length;
  const r = await lane.enqueue({ sessionId: 's' }, 'c1', validateAction({ type: 'tap', x: 5, y: 5 }, size));
  assert.deepEqual([r.status, r.reason, r.retrySafe, r.kernelCode], ['not_sent', 'kernel_refused', true, 409]);
  assert.equal(sim.log.length, before, 'no input reached the simulated phone');
  assert.equal(lane.hasControl, false, 'the lost lease is noticed and control handed back');
}));

test('long text: chunks run back to back in one queued operation; other input waits, never interleaves', () => withSim(async (sim, kernel) => {
  const lane = new PhoneLane(ID, kernel);
  await lane.acquire({ sessionId: 's' });
  const text = 'abcdefghij'.repeat(10); // 100 chars -> 4 chunks
  const typing = lane.enqueue({ sessionId: 's' }, 't', validateAction({ type: 'text', text }, size));
  await sleep(10);
  const tap = lane.enqueue({ sessionId: 's' }, 'tap', validateAction({ type: 'tap', x: 9, y: 9 }, size));
  const [t, p] = await Promise.all([typing, tap]);
  assert.equal(t.status, 'succeeded');
  assert.deepEqual(t.text, { total: 100, confirmed: 100, uncertain: 0, notSent: 0 });
  assert.equal(p.status, 'succeeded');
  const order = sim.delivered(ID).map(e => e.fun);
  assert.deepEqual(order, ['/key/sendkey', '/key/sendkey', '/key/sendkey', '/key/sendkey', '/mouse/click']);
  assert.equal(sim.delivered(ID).filter(e => e.fun === '/key/sendkey').map(e => e.data.key).join(''), text, 'chunks in order, nothing lost or repeated');
}));

test('long text: lease renewal keeps running during a send longer than the lease', () => withSim(async (sim, kernel) => {
  const lane = new PhoneLane(ID, kernel, { leaseMs: 1000, renewMs: 300 });
  await lane.acquire({ sessionId: 's' });
  const started = Date.now();
  const r = await lane.enqueue({ sessionId: 's' }, 't', validateAction({ type: 'text', text: 'x'.repeat(200) }, size)); // ~2.8 s at speed 0.1
  assert.ok(Date.now() - started > 1500, 'the send outlived the 1 s lease');
  assert.equal(r.status, 'succeeded', r.detail);
  const st = (await kernel.inputStatus()).phones.find(p => p.id === ID);
  assert.deepEqual([st.owned, st.stopped], [true, false], 'still owned, never expired');
  await lane.release({ sessionId: 's' });
}, { speed: 0.1 }));

test('long text: Stop interrupts immediately; confirmed chunks, the uncertain chunk and the unsent rest are reported', () => withSim(async (sim, kernel) => {
  const lane = new PhoneLane(ID, kernel);
  await lane.acquire({ sessionId: 's' });
  const text = 'q'.repeat(128); // 4 chunks of 32, ~1 s each at speed 0.2
  const typing = lane.enqueue({ sessionId: 's' }, 't', validateAction({ type: 'text', text }, size));
  await waitForLog(sim, 2); // chunk 2 has started
  await sleep(200);
  const stopAt = Date.now();
  const stop = await lane.stop('Stop pressed during typing');
  const stoppedIn = Date.now() - stopAt;
  const r = await typing;
  assert.equal(stop.ok, true);
  assert.ok(stoppedIn < 1000, `Stop returned in ${stoppedIn} ms, without waiting for the text`);
  assert.deepEqual([r.status, r.reason, r.retrySafe], ['uncertain', 'cancelled_during', false]);
  assert.deepEqual(r.text, { total: 128, confirmed: 32, uncertain: 32, notSent: 64 });
  assert.equal(sim.delivered(ID, stopAt).filter(e => e.fun === '/key/sendkey').length, 0, 'no chunk started after Stop');
}, { speed: 0.2 }));

test('long text: a failure on chunk 2 stops there; chunk 1 is confirmed, chunk 2 uncertain, the rest never sent', () => withSim(async (sim, kernel) => {
  const lane = new PhoneLane(ID, kernel);
  await lane.acquire({ sessionId: 's' });
  sim.faults(ID).failAfter = 1;
  const r = await lane.enqueue({ sessionId: 's' }, 't', validateAction({ type: 'text', text: 'w'.repeat(100) }, size));
  assert.deepEqual([r.status, r.reason], ['uncertain', 'kernel_failed']);
  assert.deepEqual(r.text, { total: 100, confirmed: 32, uncertain: 32, notSent: 36 });
  assert.equal(sim.delivered(ID).filter(e => e.fun === '/key/sendkey').length, 2);
  assert.equal(lane.hasControl, false);
}));

test('long text: no reply on chunk 2 is uncertain, never retried, and stops the phone before chunk 3', () => withSim(async (sim, kernel) => {
  const lane = new PhoneLane(ID, kernel);
  await lane.acquire({ sessionId: 's' });
  sim.faults(ID).hangAfter = { calls: 1, ms: 1500 };
  const r = await lane.enqueue({ sessionId: 's' }, 't', validateAction({ type: 'text', text: 'e'.repeat(100) }, size));
  assert.deepEqual([r.status, r.reason, r.retrySafe], ['uncertain', 'no_reply', false]);
  assert.deepEqual(r.text, { total: 100, confirmed: 32, uncertain: 32, notSent: 36 });
  await sleep(1600);
  assert.equal(sim.delivered(ID).filter(e => e.fun === '/key/sendkey').length, 2, 'chunk 2 sent once; chunk 3 never');
  assert.equal((await kernel.inputStatus()).phones.find(p => p.id === ID).stopped, true);
}, { kernel: { commandTimeoutMs: 500 } }));

test('long text: the whole text is validated before the first chunk is sent', () => withSim(async (sim, kernel) => {
  const bad = 'a'.repeat(150) + 'é' + 'b'.repeat(20);
  assert.throws(() => validateAction({ type: 'text', text: bad }, size), ActionError);
  assert.throws(() => validateAction({ type: 'text', text: 'x'.repeat(201) }, size), ActionError);
  assert.equal(sim.log.length, 0);
}));

async function waitForLog(sim, count) {
  for (let i = 0; i < 400 && sim.log.filter(e => e.fun === '/key/sendkey').length < count; i++) await sleep(10);
}

test('only one rack agent per kernel: a live lock refuses a second agent; a stale lock is taken over', async () => {
  const { acquireInstanceLock } = await import('../src/instance-lock.js');
  const fs = await import('node:fs'), os = await import('node:os'), path = await import('node:path');
  const { spawn } = await import('node:child_process');
  const file = path.join(os.tmpdir(), `nt-lock-test-${process.pid}.lock`);
  fs.rmSync(file, { force: true });
  const release = acquireInstanceLock(file);
  release();
  const other = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 5000)']);
  fs.writeFileSync(file, String(other.pid));
  assert.throws(() => acquireInstanceLock(file), /already running/);
  other.kill();
  await new Promise(r => other.on('exit', r));
  const again = acquireInstanceLock(file); // stale: the PID is gone
  assert.equal(fs.readFileSync(file, 'utf8'), String(process.pid));
  again();
  assert.equal(fs.existsSync(file), false);
});

// Acceptance: group actions keep individual outcomes; slow previews never build a backlog.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import { startStack, Browser, waitFor, sleep } from './helpers/stack.mjs';
import { PreviewCache } from '../server/previews.js';

test('group partial failure: individual results, and a retry never repeats successful phones', async () => {
  const s = await startStack();
  try {
    const a = new Browser(s.base); await a.login(s.users.a.email);
    const phones = (await a.get('/api/phones')).data.phones;
    const ids = phones.map(p => p.id);
    const ctl = await a.post('/api/groups/control', { phoneIds: ids });
    assert.deepEqual(ctl.data.results.map(r => r.ok), [true, true, true]);

    s.sim.faults(s.kernelIds[1]).failNext = 1;
    const g = await a.post('/api/groups/actions', { phoneIds: ids, action: { type: 'key', key: 'Home' } });
    const byId = Object.fromEntries(g.data.results.map(r => [r.phoneId, r.status]));
    assert.deepEqual([byId[ids[0]], byId[ids[1]], byId[ids[2]]], ['succeeded', 'failed', 'succeeded']);

    // The failed phone was stopped by the kernel; resume and retake it deliberately.
    const failed = (await a.get(`/api/phones/${ids[1]}`)).data.phone;
    assert.equal(failed.input.state, 'stopped');
    assert.equal((await a.post(`/api/phones/${ids[1]}/resume`, { generation: failed.input.generation })).status, 200);
    assert.equal((await a.post(`/api/phones/${ids[1]}/control`)).status, 200);

    const retry = await a.post('/api/groups/actions', { phoneIds: ids, action: { type: 'key', key: 'Home' }, retryOf: g.data.groupId });
    const rby = Object.fromEntries(retry.data.results.map(r => [r.phoneId, r.status]));
    assert.deepEqual([rby[ids[0]], rby[ids[1]], rby[ids[2]]], ['skipped', 'succeeded', 'skipped']);
    const homes = i => s.sim.delivered(s.kernelIds[i]).filter(e => e.fun === '/key/sendkey' && e.data.fn_key === 'Home').length;
    assert.deepEqual([homes(0), homes(1), homes(2)], [1, 2, 1], 'successful phones received Home exactly once');

    const other = await a.post('/api/groups/actions', { phoneIds: ids, action: { type: 'tap', x: 5, y: 5 }, retryOf: g.data.groupId });
    assert.equal(other.status, 400, 'a retry must repeat the same kind of action');
  } finally { await s.close(); }
});

test('group action on phones not all under control: those are "not sent", others proceed', async () => {
  const s = await startStack();
  try {
    const a = new Browser(s.base); await a.login(s.users.a.email);
    const ids = (await a.get('/api/phones')).data.phones.map(p => p.id);
    await a.post(`/api/phones/${ids[0]}/control`);
    const g = await a.post('/api/groups/actions', { phoneIds: ids.slice(0, 2), action: { type: 'text', text: 'hi' } });
    const byId = Object.fromEntries(g.data.results.map(r => [r.phoneId, r.status]));
    assert.equal(byId[ids[0]], 'succeeded');
    assert.equal(byId[ids[1]], 'rejected');
    assert.equal(s.sim.delivered(s.kernelIds[1]).length, 0);
  } finally { await s.close(); }
});

test('preview cache keeps one frame per phone per tier and caps waiters', async () => {
  const cache = new PreviewCache({ maxWaitersPerKey: 2, waitMs: 200 });
  for (let i = 0; i < 1000; i++) cache.put('p1', 'focus', Buffer.alloc(1000, i % 256), { srcWidth: 500, srcHeight: 1080 });
  assert.equal(cache.stats().frames, 1);
  assert.equal(cache.stats().bytes, 1000);
  assert.equal(cache.latest('p1', 'focus').seq, 1000);
  const w1 = cache.waitNewer('p1', 'focus', 1000), w2 = cache.waitNewer('p1', 'focus', 1000);
  assert.equal(await cache.waitNewer('p1', 'focus', 1000), 'busy', 'third waiter refused');
  cache.put('p1', 'focus', Buffer.alloc(10), {});
  assert.equal((await w1).seq, 1001);
  assert.equal((await w2).seq, 1001);
  assert.equal(cache.stats().waiters, 0);
  assert.equal(await cache.waitNewer('p1', 'focus', 5000), null, 'times out with nothing');
});

test('a slow viewer gets only the newest frame; frames produced while it stalls are dropped, not queued', async () => {
  const s = await startStack({ speed: 0.2 });
  try {
    const a = new Browser(s.base); await a.login(s.users.a.email);
    const id = (await a.get('/api/phones')).data.phones[0].id;
    // A viewer that opens a long-poll and never reads the response.
    const port = new URL(s.base).port;
    const stalled = net.connect(Number(port), '127.0.0.1');
    stalled.pause();
    stalled.write(`GET /api/phones/${id}/frame?tier=focus&after=0 HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\nCookie: ${a.cookie}\r\n\r\n`);
    // Keep the phone's screen changing so the rack produces new frames.
    await a.post(`/api/phones/${id}/control`);
    let lastSeq = 0;
    for (let i = 0; i < 6; i++) {
      await a.post(`/api/phones/${id}/actions`, { action: { type: 'tap', x: 40 + i * 60, y: 600 } });
      const f = await a.get(`/api/phones/${id}/frame?tier=focus&after=${lastSeq}`);
      if (f.status === 200) lastSeq = Number(f.headers.get('x-frame-seq'));
    }
    const stats = s.portal.previews.stats();
    assert.ok(stats.frames <= 2 * 4, `bounded cache (${stats.frames} frames)`);
    assert.ok(stats.waiters <= 1, 'the stalled viewer holds at most one waiter');
    const agentStats = s.agent.previews.stats;
    assert.ok(agentStats.sent >= 2);
    // A viewer returning after a pause jumps straight to the newest frame.
    await sleep(300);
    const fresh = await a.get(`/api/phones/${id}/frame?tier=focus`);
    assert.equal(Number(fresh.headers.get('x-frame-seq')), s.portal.previews.latest(id, 'focus').seq);
    stalled.destroy();
    await waitFor(() => s.portal.previews.stats().waiters === 0, { message: 'stalled waiter cleaned up' });
  } finally { await s.close(); }
});

test('grid previews run at low rate and focus previews faster, sharing one capture loop per phone', async () => {
  const s = await startStack({ speed: 0.2 });
  try {
    const a = new Browser(s.base); await a.login(s.users.a.email);
    const id = (await a.get('/api/phones')).data.phones[0].id;
    const t0 = Date.now();
    const shots0 = s.sim.log.length;
    await a.get(`/api/phones/${id}/frame?tier=grid`);
    await a.get(`/api/phones/${id}/frame?tier=focus`);
    await sleep(2000);
    const st = s.agent.previews.stats;
    assert.equal(s.agent.previews.phones.size, 1, 'one capture loop for the phone, not one per tier');
    assert.ok(st.captured > 5, `focus tier captures often (${st.captured})`);
    assert.equal(s.sim.log.length, shots0, 'previews never send input');
    assert.ok(Date.now() - t0 < 5000);
  } finally { await s.close(); }
});

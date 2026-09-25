// Acceptance: the milestone-1 path end to end, and Customer A / Customer B isolation.
// Runs the real portal + real rack agent against the SIMULATED kernel.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startStack, Browser, waitFor } from './helpers/stack.mjs';

let s, a, a2, b, staff, aPhones, bPhones;
before(async () => {
  s = await startStack({ phones: 5 });
  a = new Browser(s.base); await a.login(s.users.a.email);
  a2 = new Browser(s.base); await a2.login(s.users.a2.email);
  b = new Browser(s.base); await b.login(s.users.b.email);
  staff = new Browser(s.base); await staff.login(s.users.staff.email);
  aPhones = (await a.get('/api/phones')).data.phones;
  bPhones = (await b.get('/api/phones')).data.phones;
});
after(() => s.close());

test('complete path: login → phones → preview → control → action → release → audit', async () => {
  assert.equal(aPhones.length, 3);
  const phone = aPhones[0];
  assert.equal(phone.video.state, 'live');
  assert.equal(phone.input.state, 'ready');
  assert.equal(phone.rack.simulated, true, 'simulator is labelled');
  assert.ok(!('kernelId' in phone) && !JSON.stringify(phone).includes('5E:11'), 'no internal device IDs in the customer view');

  await a.get(`/api/phones/${phone.id}/frame?tier=focus`);
  const frame = await a.get(`/api/phones/${phone.id}/frame?tier=focus&after=0`);
  assert.equal(frame.status, 200);
  assert.equal(frame.headers.get('content-type'), 'image/jpeg');
  assert.equal(frame.headers.get('x-source-width'), '500');
  assert.equal(frame.data[0], 0xff);

  const ctl = await a.post(`/api/phones/${phone.id}/control`);
  assert.equal(ctl.status, 200);
  assert.equal(ctl.data.phone.input.state, 'yours');
  const since = Date.now();
  const tap = await a.post(`/api/phones/${phone.id}/actions`, { action: { type: 'tap', x: 250, y: 900 } });
  assert.equal(tap.data.command.status, 'succeeded');
  assert.equal(s.sim.delivered(s.kernelIds[0], since).filter(e => e.fun === '/mouse/click').length, 1);

  const rel = await a.post(`/api/phones/${phone.id}/control/release`);
  assert.equal(rel.data.phone.input.state, 'ready');
  const after = await a.post(`/api/phones/${phone.id}/actions`, { action: { type: 'tap', x: 1, y: 1 } });
  assert.deepEqual([after.data.command.status, after.data.command.reason], ['not_sent', 'not_in_control']);

  const log = (await a.get('/api/activity')).data.entries.map(e => e.action);
  for (const action of ['auth.login', 'control.acquire', 'input.tap', 'control.release']) assert.ok(log.includes(action), action);
});

test('Customer B cannot see or touch Customer A’s phones, previews, jobs or logs', async () => {
  const target = aPhones[1].id;
  assert.deepEqual(bPhones.map(p => p.name), ['Harbor phone 1']);
  const before = s.sim.log.length;
  const attempts = [
    b.get(`/api/phones/${target}`), b.get(`/api/phones/${target}/frame?tier=grid`), b.get(`/api/phones/${target}/frame?tier=focus&after=0`),
    b.get(`/api/phones/${target}/diagnostics`), b.get(`/api/phones/${target}/commands`),
    b.post(`/api/phones/${target}/control`), b.post(`/api/phones/${target}/actions`, { action: { type: 'key', key: 'Home' } }),
    b.post(`/api/phones/${target}/stop`), b.post(`/api/phones/${target}/resume`, { generation: 0 }), b.post(`/api/phones/${target}/name`, { name: 'x' }),
    b.post('/api/groups/control', { phoneIds: [bPhones[0].id, target] }),
    b.post('/api/groups/actions', { phoneIds: [bPhones[0].id, target], action: { type: 'key', key: 'Home' } }),
    b.post('/api/groups/stop', { phoneIds: [target] }),
  ];
  for (const r of await Promise.all(attempts)) assert.equal(r.status, 404, JSON.stringify(r.data));
  assert.equal(s.sim.log.length, before, 'nothing reached any phone');
  const bLog = (await b.get('/api/activity')).data.entries;
  assert.ok(bLog.every(e => e.actor_label !== 'Ada' && e.phone_id !== target), 'no Customer A entries in B’s log');
  const stop = await b.post('/api/stop-all');
  assert.deepEqual(stop.data.results.map(r => r.name), ['Harbor phone 1'], 'Stop all touches only B’s phones');
  assert.equal((await a.get(`/api/phones/${target}`)).data.phone.input.state, 'ready');
});

test('group retry cannot reference another customer’s group action', async () => {
  const phone = aPhones[2];
  await a.post('/api/groups/control', { phoneIds: [phone.id] });
  const g = await a.post('/api/groups/actions', { phoneIds: [phone.id], action: { type: 'key', key: 'Home' } });
  assert.equal(g.status, 200);
  const r = await b.post('/api/groups/actions', { phoneIds: [bPhones[0].id], action: { type: 'key', key: 'Home' }, retryOf: g.data.groupId });
  assert.equal(r.status, 404);
  await a.post('/api/groups/release', { phoneIds: [phone.id] });
});

test('roles: customers cannot use staff endpoints, staff cannot use customer control, members cannot rename', async () => {
  for (const p of ['/api/admin/summary', '/api/admin/phones', '/api/admin/customers', '/api/admin/audit']) assert.equal((await a.get(p)).status, 403, p);
  assert.equal((await a.post('/api/admin/emergency-stop', { confirm: 'STOP' })).status, 403);
  assert.equal((await staff.get('/api/phones')).status, 403);
  assert.equal((await a2.post(`/api/phones/${aPhones[0].id}/name`, { name: 'Renamed' })).status, 403);
  assert.equal((await a.post(`/api/phones/${aPhones[0].id}/name`, { name: 'Main phone' })).status, 200);
});

test('requests without a session, without CSRF, or from another origin are refused', async () => {
  const anon = new Browser(s.base);
  assert.equal((await anon.get('/api/phones')).status, 401);
  assert.equal((await anon.get(`/api/phones/${aPhones[0].id}/frame?tier=grid`)).status, 401);
  const noCsrf = await a.request('POST', `/api/phones/${aPhones[0].id}/control`, {}, { 'x-csrf-token': 'wrong' });
  assert.equal(noCsrf.status, 403);
  const foreign = await a.request('POST', `/api/phones/${aPhones[0].id}/control`, {}, { origin: 'https://evil.example' });
  assert.equal(foreign.status, 403);
});

test('unknown action types and out-of-bounds coordinates never reach the rack', async () => {
  const phone = aPhones[0];
  await a.post(`/api/phones/${phone.id}/control`);
  const before = s.sim.log.length;
  for (const action of [{ type: 'kernel', fun: '/device/set' }, { type: 'tap', x: 9999, y: 1 }, { type: 'text', text: '✓' }, { type: 'key', key: 'OPENKeyboard' }]) {
    const r = await a.post(`/api/phones/${phone.id}/actions`, { action });
    assert.equal(r.status, 400, JSON.stringify(action));
  }
  assert.equal(s.sim.log.length, before);
  await a.post(`/api/phones/${phone.id}/control/release`);
});

test('unassigning a phone ends the old customer’s control and access immediately', async () => {
  const phone = aPhones[1];
  await a.post(`/api/phones/${phone.id}/control`);
  const r = await staff.post(`/api/admin/phones/${phone.id}/unallocate`);
  assert.equal(r.status, 200);
  assert.equal((await a.get(`/api/phones/${phone.id}`)).status, 404);
  assert.equal((await a.post(`/api/phones/${phone.id}/actions`, { action: { type: 'key', key: 'Home' } })).status, 404);
  await waitFor(async () => !(await s.kernel.inputStatus()).phones.find(p => p.id === s.kernelIds[1]).owned, { message: 'lease released at the rack' });
  assert.equal((await staff.post(`/api/admin/phones/${phone.id}/allocate`, { customerId: s.customers.a, friendlyName: 'Studio phone 2' })).status, 201);
});

test('only verified in-service phones can be allocated', async () => {
  const spare = (await staff.get('/api/admin/phones')).data.phones.find(p => !p.customerId);
  assert.ok(spare);
  await staff.post(`/api/admin/phones/${spare.id}/service`, { state: 'unverified' });
  const r = await staff.post(`/api/admin/phones/${spare.id}/allocate`, { customerId: s.customers.b });
  assert.equal(r.status, 409);
  assert.equal(r.data.error, 'not_in_service');
});

test('malformed and traversal paths are refused without crashing the server', async () => {
  const port = new URL(s.base).port;
  const net = await import('node:net');
  for (const path of ['/%E0%A4%A', '/..%2f..%2fetc/passwd', '/assets/../../server/app.js', '/%00']) {
    const reply = await new Promise((resolve, reject) => {
      const sock = net.connect(Number(port), '127.0.0.1', () => sock.write(`GET ${path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n`));
      let buf = ''; sock.on('data', d => { buf += d; }); sock.on('end', () => resolve(buf)); sock.on('error', reject);
    });
    const status = Number(reply.split(' ')[1]);
    assert.ok(status === 404 || status === 400 || (status === 200 && reply.includes('<!doctype html>')), `${path} -> ${status}`);
    assert.ok(!reply.includes('createPortal'), 'server source never served');
  }
  assert.equal((await a.get('/api/phones')).status, 200, 'server still up');
});

test('a preview long-poll that outlives the allocation returns 404, not the next frame', async () => {
  const phone = aPhones[2];
  await a.get(`/api/phones/${phone.id}/frame?tier=focus`);
  const first = await a.get(`/api/phones/${phone.id}/frame?tier=focus&after=0`);
  const seq = Number(first.headers.get('x-frame-seq'));
  const waiting = a.get(`/api/phones/${phone.id}/frame?tier=focus&after=${seq}`);
  await new Promise(r => setTimeout(r, 100));
  assert.equal((await staff.post(`/api/admin/phones/${phone.id}/unallocate`)).status, 200);
  // Change the simulated screen so a new frame is produced while the request waits.
  const sim = s.sim.phone(s.kernelIds[2]);
  sim.screen.state.page = 2; sim.dirty = true;
  const r = await waiting;
  assert.equal(r.status, 404, 'no frame after the phone left this customer');
  assert.equal((await staff.post(`/api/admin/phones/${phone.id}/allocate`, { customerId: s.customers.a, friendlyName: 'Studio phone 3' })).status, 201);
});

test('activity and audit records stay with the right customer', async () => {
  const foreign = await b.get(`/api/activity?phone=${aPhones[0].id}`);
  assert.equal(foreign.status, 200);
  assert.equal(foreign.data.entries.length, 0, 'filtering by another customer’s phone returns nothing');
  const aIds = aPhones.map(p => p.id);
  const rows = s.portal.db.prepare('SELECT customer_id, phone_id FROM audit_log WHERE phone_id IS NOT NULL').all();
  for (const row of rows.filter(r => aIds.includes(r.phone_id)))
    assert.ok(row.customer_id === s.customers.a || row.customer_id === null, 'A’s phone events are never attributed to B');
  const bRows = (await b.get('/api/activity')).data.entries;
  assert.ok(bRows.every(e => !aIds.includes(e.phone_id)));
});

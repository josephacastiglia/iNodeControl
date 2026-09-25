// Acceptance: ownership conflicts with the desktop console, Stop, lease expiry, connection
// loss, uncertain outcomes and credential revocation. SIMULATED kernel; real portal + agent.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startStack, Browser, waitFor, sleep } from './helpers/stack.mjs';

const inputOf = async (s, i) => (await s.kernel.inputStatus()).phones.find(p => p.id === s.kernelIds[i]);
const inputCommands = (s, i, since) => s.sim.delivered(s.kernelIds[i], since).filter(e => e.fun.startsWith('/mouse/') || e.fun === '/key/sendkey');

async function setup(opts) {
  const s = await startStack(opts);
  const a = new Browser(s.base); await a.login(s.users.a.email);
  const phones = (await a.get('/api/phones')).data.phones;
  return { s, a, phones };
}

test('desktop console holds the phone: portal shows it and cannot take or use it', async () => {
  const { s, a, phones } = await setup();
  try {
    const desktop = await s.kernel.command('/input/acquire', { id: s.kernelIds[0] }); // the operator's console
    assert.equal(desktop.code, 0);
    await waitFor(async () => (await a.get(`/api/phones/${phones[0].id}`)).data.phone.input.state === 'operator', { message: 'operator state' });
    const r = await a.post(`/api/phones/${phones[0].id}/control`);
    assert.equal(r.status, 409);
    assert.equal(r.data.error, 'operator_control');
    const act = await a.post(`/api/phones/${phones[0].id}/actions`, { action: { type: 'key', key: 'Home' } });
    assert.equal(act.data.command.status, 'rejected');
    await s.kernel.command('/input/release', { id: s.kernelIds[0], token: desktop.leases[0].token });
  } finally { await s.close(); }
});

test('portal holds the phone: the desktop console is refused; a teammate is refused with a name', async () => {
  const { s, a, phones } = await setup();
  try {
    assert.equal((await a.post(`/api/phones/${phones[0].id}/control`)).status, 200);
    assert.equal((await s.kernel.command('/input/acquire', { id: s.kernelIds[0] })).code, 409, 'desktop acquire refused');
    const ben = new Browser(s.base); await ben.login(s.users.a2.email);
    const r = await ben.post(`/api/phones/${phones[0].id}/control`);
    assert.equal(r.status, 409);
    assert.equal(r.data.holder, 'Ada');
    assert.equal((await ben.post(`/api/phones/${phones[0].id}/actions`, { action: { type: 'key', key: 'Home' } })).data.command.status, 'rejected');
    assert.equal((await ben.get(`/api/phones/${phones[0].id}`)).data.phone.input.state, 'teammate');
  } finally { await s.close(); }
});

test('the rack operator presses Stop: portal control ends and further input is refused', async () => {
  const { s, a, phones } = await setup();
  try {
    await a.post(`/api/phones/${phones[0].id}/control`);
    await s.kernel.command('/input/stop', { id: s.kernelIds[0] });
    await waitFor(async () => (await a.get(`/api/phones/${phones[0].id}`)).data.phone.input.state === 'stopped', { message: 'stopped state' });
    const since = Date.now();
    const r = await a.post(`/api/phones/${phones[0].id}/actions`, { action: { type: 'tap', x: 1, y: 1 } });
    assert.equal(r.data.command.status, 'rejected');
    assert.equal(inputCommands(s, 0, since).length, 0);
  } finally { await s.close(); }
});

test('customer Stop cancels queued actions, releases input, and requires an explicit Resume', async () => {
  const { s, a, phones } = await setup();
  try {
    const id = phones[0].id;
    await a.post(`/api/phones/${id}/control`);
    s.sim.faults(s.kernelIds[0]).commandDelayMs = 800;
    const queued = [1, 2, 3].map(i => a.post(`/api/phones/${id}/actions`, { action: { type: 'tap', x: i, y: 1 } }));
    await sleep(150);
    const stoppedAt = Date.now();
    const stop = await a.post(`/api/phones/${id}/stop`);
    assert.equal(stop.data.result.ok, true);
    const results = (await Promise.all(queued)).map(r => r.data.command.status);
    assert.ok(results.every(r => r === 'cancelled'), results.join());
    assert.equal(inputCommands(s, 0, stoppedAt).length, 0, 'no input after Stop');
    const st = await inputOf(s, 0);
    assert.equal(st.stopped, true);
    s.sim.faults(s.kernelIds[0]).commandDelayMs = 0;

    const phone = (await a.get(`/api/phones/${id}`)).data.phone;
    assert.equal(phone.input.state, 'stopped');
    assert.equal((await a.post(`/api/phones/${id}/control`)).data.error, 'stopped', 'cannot take control until resumed');
    const stale = await a.post(`/api/phones/${id}/resume`, { generation: phone.input.generation - 1 });
    assert.equal(stale.status, 409);
    assert.equal(stale.data.error, 'state_changed');
    assert.equal((await a.post(`/api/phones/${id}/resume`, { generation: phone.input.generation })).status, 200);
    assert.equal((await a.post(`/api/phones/${id}/control`)).status, 200, 'explicit re-acquire after Resume');
    const log = (await a.get('/api/activity')).data.entries.map(e => `${e.action}:${e.outcome}`);
    assert.ok(log.includes('input.stop:ok') && log.includes('input.resume:ok') && log.includes('input.resume:refused'));
  } finally { await s.close(); }
});

test('lease expiry (agent stops renewing) stops the phone; portal control ends; no stale input', async () => {
  const { s, a, phones } = await setup({ agentOptions: { leaseMs: 1000, renewMs: 60_000 } });
  try {
    await a.post(`/api/phones/${phones[0].id}/control`);
    await waitFor(async () => (await inputOf(s, 0)).stopped, { message: 'kernel lease expiry' });
    await waitFor(async () => (await a.get(`/api/phones/${phones[0].id}`)).data.phone.input.state === 'stopped', { message: 'portal sees stopped' });
    const since = Date.now();
    assert.equal((await a.post(`/api/phones/${phones[0].id}/actions`, { action: { type: 'tap', x: 1, y: 1 } })).data.command.status, 'rejected');
    assert.equal(inputCommands(s, 0, since).length, 0);
    const lost = (await a.get('/api/activity')).data.entries.find(e => e.action === 'control.lost');
    assert.ok(lost, 'control loss is audited');
  } finally { await s.close(); }
});

test('portal–rack connection loss releases the phone; nothing is replayed after reconnect', async () => {
  const { s, a, phones } = await setup();
  try {
    const id = phones[0].id;
    await a.post(`/api/phones/${id}/control`);
    s.sim.faults(s.kernelIds[0]).commandDelayMs = 1500;
    const inFlight = a.post(`/api/phones/${id}/actions`, { action: { type: 'tap', x: 5, y: 5 } });
    await sleep(200);
    s.agent.simulateNetworkDrop();
    const r = await inFlight;
    assert.equal(r.data.command.status, 'unknown', 'in-flight action is reported as uncertain, not retried');
    await waitFor(async () => !(await inputOf(s, 0)).owned, { message: 'agent released the lease' });
    s.sim.faults(s.kernelIds[0]).commandDelayMs = 0;
    await waitFor(() => s.portal.hub.isOnline(s.credential.id), { message: 'agent reconnect' });
    const since = Date.now();
    await sleep(600);
    assert.equal(inputCommands(s, 0, since).length, 0, 'nothing replayed after reconnect');
    const phone = (await a.get(`/api/phones/${id}`)).data.phone;
    assert.notEqual(phone.input.state, 'yours', 'control is not silently restored');
    assert.equal((await a.post(`/api/phones/${id}/actions`, { action: { type: 'tap', x: 1, y: 1 } })).data.command.status, 'rejected');
    const clicks = s.sim.delivered(s.kernelIds[0]).filter(e => e.fun === '/mouse/click');
    assert.equal(clicks.length, 1, 'the uncertain tap ran at most once');
  } finally { await s.close(); }
});

test('an action the rack cannot confirm is marked uncertain, stops the phone, and is never retried', async () => {
  const { s, a, phones } = await setup({ agentOptions: { commandTimeoutMs: 600 } });
  try {
    await a.post(`/api/phones/${phones[0].id}/control`);
    s.sim.faults(s.kernelIds[0]).hangMs = 1500;
    const r = await a.post(`/api/phones/${phones[0].id}/actions`, { action: { type: 'key', key: 'Home' } });
    assert.equal(r.data.command.status, 'unknown');
    s.sim.faults(s.kernelIds[0]).hangMs = 0;
    await waitFor(async () => (await inputOf(s, 0)).stopped, { message: 'phone stopped after uncertain outcome' });
    await sleep(1600);
    assert.equal(s.sim.delivered(s.kernelIds[0]).filter(e => e.fun === '/key/sendkey').length, 1);
    const hist = (await a.get(`/api/phones/${phones[0].id}/commands`)).data.commands;
    assert.equal(hist[0].status, 'unknown');
  } finally { await s.close(); }
});

test('revoking the rack credential disconnects the agent, ends control, and refuses reconnection', async () => {
  const { s, a, phones } = await setup();
  try {
    await a.post(`/api/phones/${phones[0].id}/control`);
    const staff = new Browser(s.base); await staff.login(s.users.staff.email);
    assert.equal((await staff.post(`/api/admin/agents/${s.credential.id}/revoke`)).status, 200);
    await waitFor(() => !s.portal.hub.isOnline(s.credential.id), { message: 'agent disconnected' });
    await waitFor(async () => !(await inputOf(s, 0)).owned, { message: 'lease released on disconnect' });
    await sleep(1500);
    assert.equal(s.portal.hub.isOnline(s.credential.id), false, 'revoked agent cannot reconnect');
    const phone = (await a.get(`/api/phones/${phones[0].id}`)).data.phone;
    assert.equal(phone.rack.online, false);
    assert.equal((await a.post(`/api/phones/${phones[0].id}/control`)).status, 503);
    const denied = s.portal.db.prepare("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'agent.connect' AND outcome = 'denied'").get().n;
    assert.ok(denied >= 1);
  } finally { await s.close(); }
});

test('staff emergency stop reaches every phone, including ones the operator console holds', async () => {
  const { s, a, phones } = await setup();
  try {
    await a.post(`/api/phones/${phones[0].id}/control`);
    const desktop = await s.kernel.command('/input/acquire', { id: s.kernelIds[3] });
    assert.equal(desktop.code, 0);
    const staff = new Browser(s.base); await staff.login(s.users.staff.email);
    assert.equal((await staff.post('/api/admin/emergency-stop', { confirm: 'nope' })).status, 400);
    const r = await staff.post('/api/admin/emergency-stop', { confirm: 'STOP' });
    assert.equal(r.status, 200);
    assert.equal(r.data.results[0].phones.length, 4);
    for (let i = 0; i < 4; i++) assert.equal((await inputOf(s, i)).stopped, true, `phone ${i} stopped`);
    assert.equal((await a.get(`/api/phones/${phones[0].id}`)).data.phone.input.state, 'stopped');
  } finally { await s.close(); }
});

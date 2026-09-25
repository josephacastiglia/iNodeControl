// Starts a complete SIMULATED stack in-process for tests and local development:
//   KernelSim (fake kernel over HTTP) <- RackAgent (real agent code) -> Portal (real server)
// Nothing here touches Windows, USB boards or phones.

import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import { createPortal } from '../../server/app.js';
import { hashPassword, newId, newAgentCredential, randomToken } from '../../server/security.js';
import { KernelSim, defaultPhones } from '../../../rack-agent/sim/kernel-sim.js';
import { HttpKernel } from '../../../rack-agent/src/kernel/http-kernel.js';
import { EncoderPool } from '../../../rack-agent/src/encoder-pool.js';
import { RackAgent } from '../../../rack-agent/src/agent.js';

export const PASSWORD = 'correct horse battery';
export const sleep = ms => new Promise(r => setTimeout(r, ms));

export async function waitFor(fn, { timeoutMs = 8000, stepMs = 25, message = 'condition' } = {}) {
  const until = Date.now() + timeoutMs;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > until) throw new Error(`Timed out waiting for ${message}`);
    await sleep(stepMs);
  }
}

const quietLog = { info() {}, warn() {}, error() {} };

export async function startStack({
  phones = 4, speed = 0.05, allocation = { a: [0, 1, 2], b: [3] }, dbPath, port = 0, log = quietLog,
  simOptions = {}, agentOptions = {}, portalOptions = {},
} = {}) {
  const sim = new KernelSim({ phones: defaultPhones(phones), speed, ...simOptions });
  const kernelUrl = await sim.listen();
  const dir = dbPath ? null : fs.mkdtempSync(path.join(os.tmpdir(), 'nt-portal-'));
  const portal = createPortal({ dbPath: dbPath ?? path.join(dir, 'portal.db'), serverSecret: randomToken(32), ...portalOptions });
  const portalPort = await portal.listen(port);
  const base = `http://127.0.0.1:${portalPort}`;
  const { db } = portal;

  const now = Date.now();
  const hash = await hashPassword(PASSWORD);
  const customers = { a: newId(), b: newId() };
  db.prepare('INSERT INTO customers (id, name, plan_phones, timezone, created_at) VALUES (?, ?, ?, ?, ?)').run(customers.a, 'Northwind Studio', 10, 'America/New_York', now);
  db.prepare('INSERT INTO customers (id, name, plan_phones, timezone, created_at) VALUES (?, ?, ?, ?, ?)').run(customers.b, 'Blue Harbor Media', 1, 'Europe/London', now);
  const users = {
    staff: { email: 'staff@nodetheory.test', role: 'staff', customerId: null, name: 'Sam Staff' },
    a: { email: 'ada@northwind.test', role: 'customer_admin', customerId: customers.a, name: 'Ada' },
    a2: { email: 'ben@northwind.test', role: 'customer_member', customerId: customers.a, name: 'Ben' },
    b: { email: 'cleo@blueharbor.test', role: 'customer_admin', customerId: customers.b, name: 'Cleo' },
  };
  for (const u of Object.values(users)) {
    u.id = newId();
    db.prepare('INSERT INTO users (id, customer_id, email, name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)').run(u.id, u.customerId, u.email, u.name, u.role, hash, now);
  }
  const cred = newAgentCredential();
  db.prepare('INSERT INTO agents (id, name, secret_hash, created_at) VALUES (?, ?, ?, ?)').run(cred.id, 'Simulated rack', cred.secretHash, now);

  const kernel = new HttpKernel({ baseUrl: kernelUrl, commandTimeoutMs: agentOptions.commandTimeoutMs ?? 12_000 });
  const encoder = new EncoderPool({ size: 2 });
  const makeAgent = (secret = cred.secret) => new RackAgent({ kernel, encoder, portalUrl: `ws://127.0.0.1:${portalPort}/agent`, agentId: cred.id, secret,
    pollMs: 200, log, reconnectMinMs: 200, reconnectMaxMs: 1000, ...agentOptions });
  const agent = makeAgent();
  await agent.start();
  await waitFor(() => portal.hub.connection(cred.id)?.phones.size === phones, { message: 'agent inventory' });

  const kernelIds = defaultPhones(phones).map(p => p.deviceid);
  const phoneIdOf = kernelId => db.prepare('SELECT id FROM phones WHERE agent_id = ? AND kernel_device_id = ?').get(cred.id, kernelId).id;
  const phoneIds = kernelIds.map(phoneIdOf);
  db.prepare("UPDATE phones SET service_state = 'in_service'").run();
  const allocate = (idx, customerId, name) => db.prepare('INSERT INTO allocations (id, phone_id, customer_id, friendly_name, started_at, started_by) VALUES (?, ?, ?, ?, ?, ?)')
    .run(newId(), phoneIds[idx], customerId, name, now, users.staff.id);
  (allocation.a ?? []).forEach((i, n) => allocate(i, customers.a, `Studio phone ${n + 1}`));
  (allocation.b ?? []).forEach((i, n) => allocate(i, customers.b, `Harbor phone ${n + 1}`));

  return {
    sim, portal, agent, base, users, customers, kernelIds, phoneIds, credential: cred, kernel, encoder, makeAgent,
    async close() {
      await agent.stop().catch(() => {});
      await portal.close().catch(() => {});
      await sim.close().catch(() => {});
      await encoder.close().catch(() => {});
      if (dir) fs.rmSync(dir, { recursive: true, force: true });
    },
  };
}

/** Minimal browser: cookie jar + CSRF header, like the real web app. */
export class Browser {
  constructor(base) { this.base = base; this.cookie = ''; this.csrf = ''; }
  async request(method, pathname, body, headers = {}) {
    const res = await fetch(this.base + pathname, {
      method,
      headers: { ...(this.cookie ? { cookie: this.cookie } : {}), ...(body !== undefined ? { 'content-type': 'application/json' } : {}),
        ...(method !== 'GET' && this.csrf ? { 'x-csrf-token': this.csrf } : {}), ...headers },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      redirect: 'manual',
    });
    const set = res.headers.get('set-cookie');
    if (set) this.cookie = set.split(';')[0];
    const type = res.headers.get('content-type') ?? '';
    const data = type.includes('json') ? await res.json() : type.startsWith('image/') ? Buffer.from(await res.arrayBuffer()) : await res.text();
    return { status: res.status, data, headers: res.headers };
  }
  get(p) { return this.request('GET', p); }
  post(p, body = {}) { return this.request('POST', p, body); }
  async login(email, password = PASSWORD) {
    const r = await this.post('/api/auth/login', { email, password });
    if (r.status !== 200) throw new Error(`Login failed for ${email}: ${r.status} ${JSON.stringify(r.data)}`);
    const me = await this.get('/api/me');
    this.csrf = me.data.csrf;
    return me.data.user;
  }
}

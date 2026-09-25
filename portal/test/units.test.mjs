// Unit tests: coordinate mapping, gesture classification, action-rule parity between the
// portal and the rack agent, authentication, and database migrations.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import { contentRect, toSource, fromSource, classifyGesture, simplifyPath, presetSwipe, textProblem as uiTextProblem } from '../web/lib/coords.js';
import * as portalActions from '../server/actions.js';
import * as agentActions from '../../rack-agent/src/actions.js';
import { openDatabase } from '../server/db.js';
import { hashPassword, verifyPassword } from '../server/security.js';
import { startStack, Browser, PASSWORD } from './helpers/stack.mjs';

const src = { width: 500, height: 1080 };

test('letterboxing: a wide box pads left/right; a tall box pads top/bottom', () => {
  const wide = contentRect(1000, 1080, 500, 1080);
  assert.deepEqual([wide.left, wide.top, wide.width, wide.height], [250, 0, 500, 1080]);
  const tall = contentRect(250, 1000, 500, 1080);
  assert.equal(tall.left, 0);
  assert.ok(Math.abs(tall.top - (1000 - 540) / 2) < 1e-9);
});

test('mapping uses source size, not the (downscaled) JPEG size, and rejects letterbox taps', () => {
  const box = { width: 1000, height: 1080 }, jpeg = { width: 360, height: 778 };
  assert.equal(toSource(100, 500, box, jpeg, src), null, 'tap in the left bar is ignored');
  const centre = toSource(500, 540, box, jpeg, src);
  assert.ok(Math.abs(centre.x - 250) <= 1 && Math.abs(centre.y - 540) <= 1, JSON.stringify(centre));
  assert.deepEqual(toSource(0, 0, { width: 250, height: 540 }, src, src), { x: 0, y: 0 });
  assert.deepEqual(toSource(249.99, 539.99, { width: 250, height: 540 }, src, src), { x: 499, y: 1079 });
  assert.deepEqual(toSource(-50, 2000, { width: 250, height: 540 }, src, src, true), { x: 0, y: 1079 }, 'drags clamp to the edge');
  const back = fromSource(250, 540, { width: 250, height: 540 }, src, src);
  assert.ok(Math.abs(back.x - 125.25) < 0.01 && Math.abs(back.y - 270.25) < 0.01);
});

test('gestures: tap, long press, drag, path simplification and preset swipes stay in bounds', () => {
  assert.deepEqual(classifyGesture([[10, 10], [12, 11]], 120), { type: 'tap', x: 10, y: 10 });
  assert.deepEqual(classifyGesture([[10, 10]], 900), { type: 'longPress', x: 10, y: 10, holdMs: 900 });
  assert.equal(classifyGesture([[10, 10]], 9000).holdMs, 3000);
  const drag = classifyGesture(Array.from({ length: 100 }, (_, i) => [10 + i * 3, 500]), 400);
  assert.equal(drag.type, 'drag');
  assert.equal(drag.points.length, 24);
  assert.deepEqual(drag.points[0], [10, 500]);
  assert.deepEqual(drag.points.at(-1), [307, 500]);
  assert.equal(simplifyPath([[1, 1], [1, 1], [2, 2]]).length, 2);
  for (const d of ['up', 'down', 'left', 'right']) {
    const a = presetSwipe(d, src);
    assert.doesNotThrow(() => portalActions.validateAction(a, src), d);
  }
});

test('portal and rack agent accept and reject exactly the same actions', () => {
  const cases = [
    { type: 'tap', x: 0, y: 0 }, { type: 'tap', x: 499, y: 1079 }, { type: 'tap', x: 500, y: 0 }, { type: 'tap', x: -1, y: 0 }, { type: 'tap', x: 1.5, y: 2 },
    { type: 'longPress', x: 5, y: 5 }, { type: 'longPress', x: 5, y: 5, holdMs: 400 }, { type: 'longPress', x: 5, y: 5, holdMs: 3000 },
    { type: 'drag', points: [[1, 1]] }, { type: 'drag', points: [[1, 1], [2, 2]] }, { type: 'drag', points: Array.from({ length: 25 }, () => [1, 1]) },
    { type: 'key', key: 'Home' }, { type: 'key', key: 'ControlBar' }, { type: 'key', key: 'WIN+v' }, { type: 'key', key: 'home' },
    { type: 'text', text: 'Hello, World! 123' }, { type: 'text', text: '' }, { type: 'text', text: 'x'.repeat(200) }, { type: 'text', text: 'x'.repeat(201) },
    { type: 'text', text: 'tab\there' }, { type: 'text', text: 'café' }, { type: 'text', text: '😀' },
    { type: 'resetPointer' }, { type: 'reset' }, { type: 'raw', fun: '/mouse/click' }, null,
  ];
  for (const c of cases) {
    const p = (() => { try { return JSON.stringify(portalActions.validateAction(c, src)); } catch { return 'rejected'; } })();
    const a = (() => { try { return JSON.stringify(agentActions.validateAction(c, src)); } catch { return 'rejected'; } })();
    assert.equal(p, a, JSON.stringify(c));
    const ui = c?.type === 'text' ? uiTextProblem(c.text) === null : null;
    if (ui !== null) assert.equal(ui, p !== 'rejected', `browser text check matches for ${JSON.stringify(c.text)}`);
  }
  assert.deepEqual(portalActions.FUNCTION_KEYS, agentActions.FUNCTION_KEYS);
  assert.equal(portalActions.MAX_TEXT, agentActions.MAX_TEXT);
  assert.equal(portalActions.TEXT_CHUNK, agentActions.TEXT_CHUNK);
});

test('passwords are scrypt-hashed; wrong and unknown passwords fail', async () => {
  const hash = await hashPassword('a long enough password');
  assert.match(hash, /^scrypt\$/);
  assert.equal(await verifyPassword('a long enough password', hash), true);
  assert.equal(await verifyPassword('wrong password here', hash), false);
  assert.equal(await verifyPassword('anything', undefined), false);
  await assert.rejects(hashPassword('short'));
});

test('migrations apply once, are idempotent, and upgrade version-1 command rows to the three outcomes', async () => {
  const { DatabaseSync } = await import('node:sqlite');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nt-migrate-'));
  const file = path.join(dir, 'p.db');
  // Build a milestone-1 database (migration 001 only) with old-style statuses.
  const v1 = new DatabaseSync(file);
  v1.exec(fs.readFileSync(new URL('../server/migrations/001_initial.sql', import.meta.url), 'utf8'));
  v1.exec('CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at INTEGER NOT NULL)');
  v1.prepare('INSERT INTO schema_migrations VALUES (1, ?, 0)').run('001_initial.sql');
  v1.exec(`INSERT INTO customers (id, name, created_at) VALUES ('c', 'C', 0);
    INSERT INTO users (id, customer_id, email, name, role, password_hash, created_at) VALUES ('u', 'c', 'u@x.test', 'U', 'customer_admin', 'x', 0);
    INSERT INTO agents (id, name, secret_hash, created_at) VALUES ('rack_000000000000', 'R', 'x', 0);
    INSERT INTO phones (id, agent_id, kernel_device_id, first_seen_at, last_seen_at) VALUES ('p', 'rack_000000000000', 'K', 0, 0);`);
  for (const [id, st] of [['1', 'succeeded'], ['2', 'rejected'], ['3', 'failed'], ['4', 'cancelled'], ['5', 'unknown'], ['6', 'sent']])
    v1.prepare("INSERT INTO commands (id, customer_id, user_id, phone_id, kind, summary, status, created_at) VALUES (?, 'c', 'u', 'p', 'tap', 'Tap', ?, 0)").run(id, st);
  v1.close();

  const db = openDatabase(file);
  assert.deepEqual(db.prepare('SELECT version FROM schema_migrations ORDER BY version').all().map(r => r.version), [1, 2]);
  const rows = Object.fromEntries(db.prepare('SELECT id, status FROM commands').all().map(r => [r.id, r.status]));
  // Only rows that were refused before execution become retry-safe "not_sent"; everything else is uncertain.
  assert.deepEqual(rows, { 1: 'succeeded', 2: 'not_sent', 3: 'uncertain', 4: 'uncertain', 5: 'uncertain', 6: 'uncertain' });
  assert.throws(() => db.prepare("UPDATE commands SET status = 'failed' WHERE id = '1'").run(), /CHECK/);
  db.close();
  openDatabase(file).close(); // reopen: nothing reapplied
  fs.rmSync(dir, { recursive: true });
});

test('sessions: HttpOnly SameSite cookie, stored hashed, logout invalidates, login is rate limited', async () => {
  const s = await startStack({ phones: 1, allocation: { a: [0] } });
  try {
    const res = await fetch(s.base + '/api/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email: s.users.a.email, password: PASSWORD }) });
    const cookie = res.headers.get('set-cookie');
    assert.match(cookie, /HttpOnly/);
    assert.match(cookie, /SameSite=Strict/);
    const token = cookie.split(';')[0].split('=')[1];
    const stored = s.portal.db.prepare('SELECT token_hash FROM sessions').all().map(r => r.token_hash);
    assert.ok(!stored.includes(token), 'raw session token is not stored');

    const a = new Browser(s.base); await a.login(s.users.a.email);
    assert.equal((await a.post('/api/auth/logout')).status, 200);
    assert.equal((await a.get('/api/phones')).status, 401);

    const x = new Browser(s.base);
    for (let i = 0; i < 5; i++) assert.equal((await x.post('/api/auth/login', { email: s.users.b.email, password: 'wrong password!' })).status, 401);
    const locked = await x.post('/api/auth/login', { email: s.users.b.email, password: PASSWORD });
    assert.equal(locked.status, 429, 'correct password still refused while locked');
    const audit = s.portal.db.prepare("SELECT detail FROM audit_log WHERE action = 'auth.login'").all().map(r => r.detail).join();
    assert.ok(!audit.includes('wrong password'), 'passwords never reach the audit log');
  } finally { await s.close(); }
});

test('typed text is never stored in commands or the audit log', async () => {
  const s = await startStack({ phones: 1, allocation: { a: [0] } });
  try {
    const a = new Browser(s.base); await a.login(s.users.a.email);
    const id = (await a.get('/api/phones')).data.phones[0].id;
    await a.post(`/api/phones/${id}/control`);
    await a.post(`/api/phones/${id}/actions`, { action: { type: 'text', text: 'SuperSecret-Passw0rd' } });
    const dump = JSON.stringify([s.portal.db.prepare('SELECT * FROM commands').all(), s.portal.db.prepare('SELECT * FROM audit_log').all()]);
    assert.ok(!dump.includes('SuperSecret'), 'typed text leaked');
    assert.ok(dump.includes('Typed 20 characters'));
  } finally { await s.close(); }
});

test('measurement: region/block differences, summaries, and the latency recorder', async () => {
  const { regionMeanDiff, maxBlockDiff, summarize, LatencyRecorder, tapBox } = await import('../web/lib/measure.js');
  const w = 36, h = 78;
  const frame = (fill, patch) => { const d = new Uint8ClampedArray(w * h * 4).fill(fill); if (patch) for (let y = patch.y0; y < patch.y1; y++) for (let x = patch.x0; x < patch.x1; x++) d.set([250, 250, 250, 255], (y * w + x) * 4); return d; };
  const a = frame(10), b = frame(10, { x0: 4, y0: 4, x1: 10, y1: 10 });
  assert.equal(regionMeanDiff(a, a, w, h, { x0: 0, y0: 0, x1: w, y1: h }), 0);
  assert.ok(regionMeanDiff(a, b, w, h, { x0: 4, y0: 4, x1: 10, y1: 10 }) > 200, 'change inside the box');
  assert.equal(regionMeanDiff(a, b, w, h, { x0: 20, y0: 40, x1: 30, y1: 50 }), 0, 'no change elsewhere');
  assert.ok(maxBlockDiff(a, b, w, h) > 50, 'a small change is found by the block scan');
  assert.deepEqual(summarize([5, 1, 3, 2, 4]), { count: 5, median: 3, p95: 5, min: 1, max: 5 });
  assert.deepEqual(tapBox({ x: 250, y: 540 }, { width: 500, height: 1080 }, { width: 360, height: 778 }, 24).x0.toFixed(2), '162.72');

  let t = 1000;
  const rec = new LatencyRecorder({ threshold: 8, timeoutMs: 5000, now: () => t });
  rec.onFrame(a, w, h, t);                                     // baseline before the click
  const m = rec.start({ label: 'Tap', point: { x: 100, y: 100 }, source: { width: 500, height: 1080 } });
  t = 1150; rec.ack(m, 'succeeded');
  t = 1200; rec.onFrame(a, w, h, t);                            // nothing changed yet
  t = 1420; rec.onFrame(b, w, h, t);                            // tap box (100,100) → jpeg (7.2,7.2) changed
  assert.equal(rec.results.length, 1);
  assert.deepEqual([rec.results[0].ackMs, rec.results[0].visibleMs], [150, 420]);
  const miss = rec.start({ label: 'Home' });
  rec.ack(miss, 'succeeded');
  t = 7000; rec.tick();
  assert.equal(rec.results[1].visibleMs, null);
  assert.match(rec.results[1].note, /no visible change/);
  const notSent = rec.start({ label: 'Tap', point: { x: 1, y: 1 }, source: { width: 500, height: 1080 } });
  rec.ack(notSent, 'not_sent');
  assert.equal(rec.results[2].note, 'action not confirmed sent', 'unsent actions are not counted as latency misses');
  assert.equal(rec.summary().noVisibleChange, 1);
});

test('bootstrap-validation creates accounts and a rack credential once, writing secrets only to files', async () => {
  const { spawnSync } = await import('node:child_process');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nt-boot-'));
  const run = () => spawnSync(process.execPath, ['--disable-warning=ExperimentalWarning', 'scripts/bootstrap-validation.mjs', '--out', path.join(dir, 'out')],
    { cwd: new URL('..', import.meta.url), env: { ...process.env, NT_DB_PATH: path.join(dir, 'v.db') }, encoding: 'utf8' });
  const first = run();
  assert.equal(first.status, 0, first.stderr);
  const cred = fs.readFileSync(path.join(dir, 'out', 'rack-credential.txt'), 'utf8');
  const accounts = fs.readFileSync(path.join(dir, 'out', 'accounts.txt'), 'utf8');
  assert.match(cred, /^rack_[a-f0-9]{12}\.[A-Za-z0-9_-]{40,}$/);
  assert.ok(!first.stdout.includes(cred.split('.')[1]) && !first.stdout.includes(accounts.split('\n')[1].trim().split(/\s+/)[2]), 'no secret on the console');
  const db = openDatabase(path.join(dir, 'v.db'));
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM users').get().n, 3);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM allocations').get().n, 0, 'phones are assigned by staff later');
  db.close();
  assert.equal(run().status, 2, 'refuses to run twice on one database');
  fs.rmSync(dir, { recursive: true, force: true });
});

test('measurement: a change seen before the rack confirms (text) keeps both times; status-bar changes are ignored', async () => {
  const { LatencyRecorder, maxBlockDiff } = await import('../web/lib/measure.js');
  const w = 36, h = 100;
  const base = new Uint8ClampedArray(w * h * 4).fill(20);
  const clock = base.slice(); for (let x = 0; x < w; x++) clock.set([255, 255, 255, 255], (2 * w + x) * 4); // row 2: status bar
  assert.equal(maxBlockDiff(base, clock, w, h), 0, 'status bar change ignored');
  const typed = base.slice(); for (let y = 50; y < 56; y++) for (let x = 5; x < 10; x++) typed.set([250, 250, 250, 255], (y * w + x) * 4);
  let t = 0;
  const rec = new LatencyRecorder({ now: () => t });
  rec.setBaseline(base, w, h);
  const m = rec.start({ label: 'Type text' });
  t = 200; rec.onFrame(typed, w, h, t);
  t = 900; rec.ack(m, 'succeeded');
  assert.deepEqual([rec.results[0].visibleMs, rec.results[0].ackMs, rec.results[0].status], [200, 900, 'succeeded']);
});

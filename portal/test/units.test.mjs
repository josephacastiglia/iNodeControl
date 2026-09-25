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

test('migrations apply once and are idempotent on reopen', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nt-migrate-'));
  const file = path.join(dir, 'p.db');
  openDatabase(file).close();
  const db = openDatabase(file);
  assert.deepEqual(db.prepare('SELECT version FROM schema_migrations').all().map(r => r.version), [1]);
  db.close();
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

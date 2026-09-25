// KERNEL CONFORMANCE (real kernel source, fake HID, synthetic frames, any OS).
// Builds rack-agent/conformance/KernelHarness, which compiles src/iMouse.Kernel's
// ApiServer / InputSessions / InputRouter / FrameStore unchanged, and drives it with the
// agent's own HttpKernel + PhoneLane. This checks the agent against the actual ownership
// logic. It is NOT Windows kernel integration and NOT physical-phone validation.
// Skipped automatically when the .NET SDK is not installed.

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { HttpKernel } from '../src/kernel/http-kernel.js';
import { PhoneLane } from '../src/phone-lane.js';
import { validateAction } from '../src/actions.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const project = path.join(here, '..', 'conformance', 'KernelHarness');
const hasDotnet = spawnSync('dotnet', ['--version'], { encoding: 'utf8' }).status === 0;
const size = { width: 500, height: 1080 };
const P1 = 'HARNESS:01', P2 = 'HARNESS:02';

let proc, kernel, hid = [];
const hidFor = (pid, since = 0) => hid.slice(since).filter(l => l.startsWith(`HID ${pid} `));

before(async () => {
  if (!hasDotnet) return;
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'nt-harness-build-'));
  const build = spawnSync('dotnet', ['build', project, '-c', 'Release', '-o', out, '--nologo', '-v', 'q'], { encoding: 'utf8' });
  assert.equal(build.status, 0, build.stdout + build.stderr);
  // On Windows, HttpListener may need a URL reservation (netsh http add urlacl) or an elevated shell.
  const port = Number(process.env.NT_HARNESS_PORT) || 20000 + Math.floor(Math.random() * 20000);
  proc = spawn('dotnet', [path.join(out, 'KernelHarness.dll'), String(port), '--exit-on-stdin-close'], { stdio: ['pipe', 'pipe', 'inherit'] });
  await new Promise((resolve, reject) => {
    let buf = '';
    const t = setTimeout(() => reject(new Error('harness did not start')), 30_000);
    proc.stdout.on('data', d => {
      buf += d;
      const lines = buf.split('\n'); buf = lines.pop();
      for (const l of lines) { if (l.startsWith('READY')) { clearTimeout(t); resolve(); } if (l.startsWith('HID ')) hid.push(l.trim()); }
    });
  });
  kernel = new HttpKernel({ baseUrl: `http://127.0.0.1:${port}/api/` });
  // Wait for the synthetic receiver to deliver a first frame.
  for (let i = 0; i < 50 && !(await kernel.screenshot(P1)).ok; i++) await new Promise(r => setTimeout(r, 100));
});
after(() => { proc?.stdin.end(); proc?.kill(); });

const t = (name, fn) => test(name, { skip: !hasDotnet && 'dotnet SDK not installed' }, fn);

t('capability, device list and separate video/input status come from the real kernel code', async () => {
  const cap = await kernel.capability();
  assert.equal(cap.compatible, true);
  assert.equal(cap.simulated, false);
  const devices = await kernel.devices();
  assert.deepEqual(devices.map(d => d.deviceid).sort(), [P1, P2]);
  const status = await kernel.kernelStatus();
  const r1 = status.receivers.find(r => r.deviceid === P1), r2 = status.receivers.find(r => r.deviceid === P2);
  assert.equal(r1.live, true);
  assert.equal(r2.live, false);
  const input = await kernel.inputStatus();
  assert.equal(input.phones.length, 2);
  const boards = await kernel.boards();
  // Linux: USB enumeration fails inside the kernel (500) and the adapter returns null.
  // Windows: the kernel enumerates real boards read-only; the harness never writes to them.
  assert.ok(boards === null || Array.isArray(boards));
});

t('screenshots: image/bmp when live, JSON code 25 when no frame, code 1 for unknown ids', async () => {
  const live = await kernel.screenshot(P1);
  assert.equal(live.ok, true);
  assert.equal(live.bmp.length, 54 + 1500 * 1080);
  const none = await kernel.screenshot(P2);
  assert.deepEqual([none.ok, none.code], [false, 25]);
  const unknown = await kernel.screenshot('NOPE');
  assert.deepEqual([unknown.ok, unknown.code], [false, 1]);
});

t('input without a lease is refused before any HID output', async () => {
  const mark = hid.length;
  const data = await kernel.command('/mouse/click', { id: P1, x: 10, y: 10 });
  assert.equal(data.code, 409);
  assert.equal(hidFor('C24C', mark).length, 0);
});

t('lane: acquire, tap, text chunks, drag and long press reach HID; release frees the phone', async () => {
  const lane = new PhoneLane(P1, kernel);
  assert.deepEqual(await lane.acquire({ sessionId: 's1' }), { ok: true });
  const mark = hid.length;
  for (const a of [{ type: 'tap', x: 100, y: 200 }, { type: 'text', text: 'abc' }, { type: 'drag', points: [[300, 500], [200, 500]] }, { type: 'longPress', x: 100, y: 200, holdMs: 500 }]) {
    const r = await lane.enqueue({ sessionId: 's1' }, 'c-' + a.type, validateAction(a, size));
    assert.equal(r.status, 'succeeded', `${a.type}: ${r.message}`);
  }
  const reports = hidFor('C24C', mark);
  assert.ok(reports.some(l => l.endsWith('A101000000000000')), 'button down reached HID');
  assert.ok(reports.some(l => l.includes('A2000400')), 'letter a reached HID');
  assert.equal(hidFor('C241', mark).length, 0, 'the other phone received nothing');
  assert.equal((await lane.release({ sessionId: 's1' })).ok, true);
  const st = (await kernel.inputStatus()).phones.find(p => p.id === P1);
  assert.deepEqual([st.owned, st.stopped], [false, false]);
});

t('ownership conflict: a desktop-held lease blocks the lane, and the lane blocks the desktop', async () => {
  const desktop = await kernel.command('/input/acquire', { id: P2 });
  assert.equal(desktop.code, 0);
  const lane = new PhoneLane(P2, kernel);
  const refused = await lane.acquire({ sessionId: 's2' });
  assert.deepEqual([refused.ok, refused.reason], [false, 'owned_elsewhere']);
  await kernel.command('/input/release', { id: P2, token: desktop.leases[0].token });
  assert.equal((await lane.acquire({ sessionId: 's2' })).ok, true);
  assert.equal((await kernel.command('/input/acquire', { id: P2 })).code, 409);
  await lane.release({ sessionId: 's2' });
});

t('Stop latches in the kernel; stale-generation Resume is refused; fresh Resume works', async () => {
  const events = [];
  const lane = new PhoneLane(P1, kernel, { onEvent: e => events.push(e) });
  assert.equal((await lane.acquire({ sessionId: 's3' })).ok, true);
  const before = (await kernel.inputStatus()).phones.find(p => p.id === P1).generation;
  assert.equal((await lane.stop('test stop')).ok, true);
  assert.equal(events[0]?.reason, 'stopped');
  const st = (await kernel.inputStatus()).phones.find(p => p.id === P1);
  assert.equal(st.stopped, true);
  assert.ok(st.generation > before);
  assert.equal((await lane.acquire({ sessionId: 's4' })).reason, 'stopped');
  assert.equal((await lane.resume(before)).code, 409, 'stale generation refused');
  assert.equal((await lane.resume(st.generation)).ok, true);
  assert.equal((await lane.acquire({ sessionId: 's4' })).ok, true);
  await lane.release({ sessionId: 's4' });
});

t('lease expiry without renewal stops the phone and later input is refused', async () => {
  const events = [];
  const lane = new PhoneLane(P2, kernel, { leaseMs: 1000, renewMs: 60_000, onEvent: e => events.push(e) });
  assert.equal((await lane.acquire({ sessionId: 's5' })).ok, true);
  await new Promise(r => setTimeout(r, 1400));
  const st = (await kernel.inputStatus()).phones.find(p => p.id === P2);
  assert.equal(st.stopped, true);
  assert.match(st.message, /expired/i);
  lane.observe(st, Date.now());
  assert.equal(events[0]?.reason, 'stopped');
  const mark = hid.length;
  const r = await lane.enqueue({ sessionId: 's5' }, 'late', validateAction({ type: 'tap', x: 1, y: 1 }, size));
  assert.equal(r.status, 'rejected');
  assert.equal(hidFor('C241', mark).filter(l => !l.endsWith('A100000000000000') && !l.endsWith('A200000000000000')).length, 0);
  await lane.resume(st.generation);
});

t('real kernel timing: one 64-character sendkey exceeds the 8 s command deadline; the chunked lane succeeds', { timeout: 60_000 }, async () => {
  const text = 'abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnopqrstuvwxyz01'; // 64 chars ≈ 9 s at 140 ms each
  const desktop = await kernel.command('/input/acquire', { id: P1 });
  const started = Date.now();
  const whole = await kernel.command('/key/sendkey', { id: P1, token: desktop.leases[0].token, key: text });
  assert.equal(whole.results[0].code, 499, 'kernel cancels the command at its deadline');
  assert.ok(Date.now() - started < 10_000);
  const st = (await kernel.inputStatus()).phones.find(p => p.id === P1);
  assert.equal(st.stopped, true, 'a cancelled command latches Stop');
  await kernel.command('/input/resume', { id: P1, expected_generations: { [P1]: st.generation } });

  const lane = new PhoneLane(P1, kernel);
  assert.equal((await lane.acquire({ sessionId: 's6' })).ok, true);
  const r = await lane.enqueue({ sessionId: 's6' }, 'long-text', validateAction({ type: 'text', text }, size));
  assert.equal(r.status, 'succeeded', r.message);
  await lane.release({ sessionId: 's6' });
});

#!/usr/bin/env node
// ============================================================================
//  SIMULATED iNodeControl KERNEL — for cloud development and automated tests.
//  No USB boards, no iPhones, no AirPlay. Results from this simulator are NOT
//  Windows kernel integration and NOT physical-phone validation.
// ============================================================================
//
// Speaks the same HTTP contract as src/iMouse.Kernel/ApiServer.cs (commit ee445d7)
// and mirrors the ownership rules of InputSessions.cs:
//  - input requires a per-phone lease (/input/acquire → token, renew, release);
//  - an expired lease, a failed/cancelled command, or /input/stop latches Stop and
//    bumps the phone's generation; /input/resume clears it only after cleanup and
//    only if expected_generations still match;
//  - at most one active command per phone; a second is rejected (409), never queued;
//  - each command is cancelled after 8 s (code 499), which also latches Stop;
//  - screenshots return image/bmp, or a JSON envelope with code 25 when no live frame.
// Status JSON adds "simulated": true so every consumer can label it.

import http from 'node:http';
import crypto from 'node:crypto';
import { SimScreen } from './screen.js';

const FN_KEYS = ['Home', 'Enter', 'ENTER', 'Backspace', 'BACKSPACE', 'Tab', 'Escape', 'AppSwitch', 'ControlBar'];
const INPUT_FUNS = ['/mouse/move', '/mouse/down', '/mouse/up', '/mouse/click', '/mouse/reset', '/mouse/swipe', '/key/sendkey', '/device/usb/restart'];

class HttpError extends Error { constructor(code, message) { super(message); this.code = code; } }

export function defaultPhones(count = 6) {
  return Array.from({ length: count }, (_, i) => {
    const n = String(i + 1).padStart(2, '0');
    return {
      deviceid: `5E:11:00:00:00:${n}`, name: `Sim phone ${i + 1}`, pid: `S0${n}`, uid: `S0${n}SIM0`,
      model: 'iPhone XR', version: '18.7.10', width: 414, height: 896, imgw: 500, imgh: 1080,
      enabled: true, boardPresent: true, videoLive: true, hue: (i * 53) % 360,
    };
  });
}

const asciiOk = ch => { const c = ch.codePointAt(0); return (c >= 32 && c <= 126) || '\r\n\t\b\u001b'.includes(ch); };

export class KernelSim {
  /**
   * @param {object} [o]
   * @param {object[]} [o.phones]
   * @param {number} [o.speed] multiplies simulated HID durations (tests use < 1)
   * @param {number} [o.deadlineMs] per-command deadline (kernel: 8000)
   * @param {number} [o.keepaliveMs] identical-frame keepalive interval (AirPlay-like)
   */
  constructor({ phones = defaultPhones(), speed = 1, deadlineMs = 8000, keepaliveMs = 1000, advertiseProtocol = true } = {}) {
    this.speed = speed;
    this.deadlineMs = deadlineMs;
    this.advertiseProtocol = advertiseProtocol;
    this.closed = false;
    this.log = [];
    this.phones = new Map();
    for (const p of phones) {
      this.phones.set(p.deviceid, {
        def: { ...p },
        screen: new SimScreen(p.imgw, p.imgh, p.hue ?? 0),
        dirty: true, bmp: null, frames: 0, receiverPid: 4000 + this.phones.size,
        slot: { owner: null, active: null, cleaning: null, stopped: false, message: '', releaseFailed: false, generation: 0 },
        hid: { known: false, x: 0, y: 0, button: 0 },
        // failNext: fail the next N commands. failAfter: let N commands succeed, then fail one.
        // hangAfter {calls, ms}: let N commands answer normally, then delay one reply by ms.
        faults: { failNext: 0, failAfter: null, hangMs: 0, hangAfter: null, commandDelayMs: 0, releaseFail: false },
      });
    }
    this.keepalive = setInterval(() => {
      for (const p of this.phones.values()) if (p.def.videoLive) { p.frames++; if (p.screen.animating) p.dirty = true; }
    }, keepaliveMs);
    this.keepalive.unref();
    this.watch = setInterval(() => this.#expireLeases(), 100);
    this.watch.unref();
  }

  // ---- test/dev helpers ------------------------------------------------------
  phone(id) { const p = this.phones.get(id); if (!p) throw new Error('No sim phone ' + id); return p; }
  faults(id) { return this.phone(id).faults; }
  setVideo(id, live) { const p = this.phone(id); p.def.videoLive = live; p.dirty = true; }
  delivered(id, since = 0) { return this.log.filter(e => e.id === id && e.at >= since); }

  async listen(port = 0, host = '127.0.0.1') {
    this.server = http.createServer((req, res) => this.#handle(req, res));
    await new Promise(r => this.server.listen(port, host, r));
    const addr = this.server.address();
    this.url = `http://${host}:${addr.port}/api/`;
    return this.url;
  }

  async close() {
    this.closed = true;
    clearInterval(this.keepalive);
    clearInterval(this.watch);
    await new Promise(r => this.server ? this.server.close(() => r()) : r());
    this.server?.closeAllConnections?.();
  }

  // ---- HTTP ------------------------------------------------------------------
  #write(res, status, data) {
    const body = Buffer.from(JSON.stringify({ status, message: status === 200 ? 'ok' : 'error', data }));
    res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'content-length': body.length });
    res.end(body);
  }

  async #handle(req, res) {
    try {
      const url = new URL(req.url, 'http://x');
      const path = url.pathname.replace(/\/+$/, '');
      if (req.method === 'GET' && path.endsWith('/device/get')) return this.#write(res, 200, { code: 0, list: this.#deviceList() });
      if (req.method === 'GET' && path.endsWith('/config/usb/get')) return this.#write(res, 200, { code: 0, list: this.#boards() });
      if (req.method === 'GET' && path.endsWith('/kernel/status')) return this.#write(res, 200, this.#kernelStatus());
      if (req.method === 'GET' && path.endsWith('/input/status')) return this.#write(res, 200, this.#inputStatus());
      if (req.method === 'GET' && path.includes('/pic/screenshot')) return this.#screenshot(res, url.searchParams.get('id') ?? '');
      if (req.method === 'POST') {
        const chunks = [];
        for await (const c of req) chunks.push(c);
        const text = Buffer.concat(chunks).toString('utf8');
        let body = {};
        if (text.trim()) { try { body = JSON.parse(text); } catch (e) { return this.#write(res, 200, { code: 36, message: e.message }); } }
        const result = await this.#dispatch(String(body.fun ?? ''), body.data && typeof body.data === 'object' ? body.data : {});
        if (result.__hangMs) await new Promise(r => setTimeout(r, result.__hangMs));
        delete result.__hangMs;
        return this.#write(res, 200, result);
      }
      return this.#write(res, 404, { code: 41, message: 'Unknown path.' });
    } catch (err) {
      if (err instanceof HttpError) return this.#write(res, 200, { code: err.code, message: err.message });
      return this.#write(res, 500, { code: 33, message: err.message });
    }
  }

  #deviceList() {
    return [...this.phones.values()].map(p => ({
      deviceid: p.def.deviceid, name: p.def.name, user_name: p.def.name, device_name: p.def.model, gname: 'Simulated rack',
      state: p.def.videoLive ? 1 : 0, video_state: p.def.videoLive ? 'mirroring' : 'offline',
      receiver_name: 'iMouse2-' + p.def.pid, width: String(p.def.width), height: String(p.def.height),
      imgw: p.def.imgw, imgh: p.def.imgh, air_pid: p.def.videoLive ? p.receiverPid : 0, version: p.def.version,
      uid: p.def.uid, vid: '720A', pid: p.def.pid, rotate: 0,
    }));
  }
  #boards() {
    return [...this.phones.values()].filter(p => p.def.boardPresent)
      .map(p => ({ vid: '720A', pid: p.def.pid, uid: p.def.uid, state: p.def.enabled ? 2 : 1 }));
  }
  #kernelStatus() {
    const receivers = [...this.phones.values()].map(p => ({
      deviceid: p.def.deviceid, name: 'iMouse2-' + p.def.pid, receiver_pid: p.receiverPid, receiver_restarts: 0,
      receiver_state: p.def.videoLive ? 'mirroring' : 'offline', live: p.def.videoLive, frames: p.frames,
    }));
    const base = { code: 0, input: 'direct-hid', simulated: true, allowed: [...this.phones.values()].filter(p => p.def.enabled).map(p => p.def.pid),
      receiver: receivers.map(r => r.name).join(' / '), receivers };
    return this.advertiseProtocol ? { ...base, input_protocol: 1, input_leases_required: true } : base;
  }
  #inputStatus() {
    const now = Date.now();
    return { code: 0, protocol: 1, phones: [...this.phones.values()].filter(p => p.def.enabled).map(p => {
      const s = p.slot;
      return { id: p.def.deviceid, owned: !!s.owner, active: !!s.active, stopped: s.stopped, releasing: !!s.cleaning,
        release_failed: s.releaseFailed, message: s.message, generation: s.generation,
        lease_remaining_ms: s.owner ? Math.max(0, s.owner.deadline - now) : 0 };
    }) };
  }
  #screenshot(res, id) {
    const p = this.phones.get(id);
    if (!p) return this.#write(res, 200, { code: 1, message: 'Unknown receiver device.' });
    if (!p.def.videoLive) return this.#write(res, 200, { code: 25, message: `No live frame. Select iMouse2-${p.def.pid} in iPhone Screen Mirroring.` });
    if (p.dirty || !p.bmp) {
      p.screen.state.pointer = p.hid.known ? { x: p.hid.x, y: p.hid.y } : null;
      p.bmp = p.screen.render(Date.now(), p.def.name.toUpperCase());
      p.dirty = p.screen.animating;
      p.frames++;
    }
    res.writeHead(200, { 'content-type': 'image/bmp', 'cache-control': 'no-store', 'content-length': p.bmp.length });
    res.end(p.bmp);
  }

  // ---- ownership (mirrors InputSessions.cs) -----------------------------------
  #targets(data) {
    const ids = [...new Set(String(data.id ?? '').split(',').map(s => s.trim()).filter(Boolean))];
    if (ids.length === 0) throw new HttpError(36, 'id required');
    const phones = ids.map(id => { const p = this.phones.get(id); if (!p) throw new HttpError(1, 'Device not found: ' + id); return p; });
    if (phones.some(p => !p.def.enabled)) throw new HttpError(36, 'Every phone needs an enabled calibrated board.');
    return phones;
  }
  #token(data, id) {
    if (data.tokens && typeof data.tokens === 'object' && id in data.tokens) return String(data.tokens[id]);
    return data.token === undefined ? '' : String(data.token);
  }
  #validateOwner(p, data) {
    const s = p.slot;
    if (this.closed || s.stopped || s.cleaning) throw new HttpError(409, 'Input stopped or recovering; inspect status before resuming.');
    if (!s.owner || s.owner.token !== this.#token(data, p.def.deviceid)) throw new HttpError(409, 'A valid per-phone input lease is required.');
    if (Date.now() >= s.owner.deadline) { this.#beginClose(p, true, 'Controller lease expired.'); throw new HttpError(409, 'Controller lease expired; input stopped.'); }
  }
  #expireLeases() {
    const now = Date.now();
    for (const p of this.phones.values()) if (p.slot.owner && now >= p.slot.owner.deadline) this.#beginClose(p, true, 'Controller lease expired.');
  }
  #beginClose(p, stop, message) {
    const s = p.slot;
    s.stopped ||= stop; s.message = message; s.generation++;
    if (s.cleaning) return s.cleaning;
    const lease = s.owner; s.owner = null;
    const drained = s.active ?? Promise.resolve();
    s.cleaning = (async () => {
      await Promise.resolve();
      lease?.abort.abort();
      await drained.catch(() => {});
      p.hid.button = 0; p.hid.known = false;
      this.log.push({ at: Date.now(), id: p.def.deviceid, fun: 'release-inputs' });
      if (p.faults.releaseFail) { s.stopped = true; s.releaseFailed = true; s.message = 'Input release could not be confirmed.'; }
      s.cleaning = null;
    })();
    return s.cleaning;
  }

  async #dispatch(fun, data) {
    switch (fun) {
      case '/device/set': return { code: 41, message: 'Live binding changes are disabled in the ownership build. Stop the kernel and verify saved phone/board/receiver configuration before restarting.' };
      case '/input/acquire': return this.#acquire(data);
      case '/input/status': return this.#inputStatus();
      case '/input/renew': return this.#renew(data);
      case '/input/resume': return this.#resume(data);
      case '/input/stop': return this.#stop(data, false);
      case '/input/release': return this.#stop(data, true);
      case '/device/airplay/connect': case '/device/airplay/disconnect':
        return { code: 41, message: 'Choose or stop the receiver in the iPhone\'s Screen Mirroring menu.' };
      default:
        if (INPUT_FUNS.includes(fun)) return this.#input(fun, data);
        return { code: 41, message: 'Not implemented: ' + fun };
    }
  }

  #acquire(data) {
    const phones = this.#targets(data);
    const duration = data.lease_ms === undefined ? 30_000 : parseInt(data.lease_ms, 10);
    if (!(duration >= 1000 && duration <= 120_000)) throw new HttpError(36, 'lease_ms must be 1000–120000.');
    for (const p of phones) {
      const s = p.slot;
      if (s.owner && Date.now() >= s.owner.deadline) this.#beginClose(p, true, 'Controller lease expired.');
      if (this.closed || s.stopped || s.cleaning || s.owner || s.active)
        return { code: 409, message: 'A target is owned, stopped, or recovering. No leases acquired.' };
    }
    for (const p of phones) p.slot.owner = { token: crypto.randomBytes(16).toString('hex'), deadline: Date.now() + duration, duration, abort: new AbortController() };
    return { code: 0, leases: phones.map(p => ({ id: p.def.deviceid, token: p.slot.owner.token, lease_ms: duration })) };
  }
  #renew(data) {
    const phones = this.#targets(data);
    for (const p of phones) this.#validateOwner(p, data);
    for (const p of phones) p.slot.owner.deadline = Date.now() + p.slot.owner.duration;
    return { code: 0 };
  }
  #resume(data) {
    const phones = this.#targets(data);
    if (this.closed || phones.some(p => p.slot.cleaning || p.slot.active || p.slot.owner || p.slot.releaseFailed))
      return { code: 409, message: 'Cleanup must finish successfully before resuming.' };
    const exp = data.expected_generations;
    if (exp !== undefined && phones.some(p => typeof exp !== 'object' || exp === null || !(p.def.deviceid in exp) || Number(exp[p.def.deviceid]) !== p.slot.generation))
      return { code: 409, message: 'Input state changed; inspect status before resuming.' };
    for (const p of phones) { p.slot.stopped = false; p.slot.message = ''; }
    return { code: 0, message: 'Input ready for a new lease. Old tokens remain invalid.' };
  }
  async #stop(data, release) {
    const phones = this.#targets(data);
    if (release) for (const p of phones) this.#validateOwner(p, data);
    await Promise.all(phones.map(p => this.#beginClose(p, !release, release ? 'Controller released.' : 'Stopped by operator.')));
    const failed = phones.some(p => p.slot.releaseFailed);
    return { code: failed ? 33 : 0, message: failed ? 'Release failed; input remains stopped. Check the board.' : 'Input released; previous tokens revoked.' };
  }

  // ---- input (mirrors InputRouter.Validate / ExecuteAsync) ----------------------
  #validateCommand(fun, data, p) {
    const inImage = (x, y) => {
      const px = parseInt(data[x], 10), py = parseInt(data[y], 10);
      if (!(px >= 0 && py >= 0 && px < p.def.imgw && py < p.def.imgh)) throw new HttpError(36, 'Coordinates outside calibrated image.');
    };
    if (fun === '/device/usb/restart') return;
    if (fun === '/mouse/move' || fun === '/mouse/click') inImage('x', 'y');
    if (['/mouse/down', '/mouse/up', '/mouse/click'].includes(fun) && data.button !== undefined && parseInt(data.button, 10) !== 1)
      throw new HttpError(36, 'Only the verified left button is supported.');
    if (fun === '/mouse/swipe') {
      if (!data.direction) { inImage('x1', 'y1'); inImage('x2', 'y2'); }
      const duration = data.duration === undefined ? 300 : parseInt(data.duration, 10);
      if (!(duration >= 20 && duration <= 5000)) throw new HttpError(36, 'duration must be 20–5000 ms.');
    }
    if (fun === '/key/sendkey') {
      const key = String(data.fn_key ?? ''), value = String(data.key ?? '');
      if (key && !FN_KEYS.includes(key)) throw new HttpError(36, 'Function key has not been verified: ' + key);
      if (value.length > 1000 || (!key && !value)) throw new HttpError(36, 'Provide a key or 1–1000 ASCII characters.');
      for (const ch of value) if (!asciiOk(ch)) throw new HttpError(36, 'Unsupported character U+' + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, '0'));
    }
  }

  async #input(fun, data) {
    if (fun === '/device/usb/restart') return { code: 41, message: 'Restart packet has not been decoded.' };
    const phones = this.#targets(data);
    for (const p of phones) this.#validateCommand(fun, data, p);
    for (const p of phones) this.#validateOwner(p, data);
    if (phones.some(p => p.slot.active)) return { code: 409, message: 'Input busy; no commands queued.' };
    const done = [];
    for (const p of phones) { let resolve; p.slot.active = new Promise(r => { resolve = r; }); done.push(resolve); }
    const results = await Promise.all(phones.map(async (p, i) => {
      const lease = p.slot.owner;
      const deadline = AbortSignal.timeout(this.deadlineMs);
      const signal = AbortSignal.any([lease.abort.signal, deadline]);
      let code = 0, message = 'ok';
      try { await this.#execute(p, fun, data, signal); }
      catch (err) {
        if (signal.aborted) { code = 499; message = 'Input cancelled'; }
        else { code = 33; message = err.message; }
        p.hid.button = 0;
      }
      p.slot.active = null; done[i]();
      if (code !== 0) await this.#beginClose(p, true, message);
      return { id: p.def.deviceid, code, message };
    }));
    let hang = Math.max(...phones.map(p => p.faults.hangMs));
    for (const p of phones) {
      const h = p.faults.hangAfter;
      if (!h) continue;
      if (h.calls === 0) { hang = Math.max(hang, h.ms); p.faults.hangAfter = null; } else h.calls--;
    }
    return { code: results.every(r => r.code === 0) ? 0 : 33, results, ...(hang > 0 ? { __hangMs: hang } : {}) };
  }

  async #wait(ms, signal) {
    const scaled = ms * this.speed;
    await new Promise((resolve, reject) => {
      if (signal.aborted) return reject(new Error('cancelled'));
      const t = setTimeout(() => { signal.removeEventListener('abort', onAbort); resolve(); }, scaled);
      const onAbort = () => { clearTimeout(t); reject(new Error('cancelled')); };
      signal.addEventListener('abort', onAbort, { once: true });
    });
  }

  async #move(p, x, y, signal) {
    const h = p.hid;
    if (!h.known) {
      if (h.button) throw new Error('Reset the pointer before starting a drag.');
      await this.#wait(40, signal); h.known = true; h.x = 14; h.y = 14;
    }
    const steps = Math.round(Math.max(Math.abs(x - h.x), Math.abs(y - h.y)) / 5.1);
    await this.#wait(Math.max(0, steps) * 3, signal);
    h.x = x; h.y = y; p.dirty = true;
  }

  async #execute(p, fun, data, signal) {
    const { hid: h, screen } = p;
    const id = p.def.deviceid;
    const { token, tokens, ...safe } = data;
    this.log.push({ at: Date.now(), id, fun, data: { ...safe, id } });
    if (p.faults.commandDelayMs) await this.#wait(p.faults.commandDelayMs / this.speed, signal);
    if (p.faults.failNext > 0) { p.faults.failNext--; throw new Error('Simulated HID transport failure.'); }
    if (p.faults.failAfter !== null) {
      if (p.faults.failAfter === 0) { p.faults.failAfter = null; throw new Error('Simulated HID transport failure.'); }
      p.faults.failAfter--;
    }
    const now = () => Date.now();
    switch (fun) {
      case '/mouse/reset': h.button = 0; await this.#wait(40, signal); h.known = true; h.x = 14; h.y = 14; break;
      case '/mouse/move': {
        const from = { x: h.x, y: h.y };
        await this.#move(p, parseInt(data.x, 10), parseInt(data.y, 10), signal);
        if (h.button) { h.dragPath ??= [from]; h.dragPath.push({ x: h.x, y: h.y }); }
        break;
      }
      case '/mouse/down': await this.#wait(120, signal); h.button = 1; h.downAt = now(); h.downPos = { x: h.x, y: h.y }; h.dragPath = null; break;
      case '/mouse/up': {
        await this.#wait(5, signal);
        const held = h.button ? now() - h.downAt : 0;
        const path = h.dragPath;
        h.button = 0; h.dragPath = null;
        if (path && path.length > 1) screen.drag(path[0].x, path[0].y, path.at(-1).x, path.at(-1).y, now());
        else if (held >= 500 * this.speed) screen.longPress(h.x, h.y, now());
        else if (h.downPos) screen.tap(h.x, h.y, now());
        p.dirty = true;
        break;
      }
      case '/mouse/click': {
        await this.#move(p, parseInt(data.x, 10), parseInt(data.y, 10), signal);
        await this.#wait(200, signal);
        screen.tap(h.x, h.y, now()); p.dirty = true;
        break;
      }
      case '/mouse/swipe': {
        const x1 = parseInt(data.x1, 10), y1 = parseInt(data.y1, 10), x2 = parseInt(data.x2, 10), y2 = parseInt(data.y2, 10);
        await this.#move(p, x1, y1, signal);
        h.button = 1;
        try { await this.#wait(80 + (data.duration === undefined ? 300 : parseInt(data.duration, 10)), signal); h.x = x2; h.y = y2; }
        finally { h.button = 0; }
        screen.drag(x1, y1, x2, y2, now()); p.dirty = true;
        break;
      }
      case '/key/sendkey': {
        const fn = String(data.fn_key ?? '');
        if (fn === 'Home') { await this.#wait(280, signal); h.known = false; screen.key('Home'); }
        else if (fn === 'AppSwitch' || fn === 'ControlBar') { await this.#wait(245, signal); h.known = false; screen.key(fn); }
        else if (fn) { await this.#wait(140, signal); screen.key({ ENTER: 'Enter', BACKSPACE: 'Backspace' }[fn] ?? fn); }
        else {
          const text = String(data.key);
          for (const ch of text) { await this.#wait(ch === ' ' ? 170 : 140, signal); screen.type(ch); p.dirty = true; }
        }
        p.dirty = true;
        break;
      }
      default: throw new Error('Unsupported input operation.');
    }
  }
}

// ---- CLI -------------------------------------------------------------------
if (import.meta.url === `file://${process.argv[1]}`) {
  const arg = (name, fallback) => { const i = process.argv.indexOf(name); return i >= 0 ? process.argv[i + 1] : fallback; };
  const sim = new KernelSim({ phones: defaultPhones(parseInt(arg('--phones', '6'), 10)) });
  const url = await sim.listen(parseInt(arg('--port', '9913'), 10), '127.0.0.1');
  console.log(`SIMULATED kernel (no real phones) listening at ${url}`);
}

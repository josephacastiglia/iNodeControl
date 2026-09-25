import { EventEmitter } from 'node:events';
import { WebSocketServer } from 'ws';
import { newId, sha256, safeEqual } from './security.js';

export const AGENT_PROTOCOL = 'nodetheory-rack.v1';

export class AgentUnavailableError extends Error {
  constructor(message = 'The rack is offline.') { super(message); this.name = 'AgentUnavailableError'; }
}
/** The request reached (or may have reached) the rack but no answer came back. */
export class AgentNoAnswerError extends Error {
  constructor(message) { super(message); this.name = 'AgentNoAnswerError'; }
}
export class AgentRequestError extends Error {
  constructor(reason, message) { super(message); this.name = 'AgentRequestError'; this.reason = reason; }
}

/**
 * Accepts outbound connections from rack agents on /agent. Each agent proves itself
 * with "<id>.<secret>"; revoking the agent in the database closes its connection and
 * refuses new ones. Phones reported by an agent are recorded but not allocatable
 * until staff mark them in service.
 */
export class AgentHub extends EventEmitter {
  constructor({ db, audit, previews, requestTimeoutMs = 20_000 }) {
    super();
    this.db = db; this.audit = audit; this.previews = previews;
    this.requestTimeoutMs = requestTimeoutMs;
    this.conns = new Map();            // agentId -> connection state
    this.phoneIds = new Map();         // `${agentId}|${kernelId}` -> phone id
    this.wss = new WebSocketServer({ noServer: true, maxPayload: 4 * 1024 * 1024, handleProtocols: p => p.has(AGENT_PROTOCOL) ? AGENT_PROTOCOL : false });
    this.pingTimer = setInterval(() => this.#ping(), 15_000);
    this.pingTimer.unref();
    this.stmt = {
      agent: db.prepare('SELECT id, secret_hash, revoked_at FROM agents WHERE id = ?'),
      seen: db.prepare('UPDATE agents SET last_connected_at = ?, last_ip = ? WHERE id = ?'),
      phone: db.prepare('SELECT id FROM phones WHERE agent_id = ? AND kernel_device_id = ?'),
      insertPhone: db.prepare(`INSERT INTO phones (id, agent_id, kernel_device_id, rack_name, model, img_w, img_h, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`),
      updatePhone: db.prepare('UPDATE phones SET rack_name = ?, model = ?, img_w = ?, img_h = ?, last_seen_at = ? WHERE id = ?'),
    };
  }

  /** Handles an HTTP upgrade on /agent. Returns false if the path is not ours. */
  handleUpgrade(req, socket, head, ip) {
    const url = new URL(req.url, 'http://x');
    if (url.pathname !== '/agent') return false;
    const auth = String(req.headers.authorization ?? '');
    const m = /^Bearer (rack_[a-f0-9]{12})\.([A-Za-z0-9_-]{20,100})$/.exec(auth);
    const row = m ? this.stmt.agent.get(m[1]) : null;
    if (!m || !row || row.revoked_at || !safeEqual(sha256(m[2]), row.secret_hash)) {
      this.audit.record({ actor: { type: 'agent', id: m?.[1] ?? null }, action: 'agent.connect', outcome: 'denied', ip });
      socket.write('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');
      socket.destroy();
      return true;
    }
    this.wss.handleUpgrade(req, socket, head, ws => this.#attach(m[1], ws, ip));
    return true;
  }

  #attach(agentId, ws, ip) {
    const previous = this.conns.get(agentId);
    if (previous) previous.ws.close(4001, 'Replaced by a newer connection.');
    const conn = { agentId, ws, ip, alive: true, connectedAt: Date.now(), hello: null, kernel: null, phones: new Map(), video: new Map(), pending: new Map(), previewStats: null };
    this.conns.set(agentId, conn);
    this.stmt.seen.run(Date.now(), ip, agentId);
    this.audit.record({ actor: { type: 'agent', id: agentId }, action: 'agent.connect', outcome: 'ok', ip });
    ws.on('pong', () => { conn.alive = true; });
    ws.on('message', (data, isBinary) => {
      conn.alive = true;
      try { isBinary ? this.#onFrame(conn, data) : this.#onMessage(conn, JSON.parse(data.toString('utf8'))); }
      catch (err) { console.warn(`Bad message from ${agentId}: ${err.message}`); }
    });
    ws.on('close', () => {
      if (this.conns.get(agentId) === conn) this.conns.delete(agentId);
      for (const p of conn.pending.values()) { clearTimeout(p.timer); p.reject(new AgentNoAnswerError('Connection to the rack was lost before it answered.')); }
      conn.pending.clear();
      if (this.closed) return;
      this.audit.record({ actor: { type: 'agent', id: agentId }, action: 'agent.disconnect', outcome: 'ok' });
      this.emit('disconnected', agentId);
    });
    ws.on('error', () => {});
  }

  #ping() {
    for (const conn of this.conns.values()) {
      if (!conn.alive) { conn.ws.terminate(); continue; }
      conn.alive = false;
      try { conn.ws.ping(); } catch { /* closing */ }
    }
  }

  #onMessage(conn, msg) {
    switch (msg?.t) {
      case 'hello': conn.hello = { version: String(msg.version ?? ''), protocol: String(msg.protocol ?? '') }; conn.kernel = msg.kernel ?? null; break;
      case 'inventory': this.#onInventory(conn, msg); break;
      case 'event': this.emit('event', conn.agentId, msg); break;
      case 'video': if (typeof msg.kernelId === 'string') conn.video.set(msg.kernelId, { available: !!msg.available, code: msg.code, message: String(msg.message ?? ''), at: Date.now() }); break;
      case 'res': {
        const p = conn.pending.get(msg.id);
        if (!p) return;
        conn.pending.delete(msg.id);
        clearTimeout(p.timer);
        if (msg.ok) p.resolve(msg.result); else p.reject(new AgentRequestError(msg.error?.reason ?? 'error', msg.error?.message ?? 'The rack refused the request.'));
        break;
      }
    }
  }

  #onInventory(conn, msg) {
    conn.kernel = msg.kernel ?? conn.kernel;
    conn.previewStats = msg.previewStats ?? null;
    conn.inventoryAt = Date.now();
    const now = Date.now();
    const phones = new Map();
    for (const p of Array.isArray(msg.phones) ? msg.phones : []) {
      if (typeof p?.kernelId !== 'string' || !p.kernelId || p.kernelId.length > 64) continue;
      phones.set(p.kernelId, p);
      const key = `${conn.agentId}|${p.kernelId}`;
      let id = this.phoneIds.get(key) ?? this.stmt.phone.get(conn.agentId, p.kernelId)?.id;
      const imgW = Number.isInteger(p.imgW) ? p.imgW : 0, imgH = Number.isInteger(p.imgH) ? p.imgH : 0;
      if (!id) {
        id = newId();
        this.stmt.insertPhone.run(id, conn.agentId, p.kernelId, String(p.name ?? '').slice(0, 80), String(p.model ?? '').slice(0, 80), imgW, imgH, now, now);
        this.audit.record({ actor: { type: 'agent', id: conn.agentId }, phoneId: id, action: 'phone.discovered', outcome: 'ok', detail: { model: p.model } });
      } else if (!conn.phones.has(p.kernelId) || now - (conn.phoneSavedAt ?? 0) > 60_000) {
        this.stmt.updatePhone.run(String(p.name ?? '').slice(0, 80), String(p.model ?? '').slice(0, 80), imgW, imgH, now, id);
      }
      this.phoneIds.set(key, id);
    }
    if (!conn.phoneSavedAt || now - conn.phoneSavedAt > 60_000) conn.phoneSavedAt = now;
    conn.phones = phones;
    this.emit('inventory', conn.agentId);
  }

  #onFrame(conn, data) {
    if (data.length < 8) return;
    const headLen = data.readUInt32BE(0);
    if (headLen > 4096 || 4 + headLen > data.length) return;
    const header = JSON.parse(data.subarray(4, 4 + headLen).toString('utf8'));
    const jpeg = data.subarray(4 + headLen);
    if (jpeg[0] !== 0xff || jpeg[1] !== 0xd8) return;
    const phoneId = this.phoneIds.get(`${conn.agentId}|${header.kernelId}`);
    if (!phoneId || (header.tier !== 'grid' && header.tier !== 'focus')) return;
    this.previews.put(phoneId, header.tier, jpeg, header);
    conn.video.set(header.kernelId, { available: true, at: Date.now() });
  }

  isOnline(agentId) { return this.conns.has(agentId); }
  connection(agentId) { return this.conns.get(agentId) ?? null; }
  phoneState(agentId, kernelId) { return this.conns.get(agentId)?.phones.get(kernelId) ?? null; }
  videoState(agentId, kernelId) { return this.conns.get(agentId)?.video.get(kernelId) ?? null; }

  /** Sends one operation to a rack agent and waits for its answer. */
  request(agentId, op, args, timeoutMs = this.requestTimeoutMs) {
    const conn = this.conns.get(agentId);
    if (!conn || conn.ws.readyState !== conn.ws.OPEN) return Promise.reject(new AgentUnavailableError());
    const id = newId();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        conn.pending.delete(id);
        reject(new AgentNoAnswerError('The rack did not answer in time.'));
      }, timeoutMs);
      conn.pending.set(id, { resolve, reject, timer });
      conn.ws.send(JSON.stringify({ t: 'req', id, op, args }));
    });
  }

  /** Fire-and-forget (used for preview watch renewals). */
  notify(agentId, op, args) {
    return this.request(agentId, op, args, 5_000).catch(() => null);
  }

  revoke(agentId) {
    const conn = this.conns.get(agentId);
    if (conn) conn.ws.close(4003, 'Credential revoked.');
  }

  close() {
    this.closed = true;
    clearInterval(this.pingTimer);
    for (const conn of this.conns.values()) conn.ws.terminate();
    this.wss.close();
  }
}

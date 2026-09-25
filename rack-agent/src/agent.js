import WebSocket from 'ws';
import { Inventory } from './inventory.js';
import { PhoneLane } from './phone-lane.js';
import { PreviewManager, DEFAULT_TIERS } from './preview.js';
import { validateAction, ActionError, describeAction } from './actions.js';

export const AGENT_VERSION = '0.1.0';
export const PROTOCOL = 'nodetheory-rack.v1';
const MAX_BUFFERED = 1_500_000;

/** Frames travel as one binary message: u32 header length, JSON header, JPEG bytes. */
export function packFrame(header, jpeg) {
  const head = Buffer.from(JSON.stringify(header), 'utf8');
  const out = Buffer.allocUnsafe(4 + head.length + jpeg.byteLength);
  out.writeUInt32BE(head.length, 0);
  head.copy(out, 4);
  Buffer.from(jpeg).copy(out, 4 + head.length);
  return out;
}

class AgentError extends Error {
  constructor(reason, message) { super(message); this.reason = reason; }
}

/**
 * Runs on the rack PC. Connects outbound to the portal (no inbound port on the rack),
 * keeps the kernel on 127.0.0.1, and exposes only the fixed operations below.
 */
export class RackAgent {
  constructor({ kernel, encoder, portalUrl, agentId, secret, pollMs = 1000, tiers = DEFAULT_TIERS, log = console,
    leaseMs = 30_000, renewMs = 10_000, reconnectMinMs = 1000, reconnectMaxMs = 30_000 }) {
    const url = new URL(portalUrl);
    const local = ['localhost', '127.0.0.1', '[::1]', '::1'].includes(url.hostname);
    if (url.protocol !== 'wss:' && !(url.protocol === 'ws:' && local))
      throw new Error('The portal address must use wss:// (plain ws:// is allowed only for a portal on this PC).');
    this.portalUrl = url.toString();
    this.agentId = agentId; this.secret = secret;
    this.kernel = kernel; this.pollMs = pollMs; this.log = log;
    this.leaseMs = leaseMs; this.renewMs = renewMs;
    this.reconnectMinMs = reconnectMinMs; this.reconnectMaxMs = reconnectMaxMs;
    this.inventory = new Inventory(kernel);
    this.lanes = new Map();
    this.ws = null;
    this.connected = false;
    this.stopped = false;
    this.lastInventoryJson = '';
    this.lastInventorySentAt = 0;
    this.previews = new PreviewManager({
      kernel, encoder, tiers,
      framesOf: id => this.inventory.get(id)?.video.frames ?? 0,
      sink: {
        canSend: () => this.connected && this.ws?.readyState === WebSocket.OPEN && this.ws.bufferedAmount < MAX_BUFFERED,
        sendFrame: (header, jpeg) => this.ws.send(packFrame(header, jpeg)),
        sendVideoStatus: status => this.#send({ t: 'video', ...status }),
      },
    });
  }

  #lane(kernelId) {
    let lane = this.lanes.get(kernelId);
    if (!lane) {
      lane = new PhoneLane(kernelId, this.kernel, { leaseMs: this.leaseMs, renewMs: this.renewMs, onEvent: e => this.#send({ t: 'event', ...e }) });
      this.lanes.set(kernelId, lane);
    }
    return lane;
  }

  #send(msg) {
    if (!this.connected || this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(msg));
    return true;
  }

  async start() {
    await this.#pollOnce();
    this.pollTimer = setInterval(() => this.#pollOnce(), this.pollMs);
    this.#connect(this.reconnectMinMs);
  }

  /** One inventory poll at a time; `fresh` waits for any in-flight poll and then polls again. */
  #pollOnce() {
    if (!this.pollPromise) this.pollPromise = this.#poll().finally(() => { this.pollPromise = null; });
    return this.pollPromise;
  }
  async #fresh() {
    await this.pollPromise?.catch(() => {});
    await this.#pollOnce();
    this.#publishInventory(true);
  }

  async #poll() {
    try {
      await this.inventory.poll();
      const input = this.inventory.lastInputStatus;
      if (input) for (const lane of this.lanes.values()) lane.observe(input.phones.get(lane.kernelId), input.observedAt);
      this.#publishInventory();
    } catch (err) {
      this.log.error?.('Inventory poll failed:', err.message);
    }
  }

  #publishInventory(force = false) {
    if (!this.connected) return;
    const snap = this.inventory.snapshot(id => this.lanes.get(id)?.hasControl ?? false);
    const json = JSON.stringify(snap);
    const now = Date.now();
    if (!force && json === this.lastInventoryJson && now - this.lastInventorySentAt < 5000) return;
    this.lastInventoryJson = json;
    this.lastInventorySentAt = now;
    this.#send({ t: 'inventory', ...snap, previewStats: this.previews.stats });
  }

  #connect(delay) {
    if (this.stopped) return;
    const ws = new WebSocket(this.portalUrl, PROTOCOL, {
      headers: { authorization: `Bearer ${this.agentId}.${this.secret}` },
      handshakeTimeout: 10_000,
      maxPayload: 1 << 20,
    });
    this.ws = ws;
    let alive = true;
    const ping = setInterval(() => {
      if (!alive) { ws.terminate(); return; }
      alive = false;
      try { ws.ping(); } catch { /* closed */ }
    }, 15_000);
    ws.on('pong', () => { alive = true; });
    ws.on('open', () => {
      this.connected = true;
      delay = this.reconnectMinMs;
      this.log.info?.(`Connected to portal ${new URL(this.portalUrl).host}.`);
      this.#send({ t: 'hello', version: AGENT_VERSION, protocol: PROTOCOL, kernel: this.inventory.kernelState });
      this.#publishInventory(true);
    });
    ws.on('message', (data, isBinary) => {
      alive = true;
      if (isBinary) return;
      let msg;
      try { msg = JSON.parse(data.toString('utf8')); } catch { return; }
      if (msg?.t === 'req' && typeof msg.id === 'string') this.#handle(msg);
    });
    ws.on('unexpected-response', (_req, res) => {
      this.log.error?.(`Portal refused the agent (HTTP ${res.statusCode}). Check the agent credential; it may have been revoked.`);
    });
    ws.on('error', err => { this.log.warn?.('Portal link error:', err.message); });
    ws.on('close', () => {
      clearInterval(ping);
      const wasConnected = this.connected;
      this.connected = false;
      if (this.ws === ws) this.ws = null;
      if (wasConnected) this.#onDisconnected();
      if (!this.stopped) {
        const next = Math.min(delay * 2, this.reconnectMaxMs);
        this.reconnectTimer = setTimeout(() => this.#connect(next), delay);
      }
    });
  }

  /** Link lost: hand every phone back. Nothing resumes on reconnect without a new request. */
  async #onDisconnected() {
    this.log.warn?.('Portal connection lost; releasing all phones this agent controls.');
    this.previews.unwatchAll();
    await Promise.all([...this.lanes.values()].filter(l => l.hasControl).map(l => l.release(null, 'Portal connection lost.')));
  }

  #requirePhone(kernelId) {
    if (typeof kernelId !== 'string') throw new AgentError('bad_request', 'Missing phone.');
    const phone = this.inventory.get(kernelId);
    if (!phone) throw new AgentError('unknown_phone', 'This phone is not reported by the rack kernel.');
    return phone;
  }

  #requireInput(phone) {
    if (!this.inventory.kernelState.reachable) throw new AgentError('kernel_unreachable', 'The rack kernel is not reachable.');
    if (!this.inventory.kernelState.compatible) throw new AgentError('kernel_incompatible', this.inventory.kernelState.reason);
    if (!phone.input.enabled) throw new AgentError('input_unavailable', 'Input is not enabled for this phone at the rack.');
  }

  async #handle({ id, op, args = {} }) {
    let reply;
    try {
      reply = { t: 'res', id, ok: true, result: await this.#dispatch(op, args) };
    } catch (err) {
      reply = { t: 'res', id, ok: false, error: { reason: err.reason ?? 'error', message: err.message } };
      if (!err.reason) this.log.error?.(`Operation ${op} failed:`, err);
    }
    this.#send(reply);
  }

  async #dispatch(op, a) {
    switch (op) {
      case 'acquire': {
        const phone = this.#requirePhone(a.kernelId);
        this.#requireInput(phone);
        if (typeof a.sessionId !== 'string' || !a.sessionId) throw new AgentError('bad_request', 'Missing session.');
        const r = await this.#lane(a.kernelId).acquire({ sessionId: a.sessionId });
        await this.#fresh();
        return r;
      }
      case 'release': {
        this.#requirePhone(a.kernelId);
        const lane = this.lanes.get(a.kernelId);
        const r = lane ? await lane.release({ sessionId: a.sessionId }) : { ok: true };
        await this.#fresh();
        return r;
      }
      case 'command': {
        const phone = this.#requirePhone(a.kernelId);
        this.#requireInput(phone);
        let action;
        try { action = validateAction(a.action, { width: phone.imgW, height: phone.imgH }); }
        catch (err) { if (err instanceof ActionError) return { status: 'rejected', message: err.message }; throw err; }
        if (typeof a.commandId !== 'string' || !a.commandId) throw new AgentError('bad_request', 'Missing command id.');
        const lane = this.lanes.get(a.kernelId);
        if (!lane) return { status: 'rejected', message: 'You no longer control this phone.' };
        const started = Date.now();
        const r = await lane.enqueue({ sessionId: a.sessionId }, a.commandId, action);
        this.log.info?.(`${a.kernelId.slice(-5)} ${describeAction(action)} -> ${r.status} (${Date.now() - started} ms)`);
        // A failed, cancelled or uncertain command changes input state; report it before replying.
        if (r.status !== 'succeeded' && r.status !== 'rejected') await this.#fresh();
        return { ...r, elapsedMs: Date.now() - started };
      }
      case 'stop': {
        const ids = Array.isArray(a.kernelIds) ? a.kernelIds : [];
        const results = await Promise.all(ids.map(async kernelId => {
          if (!this.inventory.get(kernelId)) return { kernelId, ok: false, message: 'Not reported by the rack kernel.' };
          const r = await this.#lane(kernelId).stop(typeof a.reason === 'string' ? a.reason.slice(0, 200) : 'Stopped.');
          return { kernelId, ...r };
        }));
        await this.#fresh();
        return { results };
      }
      case 'emergencyStop': {
        const ids = [...this.inventory.phones.values()].filter(p => p.input.enabled).map(p => p.kernelId);
        const results = await Promise.all(ids.map(async kernelId => ({ kernelId, ...(await this.#lane(kernelId).stop('Emergency stop by NodeTheory staff.')) })));
        await this.#fresh();
        return { results };
      }
      case 'resume': {
        const phone = this.#requirePhone(a.kernelId);
        this.#requireInput(phone);
        if (!Number.isInteger(a.generation)) throw new AgentError('bad_request', 'Missing generation.');
        const r = await this.#lane(a.kernelId).resume(a.generation);
        await this.#fresh();
        return r;
      }
      case 'watch': {
        this.#requirePhone(a.kernelId);
        return { ok: this.previews.watch(a.kernelId, a.tier, a.ttlMs) };
      }
      default:
        throw new AgentError('unsupported', 'Unsupported operation.');
    }
  }

  async stop() {
    this.stopped = true;
    clearInterval(this.pollTimer);
    clearTimeout(this.reconnectTimer);
    this.previews.close();
    await Promise.all([...this.lanes.values()].map(l => l.close()));
    if (this.ws) { this.connected = false; this.ws.close(1001, 'agent stopping'); }
  }

  /** Test hook: drop the portal link abruptly, as a network failure would. */
  simulateNetworkDrop() { this.ws?.terminate(); }
}

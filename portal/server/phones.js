import { HttpError } from './http.js';

const PHONE_COLUMNS = `p.id, p.agent_id, p.kernel_device_id, p.rack_name, p.model, p.img_w, p.img_h, p.service_state,
  a.id AS allocation_id, a.customer_id, a.friendly_name, a.started_at AS allocated_at`;

/**
 * Every customer-facing lookup goes through `owned()`, which joins the phone to an
 * active allocation for the caller's customer. A phone that exists but belongs to
 * someone else is indistinguishable from one that does not exist (404).
 */
export class PhoneDirectory {
  constructor(db, hub) {
    this.db = db; this.hub = hub;
    this.stmtOwned = db.prepare(`SELECT ${PHONE_COLUMNS} FROM phones p
      JOIN allocations a ON a.phone_id = p.id AND a.ended_at IS NULL
      WHERE p.id = ? AND a.customer_id = ?`);
    this.stmtList = db.prepare(`SELECT ${PHONE_COLUMNS} FROM phones p
      JOIN allocations a ON a.phone_id = p.id AND a.ended_at IS NULL
      WHERE a.customer_id = ? ORDER BY a.friendly_name COLLATE NOCASE`);
    this.stmtAny = db.prepare(`SELECT ${PHONE_COLUMNS} FROM phones p
      LEFT JOIN allocations a ON a.phone_id = p.id AND a.ended_at IS NULL WHERE p.id = ?`);
    this.stmtAll = db.prepare(`SELECT ${PHONE_COLUMNS}, c.name AS customer_name FROM phones p
      LEFT JOIN allocations a ON a.phone_id = p.id AND a.ended_at IS NULL
      LEFT JOIN customers c ON c.id = a.customer_id ORDER BY p.agent_id, p.rack_name`);
  }

  owned(customerId, phoneId) {
    const row = customerId && typeof phoneId === 'string' ? this.stmtOwned.get(phoneId, customerId) : null;
    if (!row) throw new HttpError(404, 'not_found', 'Phone not found.');
    return row;
  }
  listFor(customerId) { return this.stmtList.all(customerId); }
  any(phoneId) {
    const row = this.stmtAny.get(phoneId);
    if (!row) throw new HttpError(404, 'not_found', 'Phone not found.');
    return row;
  }
  all() { return this.stmtAll.all(); }

  /** Source image size used for coordinate validation (from the live kernel report). */
  size(row) {
    const inv = this.hub.phoneState(row.agent_id, row.kernel_device_id);
    const width = inv?.imgW || row.img_w, height = inv?.imgH || row.img_h;
    return { width, height };
  }
}

function ago(ms) {
  const s = Math.round(ms / 1000);
  if (s < 90) return `${s} s`;
  const m = Math.round(s / 60);
  return m < 90 ? `${m} min` : `${Math.round(m / 60)} h`;
}

/** Customer-facing status. Input (control) and video are separate channels. */
export function phoneStatus(row, { hub, control, previews, user, now = Date.now() }) {
  const conn = hub.connection(row.agent_id);
  const inv = conn?.phones.get(row.kernel_device_id) ?? null;
  const kernel = conn?.kernel ?? null;
  const session = control.get(row.id);
  const lastEnded = control.lastEnded.get(row.id);
  const videoReport = conn?.video.get(row.kernel_device_id);
  const rackOnline = !!conn && !!kernel?.reachable;

  let video;
  if (!conn) video = { state: 'unknown', label: 'Rack offline', detail: 'We can’t reach the rack that hosts this phone right now.' };
  else if (!kernel?.reachable) video = { state: 'unknown', label: 'Rack not ready', detail: 'The rack software is not responding.' };
  else if (!inv) video = { state: 'unavailable', label: 'Not detected', detail: 'The rack is not reporting this phone. Our team has been notified.' };
  else if (inv.video.state === 'restarting') video = { state: 'reconnecting', label: 'Video reconnecting', detail: 'The screen feed is restarting.' };
  else if (!inv.video.live || inv.video.state === 'failed' || inv.video.state === 'offline' || (videoReport && !videoReport.available && now - videoReport.at < 5000))
    video = { state: 'unavailable', label: 'Video unavailable', detail: 'Screen mirroring has stopped. It needs our team at the rack to reconnect it; controls may still work.' };
  else {
    const stillFor = inv.video.lastFrameAt ? now - inv.video.lastFrameAt : 0;
    video = { state: 'live', label: 'Live', detail: stillFor > 60_000 ? `No new frames for ${ago(stillFor)} — the screen may simply be still.` : '' };
  }

  let input;
  if (!conn) input = { state: 'unknown', label: 'Rack offline' };
  else if (!kernel?.reachable) input = { state: 'unknown', label: 'Rack not ready' };
  else if (!kernel.compatible) input = { state: 'unavailable', label: 'Controls unavailable', detail: 'Remote control is not enabled on this rack yet.' };
  else if (!inv) input = { state: 'unavailable', label: 'Not detected' };
  else if (session && session.userId === user.id) input = { state: 'yours', label: 'You’re in control' };
  else if (session) input = { state: 'teammate', label: `In use by ${session.userName}`, holder: session.userName };
  else if (!inv.input.enabled) input = { state: 'unavailable', label: 'Controls unavailable', detail: 'The control connection for this phone isn’t ready. Our team has been notified.' };
  else if (inv.input.releaseFailed) input = { state: 'unavailable', label: 'Needs support', detail: 'The rack could not confirm that input was released. Our team needs to check this phone.' };
  else if (inv.input.releasing) input = { state: 'recovering', label: 'Finishing up', detail: 'Finishing a previous action.' };
  else if (inv.input.stopped) input = { state: 'stopped', label: 'Stopped', detail: friendlyStop(inv.input.message), generation: inv.input.generation };
  else if (inv.input.owned && !inv.input.heldByAgent) input = { state: 'operator', label: 'In use by NodeTheory', detail: 'Our operators are using this phone at the rack.' };
  else if (inv.input.owned) input = { state: 'recovering', label: 'Finishing up', detail: 'Handing control back.' };
  else input = { state: 'ready', label: 'Ready' };

  const size = { width: inv?.imgW || row.img_w, height: inv?.imgH || row.img_h };
  const out = {
    id: row.id,
    name: row.friendly_name,
    model: row.model || 'iPhone',
    screen: size,
    rack: { online: rackOnline, simulated: !!kernel?.simulated },
    video,
    input,
    lastEnded: lastEnded && lastEnded.userId === user.id && now - lastEnded.at < 120_000 ? { reason: lastEnded.reason, message: lastEnded.message, at: lastEnded.at } : null,
  };
  const grid = previews.latest(row.id, 'grid');
  out.preview = grid ? { seq: grid.seq, at: grid.receivedAt } : null;
  return out;
}

function friendlyStop(message) {
  if (!message) return 'Input is stopped. Resume to continue.';
  if (/lease expired/i.test(message)) return 'Control timed out, so input was stopped for safety. Resume to continue.';
  if (/stopped by operator/i.test(message)) return 'Input was stopped. Resume to continue.';
  if (/cancel/i.test(message)) return 'An action was cancelled, so input was stopped for safety. Resume to continue.';
  return 'Input was stopped for safety after a problem. Resume to continue.';
}

/** Staff-only technical detail. Never included in customer responses unless asked for. */
export function phoneDiagnostics(row, hub) {
  const conn = hub.connection(row.agent_id);
  const inv = conn?.phones.get(row.kernel_device_id) ?? null;
  return {
    rack: { agentId: row.agent_id, online: !!conn, version: conn?.hello?.version ?? null, kernel: conn?.kernel ?? null, previewStats: conn?.previewStats ?? null },
    phone: inv ? {
      deviceId: row.kernel_device_id, rackName: inv.name, os: inv.os, model: inv.model, image: `${inv.imgW}×${inv.imgH}`,
      board: inv.input.boardPid, boardPresent: inv.input.boardPresent, inputEnabled: inv.input.enabled,
      input: { owned: inv.input.owned, heldByAgent: inv.input.heldByAgent, active: inv.input.active, stopped: inv.input.stopped,
        releasing: inv.input.releasing, releaseFailed: inv.input.releaseFailed, message: inv.input.message, generation: inv.input.generation },
      video: { state: inv.video.state, live: inv.video.live, frames: inv.video.frames, lastFrameAt: inv.video.lastFrameAt,
        receiver: inv.receiverName, receiverState: inv.video.receiverState, receiverRestarts: inv.video.receiverRestarts },
    } : { deviceId: row.kernel_device_id, reported: false },
    videoReport: conn?.video.get(row.kernel_device_id) ?? null,
  };
}

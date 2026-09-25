// Polls the kernel's read-only endpoints and builds one snapshot per phone with the
// control channel (USB board / input lease) and the video channel (AirPlay receiver)
// reported separately. Freshness comes from the receiver frame counter advancing, not
// from `live:true` alone, and not from pictures differing: a still screen can be live.

export class Inventory {
  constructor(kernel, { now = () => Date.now() } = {}) {
    this.kernel = kernel;
    this.now = now;
    this.kernelState = { reachable: false, compatible: false, simulated: false, reason: 'Not checked yet.' };
    this.phones = new Map();          // kernelId -> snapshot
    this.frameTrack = new Map();      // kernelId -> { frames, changedAt }
    this.boards = null;
    this.boardsAt = 0;
    this.lastInputStatus = null;      // { observedAt, phones: Map }
  }

  get(kernelId) { return this.phones.get(kernelId); }

  async poll() {
    const observedAt = this.now();
    let status, devices, input;
    try {
      [status, devices, input] = await Promise.all([this.kernel.kernelStatus(), this.kernel.devices(), this.kernel.inputStatus()]);
    } catch (err) {
      this.kernelState = { reachable: false, compatible: false, simulated: false, reason: err.message };
      for (const phone of this.phones.values()) { phone.video = { ...phone.video, state: 'unknown' }; phone.input = { ...phone.input, state: 'unknown' }; }
      this.lastInputStatus = null;
      return false;
    }
    if (!this.boards || observedAt - this.boardsAt > 5000) {
      this.boards = await this.kernel.boards();
      this.boardsAt = observedAt;
    }
    const compatible = status.input_protocol === 1 && status.input_leases_required === true;
    this.kernelState = {
      reachable: true, compatible, simulated: status.simulated === true,
      reason: compatible ? '' : 'Kernel does not advertise input_protocol 1 with required leases.',
    };
    const allowed = new Set((status.allowed ?? []).map(p => String(p).toUpperCase()));
    const receivers = new Map((status.receivers ?? []).map(r => [r.deviceid, r]));
    const inputById = new Map((input.phones ?? []).map(p => [p.id, p]));
    this.lastInputStatus = { observedAt, phones: inputById };
    const boardByPid = this.boards ? new Map(this.boards.map(b => [String(b.pid).toUpperCase(), b])) : null;

    const seen = new Set();
    for (const d of devices) {
      const id = String(d.deviceid ?? '');
      if (!id) continue;
      seen.add(id);
      const pid = String(d.pid ?? '').toUpperCase();
      const rec = receivers.get(id);
      const frames = Number(rec?.frames ?? 0);
      const track = this.frameTrack.get(id);
      const samples = track?.samples ?? [];
      samples.push([observedAt, frames]);
      while (samples.length > 2 && observedAt - samples[0][0] > 5000) samples.shift();
      if (!track || frames !== track.frames) this.frameTrack.set(id, { frames, changedAt: track ? observedAt : 0, samples });
      else track.samples = samples;
      const lastFrameAt = this.frameTrack.get(id).changedAt;
      // New frames per second received by the kernel from this phone (frame counter delta,
      // last ~5 s). This is the receiver rate, independent of any viewer.
      const [t0, f0] = samples[0];
      const receiverFps = observedAt > t0 && frames >= f0 ? Math.round((frames - f0) / ((observedAt - t0) / 1000) * 10) / 10 : 0;
      const inp = inputById.get(id);
      const board = boardByPid?.get(pid);
      this.phones.set(id, {
        kernelId: id,
        name: String(d.name ?? d.user_name ?? ''),
        model: String(d.device_name ?? 'iPhone'),
        os: String(d.version ?? ''),
        imgW: Number(d.imgw) || 0,
        imgH: Number(d.imgh) || 0,
        receiverName: String(d.receiver_name ?? rec?.name ?? ''),
        video: {
          state: String(d.video_state ?? (Number(d.state) ? 'mirroring' : 'offline')),
          live: rec ? rec.live === true : Number(d.state) === 1,
          frames,
          lastFrameAt,          // 0 = not seen advancing since the agent started
          receiverFps,
          receiverState: String(rec?.receiver_state ?? ''),
          receiverRestarts: Number(rec?.receiver_restarts ?? 0),
        },
        input: {
          boardPid: pid,
          boardPresent: board ? Number(board.state) >= 1 : (this.boards ? false : null),
          enabled: allowed.has(pid) && !!inp,
          owned: !!inp?.owned,
          active: !!inp?.active,
          stopped: !!inp?.stopped,
          releasing: !!inp?.releasing,
          releaseFailed: !!inp?.release_failed,
          message: String(inp?.message ?? ''),
          generation: Number(inp?.generation ?? 0),
          leaseRemainingMs: Number(inp?.lease_remaining_ms ?? 0),
        },
      });
    }
    for (const id of [...this.phones.keys()]) if (!seen.has(id)) { this.phones.delete(id); this.frameTrack.delete(id); }
    return true;
  }

  /** Portal-facing view. `heldBy` says whether this agent's lane holds the phone. */
  snapshot(heldByAgent = () => false) {
    return {
      kernel: this.kernelState,
      phones: [...this.phones.values()].map(p => ({ ...p, input: { ...p.input, heldByAgent: heldByAgent(p.kernelId) } })),
    };
  }
}

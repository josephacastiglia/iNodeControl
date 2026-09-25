// The only module that talks to the iNodeControl kernel. It speaks the kernel's
// documented HTTP contract (analysis/input-ownership-20260916/API.md, verified against
// src/iMouse.Kernel/ApiServer.cs and InputSessions.cs at commit ee445d7):
//
//   GET  /api/device/get | /api/config/usb/get | /api/kernel/status | /api/input/status
//   GET  /api/pic/screenshot?id=PHONE&binary=true  -> image/bmp, or JSON code 25/1
//   POST /api/  {"fun":"/mouse/click","data":{...}}
//
// Every response is an envelope {status, message, data}. HTTP 200 does not mean the
// operation succeeded: callers must inspect data.code and per-phone data.results.

const LOOPBACK = new Set(['127.0.0.1', 'localhost', '[::1]', '::1']);

/** The request never reached the kernel (for example, connection refused). Nothing executed. */
export class KernelUnreachableError extends Error {
  constructor(message, cause) { super(message); this.name = 'KernelUnreachableError'; this.cause = cause; }
}
/** The request may have reached the kernel but no answer arrived. Outcome is unknown. */
export class KernelAmbiguousError extends Error {
  constructor(message, cause) { super(message); this.name = 'KernelAmbiguousError'; this.cause = cause; }
}
/** The kernel answered with something outside the contract. */
export class KernelProtocolError extends Error {
  constructor(message, data) { super(message); this.name = 'KernelProtocolError'; this.data = data; }
}

function isNotDelivered(err) {
  const code = err?.cause?.code ?? err?.code;
  return code === 'ECONNREFUSED' || code === 'ENOTFOUND' || code === 'EADDRNOTAVAIL' || code === 'EHOSTUNREACH';
}

export class HttpKernel {
  /**
   * @param {object} options
   * @param {string} [options.baseUrl] kernel API root; must be a loopback address.
   * @param {number} [options.readTimeoutMs]
   * @param {number} [options.commandTimeoutMs] must exceed the kernel's 8 s per-command deadline.
   */
  constructor({ baseUrl = 'http://127.0.0.1:9913/api/', readTimeoutMs = 4000, commandTimeoutMs = 12000 } = {}) {
    const url = new URL(baseUrl);
    if (url.protocol !== 'http:') throw new Error('The kernel address must be http:// on this PC.');
    if (!LOOPBACK.has(url.hostname)) throw new Error('The kernel must stay local to the rack PC (use 127.0.0.1).');
    if (!url.pathname.endsWith('/')) url.pathname += '/';
    this.base = url;
    this.readTimeoutMs = readTimeoutMs;
    this.commandTimeoutMs = commandTimeoutMs;
  }

  #url(path) { return new URL(path.replace(/^\/+/, ''), this.base); }

  static readEnvelope(text) {
    let root;
    try { root = JSON.parse(text); } catch { throw new KernelProtocolError('Kernel returned invalid JSON.'); }
    if (!root || typeof root !== 'object') throw new KernelProtocolError('Kernel returned an invalid envelope.');
    const data = root.data;
    if (root.status !== 200) throw new KernelProtocolError(`Kernel error ${root.status}: ${data?.message ?? root.message ?? 'unknown'}`, data);
    if (!data || typeof data !== 'object' || typeof data.code !== 'number')
      throw new KernelProtocolError('Kernel response has no result code.', data);
    return data;
  }

  async #get(path) {
    let res;
    try { res = await fetch(this.#url(path), { signal: AbortSignal.timeout(this.readTimeoutMs) }); }
    catch (err) { throw isNotDelivered(err) ? new KernelUnreachableError('Kernel is not reachable.', err) : new KernelAmbiguousError('Kernel did not answer in time.', err); }
    return HttpKernel.readEnvelope(await res.text());
  }

  async #getOk(path) {
    const data = await this.#get(path);
    if (data.code !== 0) throw new KernelProtocolError(`Kernel ${path} returned code ${data.code}: ${data.message ?? ''}`, data);
    return data;
  }

  kernelStatus() { return this.#getOk('kernel/status'); }
  inputStatus() { return this.#getOk('input/status'); }
  async devices() {
    const data = await this.#getOk('device/get');
    if (!Array.isArray(data.list)) throw new KernelProtocolError('Kernel returned an invalid device list.');
    return data.list;
  }
  /** Board list is advisory. It can fail independently (it enumerates USB on each call). */
  async boards() {
    try {
      const data = await this.#getOk('config/usb/get');
      return Array.isArray(data.list) ? data.list : null;
    } catch { return null; }
  }

  /** Refuses input unless the kernel advertises the ownership protocol. */
  async capability() {
    const status = await this.kernelStatus();
    const compatible = status.input_protocol === 1 && status.input_leases_required === true;
    return {
      compatible,
      reason: compatible ? '' : 'Kernel does not advertise input_protocol 1 with required leases; input disabled.',
      simulated: status.simulated === true,
      status,
    };
  }

  /**
   * POST one kernel function. Returns the envelope data (callers check data.code).
   * Throws KernelUnreachableError when nothing was delivered, or KernelAmbiguousError
   * when the request may have executed (timeout, reset, unparseable reply).
   */
  async command(fun, data, { timeoutMs = this.commandTimeoutMs } = {}) {
    let res;
    try {
      res = await fetch(this.base, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ fun, data }),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (err) {
      if (isNotDelivered(err)) throw new KernelUnreachableError('Kernel is not reachable.', err);
      throw new KernelAmbiguousError(`No answer from the kernel for ${fun}; the action may have run.`, err);
    }
    let text;
    try { text = await res.text(); }
    catch (err) { throw new KernelAmbiguousError(`Kernel reply to ${fun} was cut off; the action may have run.`, err); }
    try { return HttpKernel.readEnvelope(text); }
    catch (err) {
      if (err instanceof KernelProtocolError && err.data && typeof err.data.code === 'number') return err.data;
      throw new KernelAmbiguousError(`Unreadable kernel reply to ${fun}; the action may have run.`, err);
    }
  }

  /**
   * Latest raw frame for one phone. The kernel answers image/bmp when a live frame exists,
   * or a JSON envelope (code 25 = no live frame, code 1 = unknown receiver) otherwise.
   */
  async screenshot(id) {
    let res;
    try {
      res = await fetch(this.#url(`pic/screenshot?id=${encodeURIComponent(id)}&binary=true`), { signal: AbortSignal.timeout(this.readTimeoutMs) });
    } catch (err) {
      return { ok: false, code: -1, message: isNotDelivered(err) ? 'Kernel is not reachable.' : 'Kernel did not answer in time.' };
    }
    const type = (res.headers.get('content-type') ?? '').toLowerCase();
    const body = Buffer.from(await res.arrayBuffer());
    if (type.startsWith('image/bmp') && body.length > 54 && body[0] === 0x42 && body[1] === 0x4d)
      return { ok: true, bmp: body };
    if (type.startsWith('application/json')) {
      try {
        const data = HttpKernel.readEnvelope(body.toString('utf8'));
        return { ok: false, code: data.code, message: data.message ?? '' };
      } catch (err) { return { ok: false, code: -1, message: err.message }; }
    }
    return { ok: false, code: -1, message: `Unexpected screenshot type ${type || 'none'}.` };
  }
}

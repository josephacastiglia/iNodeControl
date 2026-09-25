// Same-origin API client. Cookies carry the session; state-changing requests add the
// session's CSRF token. The browser only ever talks to the portal, never to a rack.
let csrf = '';
export const setCsrf = token => { csrf = token; };

export class ApiError extends Error {
  constructor(status, body) { super(body?.message ?? `Request failed (${status}).`); this.status = status; this.code = body?.error; this.body = body; }
}

const onSignedOut = () => whenSignedOut.current?.();
/** Set `whenSignedOut.current` to handle an expired session. */
export const whenSignedOut = { current: null };

export async function api(method, path, body, { keepalive = false, signal } = {}) {
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { accept: 'application/json', ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...(method !== 'GET' ? { 'x-csrf-token': csrf } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    keepalive, signal,
  });
  const data = (res.headers.get('content-type') ?? '').includes('json') ? await res.json() : null;
  if (res.status === 401 && path !== '/api/auth/login') { onSignedOut(); throw new ApiError(401, data); }
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

export const get = (path, opts) => api('GET', path, undefined, opts);
export const post = (path, body = {}, opts) => api('POST', path, body, opts);

import { HttpError, parseCookies } from './http.js';
import { newId, randomToken, sha256, verifyPassword, csrfFor, safeEqual } from './security.js';

const IDLE_MS = 12 * 60 * 60 * 1000;
const ABSOLUTE_MS = 7 * 24 * 60 * 60 * 1000;
const TOUCH_EVERY_MS = 60 * 1000;

/** In-memory sliding-window limiter for login attempts (per account and per address). */
class Limiter {
  constructor(max, windowMs) { this.max = max; this.windowMs = windowMs; this.hits = new Map(); }
  #prune(key, now) {
    const list = (this.hits.get(key) ?? []).filter(t => now - t < this.windowMs);
    if (list.length) this.hits.set(key, list); else this.hits.delete(key);
    return list;
  }
  blocked(key, now = Date.now()) { return this.#prune(key, now).length >= this.max; }
  hit(key, now = Date.now()) { const l = this.#prune(key, now); l.push(now); this.hits.set(key, l); }
  clear(key) { this.hits.delete(key); }
}

export class Auth {
  constructor(db, { serverSecret, secureCookies }) {
    this.db = db;
    this.serverSecret = serverSecret;
    this.secure = secureCookies;
    this.cookieName = secureCookies ? '__Host-nt_session' : 'nt_session';
    this.perAccount = new Limiter(5, 15 * 60 * 1000);
    this.perAddress = new Limiter(30, 15 * 60 * 1000);
  }

  cookie(token, maxAgeSec) {
    const attrs = [`${this.cookieName}=${token}`, 'Path=/', 'HttpOnly', 'SameSite=Strict', `Max-Age=${maxAgeSec}`];
    if (this.secure) attrs.push('Secure');
    return attrs.join('; ');
  }

  async login(email, password, { ip, userAgent }) {
    const account = String(email ?? '').trim().toLowerCase();
    if (this.perAddress.blocked(ip) || this.perAccount.blocked(account))
      throw new HttpError(429, 'too_many_attempts', 'Too many sign-in attempts. Wait 15 minutes and try again.');
    const user = account ? this.db.prepare('SELECT * FROM users WHERE email = ?').get(account) : undefined;
    const ok = await verifyPassword(password, user?.password_hash);
    const customer = user?.customer_id ? this.db.prepare('SELECT status FROM customers WHERE id = ?').get(user.customer_id) : null;
    if (!ok || !user || user.disabled_at || (customer && customer.status !== 'active')) {
      this.perAccount.hit(account); this.perAddress.hit(ip);
      throw new HttpError(401, 'bad_credentials', 'Email or password is incorrect.');
    }
    this.perAccount.clear(account);
    const token = randomToken(32);
    const now = Date.now();
    const id = newId();
    this.db.prepare('INSERT INTO sessions (id, token_hash, user_id, created_at, last_seen_at, expires_at, ip, user_agent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)')
      .run(id, sha256(token), user.id, now, now, now + ABSOLUTE_MS, ip, String(userAgent ?? '').slice(0, 200));
    return { token, user, sessionId: id, cookie: this.cookie(token, Math.floor(IDLE_MS / 1000)) };
  }

  logout(session) {
    if (session) this.db.prepare('DELETE FROM sessions WHERE id = ?').run(session.id);
    return this.cookie('', 0);
  }

  /** Resolves the signed-in user from the session cookie, or null. */
  resolve(req) {
    const token = parseCookies(req.headers.cookie)[this.cookieName];
    if (!token || token.length > 100) return null;
    const row = this.db.prepare(`
      SELECT s.id AS session_id, s.last_seen_at, s.expires_at, u.id, u.email, u.name, u.role, u.customer_id, u.disabled_at,
             c.name AS customer_name, c.status AS customer_status, c.timezone AS customer_timezone, c.plan_phones
      FROM sessions s JOIN users u ON u.id = s.user_id LEFT JOIN customers c ON c.id = u.customer_id
      WHERE s.token_hash = ?`).get(sha256(token));
    if (!row) return null;
    const now = Date.now();
    if (now > row.expires_at || now - row.last_seen_at > IDLE_MS || row.disabled_at || (row.customer_id && row.customer_status !== 'active')) {
      this.db.prepare('DELETE FROM sessions WHERE id = ?').run(row.session_id);
      return null;
    }
    if (now - row.last_seen_at > TOUCH_EVERY_MS) this.db.prepare('UPDATE sessions SET last_seen_at = ? WHERE id = ?').run(now, row.session_id);
    return {
      session: { id: row.session_id, csrf: csrfFor(this.serverSecret, row.session_id) },
      user: { id: row.id, email: row.email, name: row.name, role: row.role, customerId: row.customer_id,
        customerName: row.customer_name, timezone: row.customer_timezone, planPhones: row.plan_phones },
    };
  }

  /** State-changing requests need the session's CSRF token and, if sent, a same-origin Origin. */
  checkCsrf(req, session, allowedOrigins) {
    const origin = req.headers.origin;
    if (origin && !allowedOrigins.includes(origin)) throw new HttpError(403, 'bad_origin', 'Request origin not allowed.');
    const header = req.headers['x-csrf-token'];
    if (typeof header !== 'string' || !safeEqual(header, session.csrf))
      throw new HttpError(403, 'bad_csrf', 'Your session needs refreshing. Reload the page.');
  }

  revokeUserSessions(userId) { this.db.prepare('DELETE FROM sessions WHERE user_id = ?').run(userId); }
  pruneExpired() { this.db.prepare('DELETE FROM sessions WHERE expires_at < ? OR last_seen_at < ?').run(Date.now(), Date.now() - IDLE_MS); }
}

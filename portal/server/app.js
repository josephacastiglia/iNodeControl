import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { openDatabase } from './db.js';
import { Auth } from './auth.js';
import { AuditLog } from './audit.js';
import { AgentHub } from './agent-hub.js';
import { PreviewCache } from './previews.js';
import { ControlManager } from './control.js';
import { PhoneDirectory } from './phones.js';
import { Router, HttpError, sendError, sendJson, readJson, securityHeaders, serveStatic, clientIp } from './http.js';
import { registerAuthRoutes } from './routes/auth.js';
import { registerCustomerRoutes } from './routes/customer.js';
import { registerAdminRoutes } from './routes/admin.js';

const WEB_ROOT = path.resolve(fileURLToPath(new URL('../web', import.meta.url)));

/**
 * Builds the portal. Access levels per route:
 *   public          no session (login only)
 *   user            any signed-in user
 *   customer        signed-in customer user (admin or member); scoped to their customer
 *   customer_admin  customer admin
 *   staff           NodeTheory staff
 * Every non-GET request needs the session's CSRF token.
 */
export function createPortal({ dbPath, serverSecret, secureCookies = false, publicOrigin = null, trustProxy = false, requestTimeoutMs } = {}) {
  if (!serverSecret || serverSecret.length < 32) throw new Error('serverSecret must be at least 32 characters.');
  const db = openDatabase(dbPath);
  const audit = new AuditLog(db);
  const auth = new Auth(db, { serverSecret, secureCookies });
  const previews = new PreviewCache();
  const hub = new AgentHub({ db, audit, previews, requestTimeoutMs });
  const control = new ControlManager({ hub, audit });
  const directory = new PhoneDirectory(db, hub);
  const ctx = { db, audit, auth, previews, hub, control, directory };

  const router = new Router();
  registerAuthRoutes(router, ctx);
  registerCustomerRoutes(router, ctx);
  registerAdminRoutes(router, ctx);

  const server = http.createServer(async (req, res) => {
    securityHeaders(res, secureCookies);
    let url;
    try { url = new URL(req.url, 'http://x'); } catch { return sendJson(res, 400, { error: 'bad_request' }); }
    if (!url.pathname.startsWith('/api/')) {
      try { if ((req.method === 'GET' || req.method === 'HEAD') && serveStatic(WEB_ROOT, req, res)) return; }
      catch (err) { return sendError(res, err); }
      return sendJson(res, 404, { error: 'not_found' });
    }
    try {
      const match = router.match(req.method, url.pathname);
      if (!match) throw new HttpError(404, 'not_found', 'Not found.');
      if (match.methodNotAllowed) throw new HttpError(405, 'method_not_allowed', 'Method not allowed.');
      const { route, params } = match;
      const ip = clientIp(req, trustProxy);
      const origins = allowedOrigins(req, publicOrigin, secureCookies, trustProxy);
      let resolved = null;
      if (route.access !== 'public') {
        resolved = auth.resolve(req);
        if (!resolved) throw new HttpError(401, 'signed_out', 'Please sign in.');
        const role = resolved.user.role;
        if (route.access === 'staff' && role !== 'staff') throw new HttpError(403, 'forbidden', 'Staff only.');
        if (route.access === 'customer' && !resolved.user.customerId) throw new HttpError(403, 'forbidden', 'Customer accounts only.');
        if (route.access === 'customer_admin' && role !== 'customer_admin') throw new HttpError(403, 'forbidden', 'Only account admins can do that.');
        if (req.method !== 'GET' && req.method !== 'HEAD') auth.checkCsrf(req, resolved.session, origins);
      } else if (req.headers.origin && !origins.includes(req.headers.origin)) {
        throw new HttpError(403, 'bad_origin', 'Request origin not allowed.');
      }
      const body = req.method === 'POST' ? await readJson(req) : {};
      await route.handler({ req, res, params, query: url.searchParams, body, ip, user: resolved?.user, session: resolved?.session });
    } catch (err) {
      if (!res.headersSent) sendError(res, err); else res.destroy();
    }
  });

  server.on('upgrade', (req, socket, head) => {
    if (!hub.handleUpgrade(req, socket, head, clientIp(req, trustProxy))) socket.destroy();
  });

  const pruneTimer = setInterval(() => auth.pruneExpired(), 60 * 60 * 1000);
  pruneTimer.unref();

  return {
    server, db, hub, control, previews, auth, audit, directory,
    listen(port = 0, host = '127.0.0.1') {
      return new Promise(resolve => server.listen(port, host, () => resolve(server.address().port)));
    },
    async close() {
      clearInterval(pruneTimer);
      control.close();
      hub.close();
      await new Promise(r => server.close(() => r()));
      server.closeAllConnections?.();
      db.close();
    },
  };
}

function allowedOrigins(req, publicOrigin, secure, trustProxy) {
  if (publicOrigin) return [publicOrigin];
  const host = req.headers.host ?? '';
  const proto = trustProxy && req.headers['x-forwarded-proto'] ? String(req.headers['x-forwarded-proto']).split(',')[0] : secure ? 'https' : 'http';
  return [`${proto}://${host}`];
}

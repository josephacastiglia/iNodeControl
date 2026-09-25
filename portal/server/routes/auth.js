import { HttpError, sendJson } from '../http.js';
import { AuditLog } from '../audit.js';

export function registerAuthRoutes(router, ctx) {
  const { auth, audit } = ctx;

  router.add('POST', '/api/auth/login', 'public', async ({ res, body, ip, req }) => {
    if (typeof body.email !== 'string' || typeof body.password !== 'string') throw new HttpError(400, 'bad_request', 'Enter your email and password.');
    try {
      const { user, cookie } = await auth.login(body.email, body.password, { ip, userAgent: req.headers['user-agent'] });
      res.setHeader('Set-Cookie', cookie);
      audit.record({ actor: AuditLog.actorFor(user), customerId: user.customer_id, action: 'auth.login', outcome: 'ok', ip });
      sendJson(res, 200, { ok: true });
    } catch (err) {
      if (err instanceof HttpError && err.status === 401)
        audit.record({ actor: { type: 'system' }, action: 'auth.login', outcome: 'failed', detail: { email: String(body.email).slice(0, 120) }, ip });
      throw err;
    }
  });

  router.add('POST', '/api/auth/logout', 'user', ({ res, session, user, ip }) => {
    res.setHeader('Set-Cookie', auth.logout(session));
    audit.record({ actor: AuditLog.actorFor(user), customerId: user.customerId, action: 'auth.logout', outcome: 'ok', ip });
    sendJson(res, 200, { ok: true });
  });

  router.add('GET', '/api/me', 'user', ({ res, session, user }) => {
    sendJson(res, 200, { user, csrf: session.csrf });
  });
}

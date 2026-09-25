// NodeTheory portal server.
//
// Environment:
//   NT_DB_PATH          SQLite file (default ./data/portal.db). Keep on durable, backed-up storage.
//   NT_SESSION_SECRET   32+ random characters; required. Rotating it signs everyone out of CSRF.
//   NT_PUBLIC_ORIGIN    https://portal.example.com (the exact browser origin)
//   NT_PORT / NT_HOST   listen address (default 127.0.0.1:8080; put TLS in front)
//   NT_TRUST_PROXY      "1" when behind a reverse proxy that sets X-Forwarded-For/Proto
//   NT_INSECURE_DEV     "1" only for local development over plain http
import { createPortal } from './app.js';

const env = process.env;
const insecure = env.NT_INSECURE_DEV === '1';
if (!env.NT_SESSION_SECRET) throw new Error('Set NT_SESSION_SECRET to a long random value.');
if (!insecure && !env.NT_PUBLIC_ORIGIN?.startsWith('https://')) throw new Error('Set NT_PUBLIC_ORIGIN to the https:// address customers use.');

const portal = createPortal({
  dbPath: env.NT_DB_PATH ?? 'data/portal.db',
  serverSecret: env.NT_SESSION_SECRET,
  secureCookies: !insecure,
  publicOrigin: env.NT_PUBLIC_ORIGIN ?? null,
  trustProxy: env.NT_TRUST_PROXY === '1',
});
const port = await portal.listen(Number(env.NT_PORT ?? 8080), env.NT_HOST ?? '127.0.0.1');
console.log(`NodeTheory portal listening on ${env.NT_HOST ?? '127.0.0.1'}:${port}${insecure ? ' (INSECURE DEV MODE)' : ''}`);

for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => { await portal.close(); process.exit(0); });

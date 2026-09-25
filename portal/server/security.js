import crypto from 'node:crypto';
import { promisify } from 'node:util';

const scrypt = promisify(crypto.scrypt);
const SCRYPT = { N: 16384, r: 8, p: 1, keylen: 32 };

export const newId = () => crypto.randomUUID();
export const randomToken = (bytes = 32) => crypto.randomBytes(bytes).toString('base64url');
export const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');

export function safeEqual(a, b) {
  const x = Buffer.from(String(a)), y = Buffer.from(String(b));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

export async function hashPassword(password) {
  if (typeof password !== 'string' || password.length < 10) throw new Error('Passwords need at least 10 characters.');
  const salt = crypto.randomBytes(16);
  const hash = await scrypt(password, salt, SCRYPT.keylen, { N: SCRYPT.N, r: SCRYPT.r, p: SCRYPT.p });
  return `scrypt$${SCRYPT.N}$${SCRYPT.r}$${SCRYPT.p}$${salt.toString('base64url')}$${hash.toString('base64url')}`;
}

// Used when the email is unknown, so failed logins take the same time either way.
const DUMMY_HASH = `scrypt$16384$8$1$${Buffer.alloc(16).toString('base64url')}$${Buffer.alloc(32).toString('base64url')}`;

export async function verifyPassword(password, stored = DUMMY_HASH) {
  const parts = String(stored).split('$');
  if (parts.length !== 6 || parts[0] !== 'scrypt') return false;
  const [, N, r, p, salt, expected] = parts;
  const want = Buffer.from(expected, 'base64url');
  const got = await scrypt(String(password ?? ''), Buffer.from(salt, 'base64url'), want.length, { N: +N, r: +r, p: +p });
  return crypto.timingSafeEqual(got, want) && stored !== DUMMY_HASH;
}

/** HMAC-derived CSRF token bound to one session; nothing extra is stored. */
export const csrfFor = (serverSecret, sessionId) =>
  crypto.createHmac('sha256', serverSecret).update('csrf:' + sessionId).digest('base64url');

/** Issues a rack-agent credential. Only the hash is stored; the full value is shown once. */
export function newAgentCredential() {
  const id = 'rack_' + crypto.randomBytes(6).toString('hex');
  const secret = randomToken(32);
  return { id, secret, credential: `${id}.${secret}`, secretHash: sha256(secret) };
}

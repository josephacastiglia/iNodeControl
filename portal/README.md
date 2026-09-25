# NodeTheory customer portal

The customer-facing web app and backend for NodeTheory's hosted iPhones. Customers sign in, see only the phones assigned to them, watch them live, and take control of one phone (or an explicitly selected group). Staff manage racks, phones, customers and emergency stops.

The portal never talks to a kernel directly. Each rack PC runs the [rack agent](../rack-agent/README.md), which connects out to `/agent` on this server with a revocable credential.

## Run it locally (simulated rack)

```bash
cd rack-agent && npm ci && cd ../portal && npm ci
npm run dev        # portal + rack agent + SIMULATED kernel → http://127.0.0.1:8080
```

The console prints demo accounts:
- customer admin, customer member, second customer, staff
- password: `correct horse battery`

Each run starts with a fresh database under `data/`. Every simulated screen is stamped **SIMULATOR**, and the portal shows a red "Simulated rack" banner.

## Run it for real

```bash
export NT_SESSION_SECRET="$(openssl rand -base64 48)"   # keep stable; store as a secret
export NT_PUBLIC_ORIGIN=https://portal.example.com
export NT_DB_PATH=/var/lib/nodetheory/portal.db           # durable, backed-up disk
export NT_TRUST_PROXY=1                                   # behind the TLS proxy below
npm ci --omit=dev
NT_NEW_PASSWORD='…' npm run create-staff -- you@nodetheory.io "Your Name"
npm start                                                 # listens on 127.0.0.1:8080
```

Put a TLS reverse proxy in front, and prefer HTTP/2 so browser previews and controls don't compete for connections. The `/agent` WebSocket must be proxied. Caddy example:

```
portal.example.com {
  reverse_proxy 127.0.0.1:8080
}
```

Then:
1. **Staff → Racks → Create rack credential**, and install it on the rack PC.
2. **Staff → Phones:** reported phones appear as *Unverified*. Mark a phone *In service* only after checking it at the rack; only in-service phones can be assigned.
3. **Staff → Customers:** add the customer (plan 1/10/20 phones) and its users, then assign phones.

## Security model

- **Users.**
  - Passwords are hashed with scrypt.
  - Sessions are random 256-bit tokens in an `HttpOnly; SameSite=Strict; Secure` cookie (`__Host-` prefix in production). Only a SHA-256 of the token is stored.
  - Sessions expire after 12 h idle or 7 days absolute.
  - Login is rate limited per account (5 per 15 min) and per address.
- **CSRF.** Every state-changing request needs a per-session HMAC token header. A foreign `Origin` is refused.
- **Authorization.**
  - Every customer route resolves the phone through an active allocation for the caller's customer, so another customer's phone is a 404.
  - This covers phones, previews, diagnostics, commands, control, Stop/Resume, groups and activity.
  - Ownership and control are checked again immediately before dispatch. The rack agent checks the control session again when the command reaches the front of that phone's queue.
- **Input.** Only the fixed action types in `server/actions.js` exist, and the rack agent validates them again. Kernel device IDs never come from the browser.
- **Agents.** Each credential is `rack_<id>.<secret>`; only a SHA-256 of the secret is stored. Revoking one closes the live connection and refuses reconnection.
- **Stop.**
  - A customer's **Stop all** affects only that customer's phones.
  - Staff **Emergency stop** (typed confirmation) stops every enabled phone on a rack, including phones held by the desktop console.
- **Secrets never logged.** Typed text is recorded only as its length. The audit log drops any detail key that looks like a password, token, secret or text.
- **Headers.** Strict CSP (no inline scripts or style attributes), `frame-ancestors 'none'`, `nosniff` and `no-referrer`.

## Layout

| Path | What |
|---|---|
| `server/app.js` | HTTP server, route access levels, CSRF, static files, `/agent` upgrade |
| `server/agent-hub.js` | Rack agent connections, request/response correlation, inventory, frames |
| `server/control.js` | One portal controller per phone; heartbeats; ends sessions on loss |
| `server/phones.js` | Ownership lookups; customer-facing status (control and video separate) |
| `server/previews.js` | Latest-frame cache and bounded long-poll |
| `server/routes/*.js` | Auth, customer and staff APIs |
| `server/migrations/*.sql` | Schema migrations (applied in order, once) |
| `web/` | Plain HTML/CSS/JS app in the NodeTheory graphite/coral style (no build step) |
| `test/` | Acceptance and unit tests (`npm test`) |

## Tests

`npm test` runs the real portal and real rack agent against the simulated kernel:
- customer A/B isolation and roles
- desktop-console ownership conflicts
- Stop, lease expiry, connection loss, uncertain outcomes and credential revocation
- group partial failure with retry-only-failed
- bounded previews under a stalled viewer
- coordinate mapping, portal/agent rule parity, sessions, and secrets never stored

Browser coordinate mapping and gestures are in `web/lib/coords.js` (unit-tested).

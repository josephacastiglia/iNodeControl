// One-time setup for LOCAL rack validation (not for production customers).
//
//   $env:NT_DB_PATH = 'data\winval.db'
//   npm run bootstrap-validation -- --out data\validation [--timezone America/New_York]
//
// Creates a staff account, customers "Validation A" (10-phone plan) and "Validation B"
// (1-phone pilot) with one admin user each, and one rack agent credential. Secrets are
// written to files under --out (inside portal/data, which git ignores) and never printed.
// Phones are NOT assigned here: staff assign them in the portal after checking identities.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { openDatabase } from '../server/db.js';
import { hashPassword, newId, newAgentCredential } from '../server/security.js';

const arg = (name, fallback) => { const i = process.argv.indexOf(name); return i >= 0 ? process.argv[i + 1] : fallback; };
const out = path.resolve(arg('--out', 'data/validation'));
const timezone = arg('--timezone', 'America/New_York');
new Intl.DateTimeFormat('en', { timeZone: timezone }); // throws on an unknown zone
const dbPath = process.env.NT_DB_PATH ?? 'data/portal.db';
const db = openDatabase(dbPath);
if (db.prepare("SELECT 1 FROM customers WHERE name = 'Validation A'").get()) {
  console.error(`This database already has validation accounts (${dbPath}). Use a fresh NT_DB_PATH or the existing files in ${out}.`);
  process.exit(2);
}
fs.mkdirSync(out, { recursive: true });
const password = () => crypto.randomBytes(18).toString('base64url');
const now = Date.now();
const accounts = [
  { role: 'staff', email: 'staff@validation.local', name: 'Validation Staff', customer: null },
  { role: 'customer_admin', email: 'a-admin@validation.local', name: 'A Admin', customer: 'Validation A', plan: 10 },
  { role: 'customer_admin', email: 'b-admin@validation.local', name: 'B Admin', customer: 'Validation B', plan: 1 },
];
const customerIds = {};
db.exec('BEGIN');
try {
  for (const acc of accounts) {
    if (acc.customer && !customerIds[acc.customer]) {
      customerIds[acc.customer] = newId();
      db.prepare('INSERT INTO customers (id, name, plan_phones, timezone, created_at) VALUES (?, ?, ?, ?, ?)').run(customerIds[acc.customer], acc.customer, acc.plan, timezone, now);
    }
    acc.password = password();
    db.prepare('INSERT INTO users (id, customer_id, email, name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)')
      .run(newId(), acc.customer ? customerIds[acc.customer] : null, acc.email, acc.name, acc.role, await hashPassword(acc.password), now);
  }
  var cred = newAgentCredential();
  db.prepare('INSERT INTO agents (id, name, secret_hash, created_at) VALUES (?, ?, ?, ?)').run(cred.id, 'Rack PC (validation)', cred.secretHash, now);
  db.prepare("INSERT INTO audit_log (at, actor_type, actor_label, action, outcome, detail) VALUES (?, 'system', 'bootstrap-validation', 'validation.bootstrap', 'ok', ?)")
    .run(now, JSON.stringify({ agentId: cred.id }));
  db.exec('COMMIT');
} catch (err) { db.exec('ROLLBACK'); throw err; }
db.close();

const credFile = path.join(out, 'rack-credential.txt');
const accFile = path.join(out, 'accounts.txt');
fs.writeFileSync(credFile, cred.credential, { mode: 0o600 });
fs.writeFileSync(accFile, [
  `Local validation accounts for ${dbPath} (created ${new Date(now).toISOString()}). Delete this file after validation.`,
  ...accounts.map(a => `${a.role.padEnd(15)} ${a.email.padEnd(26)} ${a.password}${a.customer ? `   (${a.customer})` : ''}`),
  '',
].join('\n'), { mode: 0o600 });
console.log(`Validation accounts created in ${dbPath}.`);
console.log(`  Rack credential: ${credFile}  (agent ${cred.id})`);
console.log(`  Sign-in details: ${accFile}`);
console.log('Secrets were written to those files only. Phones are not assigned yet: do that as staff after checking identities.');

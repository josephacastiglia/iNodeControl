// Creates a NodeTheory staff account. Usage:
//   NT_DB_PATH=data/portal.db npm run create-staff -- staff@example.com "Full Name"
// The password is read from NT_NEW_PASSWORD or prompted (not echoed to logs).
import readline from 'node:readline/promises';
import { openDatabase } from '../server/db.js';
import { hashPassword, newId } from '../server/security.js';

const [email, name] = process.argv.slice(2);
if (!email || !name) { console.error('Usage: create-staff <email> "<name>"'); process.exit(2); }
let password = process.env.NT_NEW_PASSWORD;
if (!password) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true });
  password = await rl.question('Password (10+ characters): ');
  rl.close();
}
const db = openDatabase(process.env.NT_DB_PATH ?? 'data/portal.db');
db.prepare('INSERT INTO users (id, customer_id, email, name, role, password_hash, created_at) VALUES (?, NULL, ?, ?, ?, ?, ?)')
  .run(newId(), email.toLowerCase(), name, 'staff', await hashPassword(password), Date.now());
console.log(`Staff account created for ${email}.`);
db.close();

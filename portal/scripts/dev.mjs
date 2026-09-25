// Local development: portal + rack agent + SIMULATED kernel in one process.
// Open http://127.0.0.1:8080 and sign in with a demo account printed below.
// The simulator stamps every screen "SIMULATOR"; no real phones are involved.
import { startStack, PASSWORD } from '../test/helpers/stack.mjs';

const port = Number(process.env.NT_PORT ?? 8080);
const stack = await startStack({
  phones: 8, speed: 1, port, dbPath: process.env.NT_DB_PATH ?? `data/dev-${Date.now()}.db`,
  allocation: { a: [0, 1, 2, 3, 4], b: [5] },
  log: { info: m => console.log('[agent]', m), warn: (...a) => console.warn('[agent]', ...a), error: (...a) => console.error('[agent]', ...a) },
});
console.log(`
  NodeTheory portal (DEVELOPMENT, SIMULATED RACK) → ${stack.base}

  Customer admin : ${stack.users.a.email}
  Customer member: ${stack.users.a2.email}
  Other customer : ${stack.users.b.email}
  Staff          : ${stack.users.staff.email}
  Password (all) : ${PASSWORD}

  2 simulated phones are unassigned; assign them from Staff → Phones.
`);
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => { await stack.close(); process.exit(0); });

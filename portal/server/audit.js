// Append-only audit trail. Callers pass structured detail; this module drops any key that
// looks like a secret so passwords, tokens and typed text can never be recorded.

const FORBIDDEN = /pass|secret|token|credential|cookie|text/i;

function scrub(detail) {
  if (!detail || typeof detail !== 'object') return {};
  const out = {};
  for (const [k, v] of Object.entries(detail)) {
    if (FORBIDDEN.test(k)) continue;
    out[k] = typeof v === 'string' ? v.slice(0, 300) : v;
  }
  return out;
}

export class AuditLog {
  constructor(db) {
    this.db = db;
    this.insert = db.prepare(`INSERT INTO audit_log (at, actor_type, actor_id, actor_label, customer_id, phone_id, action, outcome, detail, ip)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`);
  }

  /**
   * @param {{actor?: {type: string, id?: string, label?: string}, customerId?: string|null, phoneId?: string|null,
   *          action: string, outcome: string, detail?: object, ip?: string}} entry
   */
  record({ actor = { type: 'system' }, customerId = null, phoneId = null, action, outcome, detail, ip = null }) {
    this.insert.run(Date.now(), actor.type, actor.id ?? null, actor.label ?? '', customerId, phoneId, action, outcome,
      JSON.stringify(scrub(detail)), ip);
  }

  static actorFor(user) {
    return { type: user.role === 'staff' ? 'staff' : 'user', id: user.id, label: user.name };
  }
}

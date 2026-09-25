-- Milestone 1: customers, users, sessions, rack agents, phones, allocations,
-- commands, group actions and the audit log.

CREATE TABLE customers (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
  -- Package sold on the website. A plan size is not evidence that phones exist:
  -- phones are allocated individually from verified inventory.
  plan_phones INTEGER CHECK (plan_phones IN (1, 10, 20)),
  timezone    TEXT NOT NULL DEFAULT 'UTC',
  created_at  INTEGER NOT NULL
);

CREATE TABLE users (
  id            TEXT PRIMARY KEY,
  customer_id   TEXT REFERENCES customers(id),
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name          TEXT NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('customer_admin', 'customer_member', 'staff')),
  password_hash TEXT NOT NULL,
  disabled_at   INTEGER,
  created_at    INTEGER NOT NULL,
  CHECK ((role = 'staff') = (customer_id IS NULL))
);

-- Only a SHA-256 hash of the session token is stored.
CREATE TABLE sessions (
  id           TEXT PRIMARY KEY,
  token_hash   TEXT NOT NULL UNIQUE,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at   INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL,
  expires_at   INTEGER NOT NULL,
  ip           TEXT,
  user_agent   TEXT
);
CREATE INDEX sessions_user ON sessions(user_id);

-- Rack agents authenticate with "<id>.<secret>"; only a SHA-256 of the secret is stored.
CREATE TABLE agents (
  id                TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  secret_hash       TEXT NOT NULL,
  created_at        INTEGER NOT NULL,
  created_by        TEXT,
  revoked_at        INTEGER,
  revoked_by        TEXT,
  last_connected_at INTEGER,
  last_ip           TEXT
);

-- A phone as reported by a rack agent. New phones start 'unverified' and cannot be
-- allocated until staff confirm they work ('in_service').
CREATE TABLE phones (
  id               TEXT PRIMARY KEY,
  agent_id         TEXT NOT NULL REFERENCES agents(id),
  kernel_device_id TEXT NOT NULL,
  rack_name        TEXT NOT NULL DEFAULT '',
  model            TEXT NOT NULL DEFAULT '',
  img_w            INTEGER NOT NULL DEFAULT 0,
  img_h            INTEGER NOT NULL DEFAULT 0,
  service_state    TEXT NOT NULL DEFAULT 'unverified'
                   CHECK (service_state IN ('unverified', 'in_service', 'maintenance', 'retired')),
  service_note     TEXT NOT NULL DEFAULT '',
  first_seen_at    INTEGER NOT NULL,
  last_seen_at     INTEGER NOT NULL,
  UNIQUE (agent_id, kernel_device_id)
);

CREATE TABLE allocations (
  id            TEXT PRIMARY KEY,
  phone_id      TEXT NOT NULL REFERENCES phones(id),
  customer_id   TEXT NOT NULL REFERENCES customers(id),
  friendly_name TEXT NOT NULL,
  started_at    INTEGER NOT NULL,
  started_by    TEXT NOT NULL,
  ended_at      INTEGER,
  ended_by      TEXT
);
CREATE UNIQUE INDEX allocations_one_active ON allocations(phone_id) WHERE ended_at IS NULL;
CREATE INDEX allocations_customer ON allocations(customer_id) WHERE ended_at IS NULL;

CREATE TABLE group_actions (
  id          TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  user_id     TEXT NOT NULL REFERENCES users(id),
  kind        TEXT NOT NULL,
  summary     TEXT NOT NULL,
  retry_of    TEXT REFERENCES group_actions(id),
  created_at  INTEGER NOT NULL
);

-- Every remote input attempt. `summary` never contains typed text.
CREATE TABLE commands (
  id          TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  user_id     TEXT NOT NULL REFERENCES users(id),
  phone_id    TEXT NOT NULL REFERENCES phones(id),
  group_id    TEXT REFERENCES group_actions(id),
  kind        TEXT NOT NULL,
  summary     TEXT NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('sent', 'succeeded', 'failed', 'cancelled', 'unknown', 'rejected')),
  message     TEXT NOT NULL DEFAULT '',
  created_at  INTEGER NOT NULL,
  finished_at INTEGER,
  elapsed_ms  INTEGER
);
CREATE INDEX commands_customer ON commands(customer_id, created_at DESC);
CREATE INDEX commands_phone ON commands(phone_id, created_at DESC);
CREATE INDEX commands_group ON commands(group_id);

CREATE TABLE audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  at          INTEGER NOT NULL,
  actor_type  TEXT NOT NULL CHECK (actor_type IN ('user', 'staff', 'system', 'agent')),
  actor_id    TEXT,
  actor_label TEXT NOT NULL DEFAULT '',
  customer_id TEXT,
  phone_id    TEXT,
  action      TEXT NOT NULL,
  outcome     TEXT NOT NULL,
  detail      TEXT NOT NULL DEFAULT '{}',
  ip          TEXT
);
CREATE INDEX audit_customer ON audit_log(customer_id, id DESC);
CREATE INDEX audit_phone ON audit_log(phone_id, id DESC);

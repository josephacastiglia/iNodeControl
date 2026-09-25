-- Three-state action outcomes with progress.
--   succeeded  every step confirmed by the kernel (HID written; not proof of what iOS showed)
--   not_sent   confirmed that nothing reached the phone; the only state safe to retry
--   uncertain  no reply, failure/cancellation during execution, or partly complete
-- `sending` marks a command still in flight. Rebuilt because SQLite cannot alter CHECKs.

CREATE TABLE commands_v2 (
  id              TEXT PRIMARY KEY,
  customer_id     TEXT NOT NULL REFERENCES customers(id),
  user_id         TEXT NOT NULL REFERENCES users(id),
  phone_id        TEXT NOT NULL REFERENCES phones(id),
  group_id        TEXT REFERENCES group_actions(id),
  kind            TEXT NOT NULL,
  summary         TEXT NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('sending', 'succeeded', 'not_sent', 'uncertain')),
  reason          TEXT NOT NULL DEFAULT '',
  message         TEXT NOT NULL DEFAULT '',
  steps_total     INTEGER,
  steps_confirmed INTEGER,
  steps_uncertain INTEGER,
  chars_total     INTEGER,
  chars_confirmed INTEGER,
  chars_uncertain INTEGER,
  created_at      INTEGER NOT NULL,
  finished_at     INTEGER,
  elapsed_ms      INTEGER
);

INSERT INTO commands_v2 (id, customer_id, user_id, phone_id, group_id, kind, summary, status, reason, message, created_at, finished_at, elapsed_ms)
SELECT id, customer_id, user_id, phone_id, group_id, kind, summary,
       CASE status WHEN 'succeeded' THEN 'succeeded' WHEN 'rejected' THEN 'not_sent' ELSE 'uncertain' END,
       'migrated_' || status, message, created_at, finished_at, elapsed_ms
FROM commands;

DROP TABLE commands;
ALTER TABLE commands_v2 RENAME TO commands;
CREATE INDEX commands_customer ON commands(customer_id, created_at DESC);
CREATE INDEX commands_phone ON commands(phone_id, created_at DESC);
CREATE INDEX commands_group ON commands(group_id);

-- 记忆库 schema（v1）
-- 只追加：memory_versions / memory_events 由触发器禁止 UPDATE/DELETE。
-- 当前指针：memory_items 允许更新（正文历史必须走 memory_versions）。

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_items (
  id             TEXT PRIMARY KEY,
  layer          TEXT NOT NULL CHECK (layer IN ('L1','L2','L3','L4')),
  kind           TEXT NOT NULL CHECK (kind IN ('index','fact','sop','script','archive','insight')),
  name           TEXT NOT NULL,
  title          TEXT NOT NULL DEFAULT '',
  summary        TEXT NOT NULL DEFAULT '',
  body           TEXT NOT NULL DEFAULT '',
  tags           TEXT NOT NULL DEFAULT '[]',
  meta           TEXT NOT NULL DEFAULT '{}',
  status         TEXT NOT NULL DEFAULT 'draft'
                 CHECK (status IN ('draft','active','deprecated','archived')),
  priority       INTEGER NOT NULL DEFAULT 100,
  verified       INTEGER NOT NULL DEFAULT 0,
  confidence     REAL    NOT NULL DEFAULT 0.0,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL,
  access_count   INTEGER NOT NULL DEFAULT 0,
  last_access_at TEXT,
  UNIQUE (layer, name)
);
CREATE INDEX IF NOT EXISTS idx_items_layer ON memory_items(layer, status, priority);
CREATE INDEX IF NOT EXISTS idx_items_updated ON memory_items(updated_at DESC);

CREATE TABLE IF NOT EXISTS memory_versions (
  version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id    TEXT NOT NULL REFERENCES memory_items(id),
  title      TEXT NOT NULL,
  summary    TEXT NOT NULL,
  body       TEXT NOT NULL,
  status     TEXT NOT NULL,
  tags       TEXT NOT NULL,
  reason     TEXT NOT NULL,
  actor      TEXT NOT NULL,
  session_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_versions_item ON memory_versions(item_id, version_id DESC);

CREATE TABLE IF NOT EXISTS memory_events (
  event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id    TEXT,
  event      TEXT NOT NULL,
  actor      TEXT NOT NULL,
  session_id TEXT,
  detail     TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_item ON memory_events(item_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_time ON memory_events(created_at);

CREATE TABLE IF NOT EXISTS memory_links (
  from_id    TEXT NOT NULL REFERENCES memory_items(id),
  to_id      TEXT NOT NULL REFERENCES memory_items(id),
  rel        TEXT NOT NULL CHECK (rel IN ('indexes','supersedes','depends','related')),
  created_at TEXT NOT NULL,
  PRIMARY KEY (from_id, to_id, rel)
);

CREATE TABLE IF NOT EXISTS session_state (
  session_id TEXT PRIMARY KEY,
  working    TEXT NOT NULL DEFAULT '{}',
  plan_path  TEXT,
  updated_at TEXT NOT NULL
);

-- trigram：支持中文子串检索；不足 3 字的查询由 repository 回退 LIKE
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
  name, title, summary, body,
  content='memory_items', content_rowid='rowid', tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS trg_versions_no_update
BEFORE UPDATE ON memory_versions
BEGIN SELECT RAISE(ABORT, 'memory_versions is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_versions_no_delete
BEFORE DELETE ON memory_versions
BEGIN SELECT RAISE(ABORT, 'memory_versions is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_events_no_update
BEFORE UPDATE ON memory_events
BEGIN SELECT RAISE(ABORT, 'memory_events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_events_no_delete
BEFORE DELETE ON memory_events
BEGIN SELECT RAISE(ABORT, 'memory_events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_items_fts_ins AFTER INSERT ON memory_items
BEGIN
  INSERT INTO memory_fts(rowid, name, title, summary, body)
  VALUES (new.rowid, new.name, new.title, new.summary, new.body);
END;

CREATE TRIGGER IF NOT EXISTS trg_items_fts_upd AFTER UPDATE ON memory_items
BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, name, title, summary, body)
  VALUES ('delete', old.rowid, old.name, old.title, old.summary, old.body);
  INSERT INTO memory_fts(rowid, name, title, summary, body)
  VALUES (new.rowid, new.name, new.title, new.summary, new.body);
END;

CREATE TRIGGER IF NOT EXISTS trg_items_fts_del AFTER DELETE ON memory_items
BEGIN
  INSERT INTO memory_fts(memory_fts, rowid, name, title, summary, body)
  VALUES ('delete', old.rowid, old.name, old.title, old.summary, old.body);
END;

INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', '1');

PRAGMA user_version = 1;

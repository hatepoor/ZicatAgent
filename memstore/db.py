"""连接管理：PRAGMA、schema 初始化、版本升级。"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA_VERSION = 2
DEFAULT_DB = Path(__file__).resolve().parent.parent / "memory" / "memory.db"
_SCHEMA_SQL = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """打开连接并设置必需的 PRAGMA（不建表）。"""
    p = Path(path) if path else DEFAULT_DB
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


class Database:
    """带进程内锁的连接包装；本地单写者，写操作用 tx() 串行化。"""

    def __init__(self, path: str | Path | None = None, init: bool = True):
        self.path = Path(path) if path else DEFAULT_DB
        self.conn = connect(self.path)
        self.lock = threading.RLock()
        if init:
            self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.lock:
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            if version >= SCHEMA_VERSION:
                return
            # v2：FTS 更新触发器加 WHEN。旧库的 IF NOT EXISTS 不会替换已有触发器，
            # 必须先删再重建，否则 access_count 更新仍会触发整行重索引。
            if version < 2:
                self.conn.execute("DROP TRIGGER IF EXISTS trg_items_fts_upd")
            self.conn.executescript(_SCHEMA_SQL)
            self.conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

"""记忆仓库：唯一的读写入口。

写入规则（重要）：
- 正文变更必须先插入 memory_versions，再更新 memory_items 指针；
- 版本表与事件表只插入，触发器禁止 UPDATE/DELETE；
- 所有写操作在同一个事务内完成。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Iterable, Optional

from .common import sha256_bytes
from .db import Database

LAYERS = ("L1", "L2", "L3", "L4")
KINDS = ("index", "fact", "sop", "script", "archive", "insight")
STATUSES = ("draft", "active", "deprecated", "archived")
MAX_BODY_BYTES = 256 * 1024


class DuplicateItem(ValueError):
    """同一 (layer, name) 已存在。"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Item:
    id: str
    layer: str
    kind: str
    name: str
    title: str = ""
    summary: str = ""
    body: str = ""
    tags: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    status: str = "draft"
    priority: int = 100
    verified: int = 0
    confidence: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    access_count: int = 0
    last_access_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Item":
        def _json(value, default):
            try:
                return json.loads(value) if value else default
            except (TypeError, ValueError):
                return default

        return cls(
            id=row["id"], layer=row["layer"], kind=row["kind"], name=row["name"],
            title=row["title"], summary=row["summary"], body=row["body"],
            tags=_json(row["tags"], []), meta=_json(row["meta"], {}),
            status=row["status"], priority=row["priority"], verified=row["verified"],
            confidence=row["confidence"], created_at=row["created_at"],
            updated_at=row["updated_at"], access_count=row["access_count"],
            last_access_at=row["last_access_at"],
        )

    def to_dict(self, with_body: bool = True) -> dict:
        out = {
            "id": self.id, "layer": self.layer, "kind": self.kind, "name": self.name,
            "title": self.title, "summary": self.summary, "tags": self.tags,
            "meta": self.meta, "status": self.status, "priority": self.priority,
            "verified": self.verified, "confidence": self.confidence,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "access_count": self.access_count, "last_access_at": self.last_access_at,
        }
        if with_body:
            out["body"] = self.body
        return out


def _fts_query(query: str) -> str:
    tokens = [t for t in query.replace('"', " ").split() if t]
    return " ".join(f'"{t}"' for t in tokens)


class MemoryStore:
    def __init__(self, db: Database):
        self.db = db

    @property
    def conn(self) -> sqlite3.Connection:
        return self.db.conn

    # ---------- 事务 ----------
    @contextmanager
    def tx(self):
        with self.db.lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                yield self.conn
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    # ---------- 内部 ----------
    def _insert_version(self, conn, item: Item, reason: str, actor: str,
                        session_id: Optional[str]) -> int:
        cur = conn.execute(
            "INSERT INTO memory_versions"
            "(item_id,title,summary,body,status,tags,reason,actor,session_id,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (item.id, item.title, item.summary, item.body, item.status,
             json.dumps(item.tags, ensure_ascii=False), reason, actor, session_id, _now()),
        )
        return int(cur.lastrowid)

    def _event(self, conn, item_id: Optional[str], event: str, actor: str,
               session_id: Optional[str], detail: Optional[dict] = None) -> None:
        conn.execute(
            "INSERT INTO memory_events(item_id,event,actor,session_id,detail,created_at)"
            " VALUES (?,?,?,?,?,?)",
            (item_id, event, actor, session_id,
             json.dumps(detail or {}, ensure_ascii=False), _now()),
        )

    def _validate(self, layer: str, kind: str, status: str, name: str) -> None:
        if layer not in LAYERS:
            raise ValueError(f"layer 必须是 {LAYERS}: {layer}")
        if kind not in KINDS:
            raise ValueError(f"kind 必须是 {KINDS}: {kind}")
        if status not in STATUSES:
            raise ValueError(f"status 必须是 {STATUSES}: {status}")
        if not name or "/" in name or "\\" in name:
            raise ValueError(f"非法 name: {name!r}")
        if len(name) > 80:
            raise ValueError("name 过长（>80）")

    def _check_body(self, body: str) -> None:
        if len(body.encode("utf-8")) > MAX_BODY_BYTES:
            raise ValueError(f"body 超过 {MAX_BODY_BYTES} 字节上限")

    # ---------- 读 ----------
    def get(self, name_or_id: str) -> Optional[Item]:
        with self.db.lock:
            row = self.conn.execute(
                "SELECT * FROM memory_items WHERE id = ? OR name = ? "
                "ORDER BY (id = ?) DESC LIMIT 1",
                (name_or_id, name_or_id, name_or_id),
            ).fetchone()
        return Item.from_row(row) if row else None

    def list_items(self, layer: Optional[str] = None, layers: Optional[Iterable[str]] = None,
                   kind: Optional[str] = None, status: str = "active",
                   limit: int = 200) -> list[Item]:
        sql = "SELECT * FROM memory_items WHERE 1=1"
        args: list = []
        if layer:
            sql += " AND layer = ?"
            args.append(layer)
        if layers:
            layers = list(layers)
            sql += f" AND layer IN ({','.join('?' * len(layers))})"
            args.extend(layers)
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        if status:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY priority, updated_at DESC LIMIT ?"
        args.append(limit)
        with self.db.lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [Item.from_row(r) for r in rows]

    def search(self, query: str, layer: Optional[str] = None, limit: int = 5) -> list[Item]:
        q = (query or "").strip()
        if not q:
            return []
        with self.db.lock:
            if len(q) >= 2:
                try:
                    sql = ("SELECT i.* FROM memory_fts f JOIN memory_items i ON i.rowid = f.rowid"
                           " WHERE memory_fts MATCH ? AND i.status = 'active'")
                    args: list = [_fts_query(q)]
                    if layer:
                        sql += " AND i.layer = ?"
                        args.append(layer)
                    sql += " ORDER BY bm25(memory_fts) LIMIT ?"
                    args.append(limit)
                    rows = self.conn.execute(sql, args).fetchall()
                    if rows:
                        return [Item.from_row(r) for r in rows]
                except sqlite3.Error:
                    pass  # FTS 不可用/查询非法时降级
            like = f"%{q}%"
            sql = ("SELECT * FROM memory_items WHERE status = 'active'"
                   " AND (name LIKE ? OR title LIKE ? OR summary LIKE ? OR body LIKE ?)")
            args = [like, like, like, like]
            if layer:
                sql += " AND layer = ?"
                args.append(layer)
            sql += " ORDER BY priority, updated_at DESC LIMIT ?"
            args.append(limit)
            rows = self.conn.execute(sql, args).fetchall()
        return [Item.from_row(r) for r in rows]

    def read(self, name_or_id: str, actor: str = "agent",
             session_id: Optional[str] = None) -> Optional[Item]:
        item = self.get(name_or_id)
        if not item:
            return None
        with self.tx() as conn:
            conn.execute(
                "UPDATE memory_items SET access_count = access_count + 1, last_access_at = ? WHERE id = ?",
                (_now(), item.id),
            )
            self._event(conn, item.id, "read", actor, session_id, {"name": item.name})
        return self.get(item.id)

    def touch(self, item_id: str, actor: str = "agent",
              session_id: Optional[str] = None, event: str = "read") -> None:
        """记录一次访问（access_count + 事件），不改正文。"""
        with self.tx() as conn:
            conn.execute(
                "UPDATE memory_items SET access_count = access_count + 1, last_access_at = ? "
                "WHERE id = ?", (_now(), item_id))
            self._event(conn, item_id, event, actor, session_id, {})

    def touch_many(self, item_ids: Iterable[str], actor: str = "agent",
                   session_id: Optional[str] = None, event: str = "read") -> None:
        """批量记录访问：一条 UPDATE + 每条目一条事件，共用一个写事务。"""
        ids = [item_id for item_id in dict.fromkeys(item_ids) if item_id]
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        with self.tx() as conn:
            conn.execute(
                f"UPDATE memory_items SET access_count = access_count + 1, last_access_at = ? "
                f"WHERE id IN ({placeholders})",
                (_now(), *ids),
            )
            for item_id in ids:
                self._event(conn, item_id, event, actor, session_id, {})

    def read_with_meta(self, name_or_id: str, actor: str = "agent",
                       session_id: Optional[str] = None) -> Optional[tuple[Item, int]]:
        """读取正文 + 版本数，并把访问计数与事件放在同一个写事务里。"""
        item = self.get(name_or_id)
        if not item:
            return None
        now = _now()
        with self.tx() as conn:
            conn.execute(
                "UPDATE memory_items SET access_count = access_count + 1, last_access_at = ? "
                "WHERE id = ?", (now, item.id))
            self._event(conn, item.id, "read", actor, session_id, {"name": item.name})
            version = int(conn.execute(
                "SELECT count(*) FROM memory_versions WHERE item_id = ?", (item.id,)
            ).fetchone()[0])
        item.access_count += 1
        item.last_access_at = now
        return item, version

    def render_l1(self, max_chars: int = 2000, log: bool = True) -> str:
        items = self.list_items(layers=("L2", "L3"), status="active", limit=80)
        rules = self.get("l1_rules")
        lines = ["# [Global Memory Insight]",
                 "记忆检索用 memory_search，读正文用 memory_read"]
        if rules and rules.body:
            lines.append("")
            lines.extend(rules.body.rstrip().splitlines())
        lines.append("")
        lines.append("## 索引")
        # L2 事实全量；L3 按 priority 排序（list_items 已排），超阈值折叠尾部冷条目
        l2 = [it for it in items if it.layer == "L2"]
        l3 = [it for it in items if it.layer == "L3"]
        keep = 20
        for it in l2 + l3[:keep]:
            tag = "SKILL" if it.kind in ("sop", "script") else it.kind.upper()
            lines.append(f"[{tag}] {it.name} — {it.summary or it.title}")
        if len(l3) > keep:
            cold = " | ".join(it.name for it in l3[keep:])
            lines.append(f"[其他 {len(l3) - keep} 条冷门技能（按名检索）] {cold}")

        # 按行截断，避免切在条目中间
        out: list[str] = []
        size = 0
        for line in lines:
            if size + len(line) + 1 > max_chars and out:
                out.append(f"…（共 {len(items)} 条，已截断）")
                break
            out.append(line)
            size += len(line) + 1
        text = "\n".join(out)
        if log:
            self.log_event(None, "inject", actor="system", detail={"entries": len(items)})
        return text

    def versions(self, item_id: str, limit: int = 20) -> list[sqlite3.Row]:
        with self.db.lock:
            return self.conn.execute(
                "SELECT * FROM memory_versions WHERE item_id = ? ORDER BY version_id DESC LIMIT ?",
                (item_id, limit),
            ).fetchall()

    def version_count(self, item_id: str) -> int:
        with self.db.lock:
            return int(self.conn.execute(
                "SELECT count(*) FROM memory_versions WHERE item_id = ?", (item_id,)
            ).fetchone()[0])

    def stats(self) -> dict:
        with self.db.lock:
            items = self.conn.execute(
                "SELECT layer, status, count(*) AS n FROM memory_items GROUP BY layer, status"
            ).fetchall()
            versions = self.conn.execute("SELECT count(*) FROM memory_versions").fetchone()[0]
            events = self.conn.execute("SELECT count(*) FROM memory_events").fetchone()[0]
        return {
            "items": [dict(r) for r in items],
            "versions": versions,
            "events": events,
        }

    # ---------- 写 ----------
    def create(self, name: str, layer: str, kind: str, title: str = "",
               summary: str = "", body: str = "", tags: Iterable[str] = (),
               meta: Optional[dict] = None, status: str = "draft", priority: int = 100,
               verified: int = 0, confidence: float = 0.0,
               actor: str = "system", session_id: Optional[str] = None,
               reason: str = "create") -> Item:
        self._validate(layer, kind, status, name)
        self._check_body(body)
        item = Item(
            id=uuid.uuid4().hex, layer=layer, kind=kind, name=name, title=title,
            summary=summary, body=body, tags=list(tags), meta=meta or {},
            status=status, priority=priority, verified=verified, confidence=confidence,
            created_at=_now(), updated_at=_now(),
        )
        with self.tx() as conn:
            exists = conn.execute(
                "SELECT 1 FROM memory_items WHERE layer = ? AND name = ?", (layer, name)
            ).fetchone()
            if exists:
                raise DuplicateItem(f"{layer}/{name} 已存在")
            conn.execute(
                "INSERT INTO memory_items"
                "(id,layer,kind,name,title,summary,body,tags,meta,status,priority,"
                " verified,confidence,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.id, item.layer, item.kind, item.name, item.title, item.summary,
                 item.body, json.dumps(item.tags, ensure_ascii=False),
                 json.dumps(item.meta, ensure_ascii=False), item.status, item.priority,
                 item.verified, item.confidence, item.created_at, item.updated_at),
            )
            self._insert_version(conn, item, reason, actor, session_id)
            self._event(conn, item.id, "create", actor, session_id,
                        {"name": name, "layer": layer, "reason": reason})
        return self.get(item.id)

    def patch(self, name_or_id: str, body: Optional[str] = None, title: Optional[str] = None,
              summary: Optional[str] = None, status: Optional[str] = None,
              tags: Optional[Iterable[str]] = None, meta: Optional[dict] = None,
              priority: Optional[int] = None, verified: Optional[int] = None,
              reason: str = "patch", actor: str = "agent",
              session_id: Optional[str] = None,
              expected_version: Optional[int] = None) -> Item:
        current = self.get(name_or_id)
        if not current:
            raise KeyError(f"记忆不存在: {name_or_id}")
        if expected_version is not None:
            latest = self.versions(current.id, limit=1)
            latest_id = latest[0]["version_id"] if latest else 0
            if latest_id != expected_version:
                raise ValueError(f"版本冲突: 期望 {expected_version}，实际 {latest_id}")

        new = replace(current)
        if body is not None:
            self._check_body(body)
            new.body = body
        if title is not None:
            new.title = title
        if summary is not None:
            new.summary = summary
        if status is not None:
            self._validate(current.layer, current.kind, status, current.name)
            new.status = status
        if tags is not None:
            new.tags = list(tags)
        if meta is not None:
            new.meta = meta
        if priority is not None:
            new.priority = priority
        if verified is not None:
            new.verified = int(verified)
        new.updated_at = _now()

        with self.tx() as conn:
            conn.execute(
                "UPDATE memory_items SET title=?, summary=?, body=?, tags=?, meta=?,"
                " status=?, priority=?, verified=?, updated_at=? WHERE id=?",
                (new.title, new.summary, new.body,
                 json.dumps(new.tags, ensure_ascii=False),
                 json.dumps(new.meta, ensure_ascii=False),
                 new.status, new.priority, new.verified, new.updated_at, new.id),
            )
            self._insert_version(conn, new, reason, actor, session_id)
            self._event(conn, new.id, reason, actor, session_id, {"name": new.name})
        return self.get(new.id)

    def archive(self, name_or_id: str, reason: str = "archive", actor: str = "agent",
                session_id: Optional[str] = None) -> Item:
        return self.patch(name_or_id, status="archived", reason=reason,
                          actor=actor, session_id=session_id)

    def materialize(self, name_or_id: str, out_dir=None):
        """转发到 materialize 模块，避免调用方多记一个导入。"""
        from .materialize import materialize as _materialize
        return _materialize(self, name_or_id, out_dir)

    def log_event(self, item_id: Optional[str], event: str, actor: str = "agent",
                  session_id: Optional[str] = None, detail: Optional[dict] = None) -> None:
        with self.tx() as conn:
            self._event(conn, item_id, event, actor, session_id, detail)

    def link(self, from_name: str, to_name: str, rel: str = "related") -> None:
        a, b = self.get(from_name), self.get(to_name)
        if not a or not b:
            raise KeyError("link 两端都必须存在")
        if rel not in ("indexes", "supersedes", "depends", "related"):
            raise ValueError(f"非法 rel: {rel}")
        with self.tx() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO memory_links(from_id,to_id,rel,created_at) VALUES (?,?,?,?)",
                (a.id, b.id, rel, _now()),
            )

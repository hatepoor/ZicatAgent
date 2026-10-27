"""校验记忆迁移：sha256 一致、条目齐全、追加式约束生效。"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .common import DEFAULT_DB, MEMORY_DIR, sha256_bytes
from .db import Database
from .repository import MemoryStore

DEFAULT_MEMORY = MEMORY_DIR


class Report:
    def __init__(self):
        self.failures: list[str] = []
        self.checks = 0

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        self.checks += 1
        if not ok:
            self.failures.append(f"{label}: {detail}")
            print(f"FAIL  {label} {detail}")
        else:
            print(f"ok    {label}")

    def finish(self) -> int:
        print(f"\n共 {self.checks} 项，失败 {len(self.failures)} 项")
        return 0 if not self.failures else 1


def _body_sha(row: sqlite3.Row) -> str:
    return sha256_bytes((row["body"] or "").encode("utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="校验 memory 迁移")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--manifest", default="")
    parser.add_argument("--memory-dir", default=str(DEFAULT_MEMORY))
    args = parser.parse_args(argv)

    db_path = Path(args.db).resolve()
    memory_dir = Path(args.memory_dir).resolve()
    manifest_path = Path(args.manifest) if args.manifest else memory_dir / "backup" / "import_manifest.json"
    report = Report()

    if not manifest_path.is_file():
        print(f"manifest 不存在: {manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("entries", [])
    print(f"db={db_path}\nmanifest={manifest_path}\n条目={len(entries)}\n")

    db = Database(db_path, init=False)
    store = MemoryStore(db)

    with db.lock:
        total_items = db.conn.execute("SELECT count(*) FROM memory_items").fetchone()[0]
        total_versions = db.conn.execute("SELECT count(*) FROM memory_versions").fetchone()[0]
        total_events = db.conn.execute("SELECT count(*) FROM memory_events").fetchone()[0]
        fts_rows = db.conn.execute("SELECT count(*) FROM memory_fts").fetchone()[0]

    # 条目数一致 + manifest 外条目必须已归档（治理闭环：垃圾归档后 verify 应绿）
    _active_items = db.conn.execute(
        "SELECT count(*) FROM memory_items WHERE status != 'archived'").fetchone()[0]
    report.check(_active_items == len(entries), "条目数一致（archived 不计）",
                 f"db活跃={_active_items} manifest={len(entries)}")
    _names = {e["name"] for e in entries}
    _extra = [r[0] for r in db.conn.execute(
        "SELECT name FROM memory_items WHERE name NOT IN (%s) AND status != 'archived'"
        % ",".join("?" * len(_names)), tuple(_names))] if _names else []
    report.check(not _extra, "manifest 外条目", f"多余: {_extra}")
    report.check(total_versions >= len(entries), "每条至少一个版本", f"versions={total_versions}")
    report.check(fts_rows == total_items, "FTS 行数一致", f"fts={fts_rows} items={total_items}")
    report.check(total_events >= len(entries), "事件已记录", f"events={total_events}")

    for entry in entries:
        name = entry["name"]
        item = store.get(entry["item_id"]) or store.get(name)
        report.check(item is not None, f"条目存在 {name}", entry.get("source", ""))
        if item is None:
            continue
        if entry["kind"] != "archive":
            report.check(sha256_bytes(item.body.encode("utf-8")) == entry["body_sha256"],
                         f"正文 sha256 {name}", "")
        versions = store.versions(item.id, limit=1)
        report.check(bool(versions), f"版本存在 {name}", "")
        if versions:
            report.check(_body_sha(versions[0]) == entry["body_sha256"],
                         f"版本正文 sha256 {name}", "")
        src = memory_dir / entry["source"].replace("#RULES", "")
        if src.is_file() and entry["source"].endswith("#RULES") is False:
            report.check(sha256_bytes(src.read_bytes()) == entry["source_sha256"],
                         f"源文件未变 {entry['source']}", "")

    # 追加式：版本/事件禁止改删
    for sql, label in (
        ("UPDATE memory_versions SET body='x' WHERE version_id=1", "禁止 UPDATE memory_versions"),
        ("DELETE FROM memory_versions", "禁止 DELETE memory_versions"),
        ("UPDATE memory_events SET event='x' WHERE event_id=1", "禁止 UPDATE memory_events"),
        ("DELETE FROM memory_events", "禁止 DELETE memory_events"),
    ):
        try:
            with db.lock:
                db.conn.execute(sql)
            report.check(False, label, "没有被拒绝")
        except sqlite3.Error as exc:
            report.check("append-only" in str(exc), label, str(exc))

    l1 = store.render_l1()
    report.check(bool(l1.strip()), "L1 可渲染", f"{len(l1)} 字符")
    report.check(len(l1) <= 2000, "L1 未超长", f"{len(l1)} 字符")

    hits = store.search("sop", limit=5)
    report.check(bool(hits), "检索可用", f"{len(hits)} 条")

    stats = store.stats()
    print(f"\n统计: {json.dumps(stats, ensure_ascii=False)}")
    db.close()
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())

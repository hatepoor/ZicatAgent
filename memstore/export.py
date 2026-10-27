"""把记忆库导出为确定性 md 快照（供 git 版本化与灾备）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import DEFAULT_DB, MEMORY_DIR
from .db import Database
from .repository import MemoryStore

FRONT_MATTER = ("name", "layer", "kind", "status", "title", "summary",
                "tags", "priority", "verified", "updated_at", "version")


def _render(item, version: int) -> str:
    front = {
        "name": item.name, "layer": item.layer, "kind": item.kind,
        "status": item.status, "title": item.title, "summary": item.summary,
        "tags": item.tags, "priority": item.priority, "verified": item.verified,
        "updated_at": item.updated_at, "version": version,
    }
    lines = ["---"]
    for key in FRONT_MATTER:
        lines.append(f"{key}: {json.dumps(front[key], ensure_ascii=False)}")
    lines.append("---")
    lines.append("")
    body = item.body if item.kind != "archive" else ""
    return "\n".join(lines) + body.rstrip() + "\n"


def export(store: MemoryStore, out_dir: str | Path) -> int:
    """导出 L1/L2 条目；输出确定性：按 layer/name 排序，排除访问计数等易变字段。

    L3 不导出：kb/ 与 scripts/ 是 L3 的 git 代表（sync 后与库一致，verify 校验漂移），
    再导镜像即同一内容两份（FIX-M1）。
    """
    target = Path(out_dir)
    count = 0
    for item in store.list_items(status=None, limit=100000):
        if item.layer not in ("L1", "L2"):
            continue
        path = target / item.layer / f"{item.name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_render(item, store.version_count(item.id)), encoding="utf-8",
                        newline="\n")
        count += 1
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="导出记忆库为 md")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(MEMORY_DIR / "export"))
    args = parser.parse_args(argv)
    db = Database(Path(args.db), init=False)
    store = MemoryStore(db)
    count = export(store, args.out)
    db.close()
    print(f"已导出 {count} 条到 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

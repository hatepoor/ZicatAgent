"""记忆库备份：VACUUM INTO 快照 + 备份轮转。

说明：memory_versions / memory_events 是 append-only 的（触发器禁止删改），
所以备份任务只做"整库快照 + 备份文件轮转"，不删库内任何行。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .common import DEFAULT_DB, GRAPH_DB, MEMORY_DIR

DEFAULT_OUT = MEMORY_DIR / "backup" / "snapshots"


def _vacuum_into(src: Path, dst: Path) -> bool:
    if not src.is_file() or dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        conn.execute("VACUUM INTO ?", (str(dst),))
    finally:
        conn.close()
    return True


def _rotate(out_dir: Path, prefix: str, keep_daily: int = 7, keep_weeks: int = 4) -> list[str]:
    """保留最近 N 份；更早的只保留每周一份（最多 N 周），其余删除。"""
    files = sorted(out_dir.glob(f"{prefix}-*.db"), reverse=True)
    removed: list[str] = []
    cutoff = date.today() - timedelta(days=keep_daily)
    seen_weeks: set[tuple[int, int]] = set()
    for idx, path in enumerate(files):
        if idx < keep_daily:
            continue
        try:
            stamp = datetime.strptime(path.stem.split("-")[-1], "%Y%m%d").date()
        except ValueError:
            continue
        week = stamp.isocalendar()[:2]
        old = stamp < cutoff
        if old and week not in seen_weeks and len(seen_weeks) < keep_weeks:
            seen_weeks.add(week)
            continue
        path.unlink(missing_ok=True)
        removed.append(path.name)
    return removed


def run_backup(db_path: str | Path | None = None,
               graph_db: str | Path | None = None,
               out_dir: str | Path | None = None,
               keep_daily: int = 7, keep_weeks: int = 4) -> dict:
    db_path = Path(db_path) if db_path else DEFAULT_DB
    graph_db = Path(graph_db) if graph_db else GRAPH_DB
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    stamp = date.today().strftime("%Y%m%d")
    result = {"created": [], "skipped": [], "removed": []}

    for prefix, src in (("memory", db_path), ("graph", graph_db)):
        dst = out_dir / f"{prefix}-{stamp}.db"
        if _vacuum_into(src, dst):
            result["created"].append(dst.name)
        else:
            result["skipped"].append(dst.name)

    result["removed"] = (_rotate(out_dir, "memory", keep_daily, keep_weeks)
                         + _rotate(out_dir, "graph", keep_daily, keep_weeks))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="记忆库/检查点备份")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--graph-db", default=str(GRAPH_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--keep-daily", type=int, default=7)
    parser.add_argument("--keep-weeks", type=int, default=4)
    args = parser.parse_args(argv)
    result = run_backup(args.db, args.graph_db, args.out, args.keep_daily, args.keep_weeks)
    print(f"备份完成: 新建 {result['created']} 跳过 {result['skipped']} 清理 {result['removed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

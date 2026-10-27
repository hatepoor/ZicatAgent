"""SQLite 检查点：会话状态持久化。"""
from __future__ import annotations

import sqlite3
import lzma
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from memstore.common import GRAPH_DB

_SAVERS: dict[str, object] = {}

_COMPRESS_MARK = b"\x01"   # blob 首字节标记：有它 = 后面是 lzma 数据
_COMPRESS_MIN = 4096       # 小于 4KB 不值得压（标记本身也占空间）

class CompressedSerde(JsonPlusSerializer):
    """JsonPlus 序列化 + 大负载 lzma 压缩（FIX-4 第一层）。
    首字节标记让旧格式（无标记）数据仍可直读——兼容是靠"读侧永远先看标记"保证的。
    """

    def dumps_typed(self, obj):
        type_str, blob = super().dumps_typed(obj)
        if len(blob) >= _COMPRESS_MIN:
            blob = _COMPRESS_MARK + lzma.compress(blob)
        return type_str, blob

    def loads_typed(self, data):
        type_str, blob = data
        if blob[:1] == _COMPRESS_MARK:
            blob = lzma.decompress(blob[1:])
        return super().loads_typed((type_str, blob))

def get_saver(path: str | Path):
    resolved = str(Path(path).resolve())
    if resolved in _SAVERS:
        return _SAVERS[resolved]
    from langgraph.checkpoint.sqlite import SqliteSaver

    Path(resolved).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(resolved, check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    saver = SqliteSaver(conn,serde=CompressedSerde())
    saver.setup()
    _SAVERS[resolved] = saver
    return saver


def list_threads(path: str | Path | None = None, limit: int = 20) -> list[tuple[str, int]]:
    """返回 [(thread_id, 检查点数)]，最近的在前；库不存在时返回空。

    只读连接，schema 细节封装在这里，调用方（/threads）不直接写 SQL。
    """
    db_path = Path(path) if path else GRAPH_DB
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT thread_id, count(*) AS n, max(rowid) AS r FROM checkpoints "
            "GROUP BY thread_id ORDER BY r DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    return [(row[0], int(row[1])) for row in rows]


def list_checkpoints(path: str | Path | None, thread_id: str, limit: int = 20) -> list[str]:
    """返回该 thread 的 checkpoint_id 列表（新的在前）。"""
    db_path = Path(path) if path else GRAPH_DB
    if not db_path.is_file() or not thread_id:
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? "
            "ORDER BY rowid DESC LIMIT ?", (thread_id, limit)
        ).fetchall()
    finally:
        conn.close()
    return [row[0] for row in rows]

def prune_thread(path: str | Path | None, thread_id: str, keep: int = 20,
                 vacuum_mb:int=0) -> int:
    """FIX-4 第二层：删该 thread 较早的 checkpoint，保留最近 keep 份；返回删除数。

    两张表都要清（checkpoints 主表 + writes 挂起写入表），否则留孤儿数据。
    有挂起 interrupt 的 thread 由调用方负责不调用（恢复依赖历史检查点）。
    """
    db_path = Path(path) if path else GRAPH_DB
    if not db_path.is_file() or not thread_id or keep <= 0:
        return 0
    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    try:
        keep_ids = [row[0] for row in conn.execute(
            "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? "
            "ORDER BY rowid DESC LIMIT ?", (thread_id, keep))]
        if not keep_ids:
            return 0
        marks = ",".join("?" * len(keep_ids))
        deleted = conn.execute(
            f"DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_id NOT IN ({marks})",
            (thread_id, *keep_ids)).rowcount
        conn.execute(
            f"DELETE FROM writes WHERE thread_id = ? AND checkpoint_id NOT IN ({marks})",
            (thread_id, *keep_ids))
        #FIX-4: 删除后磁盘空间不会自动还给 OS，超过阈值才VACUUM(锁库操作，不能每次都做)
        if int(vacuum_mb or 0) > 0 and db_path.stat().st_size > int(vacuum_mb) * 1_000_000:
            conn.execute("VACUUM")
        return deleted
    finally:
        conn.close()


def clear_thread(path: str | Path | None, thread_id: str) -> int:
    """删除该 thread 的全部检查点（含 writes）；返回删除的检查点数。

    只用于“首轮任务被中断、没有可回退的历史检查点”的场景：清空后该会话
    等价于全新会话，不会把被取消的用户指令留给下一条消息。
    """
    db_path = Path(path) if path else GRAPH_DB
    if not db_path.is_file() or not thread_id:
        return 0
    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    try:
        deleted = conn.execute(
            "DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,)).rowcount
        conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
        return deleted
    finally:
        conn.close()

"""会话注册表：thread_id ↔ 人话标题 ↔ 工作目录 的映射与生命周期。

存放在 session/graph.db（与 checkpoints 同库）。真正的会话主键始终是
thread_id（LangGraph 机制）；标题只是它的别名——/resume 标题在这里翻译回
thread_id，checkpoint 读写路径零改动。
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = os.path.join(str(ROOT), "session")


def db_path() -> str:
    return os.path.join(SESSION_DIR, "graph.db")


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS session_meta (
        thread_id     TEXT PRIMARY KEY,
        title         TEXT UNIQUE,
        workspace_dir TEXT,
        created_at    TEXT,
        updated_at    TEXT,
        status        TEXT DEFAULT 'open'
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS workspace_meta (
        path          TEXT PRIMARY KEY,
        created_at    TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS session_usage (
        thread_id     TEXT PRIMARY KEY,
        usage         TEXT,
        updated_at    TEXT
    )""")


def save_usage(thread_id: str, usage: dict, db_file: str | None = None) -> None:
    """把最近一次任务的用量按 thread 持久化（切会话/重启后 /cost 仍可读）。"""
    if not thread_id or not isinstance(usage, dict) or not usage.get("requests"):
        return
    keys = ("requests", "input", "output", "last_input", "input_per_request")
    payload = json.dumps({k: int(usage.get(k) or 0) for k in keys}, ensure_ascii=False)
    conn = _conn(db_file or db_path())
    try:
        conn.execute(
            "INSERT OR REPLACE INTO session_usage (thread_id, usage, updated_at) "
            "VALUES (?, ?, datetime('now', 'localtime'))", (thread_id, payload))
    finally:
        conn.close()


def load_usage(thread_id: str, db_file: str | None = None) -> dict:
    """读取该 thread 最近一次任务用量；没有记录时返回空 dict。"""
    if not thread_id:
        return {}
    conn = _conn(db_file or db_path())
    try:
        row = conn.execute(
            "SELECT usage FROM session_usage WHERE thread_id = ?", (thread_id,)).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        return {}
    try:
        data = json.loads(row[0])
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def add_workspace(path: str, db_file: str | None = None) -> str:
    """登记一个工作区（用于左侧历史分组）；目录不存在则创建。"""
    abs_path = os.path.abspath(os.path.expanduser(path))
    os.makedirs(abs_path, exist_ok=True)
    conn = _conn(db_file or db_path())
    try:
        conn.execute(
            "INSERT OR IGNORE INTO workspace_meta (path, created_at) "
            "VALUES (?, datetime('now', 'localtime'))", (abs_path,))
    finally:
        conn.close()
    return abs_path


def list_workspaces(db_file: str | None = None) -> list[str]:
    conn = _conn(db_file or db_path())
    try:
        rows = conn.execute("SELECT path FROM workspace_meta ORDER BY path").fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows if r[0]]


def _group_workspace(workspace_dir: str, workspaces: list[str]) -> str:
    """给会话目录找最长匹配的工作区；找不到时退回父目录。"""
    target = os.path.abspath(workspace_dir or "")
    best = ""
    for workspace in workspaces:
        root = os.path.abspath(workspace)
        if target == root or target.startswith(root + os.sep):
            if len(root) > len(best):
                best = root
    return best or os.path.dirname(target) or target


def get(thread_id: str, db_file: str | None = None) -> dict | None:
    conn = _conn(db_file or db_path())
    try:
        row = conn.execute(
            "SELECT thread_id, title, workspace_dir, updated_at, status "
            "FROM session_meta WHERE thread_id = ?", (thread_id,)).fetchone()
        workspaces = [r[0] for r in conn.execute(
            "SELECT path FROM workspace_meta").fetchall() if r[0]]
    finally:
        conn.close()
    if not row:
        return None
    return {"thread_id": row[0], "title": row[1], "workspace_dir": row[2],
            "updated_at": row[3], "status": row[4],
            "workspace": _group_workspace(row[2] or "", workspaces)}


def _conn(db_file: str) -> sqlite3.Connection:
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file, check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=5000")
    ensure_table(conn)
    return conn


def register(thread_id: str, workspace_root: str, title: str | None = None,
             db_file: str | None = None, exact: bool = False) -> str:
    """登记新会话：建工作目录（有标题用标题并查重，否则 ID 短码）。返回目录路径。

    exact=True 时直接用 workspace_root 本身作为会话目录（用户显式指定工作空间），
    不再追加标题子目录。
    """
    add_workspace(workspace_root, db_file=db_file)
    short = thread_id.replace("cli-", "")[:8]
    ws = (os.path.abspath(workspace_root) if exact
          else os.path.abspath(os.path.join(workspace_root, short)))
    conn = _conn(db_file or db_path())
    try:
        if title:
            title = " ".join(title.split())[:10].strip() or title
            n = 1
            final = title
            while conn.execute("SELECT 1 FROM session_meta WHERE title = ? AND thread_id != ?",
                               (final, thread_id)).fetchone():
                n += 1
                final = f"{title}_{n}"
            title = final
            if not exact:
                ws = os.path.abspath(os.path.join(workspace_root, title))
        os.makedirs(ws, exist_ok=True)
        conn.execute(
            "INSERT OR REPLACE INTO session_meta (thread_id, title, workspace_dir, created_at, updated_at, status) "
            "VALUES (?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'), 'open')",
            (thread_id, title, ws))
    finally:
        conn.close()
    return ws


def set_workspace(thread_id: str, workspace_dir: str,
                  db_file: str | None = None) -> str:
    """把当前会话的工作目录切到指定路径（显式工作空间，不再套标题子目录）。"""
    path = os.path.abspath(os.path.expanduser(workspace_dir))
    os.makedirs(path, exist_ok=True)
    add_workspace(path, db_file=db_file)
    conn = _conn(db_file or db_path())
    try:
        exists = conn.execute("SELECT 1 FROM session_meta WHERE thread_id = ?",
                              (thread_id,)).fetchone()
        if exists:
            conn.execute(
                "UPDATE session_meta SET workspace_dir = ?, updated_at = datetime('now', 'localtime') "
                "WHERE thread_id = ?", (path, thread_id))
        else:
            conn.execute(
                "INSERT INTO session_meta (thread_id, title, workspace_dir, created_at, updated_at, status) "
                "VALUES (?, NULL, ?, datetime('now', 'localtime'), datetime('now', 'localtime'), 'open')",
                (thread_id, path))
    finally:
        conn.close()
    return path


def set_title(thread_id: str, title: str, db_file: str | None = None) -> str:
    """设置人话标题：查重加序号（标题唯一约束在写入时保证），并 rename 工作目录。"""
    title = " ".join(title.split())[:10].strip() or "未命名会话"
    conn = _conn(db_file or db_path())
    try:
        row = conn.execute("SELECT workspace_dir FROM session_meta WHERE thread_id = ?",
                           (thread_id,)).fetchone()
        if not row:
            raise KeyError(f"会话未注册: {thread_id}")
        old_dir = row[0]
        final, n = title, 1
        while conn.execute("SELECT 1 FROM session_meta WHERE title = ? AND thread_id != ?",
                           (final, thread_id)).fetchone():
            n += 1
            final = f"{title}_{n}"
        new_dir = os.path.join(os.path.dirname(old_dir), final)
        if os.path.abspath(old_dir) != os.path.abspath(new_dir) and os.path.isdir(old_dir):
            try:
                os.rename(old_dir, new_dir)
            except OSError:
                new_dir = old_dir  # 目录被占用等场景：保留旧名，标题仍写入
        conn.execute(
            "UPDATE session_meta SET title = ?, workspace_dir = ?, updated_at = datetime('now', 'localtime') "
            "WHERE thread_id = ?", (final, new_dir, thread_id))
        return new_dir
    finally:
        conn.close()


def find(text: str, db_file: str | None = None):
    """标题精确/前缀查找。返回 (记录, 候选列表)：唯一命中时候选为空。"""
    conn = _conn(db_file or db_path())
    try:
        rows = conn.execute(
            "SELECT thread_id, title, workspace_dir, updated_at, status FROM session_meta "
            "WHERE title LIKE ? ORDER BY updated_at DESC", (f"%{text}%",)).fetchall()
    finally:
        conn.close()
    exact = [r for r in rows if r[1] == text]
    if exact:
        return exact[0], []
    return (rows[0], []) if len(rows) == 1 else (None, rows)


def list_sessions(limit: int = 20, db_file: str | None = None) -> list[dict]:
    conn = _conn(db_file or db_path())
    try:
        rows = conn.execute(
            "SELECT thread_id, title, workspace_dir, updated_at, status FROM session_meta "
            "ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        workspaces = [r[0] for r in conn.execute(
            "SELECT path FROM workspace_meta").fetchall() if r[0]]
    finally:
        conn.close()
    return [{"thread_id": r[0], "title": r[1] or f"（未命名 {r[0][-8:]}）",
             "workspace_dir": r[2], "updated_at": r[3], "status": r[4],
             "workspace": _group_workspace(r[2] or "", workspaces)} for r in rows]


def workspace_of(thread_id: str, workspace_root: str, db_file: str | None = None) -> str:
    """取会话绑定的目录；未注册/未命名时按 ID 短码兜底建目录。"""
    conn = _conn(db_file or db_path())
    try:
        row = conn.execute("SELECT workspace_dir FROM session_meta WHERE thread_id = ?",
                           (thread_id,)).fetchone()
    finally:
        conn.close()
    if row and row[0]:
        return row[0]
    return register(thread_id, workspace_root, db_file=db_file)


def delete(thread_id: str, db_file: str | None = None) -> bool:
    """删除会话：session_meta 行 + checkpoints/writes 全部行（产物目录由调用方单独确认）。

    checkpoints/writes 表可能尚不存在（从未跑过任务的会话），逐表容错。
    """
    conn = _conn(db_file or db_path())
    try:
        for table in ("checkpoints", "writes"):
            try:
                conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,))
            except sqlite3.OperationalError:
                pass  # 表未建立 = 无数据
        removed = conn.execute("DELETE FROM session_meta WHERE thread_id = ?",
                               (thread_id,)).rowcount
        return removed > 0
    finally:
        conn.close()


def _can_rmtree(path: str) -> bool:
    """保护盘符根、仓库根、用户主目录及其祖先。"""
    target = os.path.realpath(os.path.abspath(path))
    root = os.path.realpath(str(ROOT))
    home = os.path.realpath(os.path.expanduser("~"))
    drive = os.path.realpath(os.path.abspath(os.sep))
    if target in {drive, root, home}:
        return False
    if root == target or root.startswith(target + os.sep):
        return False
    return True


def delete_session(thread_id: str, remove_files: bool = True,
                   db_file: str | None = None) -> dict:
    """删除会话及其独占工作目录。

    只有目录是该会话独占、且不是注册工作区根目录时才删文件；共享工作区
    （例如 /workspace 指定的项目目录）只删会话记录，避免误删别人的文件。
    """
    conn = _conn(db_file or db_path())
    try:
        row = conn.execute(
            "SELECT title, workspace_dir FROM session_meta WHERE thread_id = ?",
            (thread_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "会话不存在"}
        title, workspace = row[0], row[1]
        workspaces = [r[0] for r in conn.execute(
            "SELECT path FROM workspace_meta").fetchall() if r[0]]
        shared = conn.execute(
            "SELECT 1 FROM session_meta WHERE workspace_dir = ? AND thread_id != ? LIMIT 1",
            (workspace, thread_id)).fetchone()
        for table in ("checkpoints", "writes"):
            try:
                conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,))
            except sqlite3.OperationalError:
                pass
        conn.execute("DELETE FROM session_meta WHERE thread_id = ?", (thread_id,))
    finally:
        conn.close()

    files_removed = False
    reason = ""
    target = os.path.abspath(workspace or "")
    if remove_files and target:
        if target in {os.path.abspath(w) for w in workspaces}:
            reason = "共享工作区根目录，文件保留"
        elif shared:
            reason = "其他会话也使用该目录，文件保留"
        elif not _can_rmtree(target):
            reason = "受保护目录，文件保留"
        elif not os.path.isdir(target):
            reason = "会话目录不存在"
        else:
            try:
                shutil.rmtree(target)
                files_removed = True
            except OSError as e:
                reason = f"删除文件失败: {e}"
    return {"ok": True, "thread_id": thread_id, "title": title,
            "workspace_dir": workspace, "files_removed": files_removed,
            "files_kept_reason": reason}


def delete_workspace(path: str, db_file: str | None = None) -> dict:
    """删除工作区：其下所有会话/检查点 + 工作区目录全部文件。"""
    if not path:
        return {"ok": False, "error": "缺少工作区路径"}
    target = os.path.abspath(os.path.expanduser(path))
    conn = _conn(db_file or db_path())
    try:
        row = conn.execute("SELECT 1 FROM workspace_meta WHERE path = ?",
                           (target,)).fetchone()
        if not row:
            return {"ok": False, "error": "工作区未注册"}
        workspaces = [r[0] for r in conn.execute(
            "SELECT path FROM workspace_meta").fetchall() if r[0]]
        scope = [w for w in workspaces
                 if os.path.abspath(w) == target or os.path.abspath(w).startswith(target + os.sep)]
        sessions = conn.execute(
            "SELECT thread_id, workspace_dir FROM session_meta").fetchall()
        thread_ids = [r[0] for r in sessions
                      if _group_workspace(r[1] or "", workspaces) in scope]
        for thread_id in thread_ids:
            for table in ("checkpoints", "writes"):
                try:
                    conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,))
                except sqlite3.OperationalError:
                    pass
            conn.execute("DELETE FROM session_meta WHERE thread_id = ?", (thread_id,))
        for workspace in scope:
            conn.execute("DELETE FROM workspace_meta WHERE path = ?", (workspace,))
    finally:
        conn.close()

    files_removed = False
    reason = ""
    if not _can_rmtree(target):
        reason = "受保护目录，文件保留"
    elif not os.path.isdir(target):
        reason = "工作区目录不存在"
    else:
        try:
            shutil.rmtree(target)
            files_removed = True
        except OSError as e:
            reason = f"删除文件失败: {e}"
    return {"ok": True, "path": target, "sessions_deleted": len(thread_ids),
            "workspaces_deleted": len(scope), "files_removed": files_removed,
            "files_kept_reason": reason}

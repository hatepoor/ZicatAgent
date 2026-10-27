"""任务级文件回退：把 core.rewind 的 worldline 接到 graph 引擎。

每次工具调用前对写操作文件埋点，每轮结束提交一个节点；`/rewind file <id>`
可以只回退文件（对话状态的回退由检查点负责）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from core.rewind import RewindStore


class TaskRewind:
    def __init__(self, thread_id: str, cwd: str | Path, temp_dir: str | Path):
        root = os.path.join(str(temp_dir), ".zicat_rewind", thread_id or "default")
        self.store = RewindStore(root, str(cwd))
        self.root = root

    def track(self, path: str) -> None:
        if not path:
            return
        try:
            self.store.track_pre_edit(os.path.abspath(path))
        except Exception:  # noqa: BLE001 - 回退埋点失败不影响任务
            pass

    def commit(self, turn: int, title: str = "") -> Optional[str]:
        try:
            return self.store.commit(title or f"turn {turn}")
        except Exception:  # noqa: BLE001
            return None

    def nodes(self) -> list[tuple[str, str]]:
        try:
            return [(nid, self.store.nodes.get(nid, {}).get("title", ""))
                    for nid in reversed(self.store.linear_path())]
        except Exception:  # noqa: BLE001
            return []

    def apply(self, node_id: str) -> list[tuple[str, str]]:
        return self.store.apply_code(node_id)

    def exists(self) -> bool:
        return os.path.isdir(self.root) and os.path.isfile(os.path.join(self.root, "tree.json"))

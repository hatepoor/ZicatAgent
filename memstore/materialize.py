"""L3 技能物化：把记忆库里的脚本正文写成可执行文件（内容哈希命名）。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .repository import MemoryStore

SKILL_DIR = Path(__file__).resolve().parent.parent / "temp" / "skills"


def materialize(store: MemoryStore, name_or_id: str, out_dir: str | Path | None = None) -> Path:
    """把 kind='script' 的记忆物化到 temp/skills/<name>-<hash>.py。

    内容一变哈希就变，天然避免旧缓存；重复调用直接复用。
    """
    item = store.get(name_or_id)
    if not item:
        raise KeyError(f"记忆不存在: {name_or_id}")
    if item.kind != "script":
        raise ValueError(f"只有 script 才能物化: {item.layer}/{item.name} ({item.kind})")
    digest = hashlib.sha256(item.body.encode("utf-8")).hexdigest()[:16]
    target = Path(out_dir or SKILL_DIR) / f"{item.name}-{digest}.py"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.body, encoding="utf-8", newline="\n")
        store.log_event(item.id, "materialize", actor="system", detail={"path": str(target)})
    return target

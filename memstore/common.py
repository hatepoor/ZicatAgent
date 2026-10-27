"""共享常量与工具函数。"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT / "memory"
DEFAULT_DB = MEMORY_DIR / "memory.db"
GRAPH_DB = ROOT / "session" / "graph.db"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

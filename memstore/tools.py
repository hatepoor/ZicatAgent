"""记忆工具实现：legacy 与 graph 引擎共用。

工具的 schema 只有一份（assets/tools_schema.json），实现也只有这一份：
- `zicat.ZicatAgentHandler.do_memory_*` 转发到这里；
- `engine/runner` 只负责在任务开始时注入 L1。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .common import DEFAULT_DB
from .db import Database
from .repository import MemoryStore

MEMORY_TOOL_NAMES = (
    "memory_search", "memory_read", "memory_write", "memory_patch",
    "memory_archive", "memory_link", "memory_index",
)


class MemoryTools:
    """按需打开记忆库；不可用时返回 JSON 错误而不是抛异常。"""

    def __init__(self, db_path: Optional[str | Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self._store = None
        self._error = ""

    @property
    def store(self) -> Optional[MemoryStore]:
        if self._store is None and not self._error:
            try:
                # 已存在的库在首次打开时自动升级 schema；库缺失时保持只读降级，
                # 不在这里凭空创建空库。
                self._store = MemoryStore(
                    Database(self.db_path, init=self.db_path.exists())
                )
            except Exception as exc:  # noqa: BLE001 - 记忆库不可用时降级
                self._error = f"记忆库不可用: {exc}"
        return self._store

    def dispatch(self, name: str, args: dict) -> str:
        store = self.store
        if store is None:
            return json.dumps({"error": self._error or "记忆库不可用"}, ensure_ascii=False)
        try:
            if name == "memory_search":
                items = store.search(args.get("query", ""), layer=args.get("layer") or None,
                                     limit=int(args.get("limit", 5)))
                store.touch_many([item.id for item in items], actor="agent", event="read")
                return json.dumps([{"name": i.name, "layer": i.layer, "kind": i.kind,
                                    "summary": i.summary, "updated_at": i.updated_at}
                                   for i in items], ensure_ascii=False)
            if name == "memory_read":
                result = store.read_with_meta(args.get("name", ""), actor="agent")
                if not result:
                    return json.dumps({"error": "未找到"}, ensure_ascii=False)
                item, version = result
                return json.dumps({"name": item.name, "layer": item.layer, "kind": item.kind,
                                   "body": item.body, "version": version,
                                   "updated_at": item.updated_at}, ensure_ascii=False)
            if name == "memory_write":
                existing = store.get(args.get("name", ""))
                if existing is not None:
                    return json.dumps({
                        "error": f"条目 {args['name']} 已存在（{existing.layer}/{existing.kind}），"
                                 f"更新请用 memory_patch，新知识请换一个名字",
                        "hint": "patch 保留版本历史；重复 create 会被唯一约束拒绝",
                    }, ensure_ascii=False)
                if not args.get("summary"):
                    return json.dumps({"error": "缺少 summary：L1 索引靠它召回，必填"},
                                      ensure_ascii=False)
                item = store.create(
                    name=args["name"], layer=args["layer"], kind=args["kind"],
                    title=args.get("title", ""), summary=args.get("summary", ""),
                    body=args.get("body", ""), tags=args.get("tags", []),
                    status="draft" if args["kind"] == "script" else "active",
                    actor="agent", reason="create",
                )
                return json.dumps({"ok": True, "id": item.id}, ensure_ascii=False)
            if name == "memory_patch":
                new_body = args.get("body") or ""
                related = []
                if len(new_body) >= 8:
                    # 8 字短探针：FTS 逐字切分下长短语要求整段相邻才命中，太特异；
                    # 8 字既够特异又能容忍条目间的措辞差异
                    probe = new_body[:8]
                    related = [i.name for i in store.search(probe, limit=4)
                               if i.name != args.get("name")]
                item = store.patch(
                    args["name"], body=args.get("body"), summary=args.get("summary"),
                    reason=args.get("reason", "patch"), actor="agent",
                )
                out = {"ok": True, "id": item.id}
                if related:
                    out["related"] = related
                    out["hint"] = "检测到内容相似条目；若为同一知识请合并而非并行维护两份"
                return json.dumps(out, ensure_ascii=False)
            if name == "memory_archive":
                item = store.archive(args["name"], reason=args.get("reason", "archive"), actor="agent")
                return json.dumps({"ok": True, "id": item.id}, ensure_ascii=False)
            if name == "memory_link":
                store.link(args["from"], args["to"], args.get("rel", "related"))
                return json.dumps({"ok": True}, ensure_ascii=False)
            if name == "memory_index":
                return store.render_l1(log=False)
        except Exception as exc:  # noqa: BLE001 - 工具错误回灌给模型
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
        return json.dumps({"error": f"未知记忆工具 {name}"}, ensure_ascii=False)

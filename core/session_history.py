"""从 LangGraph checkpoint 读取会话历史，转成 Web TUI 可渲染的条目。

只读；不修改 checkpoint。工具调用与工具结果按 tool_call_id 配对，
内部轮末提示（[TIPS]/[WORKING MEMORY] 等）不进入历史。
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from engine.checkpointer import get_saver
from engine.hooks import text_of
from engine.settings import graph_config

_INTERNAL = re.compile(
    r"^\s*(\[TIPS\]|\[SYSTEM TIPS\]|\[DANGER\]|\[WORKING MEMORY\]|"
    r"###\s*\[WORKING MEMORY\]|\[MASTER\]|\[ROUND END\]|\[SYSTEM\]|"
    r"\[ERROR\]|\[System\]|\[Info\]|\[Warn\]|<global_memory>|\[Peer\])",
    re.IGNORECASE,
)
MAX_TEXT = 4000
MAX_ARGS = 300
MAX_PAYLOAD_STR = 8000


def _payload(body: str):
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        key: (value[:MAX_PAYLOAD_STR] + "…[truncated]"
              if isinstance(value, str) and len(value) > MAX_PAYLOAD_STR else value)
        for key, value in data.items()
    }


def _args_text(args) -> str:
    try:
        text = json.dumps(args or {}, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(args or "")
    return text[:MAX_ARGS] + ("…" if len(text) > MAX_ARGS else "")


def load_history(thread_id: str, limit: int = 300) -> list[dict]:
    """返回按时间顺序排列的历史条目；异常时返回空列表。"""
    if not thread_id:
        return []
    try:
        saver = get_saver(graph_config()["checkpointer"])
        tup = saver.get_tuple({"configurable": {"thread_id": thread_id}})
    except Exception:  # noqa: BLE001 - 历史读取失败不应影响会话切换
        return []
    if not tup:
        return []
    messages = ((tup.checkpoint or {}).get("channel_values") or {}).get("messages") or []

    items: list[dict] = []
    pending_tools: dict[str, dict] = {}
    for message in messages:
        if isinstance(message, HumanMessage):
            text = text_of(message).strip()
            if text and not _INTERNAL.match(text):
                items.append({"kind": "user", "text": text})
            continue

        if isinstance(message, (AIMessage, AIMessageChunk)) or hasattr(message, "tool_calls"):
            text = text_of(message)
            if text.strip():
                items.append({"kind": "assistant", "text": text})
            for call in getattr(message, "tool_calls", None) or []:
                name = str(call.get("name") or "")
                entry = {
                    "kind": "tool",
                    "name": name,
                    "args": _args_text(call.get("args")),
                    "status": "done",
                    "text": "",
                    "payload": None,
                }
                items.append(entry)
                call_id = call.get("id")
                if call_id:
                    pending_tools[str(call_id)] = entry
            continue

        if isinstance(message, ToolMessage):
            body = text_of(message)
            payload = _payload(body)
            entry = pending_tools.pop(str(getattr(message, "tool_call_id", "") or ""), None)
            if entry is None:
                entry = {
                    "kind": "tool",
                    "name": str(getattr(message, "name", "") or ""),
                    "args": "",
                    "status": "done",
                    "text": "",
                    "payload": None,
                }
                items.append(entry)
            entry["text"] = body[:MAX_TEXT]
            entry["payload"] = payload
            if getattr(message, "status", "") == "error":
                entry["status"] = "error"

    # 未拿到 ToolMessage 的调用（中断/异常）至少保留调用本身
    for item in items:
        if item["kind"] == "tool" and not item.get("text"):
            item["text"] = "（历史中无工具结果记录）"
    return items[-max(1, int(limit)):]

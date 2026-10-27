"""LLM 回调：用量统计 + 模型响应日志（供 L4 归档 / peer hint 使用）。"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Optional

from langchain_core.callbacks import BaseCallbackHandler

try:  # 新版路径；旧版退回 langchain.callbacks.base
    from langchain_core.outputs import LLMResult
except Exception:  # pragma: no cover
    LLMResult = object


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)
    return str(content or "")


class LoggingCallback(BaseCallbackHandler):
    """把每轮 Prompt/Response 追加到 `temp/model_responses/`，格式兼容 L4 压缩器。"""

    def __init__(self, path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _append(self, text: str) -> None:
        if not self.path:
            return
        path = os.path.abspath(self.path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with self._lock:
            with open(path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:  # noqa: D401
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"=== Prompt === {stamp}"]
        for batch in messages or []:
            for message in batch or []:
                lines.append(f"[{getattr(message, 'type', 'user')}] {_text(getattr(message, 'content', ''))}")
        self._append("\n".join(lines) + "\n")

    def on_llm_end(self, response, **kwargs) -> None:  # noqa: D401
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"=== Response === {stamp}"]
        for generation_batch in getattr(response, "generations", None) or []:
            for generation in generation_batch or []:
                message = getattr(generation, "message", None)
                if message is None:
                    continue
                content = _text(getattr(message, "content", ""))
                if content:
                    lines.append(content)
                for call in getattr(message, "tool_calls", None) or []:
                    lines.append(f"<tool_use>{json.dumps(call, ensure_ascii=False)}</tool_use>")
        self._append("\n".join(lines) + "\n")


class UsageTracker(BaseCallbackHandler):
    """记录 (input, output, requests)；兼容不同厂商的 token_usage 字段。"""

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.requests = 0
        # 最近一次请求的 input：它才代表“当前上下文大小”，累计 input 是整任务总和
        self.last_input = 0

    @staticmethod
    def _usage_of(response: "LLMResult") -> tuple[Optional[int], Optional[int]]:
        llm_output = getattr(response, "llm_output", None) or {}
        token_usage = llm_output.get("token_usage") or {}
        incoming = token_usage.get("prompt_tokens") or token_usage.get("input_tokens")
        outgoing = token_usage.get("completion_tokens") or token_usage.get("output_tokens")
        if incoming is None and getattr(response, "generations", None):
            try:
                message = response.generations[0][0].message
                metadata = getattr(message, "usage_metadata", None) or {}
                incoming = metadata.get("input_tokens")
                outgoing = metadata.get("output_tokens")
            except (AttributeError, IndexError, TypeError):
                pass
        return incoming, outgoing

    def on_llm_end(self, response, **kwargs) -> None:  # noqa: D401
        incoming, outgoing = self._usage_of(response)
        if incoming is None and outgoing is None:
            return
        self.requests += 1
        self.input_tokens += int(incoming or 0)
        self.output_tokens += int(outgoing or 0)
        self.last_input = int(incoming or 0)

    def snapshot(self) -> dict:
        return {"input": self.input_tokens, "output": self.output_tokens,
                "requests": self.requests, "last_input": self.last_input}

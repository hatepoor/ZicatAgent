"""工具层：复用 zicat.py 的 do_* 实现。

工具 schema 的唯一来源是 assets/tools_schema.json（含 7 个 memory_* 工具，
由 zicat.ZicatAgentHandler 的 do_memory_* 实现，legacy 与 graph 共用）。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agent_types import StepOutcome, exhaust

ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = ROOT / "memory"


def load_tools_schema(no_user_tools: bool = False) -> list[dict]:
    suffix = "_en" if os.environ.get("ZICAT_LANG", "") == "en" else ""
    path = ROOT / "assets" / f"tools_schema{suffix}.json"
    tools = json.loads(path.read_text(encoding="utf-8"))
    banned = {"ask_user", "start_long_term_update"} if no_user_tools else set()
    return [t for t in tools if t.get("function", {}).get("name") not in banned]


def _json_default(obj):
    if isinstance(obj, set):
        return list(obj)
    return str(obj)


def _touches_memory(path: str, cwd: str) -> bool:
    if not path:
        return False
    try:
        abs_path = Path(os.path.abspath(os.path.join(cwd, path)))
        abs_path.relative_to(MEMORY_DIR)
        return True
    except (ValueError, OSError):
        return False


@dataclass
class ToolRuntime:
    """一次任务内的工具执行上下文（不进 State，不可序列化）。"""

    agent: Any
    handler: Any
    tools_schema: list[dict] = field(default_factory=list)
    base_prompt: str = ""
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "requests": 0})
    last_should_exit: bool = False
    last_next_prompt: str = ""
    rewind: Any = None

    def add_usage(self, usage_metadata: dict | None) -> None:
        if not usage_metadata:
            return
        self.usage["input"] += int(usage_metadata.get("input_tokens") or 0)
        self.usage["output"] += int(usage_metadata.get("output_tokens") or 0)
        self.usage["requests"] += 1
        self.usage["last_input"] = int(usage_metadata.get("input_tokens") or 0)

    def run_tool(self, name: str, args: dict, ai_message) -> str:
        self.last_should_exit = False
        self.last_next_prompt = ""
        # 中断后同一轮里还没开始的工具不再执行；已开始的长任务由 code_run
        # 的 code_stop_signal 自行中止。
        if getattr(self.agent, "stop_sig", False):
            self.last_should_exit = True
            return json.dumps({"status": "aborted", "msg": "任务已中断"}, ensure_ascii=False)
        if name in ("file_write", "file_patch"):
            if _touches_memory(args.get("path", ""), self.handler.cwd):
                return json.dumps({"error": "memory/ 由记忆库管理，请改用 memory_write / memory_patch"},
                                  ensure_ascii=False)
            if self.rewind is not None and args.get("path"):
                self.rewind.track(os.path.join(self.handler.cwd, args["path"]))
        elif name == "file_apply_patch" and self.rewind is not None:
            try:
                from tools.files.apply_patch import parse_patch
                text = args.get("patch") or getattr(ai_message, "content", "") or ""
                for item in parse_patch(text):
                    self.rewind.track(os.path.join(self.handler.cwd, item.path))
                    if item.move_to:
                        self.rewind.track(os.path.join(self.handler.cwd, item.move_to))
            except Exception:
                pass

        response = SimpleNamespace(content=getattr(ai_message, "content", "") or "")
        gen = self.handler.dispatch(name, args or {}, response,
                                    index=int(args.get("_index", 0) or 0),
                                    tool_num=int(args.get("_tool_num", 1) or 1))
        outcome = exhaust(gen)
        if outcome is None:
            return ""
        if isinstance(outcome, StepOutcome):
            self.last_should_exit = bool(outcome.should_exit)
            self.last_next_prompt = outcome.next_prompt or ""
            data = outcome.data
        else:
            data = outcome
        if data is None:
            return ""
        if isinstance(data, (dict, list)):
            return json.dumps(data, ensure_ascii=False, default=_json_default)
        return str(data)

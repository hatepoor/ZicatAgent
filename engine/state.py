"""图状态：消息与摘要只追加。"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage


class ZicatState(TypedDict, total=False):
    # 只追加：不用 add_messages（它允许按 id 替换）
    messages: Annotated[list[AnyMessage], operator.add]
    # 追加式摘要链
    summaries: Annotated[list[str], operator.add]
    # 覆盖式：工作记忆
    working: dict
    turn: int
    exit_reason: str | None
    meta: dict

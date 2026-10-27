"""上下文构建与摘要提取（模型视图可折叠，存储不动）。"""
from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

_TRUNC_MARK = "…[已截断]"
_ANCHOR_MARK = "…[任务已截断，原文在存储中]"
DEFAULT_FOLD_RATIO = 0.7
DEFAULT_ANCHOR_RATIO = 0.5


def text_of(message: Any) -> str:
    if isinstance(message, str):
        return message
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content or "")


def _turn_size(messages: list[BaseMessage]) -> int:
    """从首条算起的一整轮长度：带 tool_calls 的 AIMessage 与其 ToolMessage 成组。

    只弹 AIMessage 会让视图以 role=tool 开头，而 OpenAI 兼容接口要求 role=tool
    紧跟带 tool_calls 的 assistant 消息。
    """
    first = messages[0]
    if not isinstance(first, AIMessage):
        return 1
    ids = {call.get("id") for call in (getattr(first, "tool_calls", None) or [])}
    if not ids or None in ids:
        return 1
    size = 1
    while size < len(messages):
        message = messages[size]
        if isinstance(message, ToolMessage) and getattr(message, "tool_call_id", None) in ids:
            size += 1
        else:
            break
    return size


def _clip(text: str, limit: int) -> str:
    """单行化后保留首尾；limit 很小时退化为只保留开头。"""
    cleaned = " ".join(str(text or "").split())
    if limit <= 0:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    head = (limit * 2) // 3
    tail = limit - head
    return cleaned[:head] + ("…" + cleaned[-tail:] if tail else "")


def digest_text(text: str, limit: int = 260) -> str:
    """引擎侧首尾摘录（不依赖模型输出），用于兜底摘要与折叠说明。"""
    return _clip(text, limit)


def _head_tail(text: str, target: int, mark: str = _TRUNC_MARK) -> str:
    """截到 target 字符：保留头部与尾部，中间放标记。

    折叠后仅存的锚点/工作记忆，尾部通常是最新内容，砍尾比砍中间伤害更大。
    """
    if target >= len(text):
        return text
    target = max(0, target)
    if target <= len(mark):
        return text[:target]
    room = target - len(mark)
    head = (room * 2) // 3
    tail = room - head
    return text[:head] + mark + (text[-tail:] if tail else "")


def _head_only(text: str, target: int) -> str:
    """普通消息截断：保留头部并计入标记长度，保证总长恰好落在 target。"""
    if target >= len(text):
        return text
    target = max(0, target)
    if target > len(_TRUNC_MARK):
        return text[:target - len(_TRUNC_MARK)] + _TRUNC_MARK
    return text[:target]


def _role_of(message: BaseMessage) -> str:
    return str(getattr(message, "type", None) or type(message).__name__)


def _span_digest(messages: list[BaseMessage], positions: list[int],
                 limit: int = 420) -> str:
    """被折叠段的存储条号范围与首尾摘录（纯抽取，不依赖模型是否给了 summary）。"""
    entries = [(position, message, text_of(message).strip())
               for message, position in zip(messages, positions)]
    entries = [item for item in entries if item[2]]
    if not entries:
        return ""
    if len(entries) == 1:
        position, message, body = entries[0]
        return f"msg{position}（{_role_of(message)}）：{_clip(body, limit)}"
    first = entries[0]
    last = entries[-1]
    part = max(40, (limit - 40) // 2)
    return (f"msg{first[0]}–{last[0]}（{_role_of(first[1])}→{_role_of(last[1])}）"
            f"首段：{_clip(first[2], part)}；末段：{_clip(last[2], part)}")


def _summary_note(summaries: list, limit: int = 800) -> str:
    """从最新往旧累加摘要，保证最近轮次不被截掉（旧的取前缀做法保留的是最旧几条）。"""
    picked: list[str] = []
    used = 0
    for item in reversed([str(s) for s in summaries[-8:]]):
        addition = len(item) + (1 if picked else 0)
        if picked and used + addition > limit:
            break
        picked.append(item)
        used += addition
    return "；".join(reversed(picked))


def _ratio(value: Any, default: float) -> float:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.1, ratio))


def _shrink_to_budget(view: list[BaseMessage], char_cap: int,
                      protected: list[BaseMessage]) -> list[BaseMessage]:
    """追加 note / working 后重算预算；超出就截断最大的消息（只改视图，不动存储）。

    protected（任务锚点、省略说明、工作记忆）先跳过；若普通消息削完仍超硬上限，
    才对 protected 做保头保尾的降级截断，最后连系统提示也让位——预算因此是硬约束，
    不再出现 cap=30k 时 view 203k 的静默超限。
    """
    cap = max(1, int(char_cap))
    total = sum(len(text_of(m)) for m in view)
    if total <= cap:
        return view
    keep_ids = {id(message) for message in protected if message is not None}

    def trim(index: int, head_tail: bool) -> None:
        nonlocal total
        overflow = total - cap
        if overflow <= 0 or index < 0 or index >= len(view):
            return
        message = view[index]
        body = getattr(message, "content", "")
        if not isinstance(body, str) or not body:
            return
        target = len(body) - overflow
        if target >= len(body):
            return
        new_body = _head_tail(body, target) if head_tail else _head_only(body, target)
        if new_body == body:
            return
        view[index] = message.model_copy(update={"content": new_body})
        total -= len(body) - len(new_body)

    # 1) 普通消息优先，最大化保留 protected 记忆
    for index in sorted(range(1, len(view)), key=lambda i: len(text_of(view[i])), reverse=True):
        if id(view[index]) in keep_ids:
            continue
        trim(index, head_tail=False)
        if total <= cap:
            return view

    # 2) protected 仍超预算：显式降级，保头保尾（最新记忆在尾部）
    for index in sorted(range(1, len(view)), key=lambda i: len(text_of(view[i])), reverse=True):
        if id(view[index]) not in keep_ids:
            continue
        trim(index, head_tail=True)
        if total <= cap:
            return view

    # 3) 兜底：系统提示本身超 cap（配置异常）时也不静默超预算
    trim(0, head_tail=True)
    return view


def build_model_messages(state, base_prompt: str, char_cap: int,
                         fold_ratio: float = DEFAULT_FOLD_RATIO,
                         anchor_ratio: float = DEFAULT_ANCHOR_RATIO) -> list[BaseMessage]:
    """构造本次调用的消息视图：只在这里折叠，不修改 state 里的消息。

    fold_ratio 是软阈值：视图总长超过 char_cap * fold_ratio 就开始折叠，
    避免每轮都贴着硬上限反复重写整份 state；_shrink_to_budget 仍按 char_cap 硬收口。
    anchor_ratio 限制首条任务锚点的预算；超出时保留头尾并注明原文在存储中。
    """
    cap = max(1, int(char_cap))
    raw_messages = list(state.get("messages") or [])
    messages = raw_messages
    positions = list(range(len(raw_messages)))

    # 首条 HumanMessage 是 state 里唯一的任务原文（其余是轮末提示与工具结果），
    # 折叠会把它永久移出视图，故先摘出来做锚点，随后重新前置。
    anchor = None
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            anchor = messages.pop(index)
            positions.pop(index)
            break

    view: list[BaseMessage] = [SystemMessage(content=base_prompt)]
    protected: list[BaseMessage] = []
    if anchor is not None:
        anchor_budget = max(1, min(cap, int(cap * _ratio(anchor_ratio, DEFAULT_ANCHOR_RATIO))))
        anchor_text = text_of(anchor)
        if len(anchor_text) > anchor_budget:
            anchor = anchor.model_copy(
                update={"content": _head_tail(anchor_text, anchor_budget, _ANCHOR_MARK)})
        view.append(anchor)
        protected.append(anchor)

    fold_at = max(1, min(cap, int(cap * _ratio(fold_ratio, DEFAULT_FOLD_RATIO))))
    total = len(base_prompt) + sum(len(text_of(m)) for m in messages)
    if anchor is not None:
        total += len(text_of(anchor))

    omitted = 0
    omitted_messages: list[BaseMessage] = []
    omitted_positions: list[int] = []
    while total > fold_at and len(messages) > 8:
        size = _turn_size(messages)
        for message in messages[:size]:
            total -= len(text_of(message))
        omitted_messages.extend(messages[:size])
        omitted_positions.extend(positions[:size])
        del messages[:size]
        del positions[:size]
        omitted += size

    if omitted:
        note = f"[系统] 已省略更早的 {omitted} 条消息（原文仍在存储中，可检索）。"
        digest = _span_digest(omitted_messages, omitted_positions)
        if digest:
            note += f"\n被省略段摘录（引擎抽取）：{digest}"
        summaries = state.get("summaries") or []
        if summaries:
            # 摘要链是模型自述、未经校验，可能与工作记忆冲突，故标注来源
            note += f"\n此前轮次摘要（模型自述/引擎抽取，未经校验）：{_summary_note(summaries)}"
        note_message = HumanMessage(content=note)
        view.append(note_message)
        protected.append(note_message)
    view.extend(messages)

    working = state.get("working") or {}
    key_info = (working.get("key_info") or "").strip()
    if key_info:
        working_message = HumanMessage(content="### [WORKING MEMORY]\n" + key_info)
        view.append(working_message)
        protected.append(working_message)
    return _shrink_to_budget(view, cap, protected)


_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>", re.S | re.I)


def extract_summary(text: str, limit: int = 200, turn: int | None = None,
                    tools: list[str] | None = None) -> str:
    """取 <summary> 内容；给了 turn 就带上轮次与触发工具，便于注入时追溯来源。"""
    match = _SUMMARY_RE.search(text or "")
    if not match:
        return ""
    body = " ".join(match.group(1).split())[:limit]
    if turn is None:
        return body
    used = "+".join([name for name in (tools or []) if name]) or "无工具"
    return f"[第{turn}轮·{used}] {body}"

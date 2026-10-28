"""DeepSeek 专用模型：ChatDeepSeek + tools 场景回传 reasoning_content。

DeepSeek 官方规则：请求携带 tools 时，历史 assistant 的 reasoning_content
必须完整回传，否则 400。ChatDeepSeek 只负责捕获字段，不负责回传，所以这里
补一个请求 payload 钩子。
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_deepseek import ChatDeepSeek


def inject_reasoning_content(payload: dict, messages: list[BaseMessage]) -> dict:
    """把历史 AI message 的 reasoning_content 按顺序写回 assistant payload。"""
    if not payload.get("tools"):
        return payload
    reasoning = (
        (message.additional_kwargs or {}).get("reasoning_content")
        for message in messages
        if isinstance(message, AIMessage)
    )
    for item in payload.get("messages") or []:
        if item.get("role") == "assistant":
            value = next(reasoning, None)
            if value:
                item["reasoning_content"] = value
    return payload


class DeepSeekChatModel(ChatDeepSeek):
    """DeepSeek 接口：保留 ChatDeepSeek 的 reasoning 捕获，并补齐回传。"""

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        messages = input_ if isinstance(input_, list) else []
        if not isinstance(messages, list):
            to_messages = getattr(input_, "to_messages", None)
            messages = to_messages() if callable(to_messages) else []
        return inject_reasoning_content(payload, messages)

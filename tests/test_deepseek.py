"""DeepSeek 请求回传：tools 场景把历史 reasoning_content 写回 assistant。"""
from __future__ import annotations

import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from engine.deepseek import inject_reasoning_content


def _payload():
    return {
        "tools": [{"type": "function", "function": {"name": "x", "parameters": {}}}],
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": []},
            {"role": "tool", "content": "ok", "tool_call_id": "c1"},
        ],
    }


class DeepSeekReplayTests(unittest.TestCase):
    def test_injects_reasoning_for_assistant_when_tools_present(self):
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="", additional_kwargs={"reasoning_content": "think"},
                      tool_calls=[{"name": "x", "args": {}, "id": "c1"}]),
            ToolMessage(content="ok", tool_call_id="c1", name="x"),
        ]
        out = inject_reasoning_content(_payload(), messages)
        self.assertEqual(out["messages"][1]["reasoning_content"], "think")

    def test_keeps_assistant_order(self):
        payload = _payload()
        payload["messages"].append({"role": "assistant", "content": "final"})
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="", additional_kwargs={"reasoning_content": "first"}),
            ToolMessage(content="ok", tool_call_id="c1", name="x"),
            AIMessage(content="final", additional_kwargs={"reasoning_content": "second"}),
        ]
        out = inject_reasoning_content(payload, messages)
        self.assertEqual(out["messages"][1]["reasoning_content"], "first")
        self.assertEqual(out["messages"][3]["reasoning_content"], "second")

    def test_no_tools_does_not_inject(self):
        payload = _payload()
        payload.pop("tools")
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="", additional_kwargs={"reasoning_content": "think"}),
        ]
        out = inject_reasoning_content(payload, messages)
        self.assertNotIn("reasoning_content", out["messages"][1])

    def test_missing_reasoning_leaves_payload_unchanged(self):
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="", additional_kwargs={}),
        ]
        out = inject_reasoning_content(_payload(), messages)
        self.assertNotIn("reasoning_content", out["messages"][1])


if __name__ == "__main__":
    unittest.main()

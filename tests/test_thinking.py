"""thinking 展示：RPC 映射与 checkpoint 历史回放。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from core import session_history
from core.rpc import _event_from_item


class ThinkingHistoryTests(unittest.TestCase):
    def test_rpc_thinking_mapping(self):
        self.assertEqual(
            _event_from_item({"kind": "thinking_delta", "next": "think"}),
            {"event": "thinking", "text": "think"},
        )

    def test_thinking_comes_before_assistant(self):
        class FakeSaver:
            def get_tuple(self, config):
                return SimpleNamespace(checkpoint={"channel_values": {"messages": [
                    HumanMessage(content="hi"),
                    AIMessage(content="answer",
                              additional_kwargs={"reasoning_content": "think"}),
                ]}})

        with patch.object(session_history, "get_saver", return_value=FakeSaver()):
            items = session_history.load_history("thread-1")
        self.assertEqual([item["kind"] for item in items],
                         ["user", "thinking", "assistant"])
        self.assertEqual(items[1]["text"], "think")

    def test_openrouter_reasoning_alias(self):
        class FakeSaver:
            def get_tuple(self, config):
                return SimpleNamespace(checkpoint={"channel_values": {"messages": [
                    AIMessage(content="answer", additional_kwargs={"reasoning": "why"}),
                ]}})

        with patch.object(session_history, "get_saver", return_value=FakeSaver()):
            items = session_history.load_history("thread-2")
        self.assertEqual([item["kind"] for item in items], ["thinking", "assistant"])
        self.assertEqual(items[0]["text"], "why")


if __name__ == "__main__":
    unittest.main()

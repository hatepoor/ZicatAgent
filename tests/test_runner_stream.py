"""流事件回归：token 流与整段 AIMessage 不得重复；工具结果带结构化 payload。"""
from __future__ import annotations

import queue
import unittest
from types import SimpleNamespace

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from engine.runner import _consume


class FakeGraph:
    def __init__(self, chunks):
        self.chunks = chunks
        self.config = None

    def stream(self, inputs, config, **kwargs):
        self.config = config
        yield from self.chunks

    def get_state(self, config):
        return SimpleNamespace(interrupts=[])


class FakeTracker:
    def snapshot(self):
        return {"requests": 1, "input": 10, "output": 5}


class FakeRuntime:
    usage = {}


class ConsumeTests(unittest.TestCase):
    def run_consume(self, chunks):
        graph = FakeGraph(chunks)
        runtime = FakeRuntime()
        runtime.agent = SimpleNamespace(stop_sig=False, task_dir=None)
        q = queue.Queue()
        _consume(graph, {"messages": []}, {"configurable": {}}, runtime, FakeTracker(),
                 q, "test", lambda _v: None)
        events = []
        while not q.empty():
            events.append(q.get())
        return events

    def test_token_stream_not_duplicated_by_full_message(self):
        chunks = [
            ("messages", (AIMessageChunk(content="hello"), {})),
            ("updates", {"agent": {"messages": [AIMessage(content="hello")]}}),
        ]
        events = self.run_consume(chunks)
        self.assertEqual(sum(1 for e in events if e.get("next") == "hello"), 1)
        self.assertFalse(any(e.get("kind") == "assistant" for e in events))

    def test_delta_events_are_batched(self):
        text = "x" * 200
        chunks = [("messages", (AIMessageChunk(content=ch), {})) for ch in text]
        chunks.append(("updates", {"agent": {"messages": [AIMessage(content=text)]}}))
        events = self.run_consume(chunks)
        deltas = [e for e in events if e.get("kind") == "delta_token"]
        self.assertLessEqual(len(deltas), 10, len(deltas))
        self.assertEqual("".join(e.get("next", "") for e in deltas), text)
        self.assertFalse(any(e.get("kind") == "assistant" for e in events))

    def test_batched_tokens_flush_before_tool_call(self):
        text = "y" * 120
        chunks = [("messages", (AIMessageChunk(content=ch), {})) for ch in text]
        chunks.append(("updates", {"agent": {"messages": [AIMessage(
            content=text,
            tool_calls=[{"name": "code_run", "args": {}, "id": "c1"}],
        )]}}))
        events = self.run_consume(chunks)
        kinds = [e.get("kind") for e in events]
        self.assertIn("delta_token", kinds)
        self.assertIn("tool_call", kinds)
        self.assertLess(kinds.index("delta_token"), kinds.index("tool_call"))
        self.assertEqual("".join(e.get("next", "") for e in events
                                 if e.get("kind") == "delta_token"), text)

    def test_thinking_stream_not_duplicated_by_full_message(self):
        chunks = [
            ("messages", (AIMessageChunk(
                content="", additional_kwargs={"reasoning_content": "think"}), {})),
            ("messages", (AIMessageChunk(content="answer"), {})),
            ("updates", {"agent": {"messages": [AIMessage(
                content="answer", additional_kwargs={"reasoning_content": "think"})]}}),
        ]
        events = self.run_consume(chunks)
        thinking = [e for e in events if e.get("kind") == "thinking_delta"]
        self.assertEqual("".join(e.get("next", "") for e in thinking), "think")
        self.assertEqual(sum(1 for e in events if e.get("next") == "answer"), 1)
        self.assertFalse(any(e.get("kind") == "assistant" for e in events))

    def test_thinking_full_message_fallback(self):
        chunks = [
            ("updates", {"agent": {"messages": [AIMessage(
                content="answer", additional_kwargs={"reasoning_content": "think"})]}}),
        ]
        events = self.run_consume(chunks)
        kinds = [e.get("kind") for e in events]
        self.assertIn("thinking_delta", kinds)
        self.assertIn("assistant", kinds)
        self.assertLess(kinds.index("thinking_delta"), kinds.index("assistant"))
        thinking = "".join(e.get("next", "") for e in events
                           if e.get("kind") == "thinking_delta")
        self.assertEqual(thinking, "think")

    def test_thinking_flushes_before_tool_call(self):
        chunks = [
            ("messages", (AIMessageChunk(
                content="", additional_kwargs={"reasoning_content": "think"}), {})),
            ("updates", {"agent": {"messages": [AIMessage(
                content="", additional_kwargs={"reasoning_content": "think"},
                tool_calls=[{"name": "code_run", "args": {}, "id": "c1"}])]}}),
        ]
        events = self.run_consume(chunks)
        kinds = [e.get("kind") for e in events]
        self.assertIn("thinking_delta", kinds)
        self.assertIn("tool_call", kinds)
        self.assertLess(kinds.index("thinking_delta"), kinds.index("tool_call"))

    def test_full_message_emitted_when_no_token_stream(self):
        chunks = [
            ("updates", {"agent": {"messages": [AIMessage(content="fallback")]}}),
        ]
        events = self.run_consume(chunks)
        self.assertTrue(any(e.get("kind") == "assistant" and e.get("next") == "fallback"
                            for e in events))

    def test_tool_result_has_structured_payload(self):
        msg = ToolMessage(content='{"status":"success","stdout":"ok","exit_code":0}',
                          tool_call_id="t1", name="code_run")
        chunks = [("updates", {"tools": {"messages": [msg]}})]
        events = self.run_consume(chunks)
        result = next(e for e in events if e.get("kind") == "tool_result")
        self.assertEqual(result["payload"]["status"], "success")
        self.assertEqual(result["payload"]["stdout"], "ok")


if __name__ == "__main__":
    unittest.main()

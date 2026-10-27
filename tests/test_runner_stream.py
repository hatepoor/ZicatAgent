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

"""引擎单元测试：追加式状态、中断恢复、预算、记忆工具、物化与导出。"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from engine.graph import build_graph
from engine.tools import load_tools_schema
from memstore.tools import MemoryTools


def _tmp_path(name):
    d = tempfile.mkdtemp(prefix="ga_test_")
    return os.path.join(d, name)


def _clean(path):
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except OSError:
            pass


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.views = []
        self.index = 0

    def invoke(self, messages):
        self.views.append(messages)
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return response


class FakeRuntime:
    tools_schema = []
    base_prompt = "sys"
    last_should_exit = False
    rewind = None

    def __init__(self):
        self.calls = []
        self.usage = {"input": 0, "output": 0, "requests": 0}

    def run_tool(self, name, args, ai_message):
        self.calls.append((name, args))
        return "tool-ok"

    def add_usage(self, usage_metadata):
        return None


def _initial(text="hi"):
    return {"messages": [HumanMessage(content=text)], "working": {}, "summaries": [],
            "turn": 0, "exit_reason": None, "meta": {}}


class GraphTests(unittest.TestCase):
    def test_append_only_messages(self):
        model = FakeModel([
            AIMessage(content="", tool_calls=[{"name": "probe", "args": {"x": 1}, "id": "c1"}]),
            AIMessage(content="done"),
        ])
        runtime = FakeRuntime()
        graph = build_graph(runtime, MemorySaver(), model=model)
        config = {"configurable": {"thread_id": "t-append"}}
        graph.invoke(_initial(), config)

        state = graph.get_state(config).values
        messages = state["messages"]
        self.assertEqual([type(m).__name__ for m in messages],
                         ["HumanMessage", "AIMessage", "ToolMessage", "AIMessage"])
        self.assertEqual(messages[0].content, "hi")
        self.assertEqual(messages[1].tool_calls[0]["name"], "probe")
        self.assertEqual(messages[2].content, "tool-ok")
        self.assertEqual(messages[3].content, "done")
        self.assertEqual(runtime.calls, [("probe", {"x": 1})])
        self.assertEqual(state["turn"], 2)

    def test_interrupt_and_resume(self):
        model = FakeModel([
            AIMessage(content="", tool_calls=[{
                "name": "ask_user",
                "args": {"question": "选哪个？", "candidates": ["1", "2"]},
                "id": "a1",
            }]),
            AIMessage(content="answered"),
        ])
        runtime = FakeRuntime()
        graph = build_graph(runtime, MemorySaver(), model=model)
        config = {"configurable": {"thread_id": "t-interrupt"}}
        graph.invoke(_initial(), config)

        snapshot = graph.get_state(config)
        self.assertTrue(getattr(snapshot, "interrupts", ()), "应该停在 interrupt")
        self.assertEqual(snapshot.interrupts[0].value["question"], "选哪个？")

        graph.invoke(Command(resume="2"), config)
        messages = graph.get_state(config).values["messages"]
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        self.assertEqual(len(tool_msgs), 1)
        self.assertIn("USER_ANSWER", tool_msgs[0].content)
        self.assertIn('"2"', tool_msgs[0].content.replace("'", '"'))
        self.assertEqual(messages[-1].content, "answered")

    def test_mixed_ask_user_and_tool_runs_sibling_once(self):
        model = FakeModel([
            AIMessage(content="", tool_calls=[
                {"name": "probe", "args": {"n": 1}, "id": "p1"},
                {"name": "ask_user", "args": {"question": "确认？"}, "id": "a1"},
            ]),
            AIMessage(content="ok"),
        ])
        runtime = FakeRuntime()
        graph = build_graph(runtime, MemorySaver(), model=model)
        config = {"configurable": {"thread_id": "t-mixed"}}
        graph.invoke(_initial(), config)
        # interrupt 发生在任何工具执行之前
        self.assertEqual(runtime.calls, [])
        graph.invoke(Command(resume="yes"), config)
        self.assertEqual(runtime.calls, [("probe", {"n": 1})])
        tool_msgs = [m for m in graph.get_state(config).values["messages"]
                     if isinstance(m, ToolMessage)]
        self.assertEqual(len(tool_msgs), 2)

    def test_budget_enforced_before_tools(self):
        model = FakeModel([
            AIMessage(content="", tool_calls=[{"name": "probe", "args": {}, "id": "c1"}]),
        ])
        runtime = FakeRuntime()
        graph = build_graph(runtime, MemorySaver(), model=model, max_turns=1)
        config = {"configurable": {"thread_id": "t-budget"}}
        graph.invoke(_initial(), config)
        state = graph.get_state(config).values
        self.assertEqual(state["exit_reason"], "MAX_TURNS")
        self.assertEqual(runtime.calls, [])          # 超预算不再执行工具
        self.assertIn("最大轮数", state["messages"][-1].content)

    def test_no_tool_call_finishes(self):
        model = FakeModel([AIMessage(content="直接回答")])
        runtime = FakeRuntime()
        graph = build_graph(runtime, MemorySaver(), model=model)
        config = {"configurable": {"thread_id": "t-finish"}}
        graph.invoke(_initial("问题"), config)
        state = graph.get_state(config).values
        self.assertEqual(state["exit_reason"], "DONE")
        self.assertEqual(state["messages"][-1].content, "直接回答")

    def test_sqlite_checkpoint_shared_thread(self):
        from engine.checkpointer import get_saver
        path = _tmp_path("shared.db")
        _clean(path)
        saver = get_saver(path)
        graph1 = build_graph(FakeRuntime(), saver, model=FakeModel([AIMessage(content="first")]))
        config = {"configurable": {"thread_id": "t-shared"}}
        graph1.invoke(_initial("one"), config)

        graph2 = build_graph(FakeRuntime(), saver, model=FakeModel([AIMessage(content="second")]))
        graph2.invoke({"messages": [HumanMessage(content="two")]}, config)
        messages = graph2.get_state(config).values["messages"]
        self.assertEqual([m.content for m in messages if isinstance(m, HumanMessage)], ["one", "two"])
        self.assertEqual(messages[-1].content, "second")
        _clean(path)


class RuntimeTests(unittest.TestCase):
    def test_memory_write_blocked(self):
        from engine.tools import ToolRuntime

        class Handler:
            cwd = os.getcwd()

            def dispatch(self, *args, **kwargs):
                raise AssertionError("不应执行 file_write")

        runtime = ToolRuntime(agent=None, handler=Handler())
        out = runtime.run_tool("file_write", {"path": "memory/evil.md", "content": "x"},
                               AIMessage(content=""))
        self.assertIn("memory_write", out)

    def test_handler_tool_result(self):
        from agent_types import StepOutcome
        from engine.tools import ToolRuntime

        class Handler:
            cwd = os.getcwd()

            def dispatch(self, name, args, response, index=0, tool_num=1):
                yield "[Action] fake\n"
                return StepOutcome({"result": "ok"}, next_prompt="")

        runtime = ToolRuntime(agent=None, handler=Handler())
        out = runtime.run_tool("file_read", {"path": "x"}, AIMessage(content=""))
        self.assertIn('"result": "ok"', out)

    def test_hooks_trim_and_working_memory(self):
        from engine.hooks import build_model_messages, extract_summary

        messages = [HumanMessage(content="x" * 400) for _ in range(20)]
        state = {"messages": messages, "working": {"key_info": "记住这个"}}
        view = build_model_messages(state, base_prompt="sys", char_cap=2000)
        self.assertLess(len(view), len(messages) + 3)
        self.assertIn("[WORKING MEMORY]", view[-1].content)
        self.assertEqual(len(state["messages"]), 20)  # 原状态未被修改
        self.assertEqual(extract_summary("前文<summary>要点</summary>后文"), "要点")
        self.assertEqual(extract_summary("没有"), "")


class MemoryToolsTests(unittest.TestCase):
    def setUp(self):
        self.path = _tmp_path("memory.db")
        _clean(self.path)
        from memstore.db import Database
        Database(self.path).close()
        self.box = MemoryTools(self.path)

    def test_write_read_patch_archive(self):
        out = json.loads(self.box.dispatch("memory_write", {
            "name": "demo_sop", "layer": "L3", "kind": "sop",
            "title": "demo", "summary": "演示", "body": "第一版",
        }))
        self.assertTrue(out.get("ok"), out)

        read = json.loads(self.box.dispatch("memory_read", {"name": "demo_sop"}))
        self.assertEqual(read["body"], "第一版")
        self.assertEqual(read["version"], 1)

        patched = json.loads(self.box.dispatch("memory_patch", {"name": "demo_sop", "body": "第二版"}))
        self.assertTrue(patched.get("ok"), patched)
        read2 = json.loads(self.box.dispatch("memory_read", {"name": "demo_sop"}))
        self.assertEqual(read2["body"], "第二版")
        self.assertEqual(read2["version"], 2)

        hits = json.loads(self.box.dispatch("memory_search", {"query": "演示"}))
        self.assertTrue(hits, hits)

        index = self.box.dispatch("memory_index", {})
        self.assertIn("demo_sop", index)

        archived = json.loads(self.box.dispatch("memory_archive", {"name": "demo_sop"}))
        self.assertTrue(archived.get("ok"), archived)
        self.assertNotIn("demo_sop —", self.box.dispatch("memory_index", {}))

    def test_link_tool(self):
        self.box.dispatch("memory_write", {"name": "a", "layer": "L2", "kind": "fact",
                                            "summary": "事实a", "body": "x"})
        self.box.dispatch("memory_write", {"name": "b", "layer": "L3", "kind": "sop",
                                            "summary": "技能b", "body": "y"})
        out = json.loads(self.box.dispatch("memory_link", {"from": "a", "to": "b", "rel": "related"}))
        self.assertTrue(out.get("ok"), out)

    def test_versions_append_only(self):
        self.box.dispatch("memory_write", {"name": "v1", "layer": "L2", "kind": "fact",
                                            "summary": "版本测试", "body": "a"})
        self.box.dispatch("memory_patch", {"name": "v1", "body": "b"})
        conn = sqlite3.connect(self.path)
        count = conn.execute("select count(*) from memory_versions where item_id = "
                             "(select id from memory_items where name='v1')").fetchone()[0]
        self.assertGreaterEqual(count, 2)
        with self.assertRaises(sqlite3.Error):
            conn.execute("update memory_versions set body='x'")
        conn.close()

    def test_schema_count(self):
        # FIX-M1 后 17；文件工具扩展 +3（grep/glob/file_apply_patch）后 20
        self.assertEqual(len(load_tools_schema()), 20)


class MaterializeTests(unittest.TestCase):
    def test_materialize_hash_path(self):
        from memstore.db import Database
        from memstore.materialize import materialize
        from memstore.repository import MemoryStore

        path = _tmp_path("mat.db")
        _clean(path)
        db = Database(path)
        store = MemoryStore(db)
        item = store.create(name="skill_a", layer="L3", kind="script", body="print(1)\n")
        out1 = materialize(store, item.id, os.path.dirname(path))
        self.assertEqual(out1.read_text(encoding="utf-8"), "print(1)\n")
        self.assertIn("skill_a-", out1.name)

        store.patch(item.id, body="print(2)\n")
        out2 = materialize(store, item.id, os.path.dirname(path))
        self.assertNotEqual(out1, out2)
        db.close()


class ExportTests(unittest.TestCase):
    def test_export_deterministic(self):
        from memstore.db import Database
        from memstore.export import export
        from memstore.repository import MemoryStore

        path = _tmp_path("export.db")
        _clean(path)
        db = Database(path)
        store = MemoryStore(db)
        store.create(name="fact_a", layer="L2", kind="fact", body="A", summary="a")
        store.create(name="sop_b", layer="L3", kind="sop", body="B", summary="b")
        out_dir = tempfile.mkdtemp(prefix="ga_export_")
        # FIX-M1：L3 不再导出（kb/scripts 是 L3 的 git 代表），镜像只含 L1/L2
        self.assertEqual(export(store, out_dir), 1)
        self.assertFalse(os.path.exists(os.path.join(out_dir, "L3")))
        first = {}
        for root, _dirs, files in os.walk(out_dir):
            for name in files:
                full = os.path.join(root, name)
                with open(full, "rb") as fh:
                    first[full] = fh.read()
        export(store, out_dir)
        for full, content in first.items():
            with open(full, "rb") as fh:
                self.assertEqual(fh.read(), content, full)
        db.close()


class RewindTests(unittest.TestCase):
    def test_file_rewind_roundtrip(self):
        from engine.rewind import TaskRewind

        temp_dir = tempfile.mkdtemp(prefix="ga_rw_tmp_")
        cwd = tempfile.mkdtemp(prefix="ga_rw_cwd_")
        target = os.path.join(cwd, "a.txt")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("v1")
        rw = TaskRewind("t-rewind", cwd, temp_dir)
        rw.track(target)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("v2")
        node = rw.commit(1)
        self.assertTrue(node)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("v3")
        changed = rw.apply(node)
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "v2")
        self.assertTrue(any(p.endswith("a.txt") for p, _ in changed))

    def test_checkpoint_listing(self):
        from engine.checkpointer import get_saver, list_checkpoints

        path = _tmp_path("list_ck.db")
        _clean(path)
        graph = build_graph(FakeRuntime(), get_saver(path),
                            model=FakeModel([AIMessage(content="ok")]))
        graph.invoke(_initial(), {"configurable": {"thread_id": "t-list"}})
        rows = list_checkpoints(path, "t-list", 10)
        self.assertTrue(rows)
        self.assertEqual(len(rows), len(set(rows)))
        _clean(path)


class BackupTests(unittest.TestCase):
    def test_backup_and_skip(self):
        from memstore.backup import run_backup
        from memstore.db import Database

        db = _tmp_path("bk.db")
        _clean(db)
        Database(db).close()
        out = tempfile.mkdtemp(prefix="ga_bk_")
        first = run_backup(db, db, out)
        self.assertEqual(len(first["created"]), 2)
        second = run_backup(db, db, out)
        self.assertEqual(second["created"], [])
        self.assertEqual(len(second["skipped"]), 2)


class SyncTests(unittest.TestCase):
    def test_sync_updates_changed_body(self):
        from memstore.db import Database
        from memstore.repository import MemoryStore
        from memstore.sync import sync

        memory_dir = tempfile.mkdtemp(prefix="ga_mem_")
        with open(os.path.join(memory_dir, "demo.md"), "w", encoding="utf-8") as fh:
            fh.write("# demo\n\n第二版\n")
        db = _tmp_path("sync.db")
        _clean(db)
        Database(db).close()
        store = MemoryStore(Database(db, init=False))
        store.create(name="demo", layer="L3", kind="sop", body="第一版")
        manifest = os.path.join(memory_dir, "backup", "import_manifest.json")
        os.makedirs(os.path.dirname(manifest), exist_ok=True)
        with open(manifest, "w", encoding="utf-8") as fh:
            json.dump({"entries": [{"name": "demo", "source_sha256": "x",
                                    "body_sha256": "y", "layer": "L3", "kind": "sop"}]}, fh)
        result = sync(db, memory_dir, manifest)
        self.assertEqual(result["updated"], 1)
        item = MemoryStore(Database(db, init=False)).get("demo")
        self.assertIn("第二版", item.body)
        self.assertEqual(MemoryStore(Database(db, init=False)).version_count(item.id), 2)


class CrossProcessTests(unittest.TestCase):
    def test_interrupt_survives_new_graph_instance(self):
        from engine.checkpointer import get_saver

        path = _tmp_path("cross.db")
        _clean(path)
        config = {"configurable": {"thread_id": "t-cross"}}
        model1 = FakeModel([AIMessage(content="", tool_calls=[{
            "name": "ask_user", "args": {"question": "继续？"}, "id": "a1"}])])
        graph1 = build_graph(FakeRuntime(), get_saver(path), model=model1)
        graph1.invoke(_initial(), config)
        self.assertTrue(graph1.get_state(config).interrupts)

        # 模拟重启：新 graph 实例，同一个 sqlite 检查点
        model2 = FakeModel([AIMessage(content="resumed-ok")])
        graph2 = build_graph(FakeRuntime(), get_saver(path), model=model2)
        self.assertTrue(graph2.get_state(config).interrupts)
        graph2.invoke(Command(resume="继续"), config)
        messages = graph2.get_state(config).values["messages"]
        self.assertEqual(messages[-1].content, "resumed-ok")
        self.assertIn("USER_ANSWER", [m.content for m in messages if isinstance(m, ToolMessage)][0])
        _clean(path)


class LongRunTests(unittest.TestCase):
    def test_thirty_round_append_only(self):
        responses = [AIMessage(content="", tool_calls=[{"name": "probe", "args": {"i": i},
                                                        "id": f"c{i}"}]) for i in range(30)]
        responses.append(AIMessage(content="done"))
        model = FakeModel(responses)
        runtime = FakeRuntime()
        graph = build_graph(runtime, MemorySaver(), model=model, max_turns=60)
        config = {"configurable": {"thread_id": "t-30"}}
        graph.invoke(_initial(), config)
        messages = graph.get_state(config).values["messages"]
        self.assertEqual(len(messages), 62)          # human + 30*(AI+tool) + final AI
        self.assertEqual(messages[0].content, "hi")  # 头部没有被裁掉
        self.assertEqual(len(runtime.calls), 30)
        # AI 与 Tool 严格交替，没有消息被替换
        for idx in range(1, 61, 2):
            self.assertIsInstance(messages[idx], AIMessage)
            self.assertIsInstance(messages[idx + 1], ToolMessage)
            self.assertEqual(messages[idx + 1].tool_call_id, messages[idx].tool_calls[0]["id"])

    def test_append_only_across_invocations(self):
        from engine.checkpointer import get_saver
        import hashlib

        path = _tmp_path("append.db")
        _clean(path)
        saver = get_saver(path)
        config = {"configurable": {"thread_id": "t-append2"}}
        model1 = FakeModel([
            AIMessage(content="", tool_calls=[{"name": "probe", "args": {}, "id": "a1"}]),
            AIMessage(content="first-done"),
        ])
        graph1 = build_graph(FakeRuntime(), saver, model=model1)
        graph1.invoke(_initial("one"), config)

        def digest(message):
            payload = f"{type(message).__name__}|{getattr(message, 'content', '')}|{getattr(message, 'tool_call_id', '')}"
            return hashlib.sha256(payload.encode()).hexdigest()

        before = [digest(m) for m in graph1.get_state(config).values["messages"]]
        model2 = FakeModel([AIMessage(content="second-done")])
        graph2 = build_graph(FakeRuntime(), saver, model=model2)
        graph2.invoke({"messages": [HumanMessage(content="two")]}, config)
        after_messages = graph2.get_state(config).values["messages"]
        after = [digest(m) for m in after_messages]
        self.assertEqual(after[:len(before)], before)   # 旧消息逐条未变
        self.assertGreater(len(after), len(before))
        humans = [m.content for m in after_messages if isinstance(m, HumanMessage)]
        self.assertEqual(humans, ["one", "two"])
        _clean(path)


class ParityTests(unittest.TestCase):
    def test_tool_parity_legacy_vs_graph_adapter(self):
        from types import SimpleNamespace
        from agent_types import exhaust
        from engine.tools import ToolRuntime
        from zicat import ZicatAgentHandler

        class Parent:
            verbose = False

            def get_ctx_multiplier(self):
                return 1.0

        cwd = tempfile.mkdtemp(prefix="ga_parity_")
        args = {"path": "parity.txt", "content": "hello-parity"}

        legacy_handler = ZicatAgentHandler(Parent(), [], cwd)
        legacy_outcome = exhaust(legacy_handler.dispatch("file_write", dict(args),
                                                          SimpleNamespace(content="")))
        legacy_file = os.path.join(cwd, "parity.txt")
        with open(legacy_file, encoding="utf-8") as fh:
            legacy_content = fh.read()
        os.remove(legacy_file)

        graph_handler = ZicatAgentHandler(Parent(), [], cwd)
        runtime = ToolRuntime(agent=None, handler=graph_handler)
        graph_out = runtime.run_tool("file_write", dict(args), AIMessage(content=""))
        with open(os.path.join(cwd, "parity.txt"), encoding="utf-8") as fh:
            graph_content = fh.read()

        self.assertEqual(legacy_content, "hello-parity")
        self.assertEqual(graph_content, legacy_content)
        self.assertEqual(json.loads(graph_out), legacy_outcome.data)


class MemoryP1Tests(unittest.TestCase):
    """memory P1 三件：2 字中文 FTS、L1 冷条目折叠、memory_write 前置校验。"""

    def setUp(self):
        self.path = _tmp_path("memory_p1.db")
        _clean(self.path)
        from memstore.db import Database
        Database(self.path).close()
        self.box = MemoryTools(self.path)

    def _write(self, name, summary, body, kind="sop"):
        return json.loads(self.box.dispatch("memory_write", {
            "name": name, "layer": "L3", "kind": kind,
            "title": name, "summary": summary, "body": body,
        }))

    def test_fts_chinese_two_char(self):
        self.assertTrue(self._write("web_sop", "浏览器自动化", "浏览器扩展操作与排障流程")["ok"])
        self.assertTrue(self._write("deploy_sop", "部署流程", "服务部署与回滚步骤")["ok"])
        store = self.box.store
        hits = store.search("浏览器")
        self.assertTrue(hits and hits[0].name == "web_sop")   # 2 字中文走 FTS 命中
        self.assertEqual(store.search("不存在词xyzq")[0].name
                         if store.search("不存在词xyzq") else None, None)

    def test_render_l1_folds_cold_l3(self):
        for i in range(24):
            self.assertTrue(self._write(f"skill_{i:02d}", f"技能{i}的摘要", f"技能{i}正文")["ok"])
        store = self.box.store
        l1 = store.render_l1()
        self.assertEqual(l1.count("## 索引"), 1)              # 无重复标题块
        self.assertIn("其他 4 条冷门技能", l1)                  # 超出 keep=20 折叠
        self.assertIn("skill_00 —", l1)                       # 头部热条目保留摘要
        self.assertIn("skill_23", l1)                         # 冷条目名字仍在（存在性编码）
        self.assertLessEqual(len(l1), 2000)

    def test_memory_write_guards(self):
        self.assertTrue(self._write("demo", "摘要", "正文")["ok"])
        dup = json.loads(self.box.dispatch("memory_write", {
            "name": "demo", "layer": "L3", "kind": "sop",
            "title": "t", "summary": "s", "body": "b",
        }))
        self.assertIn("memory_patch", dup.get("error", ""))   # 同名拦截并指引 patch
        no_sum = json.loads(self.box.dispatch("memory_write", {
            "name": "fresh", "layer": "L3", "kind": "sop",
            "title": "t", "body": "b",
        }))
        self.assertIn("summary", no_sum.get("error", ""))     # summary 必填
        self.assertTrue(self._write("fresh2", "有摘要", "正文")["ok"])  # 正常路径不受影响

    def test_memory_patch_conflict_hint(self):
        """P2：patch 内容与既有条目相似时附 related 提醒；不相似时不打扰。"""
        self.assertTrue(self._write("browser_sop", "浏览器自动化要点", "浏览器扩展注入与事件派发流程")["ok"])
        self.assertTrue(self._write("deploy_sop", "部署流程", "服务部署与回滚步骤")["ok"])
        hit = json.loads(self.box.dispatch("memory_patch", {
            "name": "deploy_sop", "body": "浏览器扩展注入与事件派发流程（修订版）"}))
        self.assertTrue(hit.get("ok"))
        self.assertIn("browser_sop", hit.get("related", []))       # 相似条目被提醒
        quiet = json.loads(self.box.dispatch("memory_patch", {
            "name": "deploy_sop", "body": "完全无关的新内容：量子计算基础"}))
        self.assertTrue(quiet.get("ok"))
        self.assertNotIn("related", quiet)                          # 不相似不打扰
        self.assertIn("browser_sop", [i.name for i in self.box.store.search("浏览器")])  # 自身不误报（探针排除 args.name）


class SandboxTests(unittest.TestCase):
    """task1 沙箱：静态扫描双阶段 + 审计钩子护栏（真实子进程执行）。"""

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _handler(self):
        from zicat import ZicatAgentHandler

        class Parent:
            verbose = False

            def get_ctx_multiplier(self):
                return 1.0

        return ZicatAgentHandler(Parent(), [], os.path.join(self.ROOT, "temp"))

    def _run(self, code, **extra):
        from types import SimpleNamespace
        from agent_types import exhaust
        h = self._handler()
        outcome = exhaust(h.dispatch("sandbox_run", {"code": code, **extra},
                                     SimpleNamespace(content="")))
        data = outcome.data if hasattr(outcome, "data") else outcome
        if isinstance(data, str):
            return {"status": "error", "raw": data}
        return data

    def test_scan_two_phase(self):
        from tools.code import sandbox_scan
        self.assertIn("subprocess", sandbox_scan("import subprocess", network=False))
        self.assertEqual(sandbox_scan("import socket", network=True), [])   # 放行后网络类不计
        r = self._run("import subprocess\nprint(1)")
        self.assertEqual(r.get("status"), "confirm_required")
        r2 = self._run("import subprocess; subprocess.run(['echo','x'])", confirmed=True)
        self.assertEqual(r2.get("status"), "error")  # 确认后执行，但钩子在子进程内拒绝

    def test_compliant_compute_passes(self):
        r = self._run("print(21 * 2)")
        self.assertEqual(r.get("status"), "success", r)
        self.assertIn("42", r.get("stdout", ""))

    def test_hooks_block_danger(self):
        import os
        outside = os.path.join(self.ROOT, "temp", "outside_probe.txt")
        cases = [
            ("open('../..').close(); open(r'%s').read()" % os.path.join(self.ROOT, "zicat.py"), "repo_read"),
            ("import os; os.remove(r'%s')" % outside, "remove_out"),   # 绝对路径指向沙箱外
            ("open(r'%s').read()" % os.path.join(self.ROOT, ".gitignore"), "root_read"),
        ]
        for code, name in cases:
            r = self._run(code)
            self.assertEqual(r.get("status"), "error", f"{name}: {r}")
            self.assertIn("[sandbox]", r.get("stdout", ""), name)

    def test_sandbox_write_allowed(self):
        r = self._run("open('probe.txt','w').write('ok'); print(open('probe.txt').read())")
        self.assertEqual(r.get("status"), "success", r)

    def test_network_gate(self):
        # 静态层：未确认时拦在 confirm_required（双阶段第一阶段）
        r = self._run("import socket; socket.getaddrinfo('localhost', 80)")
        self.assertEqual(r.get("status"), "confirm_required")
        # 钩子层：confirmed 放行静态扫描后，network=false 仍被运行时拦截
        r2 = self._run("import socket; socket.getaddrinfo('localhost', 80)", confirmed=True)
        self.assertEqual(r2.get("status"), "error", r2)
        self.assertIn("[sandbox]", r2.get("stdout", ""))


class SessionSplitTests(unittest.TestCase):
    """task9 FIX-S：会话注册表（标题查重/前缀查找/删除）与 checkpoint 库分离。"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="ga_sess_")
        self.db = os.path.join(self.tmp, "graph.db")   # 测试专用库，不污染全局注册表
        self.ws_root = os.path.join(self.tmp, "ws")
        os.makedirs(self.ws_root, exist_ok=True)

    def test_register_title_and_dedup(self):
        from core import sessions
        ws1 = sessions.register("cli-aaa111", self.ws_root, title="调研27年秋招岗位", db_file=self.db)
        self.assertTrue(os.path.basename(ws1).startswith("调研27年秋招"))
        ws2 = sessions.register("cli-bbb222", self.ws_root, title="调研27年秋招岗位", db_file=self.db)
        self.assertTrue(os.path.basename(ws2).startswith("调研27年秋招岗位_2"))
        rec, cands = sessions.find("调研27年秋招", db_file=self.db)   # 前缀查询
        self.assertIsNone(rec)                                # 多命中 → 返回候选
        self.assertEqual(len(cands), 2)
        rec, cands = sessions.find("调研27年秋招岗位_2", db_file=self.db)
        self.assertEqual(rec[0], "cli-bbb222")                # 精确命中

    def test_workspace_of_fallback(self):
        from core import sessions
        ws = sessions.workspace_of("cli-ccc333", self.ws_root, db_file=self.db)
        self.assertTrue(os.path.isdir(ws))
        self.assertEqual(sessions.workspace_of("cli-ccc333", self.ws_root, db_file=self.db), ws)

    def test_delete_clears_meta(self):
        from core import sessions
        sessions.register("cli-ddd444", self.ws_root, title="要删的会话", db_file=self.db)
        self.assertTrue(sessions.delete("cli-ddd444", db_file=self.db))
        self.assertFalse(sessions.delete("cli-ddd444", db_file=self.db))
        self.assertEqual([x for x in sessions.list_sessions(db_file=self.db)
                          if x["thread_id"] == "cli-ddd444"], [])

    def test_sessions_db_separated_from_temp(self):
        from core import sessions
        from engine.settings import SESSION_DIR
        self.assertIn("session", str(SESSION_DIR))
        self.assertTrue(sessions.db_path().startswith(str(SESSION_DIR)))


class ToolsAssemblyTests(unittest.TestCase):
    """FIX-T：schema 接口与 tools.registry 实现的装配完整性 + dispatch smoke。"""

    def test_schema_registry_parity(self):
        """schema 宣传的每个工具都必须在 registry 有实现（防 /cost 式宣传未实现）。"""
        import json
        from tools.registry import registered_names
        schema = json.load(open("assets/tools_schema.json", encoding="utf-8"))
        schema_names = {t["function"]["name"] for t in schema}
        registry = set(registered_names())
        missing = schema_names - registry
        self.assertEqual(missing, set())   # registry 缺失
        extra = registry - schema_names - {"no_tool"}  # no_tool 是引擎内部工具，不在 schema
        self.assertEqual(extra, set())

    def test_dispatch_smoke_happy_path(self):
        """逐类工具的 dispatch smoke：真实 ctx 跑 happy path。"""
        import tempfile
        from types import SimpleNamespace
        from agent_types import exhaust
        from tools.context import ToolContext
        from tools.registry import dispatch
        from zicat import ZicatAgentHandler
        from unittest import mock
        from memstore import tools as mem_tools

        tmp_db = os.path.join(tempfile.mkdtemp(prefix="ga_asm_"), "memory.db")
        from memstore.db import Database
        Database(tmp_db).close()

        class Parent:
            verbose = False

            def get_ctx_multiplier(self):
                return 1.0

        h = ZicatAgentHandler(Parent(), [], os.path.dirname(tmp_db))
        ctx = h.ctx
        # memory_write 的 smoke 走临时库，不污染全局 memory.db
        _mt_orig = mem_tools.MemoryTools
        mem_tools.MemoryTools = lambda: _mt_orig(tmp_db)
        import tools.memory as _tmem
        _tmem._MT = None                      # 清 bridge 的全局缓存，让 mock 生效

        # code_run（generator）
        out = exhaust(dispatch(ctx, "code_run", {"code": "print('smoke-code')"},
                               SimpleNamespace(content="")))
        self.assertIn("smoke-code", str(out.data))

        # file_write + file_read（generator）
        out = exhaust(dispatch(ctx, "file_write",
                               {"path": "asm.txt", "content": "asm-body"},
                               SimpleNamespace(content="")))
        self.assertEqual(out.data.get("status"), "success")
        out = exhaust(dispatch(ctx, "file_read", {"path": "asm.txt"},
                               SimpleNamespace(content="")))
        self.assertIn("asm-body", str(out.data))

        # memory_write（非 generator 工具；registry.dispatch 仍是生成器，需 exhaust）
        import uuid
        out = exhaust(dispatch(ctx, "memory_write",
                               {"name": f"asm_sop_{uuid.uuid4().hex[:6]}", "layer": "L3",
                                "kind": "sop", "summary": "装配冒烟", "body": "b"},
                               SimpleNamespace(content="")))
        self.assertIn('"ok"', str(out.data))

        # update_working_checkpoint（generator）
        out = exhaust(dispatch(ctx, "update_working_checkpoint",
                               {"key_info": "smoke"}, SimpleNamespace(content="")))
        self.assertIn("working key_info updated", str(out.data))

    def test_unknown_tool_fallback(self):
        from types import SimpleNamespace
        from agent_types import exhaust
        from tools.context import ToolContext
        from tools.registry import dispatch
        from zicat import ZicatAgentHandler

        h = ZicatAgentHandler(type("P", (), {"verbose": False,
                                             "get_ctx_multiplier": lambda s: 1.0})(), [], "temp")
        out = exhaust(dispatch(h.ctx, "no_such_tool", {}, SimpleNamespace(content="")))
        self.assertIn("未知工具", out.next_prompt)   # 兜底走 next_prompt，data 为 None


class LegacyMemoryGuardTests(unittest.TestCase):
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _handler(self, cwd):
        from zicat import ZicatAgentHandler

        class Parent:
            verbose = False

            def get_ctx_multiplier(self):
                return 1.0

        return ZicatAgentHandler(Parent(), [], cwd)

    def test_file_write_to_memory_blocked(self):
        from types import SimpleNamespace
        from agent_types import exhaust

        handler = self._handler(os.path.join(self.ROOT, "temp"))
        outcome = exhaust(handler.dispatch(
            "file_write", {"path": "../memory/__guard_write__.md", "content": "x"},
            SimpleNamespace(content="")))
        self.assertEqual(outcome.data["status"], "error")
        self.assertIn("memory_write", outcome.data["msg"])
        self.assertFalse(os.path.exists(os.path.join(self.ROOT, "memory", "__guard_write__.md")))

    def test_file_patch_to_memory_blocked(self):
        from types import SimpleNamespace
        from agent_types import exhaust

        handler = self._handler(os.path.join(self.ROOT, "temp"))
        target = os.path.join(self.ROOT, "memory", "facts.txt")
        with open(target, encoding="utf-8") as fh:
            before = fh.read()
        outcome = exhaust(handler.dispatch(
            "file_patch", {"path": "../memory/facts.txt", "old_content": "a",
                           "new_content": "b"},
            SimpleNamespace(content="")))
        self.assertEqual(outcome.data["status"], "error")
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)


class RpcTests(unittest.TestCase):
    def test_event_classification(self):
        from core.rpc import _classify_next

        self.assertEqual(_classify_next("\n🛠️ file_write\n"),
                         {"event": "tool", "name": "file_write"})
        self.assertEqual(_classify_next("\n📥 file_read: hello\n"),
                         {"event": "tool_result", "name": "file_read", "text": "hello"})
        self.assertEqual(_classify_next("\n[usage] req=1 in=2 out=3\n"),
                         {"event": "usage", "text": "req=1 in=2 out=3",
                          "requests": 1, "input": 2, "output": 3})
        self.assertEqual(_classify_next("hello")["event"], "delta")

    def test_structured_event_mapping(self):
        from core.rpc import _event_from_item

        self.assertEqual(_event_from_item({"next": "回复文本", "kind": "assistant"}),
                         {"event": "delta", "text": "回复文本"})
        self.assertEqual(
            _event_from_item({"next": "\n🛠️ file_write\n", "kind": "tool_call",
                              "name": "file_write", "args": '{"path": "a.txt"}'}),
            {"event": "tool_call", "name": "file_write", "args": '{"path": "a.txt"}'})
        self.assertEqual(
            _event_from_item({"next": "\n📥 file_read: ok\n", "kind": "tool_result",
                              "name": "file_read", "text": "line1\nline2", "ok": True}),
            {"event": "tool_result", "name": "file_read", "text": "line1\nline2", "ok": True})
        self.assertEqual(_event_from_item({"next": "[挂起] 等待输入", "kind": "notice"}),
                         {"event": "notice", "text": "[挂起] 等待输入"})
        # 无 kind 的旧式载荷仍走文本分类兜底
        self.assertEqual(_event_from_item({"next": "hello"}),
                         {"event": "delta", "text": "hello"})


class ConsumeEmitTests(unittest.TestCase):
    """回归：_consume 结构化 emit 链路（extra 的 text 与位置参数撞名曾致 TypeError）。"""

    def test_consume_emits_structured_items(self):
        import queue as _queue
        from types import SimpleNamespace
        from langchain_core.messages import AIMessage, ToolMessage
        from engine.callbacks import UsageTracker
        from engine.runner import _consume

        class FakeGraph:
            def stream(self, inputs, config, stream_mode=None):
                yield "updates", {"node": {"messages": [
                    AIMessage(content="先跑个工具", tool_calls=[
                        {"name": "code_run", "args": {"script": "print(1)"}, "id": "t1"}]),
                    ToolMessage(content="line1\nline2", name="code_run", tool_call_id="t1"),
                ]}}

            def get_state(self, config):
                return SimpleNamespace(interrupts=())

        runtime = SimpleNamespace(agent=SimpleNamespace(stop_sig=False), usage={})
        q = _queue.Queue()
        pending, usage = _consume(FakeGraph(), None, {}, runtime,
                                  UsageTracker(), q, "user", lambda v: None)
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        self.assertEqual([i.get("kind") for i in items],
                         ["assistant", "tool_call", "tool_result"])
        self.assertEqual(items[0]["next"], "先跑个工具")
        self.assertEqual(items[1]["name"], "code_run")
        self.assertIn("print(1)", items[1]["args"])
        self.assertEqual(items[2]["text"], "line1\nline2")
        self.assertTrue(items[2]["ok"])
        self.assertEqual(pending, [])

    def test_consume_marks_error_tool(self):
        import queue as _queue
        from types import SimpleNamespace
        from langchain_core.messages import AIMessage, ToolMessage
        from engine.callbacks import UsageTracker
        from engine.runner import _consume

        class FakeGraph:
            def stream(self, inputs, config, stream_mode=None):
                yield "updates", {"node": {"messages": [
                    AIMessage(content="", tool_calls=[
                        {"name": "file_read", "args": {"path": "x"}, "id": "t1"}]),
                    ToolMessage(content="boom", name="file_read", tool_call_id="t1",
                                status="error"),
                ]}}

            def get_state(self, config):
                return SimpleNamespace(interrupts=())

        q = _queue.Queue()
        _consume(FakeGraph(), None, {}, SimpleNamespace(agent=SimpleNamespace(stop_sig=False), usage={}),
                 UsageTracker(), q, "user", lambda v: None)
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        result = next(i for i in items if i.get("kind") == "tool_result")
        self.assertFalse(result["ok"])


class ResumeWorkingTests(unittest.TestCase):
    """回归：resume 必须从 checkpoint 回填 working（否则空副本覆盖持久化工作记忆）。"""

    def test_resume_backfills_working(self):
        from types import SimpleNamespace
        from unittest import mock
        import engine.runner as runner_mod
        from engine.callbacks import UsageTracker

        handler = SimpleNamespace(working={})
        state_calls = {"n": 0}

        class FakeGraph:
            def __init__(self):
                self.values = {"working": {"key_info": "任务要点：修 bug"}}

            def get_state(self, config):
                state_calls["n"] += 1
                if state_calls["n"] == 1:
                    return SimpleNamespace(
                        interrupts=(SimpleNamespace(value={"question": "继续吗？"}),),
                        values=self.values)
                return SimpleNamespace(interrupts=(), values=self.values)

            def stream(self, inputs, config, stream_mode=None):
                return iter([])

        fake_runtime = SimpleNamespace(agent=SimpleNamespace(stop_sig=False), usage={})
        with mock.patch.object(runner_mod, "_build_context",
                               return_value=(handler, "sys")), \
             mock.patch.object(runner_mod, "_build",
                               return_value=(fake_runtime, UsageTracker(), FakeGraph(),
                                             {"configurable": {"thread_id": "t"}})):
            has_pending, _final, _usage = runner_mod.resume_pending(
                SimpleNamespace(), "t", interrupt_handler=lambda v: "好")

        self.assertTrue(has_pending)
        self.assertEqual(handler.working, {"key_info": "任务要点：修 bug"})


class DotenvKeysTests(unittest.TestCase):
    """FIX-2：.env 的 ZICAT_OAI_n__FIELD 组装为 oai_config_n（字段小写、数值转换）。"""

    def test_dotenv_grouping_coercion(self):
        import os
        import tempfile
        from unittest import mock
        import mykey_loader as kl

        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as fh:
                fh.write("ZICAT_OAI_1__APIBASE=https://x/v1\n"
                         "ZICAT_OAI_1__APIKEY=sk-test\n"
                         "ZICAT_OAI_1__MAX_TOKENS=32768\n"
                         "ZICAT_OAI_1__STREAM=false\n"
                         "ZICAT_OAI_2__APIBASE=https://y/v1\n"
                         "ZICAT_OAI_2__APIKEY=sk-2\n"
                         "ZICAT_OAI_2__MODEL=m2\n")
            with mock.patch.object(kl, "ENV_PATH", env_path), \
                 mock.patch.dict(os.environ, {}, clear=True):
                data = kl._dotenv_data()

        self.assertEqual(sorted(data), ["oai_config_1", "oai_config_2"])
        self.assertEqual(data["oai_config_1"]["apibase"], "https://x/v1")
        self.assertEqual(data["oai_config_1"]["apikey"], "sk-test")
        self.assertEqual(data["oai_config_1"]["max_tokens"], 32768)  # int 转换
        self.assertEqual(data["oai_config_2"]["model"], "m2")

    def test_dotenv_missing_returns_none(self):
        import os
        import tempfile
        from unittest import mock
        import mykey_loader as kl

        with mock.patch.object(kl, "ENV_PATH",
                               os.path.join(tempfile.gettempdir(), "zicat-no-such.env")):
            self.assertIsNone(kl._dotenv_data())


class AbortFinalTextTests(unittest.TestCase):
    """回归：中断的任务不得把 checkpoint 里历史轮次的 AIMessage 当作本任务最终回复。"""

    def test_run_graph_task_blank_final_on_stop(self):
        import queue as _queue
        from types import SimpleNamespace
        from unittest import mock
        import engine.runner as runner_mod

        agent = SimpleNamespace(stop_sig=True, graph_thread_id="t", graph_rewind_to="",
                                log_path=False, extra_sys_prompts=[])
        from langchain_core.messages import AIMessage

        class FakeGraph:
            def get_state(self, config):
                return SimpleNamespace(values={"messages": [AIMessage(content="上一任务旧文本")],
                                               "interrupts": ()})

            def stream(self, inputs, config, stream_mode=None):
                return iter([])

        class _FakeTracker:
            def snapshot(self):
                return {"requests": 0, "input": 0, "output": 0}

        fake = (SimpleNamespace(agent=agent, usage={}), _FakeTracker(), FakeGraph(),
                {"configurable": {"thread_id": "t"}})
        with mock.patch.object(runner_mod, "_build", return_value=fake):
            final, _usage, _tid = runner_mod.run_graph_task(
                agent, "任务", _queue.Queue(), None, "sys")

        self.assertEqual(final, "")  # 修复前会返回 "上一任务旧文本"


class Fix4CheckpointTests(unittest.TestCase):
    """FIX-4：checkpoint 压缩 serde + retention。"""

    def test_serde_roundtrip_and_threshold(self):
        from engine.checkpointer import CompressedSerde, _COMPRESS_MARK, _COMPRESS_MIN
        serde = CompressedSerde()
        small = {"k": "v"}
        t1, b1 = serde.dumps_typed(small)
        self.assertLess(len(b1), _COMPRESS_MIN)
        self.assertNotEqual(b1[:1], _COMPRESS_MARK)          # 小负载不压缩
        self.assertEqual(serde.loads_typed((t1, b1)), small)
        big = {"msgs": ["档案数据行" * 2000]}
        t2, b2 = serde.dumps_typed(big)
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        raw_len = len(JsonPlusSerializer().dumps_typed(big)[1])
        self.assertGreaterEqual(raw_len, _COMPRESS_MIN)       # 原始负载确实过了压缩阈值
        self.assertEqual(b2[:1], _COMPRESS_MARK)             # 大负载带标记
        self.assertLess(len(b2), raw_len // 4)               # 压缩显著生效
        self.assertEqual(serde.loads_typed((t2, b2)), big)   # roundtrip 一致

    def test_serde_reads_legacy_unmarked(self):
        from engine.checkpointer import CompressedSerde
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        data = {"k": "旧格式"}
        t, blob = JsonPlusSerializer().dumps_typed(data)     # 无标记的旧数据
        self.assertEqual(CompressedSerde().loads_typed((t, blob)), data)

    def test_prune_keeps_latest_and_clears_writes(self):
        import os
        import tempfile
        from engine.checkpointer import get_saver, prune_thread
        from langgraph.checkpoint.base import Checkpoint

        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "t.db")
        saver = get_saver(db)
        tid = "prune-test"
        for i in range(5):
            cp = Checkpoint(id=f"cp{i}", ts="2026-10-24T00:00:00",
                            channel_values={"i": i}, channel_versions={}, versions_seen={})
            saver.put({"configurable": {"thread_id": tid, "checkpoint_ns": "",
                                        "checkpoint_id": cp["id"]}}, cp, {}, {})
        deleted = prune_thread(db, tid, keep=2)
        self.assertEqual(deleted, 3)
        import sqlite3
        conn = sqlite3.connect(db)
        left = [r[0] for r in conn.execute(
            "SELECT checkpoint_id FROM checkpoints ORDER BY rowid")]
        conn.close()
        self.assertEqual(left, ["cp3", "cp4"])                # 保留最新两份
        state = saver.get_tuple({"configurable": {"thread_id": tid, "checkpoint_ns": ""}})
        self.assertEqual(state.checkpoint["channel_values"].get("i"), 4)

    def test_retention_defaults_present(self):
        from engine.settings import graph_config
        cfg = graph_config()
        self.assertEqual(int(cfg.get("ckpt_retention", 0)), 20)
        self.assertEqual(int(cfg.get("ckpt_vacuum_mb", 0)), 64)

    def test_prune_vacuum_threshold(self):
        import os
        import tempfile
        from engine.checkpointer import get_saver, prune_thread
        from langgraph.checkpoint.base import Checkpoint

        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "t.db")
        saver = get_saver(db)
        tid = "vac-test"
        for i in range(3):
            cp = Checkpoint(id=f"cp{i}", ts="2026-10-24T00:00:00",
                            channel_values={"i": i}, channel_versions={}, versions_seen={})
            saver.put({"configurable": {"thread_id": tid, "checkpoint_ns": "",
                                        "checkpoint_id": cp["id"]}}, cp, {}, {})
        # 阈值给 0 = 不 VACUUM；正常路径只删除不抛错
        self.assertEqual(prune_thread(db, tid, keep=1, vacuum_mb=0), 2)
        import sqlite3
        conn = sqlite3.connect(db)
        self.assertEqual(conn.execute("SELECT count(*) FROM checkpoints").fetchone()[0], 1)
        conn.close()

    def test_clear_thread_removes_all_checkpoints(self):
        import os
        import tempfile
        from engine.checkpointer import clear_thread, get_saver
        from langgraph.checkpoint.base import Checkpoint

        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "t.db")
        saver = get_saver(db)
        tid = "clear-test"
        for i in range(3):
            cp = Checkpoint(id=f"cp{i}", ts="2026-10-24T00:00:00",
                            channel_values={"i": i}, channel_versions={}, versions_seen={})
            saver.put({"configurable": {"thread_id": tid, "checkpoint_ns": "",
                                        "checkpoint_id": cp["id"]}}, cp, {}, {})
        self.assertEqual(clear_thread(db, tid), 3)
        self.assertIsNone(saver.get_tuple({"configurable": {"thread_id": tid}}))


class DualStreamTests(unittest.TestCase):
    def test_dual_stream_dedup(self):
        """task7：messages token 流与 updates 整段去重——token 已流则 updates 不重复发正文。"""
        # （FIX-4 类内占位误插的测试，保留于本类）
        import queue as _queue
        from types import SimpleNamespace
        from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
        from engine.callbacks import UsageTracker
        from engine.runner import _consume

        class FakeGraph:
            def stream(self, inputs, config, stream_mode=None):
                # messages 流：token 增量（与 updates 的 AIMessage 全文一致）
                yield "messages", (AIMessageChunk(content="答案 42"), {"langgraph_node": "agent"})
                yield "messages", (AIMessageChunk(content=" 完毕"), {"langgraph_node": "agent"})
                yield "updates", {"agent": {"messages": [
                    AIMessage(content="答案 42 完毕")]}}
                yield "updates", {"tools": {"messages": [
                    ToolMessage(content="ok", name="code_run", tool_call_id="t9")]}}
                # 下一轮：无 token 流的 AIMessage（如工具轮消息）→ 应发 assistant
                yield "updates", {"agent": {"messages": [AIMessage(content="第二轮新内容")]}}

            def get_state(self, config):
                return SimpleNamespace(interrupts=())

        runtime = SimpleNamespace(agent=SimpleNamespace(stop_sig=False), usage={})
        q = _queue.Queue()
        _consume(FakeGraph(), None, {}, runtime, UsageTracker(), q, "user", lambda v: None)
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        tokens = [i["next"] for i in items if i.get("kind") == "delta_token"]
        assistants = [i["next"] for i in items if i.get("kind") == "assistant"]
        self.assertEqual(tokens, ["答案 42", " 完毕"])            # token 增量逐条
        self.assertEqual(assistants, ["第二轮新内容"])              # 已流正文不重复；新内容照发

    def test_internal_node_messages_are_not_streamed(self):
        """messages 流里的 HumanMessage/ToolMessage 是节点输出，不是模型正文。"""
        import queue as _queue
        from types import SimpleNamespace
        from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
        from engine.callbacks import UsageTracker
        from engine.runner import _consume

        class FakeGraph:
            def stream(self, inputs, config, stream_mode=None):
                yield "messages", (HumanMessage(content="<global_memory>[RULES]"), {})
                yield "messages", (ToolMessage(content="raw tool body", name="memory_index",
                                               tool_call_id="c1"), {})
                yield "messages", (AIMessageChunk(content="真正的回答"), {})
                yield "updates", {"agent": {"messages": [AIMessage(content="真正的回答")]}}

            def get_state(self, config):
                return SimpleNamespace(interrupts=())

        runtime = SimpleNamespace(agent=SimpleNamespace(stop_sig=False), usage={})
        q = _queue.Queue()
        _consume(FakeGraph(), None, {}, runtime, UsageTracker(), q, "user", lambda v: None)
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        streamed = "".join(i["next"] for i in items if i.get("kind") == "delta_token")
        self.assertEqual(streamed, "真正的回答")                  # 内部提示/工具正文不得混入
        self.assertNotIn("global_memory", streamed)
        self.assertNotIn("raw tool body", streamed)

    def test_usage_tracker_tracks_last_request_input(self):
        from types import SimpleNamespace
        from engine.callbacks import UsageTracker

        tracker = UsageTracker()
        for prompt, completion in ((100, 5), (250, 7)):
            tracker.on_llm_end(SimpleNamespace(
                llm_output={"token_usage": {"prompt_tokens": prompt,
                                            "completion_tokens": completion}},
                generations=[]))
        snap = tracker.snapshot()
        self.assertEqual(snap["input"], 350)      # 整任务累计
        self.assertEqual(snap["last_input"], 250)  # 当前请求的上下文

    def test_consume_emits_live_usage(self):
        import queue as _queue
        from types import SimpleNamespace
        from langchain_core.messages import AIMessage
        from engine.callbacks import UsageTracker
        from engine.runner import _consume

        class FakeGraph:
            def stream(self, inputs, config, stream_mode=None):
                yield "updates", {"agent": {"messages": [AIMessage(content="ok")]}}

            def get_state(self, config):
                return SimpleNamespace(interrupts=())

        runtime = SimpleNamespace(agent=SimpleNamespace(stop_sig=False),
                                  usage={"requests": 1, "input": 120,
                                         "output": 10, "last_input": 120})
        q = _queue.Queue()
        _consume(FakeGraph(), None, {}, runtime, UsageTracker(), q, "user", lambda v: None)
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        usage = next(e for e in events if e.get("kind") == "usage")
        self.assertEqual(usage["last_input"], 120)
        self.assertEqual(usage["input"], 120)

    def test_abort_rewinds_to_pre_task_checkpoint(self):
        """中断后回退到任务开始前的 checkpoint，下一条消息不会续跑被取消的任务。"""
        import queue as _queue
        from types import SimpleNamespace
        from unittest import mock
        from langchain_core.messages import AIMessageChunk
        import engine.runner as runner_mod

        agent = SimpleNamespace(stop_sig=False, graph_thread_id="t",
                                graph_rewind_to="", graph_drop_thread=False,
                                log_path=False, extra_sys_prompts=[])

        class FakeGraph:
            def get_state(self, config):
                return SimpleNamespace(
                    values={"messages": [AIMessage(content="旧回答")]},
                    interrupts=(),
                    config={"configurable": {"checkpoint_id": "base-cp"}},
                )

            def stream(self, inputs, config, stream_mode=None):
                yield "messages", (AIMessageChunk(content="半截回答"), {})
                agent.stop_sig = True

        class _FakeTracker:
            def snapshot(self):
                return {"requests": 0, "input": 0, "output": 0}

        fake = (SimpleNamespace(agent=agent, usage={}), _FakeTracker(), FakeGraph(),
                {"configurable": {"thread_id": "t"}})
        with mock.patch.object(runner_mod, "_build", return_value=fake):
            final, _usage, _tid = runner_mod.run_graph_task(
                agent, "被取消的任务", _queue.Queue(), None, "sys")

        self.assertEqual(final, "")
        self.assertEqual(agent.graph_rewind_to, "base-cp")
        self.assertEqual(agent.pending_interrupts, [])

    def test_run_tool_skipped_after_stop(self):
        from types import SimpleNamespace
        from engine.tools import ToolRuntime

        rt = ToolRuntime(agent=SimpleNamespace(stop_sig=True), handler=None)
        out = json.loads(rt.run_tool("memory_read", {}, AIMessage(content="")))
        self.assertEqual(out.get("status"), "aborted")
        self.assertTrue(rt.last_should_exit)

class RpcBridgeTests(unittest.TestCase):
    """桥层：display 事件 → JSONL 事件，以及 ask_user 的问答回路。"""

    def test_pump_maps_items_and_done(self):
        import io
        import json as _json
        import queue as _queue
        from types import SimpleNamespace
        from core.rpc import RpcBridge

        out = io.StringIO()
        bridge = RpcBridge(out)
        q = _queue.Queue()
        q.put({"next": "hi", "kind": "assistant"})
        q.put({"next": "\n🛠️ t\n", "kind": "tool_call", "name": "t", "args": "{}"})
        q.put({"next": "\n[usage] req=1 in=2 out=3\n"})
        q.put({"done": "final"})
        agent = SimpleNamespace(last_graph_usage={"requests": 1, "input": 2, "output": 3})
        bridge.attach(q, agent)
        bridge.wait(5)
        events = [_json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(events[0], {"event": "delta", "text": "hi"})
        self.assertEqual(events[1]["event"], "tool_call")
        self.assertEqual(events[2], {"event": "usage", "text": "req=1 in=2 out=3",
                                     "requests": 1, "input": 2, "output": 3})
        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(events[-1]["usage"]["input"], 2)

    def test_ask_answer_roundtrip(self):
        import io
        import json as _json
        import threading
        import time
        from core.rpc import RpcBridge

        out = io.StringIO()
        bridge = RpcBridge(out)
        holder = {}

        def asker():
            holder["answer"] = bridge.ask({"question": "继续吗？", "candidates": ["是", "否"]})

        thread = threading.Thread(target=asker)
        thread.start()
        for _ in range(100):  # 等 interrupt 事件落地
            if out.getvalue().strip():
                break
            time.sleep(0.02)
        bridge.answer("是")
        thread.join(2)
        self.assertEqual(holder.get("answer"), "是")
        event = _json.loads(out.getvalue().splitlines()[0])
        self.assertEqual(event["event"], "interrupt")
        self.assertEqual(event["candidates"], ["是", "否"])

    def test_slash_commands_from_help(self):
        from core.rpc import _slash_commands

        commands = _slash_commands()
        names = [c["cmd"] for c in commands]
        self.assertIn("/help", names)
        self.assertIn("/exit", names)
        self.assertEqual(len(names), len(set(names)))  # 基名去重
        desc = {c["cmd"]: c["desc"] for c in commands}
        self.assertEqual(desc["/help"], "显示本帮助")
        self.assertEqual(desc["/exit"], "")  # /exit /quit 同行别名不带描述
        self.assertNotIn("[范围]", desc["/review"])  # 参数占位不混入描述

    def test_usage_regex_anchor(self):
        from core.rpc import _classify_next

        # about=2 不得误配出 out=2
        event = _classify_next("\n[usage] req=1 in=10 about=2\n")
        self.assertEqual(event["input"], 10)
        self.assertEqual(event["output"], 0)


class CallbackTests(unittest.TestCase):
    def test_usage_tracker_both_shapes(self):
        from types import SimpleNamespace
        from engine.callbacks import UsageTracker

        tracker = UsageTracker()
        tracker.on_llm_end(SimpleNamespace(
            llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}},
            generations=[]))
        message = SimpleNamespace(usage_metadata={"input_tokens": 7, "output_tokens": 3})
        tracker.on_llm_end(SimpleNamespace(
            llm_output={}, generations=[[SimpleNamespace(message=message)]]))
        self.assertEqual(
            tracker.snapshot(),
            {"input": 17, "output": 8, "requests": 2, "last_input": 7},
        )


class ViewFoldTests(unittest.TestCase):
    def test_summaries_used_when_folding(self):
        from engine.hooks import build_model_messages

        messages = [HumanMessage(content="x" * 1000) for _ in range(20)]
        state = {"messages": messages, "summaries": ["第一轮摘要"], "working": {}}
        view = build_model_messages(state, "sys", 500)
        text = "\n".join(m.content for m in view if isinstance(m.content, str))
        self.assertIn("第一轮摘要", text)
        self.assertLess(len(view), len(messages) + 3)


class StopMidStreamTests(unittest.TestCase):
    def test_stops_after_chunk(self):
        from types import SimpleNamespace
        from langchain_core.messages import AIMessageChunk
        from engine.graph import _invoke_with_stop

        agent = SimpleNamespace(stop_sig=False)

        class StreamingModel:
            def __init__(self):
                self.chunks = 0

            def stream(self, messages):
                for index in range(3):
                    self.chunks += 1
                    yield AIMessageChunk(content=str(index))
                    if index == 0:
                        agent.stop_sig = True

        model = StreamingModel()
        result = _invoke_with_stop(model, ["hi"], agent)
        self.assertEqual(model.chunks, 2)
        self.assertEqual(result.content, "01")


class TurnEndTests(unittest.TestCase):
    def _runtime(self, task_dir=None):
        from zicat import ZicatAgentHandler
        from engine.tools import ToolRuntime

        class Parent:
            verbose = False
            intervene = None
            extrakeyinfo = None
            _turn_end_hooks = {}

            def __init__(self):
                self.task_dir = task_dir

            def get_ctx_multiplier(self):
                return 1.0

        parent = Parent()
        handler = ZicatAgentHandler(parent, [], tempfile.mkdtemp(prefix="ga_turn_"))
        return ToolRuntime(agent=parent, handler=handler, base_prompt="sys")

    def test_no_tool_retry_on_incomplete_response(self):
        runtime = self._runtime()
        model = FakeModel([AIMessage(content="[!!! 流异常中断"),
                           AIMessage(content="done")])
        graph = build_graph(runtime, MemorySaver(), model=model)
        config = {"configurable": {"thread_id": "t-retry"}}
        graph.invoke(_initial(), config)
        messages = graph.get_state(config).values["messages"]
        self.assertEqual(model.index, 2)
        self.assertTrue(any(isinstance(m, HumanMessage) and "Incomplete response" in m.content
                            for m in messages))
        self.assertEqual(messages[-1].content, "done")

    def test_keyinfo_injected_by_turn_end(self):
        task_dir = tempfile.mkdtemp(prefix="ga_taskdir_")
        with open(os.path.join(task_dir, "_keyinfo"), "w", encoding="utf-8") as fh:
            fh.write("记住暗号")
        runtime = self._runtime(task_dir)
        model = FakeModel([
            AIMessage(content="", tool_calls=[{"name": "probe", "args": {}, "id": "c1"}]),
            AIMessage(content="done"),
        ])
        graph = build_graph(runtime, MemorySaver(), model=model)
        config = {"configurable": {"thread_id": "t-keyinfo"}}
        graph.invoke(_initial(), config)
        working = graph.get_state(config).values.get("working") or {}
        self.assertIn("[MASTER] 记住暗号", working.get("key_info", ""))


class WorkingSyncTests(unittest.TestCase):
    def test_working_update_written_back_to_state(self):
        from types import SimpleNamespace

        model = FakeModel([
            AIMessage(content="", tool_calls=[{"name": "probe", "args": {}, "id": "c1"}]),
            AIMessage(content="done"),
        ])

        class UpdatingRuntime(FakeRuntime):
            def __init__(self):
                super().__init__()
                self.handler = SimpleNamespace(working={})

            def run_tool(self, name, args, ai_message):
                self.handler.working["key_info"] = "remembered"
                return super().run_tool(name, args, ai_message)

        runtime = UpdatingRuntime()
        graph = build_graph(runtime, MemorySaver(), model=model)
        config = {"configurable": {"thread_id": "t-working"}}
        graph.invoke(_initial(), config)
        self.assertEqual(graph.get_state(config).values["working"]["key_info"], "remembered")


class StopRequestTests(unittest.TestCase):
    def test_stop_file_consumed(self):
        from types import SimpleNamespace
        from engine.runner import _stop_requested

        task_dir = tempfile.mkdtemp(prefix="ga_task_")
        agent = SimpleNamespace(stop_sig=False, task_dir=task_dir)
        self.assertFalse(_stop_requested(agent))
        stop_file = os.path.join(task_dir, "_stop")
        open(stop_file, "w", encoding="utf-8").close()
        self.assertTrue(_stop_requested(agent))
        self.assertTrue(agent.stop_sig)
        self.assertFalse(os.path.exists(stop_file))


class LoggingCallbackTests(unittest.TestCase):
    def test_writes_prompt_response_markers(self):
        from types import SimpleNamespace
        from langchain_core.messages import AIMessage, HumanMessage
        from engine.callbacks import LoggingCallback

        path = _tmp_path("log_responses.txt")
        _clean(path)
        callback = LoggingCallback(path)
        callback.on_chat_model_start({}, [[HumanMessage(content="hi")]])
        callback.on_llm_end(SimpleNamespace(
            generations=[[SimpleNamespace(message=AIMessage(content="hello"))]]))
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("=== Prompt ===", text)
        self.assertIn("=== Response ===", text)
        self.assertIn("hello", text)
        _clean(path)


class HistoryFilterTests(unittest.TestCase):
    def test_internal_prompts_filtered(self):
        from core.session_history import _INTERNAL

        for text in ("[TIPS] 补 summary", "### [WORKING MEMORY]",
                     "<global_memory>[RULES]</global_memory>",
                     "[ERROR] Blank response", "[System] 检测到大代码块",
                     "[Info] Updated key_info.", "[Warn] empty"):
            self.assertIsNotNone(_INTERNAL.match(text), text)
        self.assertIsNone(_INTERNAL.match("帮我看下这道题"))
        self.assertIsNone(_INTERNAL.match("/team 做一次检查"))


class ReflectStartTests(unittest.TestCase):
    def test_start_reflect_uses_agentmain_reflect_mode(self):
        from unittest import mock
        from core import modes

        with mock.patch.object(modes.subprocess, "Popen") as popen:
            ok, _msg = modes.start_reflect_task("scheduler")

        self.assertTrue(ok)
        cmd = popen.call_args.args[0]
        self.assertTrue(cmd[1].endswith("agentmain.py"))
        self.assertEqual(cmd[-2:], ["--reflect", "reflect/scheduler.py"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

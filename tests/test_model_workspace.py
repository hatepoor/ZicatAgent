"""模型配置 / 工作空间 / 斜杠命令批量输出的回归测试。"""
from __future__ import annotations

import os
import queue
import shutil
import tempfile
import unittest
from unittest import mock

from core import sessions
from core.model_config import list_models_after_write, save_model, upsert_env

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ModelConfigTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="zicat_cfg_", dir=os.path.join(ROOT, "temp"))
        self.env = os.path.join(self.dir, ".env")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write_env(self, text):
        with open(self.env, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def test_upsert_env_updates_and_appends(self):
        text = "A=1\nZICAT_OAI_1__MODEL=old\n"
        text = upsert_env(text, "ZICAT_OAI_1__MODEL", "new")
        self.assertIn("ZICAT_OAI_1__MODEL=new", text)
        self.assertNotIn("old", text)
        text = upsert_env(text, "ZICAT_OAI_1__NAME", "demo")
        self.assertIn("ZICAT_OAI_1__NAME=demo", text)

    def test_save_model_custom_env(self):
        self.write_env(
            "ZICAT_OAI_1__APIBASE=https://a\n"
            "ZICAT_OAI_1__APIKEY=secret-key\n"
            "ZICAT_OAI_1__MODEL=m1\n"
        )
        models = save_model(0, {
            "base_url": "https://b",
            "model": "m2",
            "name": "demo",
            "context_window": 128000,
            "max_tokens": 8192,
            "temperature": 0.7,
        }, env_path=self.env)
        self.assertEqual(models[0]["base_url"], "https://b")
        self.assertEqual(models[0]["model"], "m2")
        self.assertEqual(models[0]["max_tokens"], "8192")
        with open(self.env, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("ZICAT_OAI_1__APIBASE=https://b", text)
        self.assertIn("ZICAT_OAI_1__MAX_TOKENS=8192", text)
        self.assertIn("ZICAT_OAI_1__APIKEY=secret-key", text)

    def test_provider_and_effort_roundtrip(self):
        self.write_env(
            "ZICAT_OAI_1__APIBASE=https://a\n"
            "ZICAT_OAI_1__MODEL=m1\n"
        )
        models = save_model(0, {
            "provider": "deepseek",
            "reasoning_effort": "medium",
        }, env_path=self.env)
        self.assertEqual(models[0]["provider"], "deepseek")
        self.assertEqual(models[0]["reasoning_effort"], "medium")
        self.assertIn("xhigh", models[0]["reasoning_effort_options"])
        with open(self.env, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("ZICAT_OAI_1__PROVIDER=deepseek", text)
        self.assertIn("ZICAT_OAI_1__REASONING_EFFORT=medium", text)

    def test_provider_switch_drops_incompatible_effort(self):
        self.write_env(
            "ZICAT_OAI_1__APIBASE=https://a\n"
            "ZICAT_OAI_1__MODEL=m1\n"
            "ZICAT_OAI_1__PROVIDER=deepseek\n"
            "ZICAT_OAI_1__REASONING_EFFORT=max\n"
        )
        models = save_model(0, {"provider": "openai"}, env_path=self.env)
        self.assertEqual(models[0]["provider"], "openai")
        self.assertEqual(models[0]["reasoning_effort"], "")
        with open(self.env, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("REASONING_EFFORT", text)

    def test_invalid_provider_and_effort_rejected(self):
        self.write_env(
            "ZICAT_OAI_1__APIBASE=https://a\n"
            "ZICAT_OAI_1__MODEL=m1\n"
        )
        with self.assertRaises(ValueError):
            save_model(0, {"provider": "unknown"}, env_path=self.env)
        with self.assertRaises(ValueError):
            save_model(0, {"provider": "openai", "reasoning_effort": "max"},
                       env_path=self.env)

    def test_masked_key_not_written(self):
        self.write_env(
            "ZICAT_OAI_1__APIBASE=https://a\n"
            "ZICAT_OAI_1__APIKEY=secret-key\n"
            "ZICAT_OAI_1__MODEL=m1\n"
        )
        save_model(0, {"api_key": "secr…-key"}, env_path=self.env)
        with open(self.env, encoding="utf-8") as f:
            self.assertIn("ZICAT_OAI_1__APIKEY=secret-key", f.read())

    def test_new_model_uses_next_env_index(self):
        self.write_env(
            "ZICAT_OAI_1__APIBASE=https://a\n"
            "ZICAT_OAI_1__MODEL=m1\n"
        )
        models = save_model(1, {
            "base_url": "https://c", "model": "m2", "name": "second",
        }, env_path=self.env)
        self.assertEqual(len(models), 2)
        with open(self.env, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("ZICAT_OAI_2__APIBASE=https://c", text)

    def test_effective_context_cap_from_model_window(self):
        from engine import settings

        with mock.patch.object(settings, "oai_configs",
                               return_value=[{"context_window": "1,000,000"}]):
            self.assertEqual(settings.effective_context_char_cap(0), 3_000_000)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="zicat_ws_", dir=os.path.join(ROOT, "temp"))
        self.db = os.path.join(self.dir, "graph.db")
        self.ws = os.path.join(self.dir, "target")
        self.root = os.path.join(self.dir, "root")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_register_exact_uses_given_dir(self):
        path = sessions.register("cli-exact01", self.ws, title="demo",
                                 db_file=self.db, exact=True)
        self.assertEqual(os.path.abspath(path), os.path.abspath(self.ws))
        self.assertTrue(os.path.isdir(self.ws))
        self.assertIn(os.path.abspath(self.ws), sessions.list_workspaces(db_file=self.db))
        rows = sessions.list_sessions(db_file=self.db)
        self.assertEqual(os.path.abspath(rows[0]["workspace"]), os.path.abspath(self.ws))

    def test_add_workspace_and_group(self):
        sessions.add_workspace(self.ws, db_file=self.db)
        self.assertIn(os.path.abspath(self.ws), sessions.list_workspaces(db_file=self.db))
        child = os.path.join(self.ws, "session-a")
        os.makedirs(child, exist_ok=True)
        sessions.register("cli-group01", self.ws, title="grouped", db_file=self.db)
        row = sessions.get("cli-group01", db_file=self.db)
        self.assertEqual(os.path.abspath(row["workspace"]), os.path.abspath(self.ws))

    def test_usage_roundtrip(self):
        usage = {"requests": 2, "input": 300, "output": 30,
                 "last_input": 150, "input_per_request": 150}
        sessions.save_usage("cli-usage01", usage, db_file=self.db)
        self.assertEqual(sessions.load_usage("cli-usage01", db_file=self.db), usage)
        self.assertEqual(sessions.load_usage("cli-missing", db_file=self.db), {})
        sessions.save_usage("cli-usage02", {"requests": 0}, db_file=self.db)
        self.assertEqual(sessions.load_usage("cli-usage02", db_file=self.db), {})

    def test_agent_new_session_clears_state(self):
        from agentmain import ZicatAgent

        agent = ZicatAgent()
        agent.graph_thread_id = "cli-old"
        agent.history = ["old"]
        agent.all_outputs = [{"x": 1}]
        agent.new_session()
        self.assertEqual(agent.graph_thread_id, "")
        self.assertEqual(agent.history, [])
        self.assertEqual(agent.all_outputs, [])
        self.assertIsNone(agent.handler)

    def test_delete_session_removes_own_files(self):
        root = os.path.join(self.dir, "wroot")
        sessions.add_workspace(root, db_file=self.db)
        ws = sessions.register("cli-del01", root, title="del", db_file=self.db)
        with open(os.path.join(ws, "f.txt"), "w", encoding="utf-8") as f:
            f.write("x")
        result = sessions.delete_session("cli-del01", db_file=self.db)
        self.assertTrue(result["ok"])
        self.assertTrue(result["files_removed"])
        self.assertFalse(os.path.exists(ws))
        self.assertIsNone(sessions.get("cli-del01", db_file=self.db))

    def test_delete_shared_workspace_session_keeps_files(self):
        root = os.path.join(self.dir, "shared")
        sessions.add_workspace(root, db_file=self.db)
        ws = sessions.register("cli-shared", root, title="shared", db_file=self.db, exact=True)
        target = os.path.join(ws, "keep.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("keep")
        result = sessions.delete_session("cli-shared", db_file=self.db)
        self.assertTrue(result["ok"])
        self.assertFalse(result["files_removed"])
        self.assertTrue(os.path.isfile(target))
        self.assertIsNone(sessions.get("cli-shared", db_file=self.db))

    def test_delete_workspace_removes_sessions_and_files(self):
        root = os.path.join(self.dir, "workspace")
        sessions.add_workspace(root, db_file=self.db)
        ws1 = sessions.register("cli-ws01", root, title="one", db_file=self.db)
        ws2 = sessions.register("cli-ws02", root, title="two", db_file=self.db)
        for ws in (ws1, ws2):
            with open(os.path.join(ws, "f.txt"), "w", encoding="utf-8") as f:
                f.write("x")
        result = sessions.delete_workspace(root, db_file=self.db)
        self.assertTrue(result["ok"])
        self.assertEqual(result["sessions_deleted"], 2)
        self.assertTrue(result["files_removed"])
        self.assertFalse(os.path.exists(root))
        self.assertEqual(sessions.list_sessions(db_file=self.db), [])
        self.assertNotIn(os.path.abspath(root), sessions.list_workspaces(db_file=self.db))

    def test_set_workspace_updates_registry(self):
        sessions.register("cli-update01", self.root, title="demo", db_file=self.db)
        path = sessions.set_workspace("cli-update01", self.ws, db_file=self.db)
        self.assertEqual(os.path.abspath(path), os.path.abspath(self.ws))
        self.assertEqual(
            os.path.abspath(sessions.workspace_of("cli-update01", self.root, db_file=self.db)),
            os.path.abspath(self.ws))

    def test_agent_set_workspace(self):
        from agentmain import ZicatAgent

        agent = ZicatAgent()
        try:
            with mock.patch("core.sessions.db_path", return_value=self.db):
                path = agent.set_workspace(self.ws, exact=True)
            self.assertEqual(os.path.abspath(path), os.path.abspath(self.ws))
            self.assertEqual(os.path.abspath(agent.get_workspace()), os.path.abspath(self.ws))
        finally:
            with mock.patch("core.sessions.db_path", return_value=self.db):
                agent.set_workspace(agent.default_workspace, exact=False)


class SlashBatchTests(unittest.TestCase):
    def test_model_output_is_single_multiline_done(self):
        from agentmain import ZicatAgent

        agent = ZicatAgent()
        q = queue.Queue()
        result = agent._handle_slash_cmd("/model", q)
        self.assertIsNone(result)
        item = q.get(timeout=3)
        self.assertIn("done", item)
        self.assertIn("Base URL", item["done"])
        self.assertIn("API Key", item["done"])
        self.assertIn("\n", item["done"])
        self.assertTrue(q.empty())

    def test_workspace_command(self):
        from agentmain import ZicatAgent

        tmp = tempfile.mkdtemp(prefix="zicat_ws_cmd_", dir=os.path.join(ROOT, "temp"))
        db = os.path.join(tmp, "graph.db")
        try:
            with mock.patch("core.sessions.db_path", return_value=db):
                agent = ZicatAgent()
                try:
                    q = queue.Queue()
                    result = agent._handle_slash_cmd(f"/workspace {tmp}", q)
                    self.assertIsNone(result)
                    item = q.get(timeout=3)
                    self.assertIn("工作空间已切换", item["done"])
                    self.assertEqual(os.path.abspath(agent.get_workspace()), os.path.abspath(tmp))
                finally:
                    agent.set_workspace(agent.default_workspace, exact=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

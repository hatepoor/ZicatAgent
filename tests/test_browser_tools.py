"""浏览器工具的导入与 JSON 序列化回归（FIX-T 漏迁 json_default）。"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

from agent_types import exhaust
import tools.browser as browser


class Ctx:
    cwd = os.getcwd()

    def get_abs_path(self, path):
        return os.path.abspath(os.path.join(self.cwd, path))

    def extract_code_block(self, response, code_type):
        return None

    def get_tool_maxlen(self, limit, args, growth_rate=1.0):
        return int(limit)

    def get_anchor_prompt(self, skip=False):
        return ""

    def print(self, *args, **kwargs):
        pass


class BrowserToolTests(unittest.TestCase):
    def test_web_execute_js_serializes_set(self):
        original = browser._web_execute_js
        browser._web_execute_js = lambda *a, **k: {"js_return": {1, 2}, "ok": True}
        try:
            outcome = exhaust(browser.do_web_execute_js(
                Ctx(), {"script": "return [1,2]"}, SimpleNamespace(content="")))
        finally:
            browser._web_execute_js = original
        self.assertIn("js_return", outcome.data)
        self.assertIn("[1, 2]", outcome.data)

    def test_web_scan_serializes_result(self):
        original = browser._web_scan
        browser._web_scan = lambda **k: {"tabs": [], "content": "<div>ok</div>"}
        try:
            outcome = exhaust(browser.do_web_scan(
                Ctx(), {"tabs_only": False}, SimpleNamespace(content="")))
        finally:
            browser._web_scan = original
        self.assertIn("<div>ok</div>", outcome.data)


if __name__ == "__main__":
    unittest.main()

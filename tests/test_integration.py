"""进程级集成测试：RPC 协议与 --reflect 模式（都不调用真实模型）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


class IntegrationTests(unittest.TestCase):
    def _run(self, args, stdin: str = "", timeout: int = 60):
        return subprocess.run(
            [PY, "-X", "utf8", "agentmain.py", *args],
            cwd=ROOT, input=stdin, text=True, capture_output=True, timeout=timeout,
        )

    def test_rpc_cost_and_exit(self):
        commands = ('{"type":"task","text":"/cost"}\n'
                    '{"type":"exit"}\n')
        result = self._run(["--rpc"], commands)
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        events = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            events.append(json.loads(line)["event"])
        self.assertEqual(events[0], "ready")
        self.assertIn("done", events)
        self.assertEqual(events[-1], "exit")
        self.assertLess(events.index("done"), events.index("exit"))

    def test_reflect_mode_runs_and_exits(self):
        with tempfile.TemporaryDirectory(prefix="ga_reflect_") as tmp:
            script = os.path.join(tmp, "probe.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write(
                    "INTERVAL = 0.1\n"
                    "_calls = 0\n"
                    "def check():\n"
                    "    global _calls\n"
                    "    _calls += 1\n"
                    "    return '/cost' if _calls == 1 else '/exit'\n")
            result = self._run(["--reflect", script, "--nobg"], timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr[-500:])
        self.assertIn("[Reflect] triggered", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

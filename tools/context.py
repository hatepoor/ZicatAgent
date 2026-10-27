"""ToolContext：工具可见的共享状态视图（FIX-T 显式注入，替代 self.* 隐式耦合）。

状态所有权仍在 ZicatAgentHandler；ctx 是它的只读视图 + 工具辅助方法。
属性全部走 property 动态透传——handler.print 等可能在构造后被替换（no_print），
快照会拿到旧值。
"""
from __future__ import annotations

import os
import re
from pathlib import Path


class ToolContext:
    """一次工具调用的上下文；由 handler 构造并注入给每个工具函数。"""

    def __init__(self, handler):
        self.handler = handler

    # ---------- 动态透传 ----------
    @property
    def parent(self):
        return self.handler.parent

    @property
    def cwd(self):
        return self.handler.cwd

    @property
    def working(self):
        return self.handler.working

    @property
    def history_info(self):
        return self.handler.history_info

    @property
    def code_stop_signal(self):
        return self.handler.code_stop_signal

    @property
    def current_turn(self):
        return self.handler.current_turn

    @property
    def print(self):
        return self.handler.print

    # ---------- 工具辅助方法 ----------
    def get_tool_maxlen(self, l, args, growth_rate=1.0):
        multiplier = 1 + (self.parent.get_ctx_multiplier() - 1) * growth_rate
        return int(l * multiplier / args.get('_tool_num', 1))

    def get_abs_path(self, path):
        if not path:
            return ""
        return os.path.abspath(os.path.join(self.cwd, path))

    def memory_write_blocked(self, path):
        """memory/ 只能经 memory_* 工具写；返回拦截说明或 None。"""
        if not path:
            return None
        try:
            abs_path = os.path.abspath(os.path.join(self.cwd, path))
            from tools.util import MEMORY_ROOT
            rel = os.path.relpath(abs_path, MEMORY_ROOT)
        except (ValueError, OSError):
            return None
        if rel == '..' or rel.startswith('..' + os.sep):
            return None
        return ("❌ memory/ 由记忆库（SQLite）管理：请改用 memory_write / memory_patch / "
                "memory_archive；file_write/file_patch 禁止写 memory/。")

    def write_blocked(self, path):
        """写操作边界：memory/、敏感文件、允许根之外的路径。"""
        blocked = self.memory_write_blocked(path)
        if blocked:
            return blocked
        if not path:
            return None
        try:
            from tools.util import ROOT
            roots = [os.path.abspath(self.cwd), os.path.abspath(str(ROOT))]
            extra = os.environ.get('ZICAT_FILE_ROOTS', '')
            roots += [os.path.abspath(p) for p in extra.split(os.pathsep) if p.strip()]
            target = os.path.realpath(os.path.abspath(os.path.join(self.cwd, path)))
            if not os.environ.get('ZICAT_ALLOW_OUTSIDE_WRITE'):
                allowed = any(
                    target == os.path.realpath(r) or
                    target.startswith(os.path.realpath(r) + os.sep)
                    for r in roots)
                if not allowed:
                    return (f"❌ 写操作超出允许目录: {target}。"
                            f"可用 ZICAT_FILE_ROOTS 追加允许目录。")
        except (ValueError, OSError):
            return None
        name = os.path.basename(target).lower()
        if name in {'.env', 'mykey.py', 'mykey.json', 'memory.db'}:
            return f"❌ 拒绝写入敏感文件: {name}"
        if '.git' in Path(target).parts:
            return "❌ 拒绝写入 .git/ 目录"
        return None

    def extract_code_block(self, response, code_type):
        code_type = {'python': 'python|py', 'powershell': 'powershell|ps1|pwsh',
                     'bash': 'bash|sh|shell'}.get(code_type, re.escape(code_type))
        matches = re.findall(rf"```(?:{code_type})\n(.*?)\n```", response.content, re.DOTALL)
        return matches[-1].strip() if matches else None

    def get_anchor_prompt(self, skip=False):
        return self.handler._get_anchor_prompt(skip=skip)

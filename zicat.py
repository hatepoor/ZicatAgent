"""zicatAgent 工具兼容层（FIX-T 后只剩壳）。

工具实现已迁至 tools/ 包（code/files/browser/memory/session_ctl 六子包 + registry 装配）；
本模块保留：
  - ZicatAgentHandler（状态所有权 + dispatch 委托 + turn_end_callback/_get_anchor_prompt）
  - agentmain / engine 引用的公共 API（load_L1 / get_global_memory / smart_format /
    consume_file / format_error / safe_print / code_run re-export）
"""
import os
import re
import sys
import time

from agent_types import BaseHandler

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 工具域装配（触发 @register）+ 公共 API re-export
import tools.code  # noqa: F401,E402  注册 code_run / sandbox_run
import tools.files  # noqa: F401,E402
import tools.browser  # noqa: F401,E402
import tools.memory  # noqa: F401,E402
import tools.session_ctl  # noqa: F401,E402  注册 no_tool 等内部工具
from tools.util import (  # noqa: F401,E402
    consume_file, format_error, safe_print, smart_format,
)

script_dir = os.path.dirname(os.path.abspath(__file__))


def load_L1():
    """优先从记忆库动态渲染 L1；库不可用时回退到文件。"""
    try:
        from memstore.tools import MemoryTools
        store = MemoryTools().store
        if store is not None:
            return store.render_l1(log=True)
    except Exception:
        pass
    try:
        with open(os.path.join(script_dir, 'memory/l1_fallback.txt'), 'r',
                  encoding='utf-8', errors='replace') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        return ''


def get_global_memory():
    prompt = "\n"
    try:
        suffix = '_en' if os.environ.get('ZICAT_LANG', '') == 'en' else ''
        insight = load_L1()
        with open(os.path.join(script_dir, f'assets/l1_structure{suffix}.txt'), 'r',
                  encoding='utf-8') as f:
            structure = f.read()
        prompt += f'cwd = {os.path.join(script_dir, "temp")} (./)\n'
        prompt += "\n[Memory] (../memory)\n"
        prompt += structure + '\n[L1 索引] (来自记忆库，动态生成):\n'
        prompt += insight + "\n"
    except FileNotFoundError:
        pass
    return prompt


class ZicatAgentHandler(BaseHandler):
    """会话 handler：工具域状态的所有权 + dispatch 委托 tools.registry。

    FIX-T：17 个工具实现已迁至 tools/ 六子包；本类保留状态所有权
    （ctx 动态透传给工具）与非工具职责（anchor/turn_end）。
    """

    def __init__(self, parent, last_history=None, cwd='./temp'):
        self.parent = parent
        self.working = {}
        self.cwd = cwd
        self.current_turn = 0
        self.history_info = last_history if last_history else []
        self.code_stop_signal = []
        self._done_hooks = []
        self.print = safe_print
        from tools.context import ToolContext
        self.ctx = ToolContext(self)

    # ---------- dispatch 委托（yield 流式协议不变） ----------
    def dispatch(self, tool_name, args, response, index=0, tool_num=1):
        from tools.registry import dispatch as _registry_dispatch
        ret = yield from _registry_dispatch(self.ctx, tool_name, args, response, index, tool_num)
        return ret

    # ---------- 非工具职责（依赖 history/working/parent，留守本类） ----------
    def _fold_earlier(self, lines):
        FALLBACK = '直接回答了用户问题'
        parts, cnt, last = [], 0, ''

        def flush():
            if cnt:
                if FALLBACK in last:
                    parts.append(f'[Agent]（{cnt} turns）')
                else:
                    parts.append(f'{last}（{cnt} turns）')

        for line in lines:
            if line.startswith('[USER]'):
                flush()
                parts.append(line)
                cnt = 0
                last = ''
            else:
                cnt += 1
                last = line
        flush()
        return "\n".join(parts[-70:])

    def _get_anchor_prompt(self, skip=False):
        if skip:
            return "\n"
        h = self.history_info
        W = 30
        earlier = (f'<earlier_context>\n{self._fold_earlier(h[:-W])}\n</earlier_context>\n'
                   if len(h) > W and self.current_turn % 4 == 1 else "")
        joined_history = "\n".join(h[-W:])
        history = f'<history>\n{joined_history}\n</history>' if self.current_turn % 2 == 1 else ""
        prompt = f"\n### [WORKING MEMORY]\n{earlier}{history}"
        prompt += f"\nCurrent turn: {self.current_turn}\n"
        if self.working.get('key_info'):
            prompt += f"\n<key_info>{self.working.get('key_info')}</key_info>"
        if getattr(self.parent, 'verbose', False):
            self.print(prompt)
        return prompt

    def turn_end_callback(self, response, tool_calls, tool_results, turn, next_prompt, exit_reason):
        _c = re.sub(r'```.*?```|<thinking>.*?</thinking>', '', response.content, flags=re.DOTALL)
        rsumm = re.search(r"<summary>(.*?)</summary>", _c, re.DOTALL)
        raw = (rsumm.group(1) if rsumm else _c).strip()
        if raw:
            summary = smart_format(raw.replace('\n', ''), max_str_len=80)
            self.history_info.append('[Agent] ' + summary)
        if not rsumm and tool_calls and tool_calls[0]['tool_name'] != 'no_tool':
            next_prompt += "\n\n\n[TIPS] 必须在回复文本中包含<summary>！\n\n"

        if turn % 175 == 0:
            next_prompt += f"\n\n[DANGER] Turn {turn}. Must call ask_user to summarize progress and get direction. No more blind retries."
        elif turn % 17 == 0:
            next_prompt += (f"\n\n[DANGER] Turn {turn}. Call update_working_checkpoint to save key "
                            "context. Stop ineffective retries; if no progress, switch strategy: "
                            "1) Probe physical boundaries 2) **Re-read relevant SOPs**")
        elif turn % 41 == 0:
            next_prompt += (f"\n\n[DANGER] Turn {turn}. Write checkpoints/key findings/tried approaches "
                            "to a **file** for future reference (not only working_checkpoint!). "
                            "Avoid losing critical info.")
        elif turn % 15 == 0:
            next_prompt += f'<global_memory>{get_global_memory()}</global_memory>'

        injkeyinfo = self.parent.extrakeyinfo or consume_file(self.parent.task_dir, '_keyinfo')
        injprompt = self.parent.intervene or consume_file(self.parent.task_dir, '_intervene')
        if injkeyinfo:
            self.working['key_info'] = self.working.get('key_info', '') + f"\n[MASTER] {injkeyinfo}"
        if injprompt:
            next_prompt += f"\n\n[MASTER] {injprompt}\n"
        self.parent.intervene = self.parent.extrakeyinfo = None
        for hook in list(getattr(self.parent, '_turn_end_hooks', {}).values()):
            hook(locals())  # 当前为只读视图
        return next_prompt

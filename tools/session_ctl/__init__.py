"""会话控制工具：update_working_checkpoint / ask_user / start_long_term_update / no_tool。"""
from __future__ import annotations

import os
import re

from tools.registry import register
from tools.files import _file_read as file_read


def ask_user(question, candidates=None):
    """question: 向用户提出的问题。candidates: 可选的候选项列表"""
    return {"status": "INTERRUPT", "intent": "HUMAN_INTERVENTION",
            "data": {"question": question, "candidates": candidates or []}}


def _retry_or_exit(ctx, prompt):
    ctx.handler._empty_ct = getattr(ctx.handler, '_empty_ct', 0) + 1
    if ctx.handler._empty_ct >= 3:
        return __import__('agent_types').StepOutcome({}, should_exit=True)
    return __import__('agent_types').StepOutcome({}, next_prompt=prompt)


@register("update_working_checkpoint")
def do_update_working_checkpoint(ctx, args, response):
    """为整个任务设定后续需要临时记忆的重点。"""
    key_info = args.get("key_info", "")
    if "key_info" in args:
        ctx.working['key_info'] = key_info
    ctx.working['passed_sessions'] = 0
    yield "[Info] Updated key_info.\n"
    next_prompt = ctx.get_anchor_prompt(skip=args.get('_index', 0) > 0)
    if ctx.current_turn <= 1:
        next_prompt += ("\n[TIPS] Working checkpoint updated. Do not call "
                        "update_working_checkpoint again unless new, non-obvious facts appear. "
                        "Skip for short tasks.\n")
    from agent_types import StepOutcome
    return StepOutcome({"result": "working key_info updated"}, next_prompt=next_prompt)


@register("ask_user")
def do_ask_user(ctx, args, response):
    question = args.get("question", "请提供输入：")
    candidates = args.get("candidates", [])
    result = ask_user(question, candidates)
    yield "Waiting for your answer ...\n"
    from agent_types import StepOutcome
    return StepOutcome(result, next_prompt="", should_exit=True)


@register("no_tool")
def do_no_tool(ctx, args, response):
    """这是一个特殊工具，由引擎自主调用，不要包含在 tools_schema 里。
    当模型在一轮中未显式调用任何工具时，由引擎自动触发。
    二次确认仅在回复几乎只包含<thinking>/<summary>和一段大代码块时触发。"""
    content = getattr(response, 'content', '') or ""
    thinking = getattr(response, 'thinking', '') or ""
    if not response or (not content.strip() and not thinking.strip()):
        yield "[Warn] LLM returned an empty response. Retrying...\n"
        return _retry_or_exit(ctx, "[ERROR] Blank response, regenerate and tooluse")
    if '[!!! 流异常中断' in content[-100:] or '!!!Error:' in content[50:][-100:] or \
            (content.endswith('</summary>') and len(content) < 100):
        return _retry_or_exit(ctx, "[ERROR] Incomplete response. Regenerate and tooluse.")
    if content.rstrip().endswith('</｜DSML｜ calls>'):
        return _retry_or_exit(ctx, "[ERROR] Tool call format invalid; no tool was called. "
                                   "Regenerate using proper tool calls.")
    if 'max_tokens !!!]' in content[-100:]:
        return _retry_or_exit(ctx, "[ERROR] max_tokens limit reached. Use multi small steps to do it.")

    code_block_pattern = r"```[a-zA-Z0-9_]*\n[\s\S]{50,}?```"
    blocks = re.findall(code_block_pattern, content)
    if len(blocks) == 1:
        m = re.search(code_block_pattern, content)
        after_block = content[m.end():]
        if not after_block.strip():
            residual = content.replace(m.group(0), "")
            residual = re.sub(r"<thinking>[\s\S]*?</thinking>", "", residual, flags=re.IGNORECASE)
            residual = re.sub(r"<summary>[\s\S]*?</summary>", "", residual, flags=re.IGNORECASE)
            clean_residual = re.sub(r"\s+", "", residual)
            if len(clean_residual) <= 30:
                yield ("[Info] Detected large code block without tool call and no extra natural "
                       "language. Requesting clarification.\n")
                next_prompt = (
                    "[System] 检测到你在上一轮回复中主要内容是较大代码块，且本轮未调用任何工具。\n"
                    "如果这些代码需要执行、写入文件或进一步分析，请重新组织回复并显式调用相应工具"
                    "（例如：code_run、file_write、file_patch 等）；\n"
                    "如果只是向用户展示或讲解代码片段，请在回复中补充自然语言说明，"
                    "并明确是否还需要额外的实际操作。"
                )
                return __import__('agent_types').StepOutcome({}, next_prompt=next_prompt)
    return __import__('agent_types').StepOutcome(response, next_prompt=None)


@register("start_long_term_update")
def do_start_long_term_update(ctx, args, response):
    """Agent觉得当前任务完成后有重要信息需要记忆时调用此工具。"""
    from zicat import get_global_memory  # 延迟导入避免循环（zicat 导入本包触发注册）
    prompt = get_global_memory() + '''【记忆提纯】任务完成或到达重要检查点后，按L0提取最近一次任务中【事实验证成功且长期有效】的环境事实、用户偏好、重要步骤；已在整理则不重复启动。
先读后patch，将已验证、长期有用且难以重建的新知识融入旧条目，合并重复、压缩冗述，不堆叠流水账。以更少文字保留更高复用价值；不得为缩短而丢失关键事实、适用条件和踩坑信息。无提纯价值则跳过，索引按需同步。
禁止：临时状态、推理过程、未验证信息、通用常识、易重建细节；不得将模型推测或建议记作用户要求。
记忆整理仅是内部收尾；完成或跳过后，仍须向用户报告原任务结果。'''
    yield "[Info] Start distilling good memory for long-term storage.\n"
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'memory', 'kb', 'memory_management_sop.md')
    if os.path.exists(path):
        result = 'This is L0:\n' + file_read(path, show_linenos=False)
    else:
        result = "Memory Management SOP not found. Do not update memory."
    l1 = get_global_memory()
    if l1 and len(l1) > 6000:
        result += 'L1 (insight or index) is too large, follow L0 and cleanup sop to fix it!'
    if ctx.current_turn < 10:
        result, prompt = 'start_long_term_update is only used after completing a long turn task!', '\n'
    from agent_types import StepOutcome
    return StepOutcome(result, next_prompt=prompt)

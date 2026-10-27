"""记忆工具七件：dispatch 薄桥。

真正的实现在 memstore/（独立子系统）；本桥只做 ctx 相关的
next_prompt 注入与 MemoryTools 惰性获取——engine 不直接写记忆的边界不变。
"""
from __future__ import annotations

from tools.registry import register

_MT = None


def _memory_tools():
    global _MT
    if _MT is None:
        try:
            from memstore.tools import MemoryTools
            _MT = MemoryTools()
        except Exception:
            _MT = False  # False = 已尝试但不可用
    return _MT or None


def _memory_call(ctx, name, args):
    from agent_types import StepOutcome
    skip = (args or {}).get('_index', 0) > 0
    next_prompt = ctx.get_anchor_prompt(skip=skip)
    tools = _memory_tools()
    if tools is None:
        return StepOutcome({"error": "记忆库不可用"}, next_prompt=next_prompt)
    data = tools.dispatch(name, args or {})
    if name == "memory_read":
        next_prompt += ("\n[SYSTEM TIPS] 正在读取长期记忆，若决定按其中的 SOP 执行，"
                        "请提取关键点 update working memory。")
    return StepOutcome(data, next_prompt=next_prompt)


@register("memory_search", generator=False)
def do_memory_search(ctx, args, response):
    return _memory_call(ctx, "memory_search", args)


@register("memory_read", generator=False)
def do_memory_read(ctx, args, response):
    return _memory_call(ctx, "memory_read", args)


@register("memory_write", generator=False)
def do_memory_write(ctx, args, response):
    return _memory_call(ctx, "memory_write", args)


@register("memory_patch", generator=False)
def do_memory_patch(ctx, args, response):
    return _memory_call(ctx, "memory_patch", args)


@register("memory_archive", generator=False)
def do_memory_archive(ctx, args, response):
    return _memory_call(ctx, "memory_archive", args)


@register("memory_link", generator=False)
def do_memory_link(ctx, args, response):
    return _memory_call(ctx, "memory_link", args)


@register("memory_index", generator=False)
def do_memory_index(ctx, args, response):
    return _memory_call(ctx, "memory_index", args)

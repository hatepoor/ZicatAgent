"""工具装配注册表：schema（模型侧接口）与实现（这里）的显式对应。

新增工具 = assets/tools_schema.json 加一条 + 任一子包写一个 @register 函数。
dispatch 是生成器函数：与 agent_types.BaseHandler 的 yield 流式协议逐字节兼容。
"""
from __future__ import annotations

from agent_types import StepOutcome

# name -> (fn, is_generator)
TOOL_DEFS: dict[str, tuple] = {}


def register(name: str, generator: bool = True):
    def deco(fn):
        TOOL_DEFS[name] = (fn, generator)
        return fn
    return deco


def registered_names() -> list[str]:
    return sorted(TOOL_DEFS)


def dispatch(ctx, tool_name, args, response, index: int = 0, tool_num: int = 1):
    """与 BaseHandler.dispatch 行为逐字节一致的装配分发（生成器函数）。"""
    args['_index'] = index
    args['_tool_num'] = tool_num
    if tool_name in TOOL_DEFS:
        fn, is_gen = TOOL_DEFS[tool_name]
        if is_gen:
            ret = yield from fn(ctx, args, response)
            return ret
        return fn(ctx, args, response)
    if tool_name == 'bad_json':
        return StepOutcome(None, next_prompt=args.get('msg', 'bad_json'), should_exit=False)
    yield f"未知工具: {tool_name}\n"
    return StepOutcome(None, next_prompt=f"未知工具 {tool_name}", should_exit=False)

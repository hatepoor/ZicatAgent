"""StateGraph：prepare → agent ⇄ tools → finalize，ask_user 走 interrupt。"""
from __future__ import annotations

import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .hooks import build_model_messages, digest_text, extract_summary, text_of
from .llm import build_chat_model
from .state import ZicatState


def _invoke_with_stop(model, view, agent):
    """流式调用模型；每个 chunk 之间检查 stop_sig，Ctrl+C 能尽快停下。"""
    should_stop = lambda: bool(getattr(agent, "stop_sig", False))
    if should_stop():
        return AIMessage(content="")
    stream = getattr(model, "stream", None)
    if stream is None:
        return model.invoke(view)
    accumulated = None
    for chunk in stream(view):
        accumulated = chunk if accumulated is None else accumulated + chunk
        if should_stop():
            break
    if accumulated is None:
        return model.invoke(view)
    return accumulated


def _coverage_summary(state, turn: int, min_chars: int) -> str:
    """大输入轮没有模型 <summary> 时，由引擎补一条可追溯的抽取式摘要。

    覆盖缺口来自“模型忘了写 summary”：折叠推进后该段会从视图消失，
    只靠模型自述的摘要链就会漏掉整段。这里用存储消息的条号 + 首尾摘录兜底。
    """
    messages = state.get("messages") or []
    if not messages or int(min_chars) <= 0:
        return ""
    last = messages[-1]
    body = text_of(last)
    if len(body) < int(min_chars):
        return ""
    if isinstance(last, HumanMessage):
        kind = "用户输入"
    elif isinstance(last, ToolMessage):
        kind = f"工具{getattr(last, 'name', '') or ''}结果"
    else:
        return ""
    return (f"[第{turn}轮·引擎抽取·msg{len(messages) - 1}·{kind}·模型未给摘要] "
            f"{digest_text(body, 260)}")


def build_graph(runtime, checkpointer=None, max_turns: int = 180, context_cap: int = 114000,
                model=None, callbacks=None, fold_ratio: float = 0.7,
                anchor_ratio: float = 0.5, summary_min_chars: int = 8000, llm_no: int = 0):
    model = model or build_chat_model(tools_schema=runtime.tools_schema, callbacks=callbacks,
                                      index=llm_no)

    def _turn_end(state, ai, exit_reason=None):
        """复用 zicat.turn_end_callback：周期提醒、L1 刷新、_keyinfo/_intervene 注入。"""
        handler = getattr(runtime, "handler", None)
        if handler is None or not hasattr(handler, "turn_end_callback"):
            return ""
        calls = [{"tool_name": call.get("name", ""), "args": call.get("args") or {}}
                 for call in (getattr(ai, "tool_calls", None) or [])]
        if not calls:
            calls = [{"tool_name": "no_tool", "args": {}}]
        response = SimpleNamespace(content=text_of(ai))
        try:
            return handler.turn_end_callback(
                response, calls, [], int(state.get("turn", 0)), "", exit_reason or {}) or ""
        except Exception:  # noqa: BLE001 - 轮末提示失败不影响主流程
            return ""

    def prepare(state):
        return {"exit_reason": None}

    def agent_node(state):
        view = build_model_messages(state, runtime.base_prompt, context_cap,
                                    fold_ratio=fold_ratio, anchor_ratio=anchor_ratio)
        ai = _invoke_with_stop(model, view, getattr(runtime, "agent", None))
        turn = int(state.get("turn", 0)) + 1
        update = {"messages": [ai], "turn": turn}
        runtime.add_usage(getattr(ai, "usage_metadata", None))
        # 摘要带轮次与触发工具：它是模型自述、无校验，注入时要能追溯到哪一轮
        tools = [str(call.get("name") or "") for call in (getattr(ai, "tool_calls", None) or [])]
        summary = extract_summary(text_of(ai), turn=turn, tools=tools)
        if summary:
            update["summaries"] = [summary]
        else:
            # 大轮次没有自述摘要：补引擎抽取摘要，避免折叠后整段失去覆盖
            fallback = _coverage_summary(state, turn, summary_min_chars)
            if fallback:
                update["summaries"] = [fallback]
        return update

    def route_after_agent(state):
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None) or []
        # 预算优先：超限直接收尾，不再执行工具（避免递归到 recursion_limit 抛异常）
        if int(state.get("turn", 0)) >= max_turns:
            return "finalize"
        if calls:
            if any(call.get("name") == "ask_user" for call in calls):
                return "human"
            return "tools"
        return "check"

    def tools_node(state):
        ai = state["messages"][-1]
        results = []
        exit_reason = None
        for call in ai.tool_calls:
            data = runtime.run_tool(call.get("name", ""), dict(call.get("args") or {}), ai)
            results.append(ToolMessage(content=data, tool_call_id=call.get("id", ""),
                                       name=call.get("name", "")))
            if runtime.last_should_exit:
                exit_reason = "EXIT"
        update = {"messages": results}
        if exit_reason:
            update["exit_reason"] = exit_reason
        else:
            extra = _turn_end(state, ai)
            if extra:
                update["messages"].append(HumanMessage(content=extra))
        handler = getattr(runtime, "handler", None)
        if handler is not None:
            update["working"] = dict(getattr(handler, "working", {}) or {})
        if runtime.rewind is not None:
            runtime.rewind.commit(int(state.get("turn", 0)))
        return update

    def after_tools(state):
        return "finalize" if state.get("exit_reason") else "agent"

    def human_node(state):
        ai = state["messages"][-1]
        calls = list(ai.tool_calls)
        results: dict[int, ToolMessage] = {}

        # 先处理 ask_user：interrupt 会在任何工具真正执行前抛出，
        # 恢复时也不会重放兄弟工具（避免重复副作用）。
        for idx, call in enumerate(calls):
            if call.get("name") != "ask_user":
                continue
            args = dict(call.get("args") or {})
            answer = interrupt({
                "question": args.get("question", ""),
                "candidates": args.get("candidates") or [],
            })
            payload = {"status": "USER_ANSWER", "data": answer}
            results[idx] = ToolMessage(content=json.dumps(payload, ensure_ascii=False),
                                       tool_call_id=call.get("id", ""), name="ask_user")

        # 恢复之后才执行同一轮里的其它工具（只会执行一次）
        for idx, call in enumerate(calls):
            if idx in results:
                continue
            name = call.get("name", "")
            args = dict(call.get("args") or {})
            data = runtime.run_tool(name, args, ai)
            results[idx] = ToolMessage(content=data, tool_call_id=call.get("id", ""), name=name)

        if runtime.rewind is not None:
            runtime.rewind.commit(int(state.get("turn", 0)))
        update = {"messages": [results[i] for i in sorted(results)]}
        extra = _turn_end(state, ai)
        if extra:
            update["messages"].append(HumanMessage(content=extra))
        handler = getattr(runtime, "handler", None)
        if handler is not None:
            update["working"] = dict(getattr(handler, "working", {}) or {})
        return update

    def check_node(state):
        """无工具轮：复用 zicat.do_no_tool 做空回复/截断/大代码块二次确认。"""
        ai = state["messages"][-1]
        handler = getattr(runtime, "handler", None)
        if handler is None or not hasattr(handler, "dispatch"):
            return {}
        runtime.run_tool("no_tool", {}, ai)
        prompt = runtime.last_next_prompt
        if not prompt:
            return {"exit_reason": "EXIT"} if runtime.last_should_exit else {}
        extra = _turn_end(state, ai)
        content = (prompt + ("\n\n" + extra if extra else "")).strip()
        return {"messages": [HumanMessage(content=content)]}

    def after_check(state):
        if state.get("exit_reason"):
            return "finalize"
        last = state["messages"][-1]
        return "agent" if isinstance(last, HumanMessage) else "finalize"

    def finalize(state):
        reason = state.get("exit_reason")
        if not reason:
            reason = "MAX_TURNS" if int(state.get("turn", 0)) >= max_turns else "DONE"
        if reason == "MAX_TURNS":
            note = (f"[系统] 已达到最大轮数 {max_turns}，任务在此收尾。"
                    "请基于已有信息给出当前结论，并说明未完成部分。")
            return {"exit_reason": reason, "messages": [AIMessage(content=note)]}
        return {"exit_reason": reason}

    builder = StateGraph(ZicatState)
    builder.add_node("prepare", prepare)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_node("human", human_node)
    builder.add_node("check", check_node)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "agent")
    builder.add_conditional_edges("agent", route_after_agent,
                                  {"tools": "tools", "human": "human", "check": "check",
                                   "finalize": "finalize"})
    builder.add_conditional_edges("tools", after_tools, {"agent": "agent", "finalize": "finalize"})
    builder.add_edge("human", "agent")
    builder.add_conditional_edges("check", after_check, {"agent": "agent", "finalize": "finalize"})
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)

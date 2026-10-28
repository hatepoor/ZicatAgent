"""运行入口：把图事件翻译成 CLI 的 next/done 协议；支持跨进程 resume。"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Callable, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from . import settings
from .callbacks import LoggingCallback, UsageTracker
from .checkpointer import get_saver
from .graph import build_graph
from .hooks import text_of
from .rewind import TaskRewind
from .tools import ToolRuntime, load_tools_schema


def _stop_requested(agent) -> bool:
    """Ctrl+C（stop_sig）或 --task 模式的 `_stop` 文件都算中断请求。"""
    if getattr(agent, "stop_sig", False):
        return True
    task_dir = getattr(agent, "task_dir", None)
    if not task_dir:
        return False
    stop_file = os.path.join(task_dir, "_stop")
    if not os.path.isfile(stop_file):
        return False
    try:
        os.remove(stop_file)
    except OSError:
        pass
    agent.stop_sig = True
    return True


def _default_interrupt_handler(value) -> Optional[str]:
    """返回 None 表示当前无法回答（非交互），让任务保持挂起。"""
    question = value.get("question") if isinstance(value, dict) else str(value)
    candidates = value.get("candidates") if isinstance(value, dict) else None
    print(f"\n[HUMAN] {question}")
    if candidates:
        for idx, item in enumerate(candidates, 1):
            print(f"  {idx}. {item}")
    try:
        return input("> ")
    except (EOFError, KeyboardInterrupt):
        return None


def _emit(display_queue, next_text: str, source: str = "user", **extra) -> None:
    """投递显示事件；extra 携带结构化字段（kind/name/args/text），供 RPC 等前端使用。

    位置参数叫 next_text 以免与 extra 里的 `text`（工具结果多行预览）撞名。
    `next` 纯文本始终保留，面向 CLI / --task 的消费端不受结构化字段影响。
    """
    if display_queue is not None:
        item = {"next": next_text, "source": source}
        item.update(extra)
        display_queue.put(item)
    else:
        print(next_text, end="", flush=True)


def _args_summary(args, limit: int = 200) -> str:
    """工具调用参数的显示摘要（单行 JSON，超长截断）。"""
    try:
        text = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(args)
    if len(text) > limit:
        text = text[:limit] + " …"
    return text


def _reasoning_of(message) -> str:
    """取流式/非流式消息里的思考内容；兼容 DeepSeek 与 OpenRouter 风格。"""
    extra = getattr(message, "additional_kwargs", {}) or {}
    for key in ("reasoning_content", "reasoning"):
        value = extra.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


class _DeltaBatcher:
    """把逐 token 的 delta 合并成小批，降低 RPC/SSE 事件数。

    80 字符或 40ms 先到先发；结构化事件（tool_call/tool_result）前必须
    flush，保证前端看到的 token 顺序与事件顺序一致。
    """

    def __init__(self, display_queue, source: str, min_chars: int = 80,
                 max_interval: float = 0.04, kind: str = "delta_token"):
        self.queue = display_queue
        self.source = source
        self.min_chars = max(1, int(min_chars))
        self.max_interval = max(0.0, float(max_interval))
        self.kind = kind
        self.parts: list[str] = []
        self.size = 0
        self.last = time.monotonic()

    def push(self, text: str) -> None:
        if not text:
            return
        self.parts.append(text)
        self.size += len(text)
        if self.size >= self.min_chars or (time.monotonic() - self.last) >= self.max_interval:
            self.flush()

    def flush(self) -> None:
        if not self.parts:
            return
        _emit(self.queue, "".join(self.parts), self.source, kind=self.kind)
        self.parts.clear()
        self.size = 0
        self.last = time.monotonic()


def _cfg_float(cfg: dict, key: str, default: float) -> float:
    try:
        return float(cfg.get(key, default))
    except (TypeError, ValueError):
        return default


def _cfg_int(cfg: dict, key: str, default: int) -> int:
    try:
        return int(cfg.get(key, default))
    except (TypeError, ValueError):
        return default


def set_llm_no(agent, index: int) -> None:
    """/model 热切换：写 agent 状态并持久化到 temp/llm_state.json（重启保留）。"""
    agent.llm_no = int(index)
    try:
        import json as _json
        state_path = os.path.join(str(settings.ROOT), "temp", "llm_state.json")
        with open(state_path, "w", encoding="utf-8") as fh:
            _json.dump({"llm_no": agent.llm_no}, fh)
    except OSError:
        pass


def _load_llm_no(agent) -> int:
    """启动时恢复上次切换的模型索引；单配置时恒 0。"""
    if int(getattr(agent, "llm_no", 0) or 0):
        return int(agent.llm_no)
    try:
        import json as _json
        state_path = os.path.join(str(settings.ROOT), "temp", "llm_state.json")
        with open(state_path, encoding="utf-8") as fh:
            return int(_json.load(fh).get("llm_no", 0) or 0)
    except (OSError, ValueError):
        return 0


def _durability_for(agent, cfg: dict) -> Optional[str]:
    """非交互 --task 只在退出/中断时落 checkpoint，避免每个 super-step 重写整份 state。

    交互会话保持 LangGraph 默认（按步落盘），/rewind 的粒度不受影响；
    调用方也可显式用 graph_config.durability 或 agent.graph_durability 覆盖。
    """
    value = cfg.get("durability", getattr(agent, "graph_durability", None))
    if value in ("sync", "async", "exit"):
        return str(value)
    if getattr(agent, "task_dir", None):
        return "exit"
    return None


def _usage_with_rates(usage: dict) -> dict:
    """累计 input/output 是各次请求之和；last_input 才是当前上下文大小。"""
    if not isinstance(usage, dict):
        return dict(usage or {})
    out = dict(usage)
    requests = int(out.get("requests") or 0)
    if requests > 0:
        out.setdefault("input_per_request", int(int(out.get("input") or 0) / requests))
        out.setdefault("output_per_request", int(int(out.get("output") or 0) / requests))
        if not out.get("last_input"):
            out["last_input"] = out["input_per_request"]
    return out


def _persist_usage(thread_id: str, usage: dict) -> None:
    """把任务用量按 thread 落库；切会话/重启后 /cost 仍可读。"""
    if not thread_id or not isinstance(usage, dict) or not usage.get("requests"):
        return
    try:
        from core import sessions
        sessions.save_usage(thread_id, usage)
    except Exception:  # noqa: BLE001 - 用量持久化失败不影响任务结果
        pass


def _build_context(agent):
    """为 resume 等入口构造 handler 与 system prompt（不依赖当前任务）。"""
    import zicat
    from zicat import ZicatAgentHandler

    suffix = "_en" if os.environ.get("ZICAT_LANG", "") == "en" else ""
    prompt_file = settings.ROOT / "assets" / f"sys_prompt{suffix}.txt"
    try:
        base = prompt_file.read_text(encoding="utf-8")
    except OSError:
        base = ""
    sys_prompt = base + f"\nToday: {time.strftime('%Y-%m-%d %a')}\n" + zicat.get_global_memory()
    sys_prompt += "".join(getattr(agent, "extra_sys_prompts", []) or [])
    handler = ZicatAgentHandler(agent, list(getattr(agent, "history", []) or []),
                                  str(settings.ROOT / "temp"))
    return handler, sys_prompt


def _build(agent, handler, sys_prompt: str, thread_id: str):
    cfg = settings.graph_config()
    llm_no = _load_llm_no(agent)
    runtime = ToolRuntime(
        agent=agent, handler=handler,
        tools_schema=load_tools_schema(no_user_tools="--no-user-tools" in sys.argv),
        base_prompt=sys_prompt,   # 已含记忆库动态渲染的 L1（见 zicat.load_L1）
        rewind=TaskRewind(thread_id, settings.ROOT, settings.ROOT / "temp"),
    )
    tracker = UsageTracker()
    callbacks = [tracker]
    log_path = getattr(agent, "log_path", None)
    if log_path:
        callbacks.append(LoggingCallback(log_path))
    max_turns = int(cfg["max_turns"])
    graph = build_graph(runtime, get_saver(cfg["checkpointer"]),
                        max_turns=max_turns,
                        context_cap=settings.effective_context_char_cap(llm_no, cfg),
                        callbacks=callbacks,
                        fold_ratio=_cfg_float(cfg, "fold_ratio", 0.7),
                        anchor_ratio=_cfg_float(cfg, "anchor_ratio", 0.5),
                        summary_min_chars=_cfg_int(cfg, "summary_min_chars", 8000),
                        llm_no=llm_no)
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": int(cfg.get("recursion_limit") or max_turns * 2 + 20),
    }
    return runtime, tracker, graph, config


def _final_text(graph, config) -> str:
    messages = graph.get_state(config).values.get("messages") or []
    finals = [m for m in messages if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)]
    return text_of(finals[-1]) if finals else (text_of(messages[-1]) if messages else "")


def _consume(graph, inputs, config, runtime, tracker, display_queue, source, handler_interrupt,
             durability: Optional[str] = None):
    """消费图事件；遇到 interrupt 时尝试回答，回答不了就保持挂起。

    stream_mode 双流："messages" 提供 token 级增量（真流式，kind=delta_token），
    "updates" 提供结构化事件（tool_call/tool_result）。updates 里的整段
    AIMessage 全文与 token 流重复，改为记录去重键、不重复发送正文。
    """
    pending: list = []
    while True:
        kwargs = {"durability": durability} if durability else {}
        content_batcher = _DeltaBatcher(display_queue, source, kind="delta_token")
        thinking_batcher = _DeltaBatcher(display_queue, source, kind="thinking_delta")
        tok_seen = False
        thinking_seen = False
        for mode, chunk in graph.stream(inputs, config,
                                        stream_mode=["messages", "updates"], **kwargs):
            if _stop_requested(runtime.agent):
                break
            if mode == "messages":
                msg = chunk[0] if isinstance(chunk, tuple) and len(chunk) == 2 else None
                # messages 流不只包含模型 token：节点返回的 HumanMessage（轮末
                # <global_memory> 提示）和 ToolMessage（工具结果）也会被推流。
                # 只有 AIMessage 才是模型产出，其余一律不进助手正文。
                if isinstance(msg, AIMessage):
                    reasoning = _reasoning_of(msg)
                    if reasoning:
                        thinking_seen = True
                        thinking_batcher.push(reasoning)
                    delta = getattr(msg, "content", None)
                    if isinstance(delta, str) and delta:
                        tok_seen = True
                        content_batcher.push(delta)
                continue
            if not isinstance(chunk, dict):
                continue
            # 结构化事件前先落盘 thinking / token，保持顺序。
            thinking_batcher.flush()
            content_batcher.flush()
            for _node, update in chunk.items():
                if not isinstance(update, dict):
                    continue
                for message in update.get("messages") or []:
                    if isinstance(message, AIMessage):
                        reasoning = _reasoning_of(message)
                        if reasoning and not thinking_seen:
                            # 非流式 / messages 流未带 reasoning 时，用整段补发一次。
                            _emit(display_queue, reasoning, source, kind="thinking_delta")
                        thinking_seen = False
                        text = text_of(message)
                        if text and not tok_seen:
                            # token 流已发出本轮正文时不再重复整段；tok_seen 无论
                            # 是否有文本都要复位，避免上一条工具调用轮的 token 串到下一轮。
                            _emit(display_queue, text, source, kind="assistant")
                        tok_seen = False
                        for call in getattr(message, "tool_calls", None) or []:
                            name = str(call.get("name") or "")
                            _emit(display_queue, f"\n🛠️ {name}\n", source,
                                  kind="tool_call", name=name,
                                  call_id=str(call.get("id") or ""),
                                  args=_args_summary(call.get("args")))
                        # 每轮模型调用结束就推一次用量：last_input 是当前请求的
                        # 上下文大小，前端据此实时更新；累计 input 只是整任务总和。
                        usage_now = tracker.snapshot()
                        if not usage_now.get("requests"):
                            usage_now = dict(runtime.usage or {})
                        elif not usage_now.get("last_input"):
                            usage_now["last_input"] = int(
                                (runtime.usage or {}).get("last_input") or 0)
                        if usage_now.get("requests"):
                            usage_now = _usage_with_rates(usage_now)
                            _emit(display_queue, "", source, kind="usage",
                                  requests=int(usage_now.get("requests") or 0),
                                  input=int(usage_now.get("input") or 0),
                                  output=int(usage_now.get("output") or 0),
                                  last_input=int(usage_now.get("last_input") or 0),
                                  input_per_request=int(usage_now.get("input_per_request") or 0))
                    elif isinstance(message, ToolMessage):
                        body = text_of(message)
                        preview = body[:160].replace("\n", " ")
                        payload = None
                        try:
                            parsed = json.loads(body)
                            if isinstance(parsed, dict):
                                payload = {
                                    key: (value[:8000] + "…[truncated]"
                                          if isinstance(value, str) and len(value) > 8000
                                          else value)
                                    for key, value in parsed.items()
                                }
                        except (TypeError, ValueError):
                            payload = None
                        _emit(display_queue, f"\n📥 {message.name}: {preview}\n", source,
                              kind="tool_result", name=str(message.name or ""),
                              call_id=str(getattr(message, "tool_call_id", "") or ""),
                              text=body[:1200].rstrip(),
                              payload=payload,
                              ok=getattr(message, "status", "success") != "error")

        thinking_batcher.flush()
        content_batcher.flush()
        snapshot = graph.get_state(config)
        pending = list(getattr(snapshot, "interrupts", ()) or ())
        if not pending:
            break
        answers = [handler_interrupt(item.value) for item in pending]
        if any(answer is None for answer in answers):
            break  # 非交互：保持挂起，等待 /resume
        inputs = Command(resume=answers[0] if len(answers) == 1 else answers)

    usage = tracker.snapshot()
    if usage["requests"] == 0:
        usage = dict(runtime.usage)
    return pending, _usage_with_rates(usage)


def run_graph_task(agent, query: str, display_queue, handler, sys_prompt: str,
                   source: str = "user", thread_id: Optional[str] = None,
                   interrupt_handler: Optional[Callable] = None) -> tuple[str, dict, str]:
    """执行一个任务，返回 (最终回答, 用量, thread_id)。"""
    cfg = settings.graph_config()
    thread_id = thread_id or getattr(agent, "graph_thread_id", "") or f"cli-{time.time_ns()}"
    agent.graph_thread_id = thread_id

    runtime, tracker, graph, config = _build(agent, handler, sys_prompt, thread_id)
    drop = bool(getattr(agent, "graph_drop_thread", False))
    drops = getattr(agent, "graph_drop_threads", None)
    if drops is not None and thread_id in drops:
        drop = True
    if drop:
        # 首轮任务被中断：没有更早的 checkpoint 可回退，直接清空该 thread，
        # 否则下一条消息会看到被取消的指令并继续执行。
        agent.graph_drop_thread = False
        if drops is not None:
            drops.discard(thread_id)
        agent.graph_rewind_to = ""
        try:
            from .checkpointer import clear_thread
            clear_thread(cfg["checkpointer"], thread_id)
        except Exception:  # noqa: BLE001 - 清理失败不应阻塞新任务
            pass
    rewinds = getattr(agent, "graph_rewinds", None) or {}
    if drop:
        rewinds.pop(thread_id, None)   # 清空 thread 优先于回退
    rewind_to = getattr(agent, "graph_rewind_to", "")
    if rewind_to:
        # 显式 /rewind 优先；同 thread 的中断回退目标作废
        agent.graph_rewind_to = ""
        rewinds.pop(thread_id, None)
    else:
        rewind_to = rewinds.pop(thread_id, "")
    if rewind_to:
        config["configurable"]["checkpoint_id"] = rewind_to

    key_info = ""
    if handler is not None:
        key_info = (getattr(handler, "working", {}) or {}).get("key_info", "")
    existing = graph.get_state(config)
    base_checkpoint = (
        ((getattr(existing, "config", None) or {}).get("configurable") or {})
        .get("checkpoint_id") or ""
    )
    inputs: object = {"messages": [HumanMessage(content=query)]}
    if not (existing.values or {}).get("messages"):
        inputs.update({
            "working": {"key_info": key_info},
            "summaries": [],
            "turn": 0,
            "exit_reason": None,
            "meta": {"engine": "graph", "session": thread_id, "source": source},
        })

    handler_interrupt = interrupt_handler or _default_interrupt_handler
    durability = _durability_for(agent, cfg)
    usage: dict = {}
    pending: list = []
    error = ""
    agent.graph_last_error = ""
    try:
        pending, usage = _consume(graph, inputs, config, runtime, tracker, display_queue,
                                  source, handler_interrupt, durability=durability)
    except BaseException as exc:  # noqa: BLE001 - 失败轮也要落账并标记，不能静默沿用上一轮数字
        error = f"{type(exc).__name__}: {exc}"
        usage = tracker.snapshot()
        if not usage.get("requests"):
            usage = dict(runtime.usage or {})
        usage = _usage_with_rates(usage)
        usage["invalid"] = True
        usage["error"] = error
        agent.graph_last_error = error
        raise
    finally:
        if error:
            try:  # 兜底查询失败不应掩盖原始异常
                pending = list(getattr(graph.get_state(config), "interrupts", ()) or [])
            except Exception:  # noqa: BLE001
                pending = []
        agent.last_graph_usage = usage
        _persist_usage(thread_id, usage)
        if getattr(agent, "stop_sig", False):
            # 中断不是“暂停”：挂起问题作废，且把检查点回退到任务开始前。
            # 否则下一条用户消息会接在被取消的指令（或悬空 tool_call）后面，
            # 模型会把旧任务继续做下去。
            agent.pending_interrupts = []
            pending = []
            if base_checkpoint:
                agent.graph_rewind_to = base_checkpoint
                rewinds = getattr(agent, "graph_rewinds", None)
                if rewinds is None:
                    rewinds = {}
                    agent.graph_rewinds = rewinds
                rewinds[thread_id] = base_checkpoint
            else:
                agent.graph_drop_thread = True
                drops = getattr(agent, "graph_drop_threads", None)
                if drops is None:
                    drops = set()
                    agent.graph_drop_threads = drops
                drops.add(thread_id)
        else:
            agent.pending_interrupts = [item.value for item in pending]
    # FIX-4: 任务正常收尾后裁剪该会话的旧 checkpoint（挂起/中断时不裁：恢复与
    # 回退都依赖历史检查点，裁剪可能把回退目标删掉）。
    stopped = bool(getattr(agent, "stop_sig", False))
    cfg_retention = int(cfg.get("ckpt_retention", 20) or 20)
    if cfg_retention > 0 and not pending and not stopped:
        try:
            from .checkpointer import prune_thread
            prune_thread(cfg["checkpointer"], thread_id, keep=cfg_retention,
                         vacuum_mb=int(cfg.get("ckpt_vacuum_mb", 0) or 0))
        except Exception:  # noqa: BLE001 - 清理失败不影响任务结果
            pass
    final_text = _final_text(graph, config)
    if stopped:
        # 中断的任务：checkpoint 里最后一条 AIMessage 属于历史轮次，
        # 不能当作本任务的最终回复返回（--task/RPC 的 done 语义）。
        final_text = ""
    if pending:
        _emit(display_queue, f"\n[挂起] 任务在 ask_user 处等待输入；用 `/resume {thread_id}` 回答。\n",
              source, kind="notice")
    return final_text, usage, thread_id


def resume_pending(agent, thread_id: str, display_queue=None,
                   interrupt_handler: Optional[Callable] = None) -> tuple[bool, str, dict]:
    """跨进程恢复：读取挂起中的 interrupt，回答后继续同一 thread。

    返回 (是否有挂起, 最终回答, 用量)。
    """
    cfg = settings.graph_config()
    handler, sys_prompt = _build_context(agent)
    runtime, tracker, graph, config = _build(agent, handler, sys_prompt, thread_id)
    durability = _durability_for(agent, cfg)
    snapshot = graph.get_state(config)
    pending = list(getattr(snapshot, "interrupts", ()) or ())
    if not pending:
        return False, "", {}
    # 新建 handler 的 working 是空的，而 human/tools 节点每轮用 handler.working
    # 覆盖回写 state；不回填会让 checkpoint 里的工作记忆在恢复瞬间被空副本抹掉。
    saved_working = (snapshot.values or {}).get("working") or {}
    if saved_working:
        handler.working = dict(saved_working)

    handler_interrupt = interrupt_handler or _default_interrupt_handler
    answers = [handler_interrupt(item.value) for item in pending]
    if any(answer is None for answer in answers):
        return True, "", {}
    inputs = Command(resume=answers[0] if len(answers) == 1 else answers)
    left, usage = _consume(graph, inputs, config, runtime, tracker, display_queue,
                           "user", handler_interrupt, durability=durability)
    final_text = _final_text(graph, config)
    agent.last_graph_usage = usage
    _persist_usage(thread_id, usage)
    agent.pending_interrupts = [item.value for item in left]
    return True, final_text, usage

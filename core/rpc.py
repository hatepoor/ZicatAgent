"""JSONL 协议后端：给 Web UI 与自动化脚本提供结构化事件流。

用法：`python agentmain.py --rpc`

协议（stdin 指令 / stdout 事件，均为单行 JSON）：
  -> {"type": "task", "text": "..."}      提交任务
  -> {"type": "answer", "text": "..."}    回答 ask_user 挂起的问题
  -> {"type": "set_model", "index": N}    切换主模型（N 为 0 起索引，任务间生效）
  -> {"type": "get_models", "reveal": false}  读取模型组（默认 API Key 掩码）
  -> {"type": "save_model", "index": N, "config": {...}}  保存到 .env 并 reload
  -> {"type": "get_workspace"}            读取当前/根/默认工作空间
  -> {"type": "set_workspace", "path": "..."}  切换工作空间（不存在则创建）
  -> {"type": "get_sessions"}             读取会话/工作区历史列表
  -> {"type": "new_session"}              开新会话（清空当前 thread）
  -> {"type": "switch_session", "thread_id": "..."}  切换到已有会话
  -> {"type": "abort"}                    中断当前任务
  -> {"type": "exit"}                     退出
  <- {"event": "ready", "engine", "model", "cwd", "commands", "models", "workspace", "sessions"}   commands 为内核斜杠命令表
  <- {"event": "models", "models", "active"}              模型组列表
  <- {"event": "model_switched", "index", "model", "name"} 模型切换完成
  <- {"event": "workspace", "workspace", "workspace_root", "default_workspace"} 工作空间
  <- {"event": "sessions", "sessions", "workspaces", "active_thread_id"}  历史会话
  <- {"event": "session_new"}             新会话已建立
  <- {"event": "session_switched", "record"}  已切换会话
  <- {"event": "delta", "text"}                          助手回复（整段追加）
  <- {"event": "thinking", "text"}                       思考内容增量（折叠展示）
  <- {"event": "tool_call", "name", "args"}              工具调用开始（args 为显示摘要）
  <- {"event": "tool_result", "name", "text", "ok"}      工具结果（多行预览）
  <- {"event": "notice", "text"}                         系统提示（挂起、命令回显等）
  <- {"event": "tool", "name"}                           旧式兜底：仅工具名
  <- {"event": "tool_result", "name", "text"}            旧式兜底：单行预览
  <- {"event": "usage", "requests", "input", "output", "text"}
  <- {"event": "interrupt", "question", "candidates"}
  <- {"event": "done", "text", "usage"}
  <- {"event": "exit"}
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading


class RpcBridge:
    """把 Agent 的 display_queue / interrupt 转成 JSONL 事件。"""

    def __init__(self, out) -> None:
        self.out = out
        self._lock = threading.Lock()  # pump 线程与 ask 线程可能并发 emit
        self._answer = None
        self._answer_event = threading.Event()
        self._pump_thread = None

    def emit(self, payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        try:
            with self._lock:
                self.out.write(line + "\n")
                self.out.flush()
        except (BrokenPipeError, ValueError):
            pass

    # ask_user（graph 引擎的 interrupt）走这里
    def ask(self, value):
        question = value.get("question") if isinstance(value, dict) else str(value)
        candidates = value.get("candidates") if isinstance(value, dict) else []
        self._answer = None
        self._answer_event.clear()
        self.emit({"event": "interrupt", "question": question, "candidates": candidates or []})
        self._answer_event.wait()
        answer = self._answer
        self._answer = None
        return answer

    def answer(self, text):
        self._answer = text
        self._answer_event.set()

    def attach(self, display_queue, agent) -> None:
        thread = threading.Thread(target=self._pump, args=(display_queue, agent), daemon=True)
        self._pump_thread = thread
        thread.start()

    def busy(self) -> bool:
        thread = self._pump_thread
        return bool(thread is not None and thread.is_alive())

    def wait(self, timeout: float = 30.0) -> None:
        """等待当前任务结束（exit 时避免截断 done 事件）。"""
        thread = self._pump_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)

    def _pump(self, display_queue, agent) -> None:
        try:
            while True:
                item = display_queue.get()
                if "next" in item:
                    self.emit(_event_from_item(item))
                if "done" in item:
                    usage = getattr(agent, "last_graph_usage", None) or {}
                    self.emit({"event": "done", "text": item["done"], "usage": usage})
                    break
        finally:
            self._pump_thread = None


def _event_from_item(item: dict) -> dict:
    """display 事件 → RPC 事件；带结构化 kind 的走新协议，纯文本走旧式分类。"""
    kind = item.get("kind")
    if kind == "assistant":
        return {"event": "delta", "text": item["next"]}
    if kind == "delta_token":
        return {"event": "delta", "text": item["next"]}   # token 级增量（真流式）
    if kind == "thinking_delta":
        return {"event": "thinking", "text": item["next"]}  # 思考内容增量
    if kind == "tool_call":
        event = {"event": "tool_call", "name": item.get("name", ""),
                 "args": item.get("args", "")}
        if item.get("call_id"):
            event["call_id"] = item["call_id"]
        return event
    if kind == "tool_result":
        event = {"event": "tool_result", "name": item.get("name", ""),
                 "text": item.get("text", ""), "ok": bool(item.get("ok", True))}
        if item.get("call_id"):
            event["call_id"] = item["call_id"]
        if item.get("payload") is not None:
            event["payload"] = item["payload"]
        return event
    if kind == "usage":
        return {"event": "usage", "text": item.get("next", ""),
                "requests": int(item.get("requests") or 0),
                "input": int(item.get("input") or 0),
                "output": int(item.get("output") or 0),
                "last_input": int(item.get("last_input") or 0),
                "input_per_request": int(item.get("input_per_request") or 0)}
    if kind == "notice":
        return {"event": "notice", "text": item["next"]}
    return _classify_next(item["next"])


def _classify_next(text: str) -> dict:
    stripped = text.strip("\n")
    if stripped.startswith("🛠️ "):
        return {"event": "tool", "name": stripped[2:].strip()}
    if stripped.startswith("📥 "):
        body = stripped[2:]
        name, _, preview = body.partition(": ")
        return {"event": "tool_result", "name": name.strip(), "text": preview.strip()}
    if stripped.startswith("[usage]"):
        body = stripped[len("[usage]"):].strip()
        # \b 锚定，避免 about=2 之类误配出 out=2
        nums = dict(re.findall(r"\b(req|in|out)=(\d+)", body))
        return {"event": "usage", "text": body,
                "requests": int(nums.get("req", "0")),
                "input": int(nums.get("in", "0")),
                "output": int(nums.get("out", "0"))}
    return {"event": "delta", "text": text}


def _model_name(agent) -> str:
    try:
        from core.model_config import list_models
        from engine.runner import _load_llm_no
        models = list_models()
        if not models:
            return "?"
        idx = max(0, min(int(_load_llm_no(agent) or 0), len(models) - 1))
        cfg = models[idx]
        return str(cfg.get("model") or cfg.get("name") or "?")
    except Exception:  # noqa: BLE001 - 仅显示用途
        return "?"


def _slash_commands() -> list[dict]:
    """从 core.commands.HELP（命令表唯一事实源）解析斜杠命令列表，随 ready 下发。

    HELP 行格式为 `命令 [参数]  ……  描述`（描述与参数间以 2+ 空格对齐）。
    """
    try:
        from core.commands import HELP
    except Exception:  # noqa: BLE001 - 仅显示用途
        return []
    commands: list[dict] = []
    seen: set[str] = set()
    for line in HELP.splitlines():
        stripped = line.strip()
        if not stripped.startswith("/"):
            continue
        cells = re.split(r"\s{2,}", stripped, maxsplit=1)
        cmd = cells[0].split()[0]
        desc = cells[1].strip() if len(cells) > 1 else ""
        if desc.startswith("/"):  # /exit  /quit 这类同行别名，不留描述
            desc = ""
        if cmd in seen:
            continue
        seen.add(cmd)
        commands.append({"cmd": cmd, "desc": desc})
    return commands


def _models_payload(agent, reveal: bool = False) -> dict:
    from core.model_config import list_models
    from engine.runner import _load_llm_no
    models = list_models(reveal=reveal)
    active = int(_load_llm_no(agent) or 0)
    try:
        from engine.settings import effective_context_char_cap
        ctx_cap = effective_context_char_cap(active)
    except Exception:  # noqa: BLE001
        ctx_cap = 0
    return {"models": models, "active": active, "context_char_cap": ctx_cap}


def _workspace_payload(agent) -> dict:
    try:
        current = agent.get_workspace()
    except Exception:  # noqa: BLE001
        current = os.getcwd()
    return {"workspace": current,
            "workspace_root": getattr(agent, "workspace_root", current),
            "default_workspace": getattr(agent, "default_workspace",
                                         os.path.abspath(os.path.join(os.getcwd(), "temp")))}


def _sessions_payload(agent) -> dict:
    from core import sessions
    active = getattr(agent, "graph_thread_id", "")
    return {
        "sessions": sessions.list_sessions(limit=100),
        "workspaces": sessions.list_workspaces(),
        "active_thread_id": active,
        "active_workspace": agent.get_workspace(),
        "usage": sessions.load_usage(active) if active else {},
    }


def rpc_main(agent, out) -> None:
    bridge = RpcBridge(out)
    agent._rpc_bridge = bridge
    try:
        _payload = _models_payload(agent)
        _current = _payload["active"]
        _models = _payload["models"]
        _model_list = [c.get("name") or c.get("model", "") for c in _models]
    except Exception:  # noqa: BLE001
        _current, _model_list, _models = 0, [], []
    try:
        _sess = _sessions_payload(agent)
        _sess_title = next(
            (s["title"] for s in _sess["sessions"]
             if s["thread_id"] == _sess["active_thread_id"]), "")
    except Exception:  # noqa: BLE001
        _sess = {"sessions": [], "workspaces": [], "active_thread_id": "",
                 "active_workspace": os.getcwd()}
        _sess_title = ""
    _ws = _workspace_payload(agent)
    try:
        from engine.settings import effective_context_char_cap
        _ctx_cap = effective_context_char_cap(_current)
    except Exception:  # noqa: BLE001
        _ctx_cap = 0
    try:
        from core.session_history import load_history
        _history = load_history(_sess["active_thread_id"])
    except Exception:  # noqa: BLE001
        _history = []
    bridge.emit({"event": "ready", "engine": getattr(agent, "engine", "graph"),
                 "model": _model_name(agent), "cwd": os.getcwd(),
                 "commands": _slash_commands(),
                 "model_list": _model_list, "llm_no": _current,
                 "models": _models, "active": _current,
                 "workspace": _ws["workspace"],
                 "workspace_root": _ws["workspace_root"],
                 "default_workspace": _ws["default_workspace"],
                 "context_char_cap": _ctx_cap,
                 "sessions": _sess["sessions"],
                 "workspaces": _sess["workspaces"],
                 "thread_id": _sess["active_thread_id"],
                 "usage": _sess.get("usage", {}),
                 "history": _history,
                 "session": _sess_title})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            command = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = command.get("type")
        if kind == "task":
            text = str(command.get("text", "")).strip()
            if not text:
                continue
            display_queue = agent.put_task(text, source="user")
            bridge.attach(display_queue, agent)
        elif kind == "answer":
            bridge.answer(str(command.get("text", "")))
        elif kind == "get_sessions":
            try:
                bridge.emit({"event": "sessions", **_sessions_payload(agent)})
            except Exception as e:  # noqa: BLE001
                bridge.emit({"event": "notice", "text": f"读取会话列表失败: {e}"})
        elif kind == "get_history":
            tid = str(command.get("thread_id") or getattr(agent, "graph_thread_id", "") or "")
            try:
                from core.session_history import load_history
                bridge.emit({"event": "history", "thread_id": tid,
                             "history": load_history(tid)})
            except Exception as e:  # noqa: BLE001
                bridge.emit({"event": "notice", "text": f"读取会话历史失败: {e}"})
        elif kind == "new_session":
            if getattr(agent, "is_running", False):
                bridge.emit({"event": "notice",
                             "text": "当前任务仍在运行；先中断再开新会话。"})
            else:
                agent.new_session()
                bridge.emit({"event": "session_new", **_sessions_payload(agent)})
                bridge.emit({"event": "notice", "text": "已开新会话。"})
        elif kind == "switch_session":
            if getattr(agent, "is_running", False):
                bridge.emit({"event": "notice",
                             "text": "当前任务仍在运行；先中断再切换会话。"})
            else:
                try:
                    record = agent.switch_session(str(command.get("thread_id", "")))
                    from core.session_history import load_history
                    bridge.emit({"event": "session_switched",
                                 "record": record,
                                 "history": load_history(record.get("thread_id", "")),
                                 **_sessions_payload(agent)})
                    bridge.emit({"event": "notice",
                                 "text": f"已切换到会话「{record.get('title') or record.get('thread_id')}」。"})
                except Exception as e:  # noqa: BLE001
                    bridge.emit({"event": "notice", "text": f"切换会话失败: {e}"})
        elif kind == "delete_session":
            if getattr(agent, "is_running", False):
                bridge.emit({"event": "notice",
                             "text": "当前任务仍在运行；先中断再删除会话。"})
            else:
                from core import sessions as _sessions
                tid = str(command.get("thread_id", ""))
                active = tid == getattr(agent, "graph_thread_id", "")
                result = _sessions.delete_session(tid)
                if not result.get("ok"):
                    bridge.emit({"event": "notice", "text": f"删除会话失败: {result.get('error')}"})
                else:
                    if active:
                        agent.new_session()
                    bridge.emit({"event": "sessions", **_sessions_payload(agent)})
                    if active:
                        bridge.emit({"event": "session_new", **_sessions_payload(agent)})
                    kept = result.get("files_kept_reason")
                    bridge.emit({"event": "notice",
                                 "text": f"已删除会话「{result.get('title') or tid}」"
                                         + (f"；文件保留：{kept}" if kept else "，文件已删除")})
        elif kind == "delete_workspace":
            if getattr(agent, "is_running", False):
                bridge.emit({"event": "notice",
                             "text": "当前任务仍在运行；先中断再删除工作区。"})
            else:
                from core import sessions as _sessions
                target = str(command.get("path", ""))
                active_record = (_sessions.get(agent.graph_thread_id)
                                 if getattr(agent, "graph_thread_id", "") else None)
                active_ws = os.path.abspath((active_record or {}).get("workspace_dir") or "")
                target_abs = os.path.abspath(os.path.expanduser(target)) if target else ""
                reset = bool(active_ws and target_abs and (
                    active_ws == target_abs or active_ws.startswith(target_abs + os.sep)))
                result = _sessions.delete_workspace(target)
                if not result.get("ok"):
                    bridge.emit({"event": "notice",
                                 "text": f"删除工作区失败: {result.get('error')}"})
                else:
                    if reset:
                        agent.new_session()
                        try:
                            agent.set_workspace(agent.default_workspace, exact=False)
                        except Exception:  # noqa: BLE001
                            pass
                        bridge.emit({"event": "workspace",
                                     **_workspace_payload(agent), "changed": True})
                        bridge.emit({"event": "session_new", **_sessions_payload(agent)})
                    bridge.emit({"event": "sessions", **_sessions_payload(agent)})
                    kept = result.get("files_kept_reason")
                    bridge.emit({"event": "notice",
                                 "text": f"已删除工作区 {result.get('path')}："
                                         f"会话 {result.get('sessions_deleted', 0)} 个"
                                         + (f"；文件保留：{kept}" if kept else "，文件已删除")})
        elif kind == "get_models":
            try:
                bridge.emit({"event": "models",
                             **_models_payload(agent, reveal=bool(command.get("reveal")))})
            except Exception as e:  # noqa: BLE001
                bridge.emit({"event": "notice", "text": f"读取模型配置失败: {e}"})
        elif kind == "save_model":
            try:
                from core.model_config import save_model
                idx = int(command.get("index", 0))
                cfg = command.get("config") or {}
                models = save_model(idx, cfg)
                bridge.emit({"event": "models", "models": models,
                             "active": _models_payload(agent)["active"]})
                bridge.emit({"event": "notice",
                             "text": f"模型 [{idx + 1}] 已保存（下个任务生效）"})
            except Exception as e:  # noqa: BLE001
                bridge.emit({"event": "notice", "text": f"保存模型失败: {e}"})
        elif kind == "get_workspace":
            try:
                bridge.emit({"event": "workspace", **_workspace_payload(agent)})
            except Exception as e:  # noqa: BLE001
                bridge.emit({"event": "notice", "text": f"读取工作空间失败: {e}"})
        elif kind == "set_workspace":
            try:
                agent.set_workspace(command.get("path") or None, exact=True)
                payload = _workspace_payload(agent)
                bridge.emit({"event": "workspace", **payload, "changed": True})
                bridge.emit({"event": "sessions", **_sessions_payload(agent)})
                bridge.emit({"event": "notice",
                             "text": f"工作空间已切换 → {payload['workspace']}"})
            except Exception as e:  # noqa: BLE001
                bridge.emit({"event": "notice", "text": f"切换工作空间失败: {e}"})
        elif kind == "set_model":
            try:
                idx = int(command.get("index", 0))
                from engine.runner import set_llm_no
                from core.model_config import list_models
                cfgs = list_models()
                if 0 <= idx < len(cfgs):
                    set_llm_no(agent, idx)
                    bridge.emit({"event": "model_switched", "index": idx,
                                 "active": idx,
                                 "model": cfgs[idx].get("model", ""),
                                 "name": cfgs[idx].get("name", "")})
                else:
                    bridge.emit({"event": "notice", "text": f"模型索引越界 0-{len(cfgs) - 1}"})
            except (TypeError, ValueError):
                bridge.emit({"event": "notice", "text": "set_model 需要 integer index"})
        elif kind == "abort":
            bridge.answer(None)   # 让挂起中的 interrupt 以“未回答”退出
            agent.abort()
        elif kind == "exit":
            if bridge.busy():
                bridge.answer(None)
                agent.abort()
                bridge.wait(30)
            break

    bridge.emit({"event": "exit"})
    try:
        agent.task_queue.put("__rpc_exit__")
    except Exception:  # noqa: BLE001 - 退出路径不抛错
        pass

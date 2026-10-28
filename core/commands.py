"""内核斜杠命令分发：Web UI / RPC / 自动化入口共用，不依赖任何终端前端。

约定：`handle()` 的返回值
  - ``None`` —— 命令已被消费，结果已通过 ``emit`` 输出；
  - ``str``  —— 要投递给 agent 的查询（可能被改写，例如 /review 注入 prompt）。

未识别的斜杠命令原样返回，交给 agent 自行处理。
"""
from __future__ import annotations

import os
from typing import Callable, Optional

import core.modes as modes
import core.plan_state as plan_state
import core.review as review

Emit = Callable[[str], None]

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HELP = """zicatAgent 命令
  /help                    显示本帮助
  /review [范围]           在当前会话内做对抗式代码评审（默认审 git diff）
  /continue                列出 graph 会话（同 /threads）
  /plan                    查看当前计划进度
  /plan <plan.md>          绑定计划文件（支持绝对/相对路径）
  /model [N]               查看模型详情/切换模型（N=序号，1 起）
  /model set <N> k=v ...   修改模型配置（base_url/api_key/model/name/context_window/max_tokens/temperature/provider/reasoning_effort）
  /effort [level]          查看/设置当前模型思考强度（off/low/medium/high/xhigh/max）
  /workspace [路径]        查看或切换工作空间（默认 当前目录/temp）
  /cost                    查看 graph 引擎 token 用量与上下文配置
  /scheduler               列出可自启动的 reflect 服务与定时任务
  /scheduler start <名字>  后台启动 reflect/<名字>.py
  /scheduler stop <名字>   停止运行中的 reflect 服务
  /scheduler refresh       清空进程扫描缓存后重新探测
  /goal [目标]             进入 Goal 模式
  /team [集群目标]         进入 Goal Team 多 worker 协作
  /autorun [种子]          进入自主运行模式
  /distill [目标]        启用技能蒸馏
  /update [备注]           更新仓库并报告影响面
  /threads                 列出 LangGraph 会话
  /resume <标题|前缀>      下一个任务接着该会话跑
  /new [一句话]            开新会话（标题取自第一句话）
  /del <标题>              删除会话对话与检查点（产物目录保留）
  /memory index            查看 L1 索引
  /memory search <关键词>  检索记忆库
  /rewind [n]              列出/回退对话检查点（graph）
  /rewind files|file <id>  文件回退点 / 回退文件
  /exit  /quit             退出
其余内容直接作为任务发给 agent。
"""


def _messages(agent):
    return getattr(agent, "history", None) or []


def _cmd_model(agent, rest: str, emit: Emit) -> None:
    """/model：查看详情；N 切换；set N k=v 修改配置。"""
    from core.model_config import list_models, save_model
    from engine.runner import _load_llm_no, set_llm_no

    models = list_models()
    current = int(_load_llm_no(agent) or 0)
    rest = (rest or "").strip()

    if not rest:
        emit("模型配置：")
        if not models:
            emit("  （未找到模型组；请在 .env 添加 ZICAT_OAI_1__APIBASE/APIKEY/MODEL）")
            return
        for i, c in enumerate(models):
            mark = " ← 当前" if i == current else ""
            emit(f"  [{i + 1}] {c.get('name') or c.get('model')}{mark}")
            emit(f"      Base URL: {c.get('base_url') or '—'}")
            emit(f"      API Key : {c.get('api_key') or '—'}")
            emit(f"      模型名  : {c.get('model') or '—'}")
            emit(f"      上下文  : {c.get('context_window') or '—'} | "
                 f"最大输出: {c.get('max_tokens') or '—'} | "
                 f"temperature: {c.get('temperature') if c.get('temperature') != '' else '—'}")
            emit(f"      接口    : {c.get('provider') or 'openai'} | "
                 f"思考强度: {c.get('reasoning_effort') or '未设置'}")
        emit("  修改：/model set <序号> base_url=... api_key=... model=... "
             "context_window=... max_tokens=...")
        return

    parts = rest.split()
    if parts[0].lower() == "set":
        if len(parts) < 3:
            emit("用法: /model set <序号> base_url=... api_key=... model=...")
            return
        try:
            index = int(parts[1]) - 1
        except ValueError:
            emit("序号应为数字（1 起）")
            return
        aliases = {
            "base_url": "base_url", "baseurl": "base_url", "apibase": "base_url",
            "api_key": "api_key", "apikey": "api_key", "key": "api_key",
            "model": "model", "name": "name",
            "context": "context_window", "context_window": "context_window",
            "max_tokens": "max_tokens", "max_output": "max_tokens", "max": "max_tokens",
            "temperature": "temperature", "temp": "temperature",
            "provider": "provider", "interface": "provider",
            "reasoning_effort": "reasoning_effort", "effort": "reasoning_effort",
        }
        values = {}
        for item in parts[2:]:
            field, sep, value = item.partition("=")
            if not sep:
                emit(f"忽略无效参数: {item}（需要 k=v）")
                continue
            key = aliases.get(field.lower())
            if not key:
                emit(f"忽略未知字段: {field}")
                continue
            values[key] = value
        try:
            save_model(index, values)
            emit(f"✅ 模型 [{index + 1}] 已保存（下个任务生效）")
        except Exception as e:  # noqa: BLE001
            emit(f"保存失败: {e}")
        return

    if not rest.isdigit():
        emit(f"/model 参数应为序号（1 起）或 set ...，收到: {rest}")
        return
    n = int(rest) - 1
    if n < 0 or n >= len(models):
        emit(f"序号超出范围 1-{len(models)}")
        return
    set_llm_no(agent, n)
    c = models[n]
    emit(f"模型已切换 → [{n + 1}] {c.get('name') or c.get('model')}（下个任务生效）")


def _cmd_effort(agent, rest: str, emit: Emit) -> None:
    """/effort：查看或设置当前模型的思考强度。"""
    from core.model_config import REASONING_EFFORT_OPTIONS, list_models, save_model
    from engine.runner import _load_llm_no

    models = list_models()
    if not models:
        emit("没有可用的模型配置")
        return
    index = max(0, min(int(_load_llm_no(agent) or 0), len(models) - 1))
    current = models[index]
    provider = str(current.get("provider") or "openai")
    levels = REASONING_EFFORT_OPTIONS.get(provider, [])
    value = (rest or "").strip().lower()

    if not value:
        emit(f"当前模型 [{index + 1}] {current.get('name') or current.get('model') or '?'}")
        emit(f"接口: {provider}")
        emit(f"思考强度: {current.get('reasoning_effort') or '未设置'}")
        if levels:
            emit("可选: " + " / ".join(levels))
        return

    if value not in levels:
        emit(f"用法: /effort {'|'.join(levels) or '<当前接口无可用档位>'}")
        return
    try:
        save_model(index, {"reasoning_effort": value})
    except Exception as exc:  # noqa: BLE001 - 命令失败回显给用户
        emit(f"保存失败: {exc}")
        return
    emit(f"✅ 模型 [{index + 1}] 思考强度 → {value}（下个任务生效）")


def _cmd_workspace(agent, rest: str, emit: Emit) -> None:
    rest = (rest or "").strip()
    try:
        if not rest:
            emit(f"当前工作空间: {agent.get_workspace()}")
            emit(f"工作空间根目录: {agent.workspace_root}")
            emit("用法: /workspace <路径>（默认 当前目录/temp；不存在会自动创建）")
            return
        path = agent.set_workspace(rest, exact=True)
        emit(f"✅ 工作空间已切换 → {path}")
    except Exception as e:  # noqa: BLE001
        emit(f"切换失败: {e}")


def _cmd_cost(agent, emit: Emit) -> None:
    from engine import settings as graph_settings
    from engine.runner import _load_llm_no

    cfg = graph_settings.graph_config()
    llm_no = _load_llm_no(agent)
    cap = graph_settings.effective_context_char_cap(llm_no, cfg)
    lines = ["## 用量"]
    graph_usage = getattr(agent, "last_graph_usage", None) or {}
    if graph_usage.get("requests"):
        lines.append(
            f"当前会话最近任务: 请求 {graph_usage.get('requests', 0)} | "
            f"输入 {graph_usage.get('input', 0):,} | 输出 {graph_usage.get('output', 0):,}"
        )
        last_input = graph_usage.get("last_input") or graph_usage.get("input_per_request")
        if last_input:
            lines.append(f"最近请求上下文: {int(last_input):,} tok")
    else:
        lines.append("当前会话暂无 LLM 用量记录（本进程内还没跑任务，或该会话尚未产生用量）。")
    lines.append(f"引擎视图预算: {int(cap):,} 字符")
    lines.append(f"最大轮数: {cfg.get('max_turns')}")
    thread = getattr(agent, "graph_thread_id", "") or "（尚无）"
    lines.append(f"当前会话: {thread}")
    emit("\n".join(lines))


def _cmd_scheduler(args: str, emit: Emit) -> None:
    parts = args.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub == "refresh":
        modes.invalidate_running_cache()
        emit("已清空进程扫描缓存。")
        return

    if sub in ("start", "stop"):
        if not rest:
            emit(f"用法: /scheduler {sub} <名字>")
            return
        # 接受 `scheduler` 或 `reflect/scheduler.py` 两种写法
        name = rest
        if sub == "start":
            stem = name[len("reflect/"):].rsplit(".py", 1)[0] if name.startswith("reflect/") else name.rsplit(".py", 1)[0]
            ok, msg = modes.start_reflect_task(stem)
        else:
            full = name if name.startswith("reflect/") else f"reflect/{name}"
            if not full.endswith(".py"):
                full += ".py"
            ok, msg = modes.stop_service(full)
        emit(("✅ " if ok else "❌ ") + msg)
        return

    services = modes.list_launchable_services()
    running = modes.running_services()
    tasks = modes.list_scheduler_tasks()
    lines = ["## 可自启动的 reflect 服务"]
    if services and not running:
        try:
            import psutil  # noqa: F401
        except Exception:
            lines.append("（未安装 psutil：无法探测运行状态，下面的「未运行」不可信；"
                         "安装后可启停服务）")
    if not services:
        lines.append("（reflect/ 下没有可启动的脚本）")
    for svc in services:
        name = svc["name"]
        mark = "● 运行中" if name in running else "○ 未运行"
        doc = (svc.get("doc") or "").strip().splitlines()
        desc = f"  — {doc[0]}" if doc else ""
        lines.append(f"  {mark}  {name}{desc}")
    lines.append("")
    lines.append("## 定时任务（sche_tasks/*.json）")
    if not tasks:
        lines.append("（暂无定时任务）")
    for t in tasks:
        state = "启用" if t.get("enabled") else "停用"
        lines.append(f"  [{state}] {t['name']}  schedule={t.get('schedule') or '-'}")
    lines.append("")
    lines.append("用法: /scheduler start <名字> | stop <名字> | refresh")
    emit("\n".join(lines))


def _cmd_threads(emit: Emit) -> None:
    from core import sessions

    try:
        rows = sessions.list_sessions()
    except Exception as exc:  # noqa: BLE001 - 只读列表失败不致命
        emit(f"读取会话注册表失败: {exc}")
        return
    if not rows:
        emit("尚无会话（新任务会自动登记）。")
        return
    lines = ["## 会话（thread → 检查点数，最近在前）"]
    for thread_id, count in rows:
        lines.append(f"  {thread_id}  ({count} 个检查点)")
    lines.append("")
    lines.append("用 `/resume <thread_id>` 让下一个任务接着该会话跑。")
    emit("\n".join(lines))


def _cmd_rewind(agent, args: str, emit: Emit) -> None:
    from engine.checkpointer import list_checkpoints
    from engine import settings as graph_settings

    thread = getattr(agent, "graph_thread_id", "")
    if not thread:
        emit("当前没有 graph 会话（先跑一个任务，或用 /resume 指定 thread）。")
        return
    parts = (args or "").split(maxsplit=1)
    sub = parts[0].lower() if parts else ""

    if sub in ("files", "file"):
        from engine.rewind import TaskRewind
        rw = TaskRewind(thread, graph_settings.ROOT, graph_settings.ROOT / "temp")
        if sub == "file":
            if len(parts) < 2:
                emit("用法: /rewind file <节点id>（先用 /rewind files 查看）")
                return
            try:
                changed = rw.apply(parts[1])
            except Exception as exc:  # noqa: BLE001
                emit(f"文件回退失败: {exc}")
                return
            emit("文件已回退: " + ", ".join(f"{p} ({s})" for p, s in changed))
            return
        if not rw.exists():
            emit("没有文件回退记录（worldline 只记录 file_write/file_patch）。")
            return
        lines = ["## 文件回退点（新→旧）"]
        for node_id, title in rw.nodes()[:20]:
            lines.append(f"  {node_id}  {title}")
        lines.append("用 `/rewind file <节点id>` 只回退文件。")
        emit("\n".join(lines))
        return

    rows = list_checkpoints(graph_settings.graph_config().get("checkpointer"), thread, 20)
    if not rows:
        emit("该会话没有检查点。")
        return
    if not args or sub in ("list", ""):
        lines = [f"## 对话回退点（thread={thread}，1=最新）"]
        for idx, checkpoint_id in enumerate(rows, 1):
            lines.append(f"  [{idx}] {checkpoint_id}")
        lines.append("")
        lines.append("用 `/rewind <n>` 让下一个任务从该检查点继续；`/rewind files` 看文件回退点。")
        emit("\n".join(lines))
        return
    try:
        n = int(sub)
    except ValueError:
        emit("用法: /rewind [n] | /rewind files | /rewind file <节点id>")
        return
    if not 1 <= n <= len(rows):
        emit(f"序号超出范围（1–{len(rows)}）。")
        return
    agent.graph_rewind_to = rows[n - 1]
    emit(f"下一个任务将从检查点 {rows[n - 1]} 继续（仅对话状态；文件回退用 /rewind file）。")


def _cmd_memory(args: str, emit: Emit) -> None:
    from memstore.db import Database
    from memstore.repository import MemoryStore
    from engine import settings as graph_settings

    parts = args.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""
    db_path = graph_settings.graph_config().get("memory_db")
    try:
        db = Database(db_path, init=True)
    except Exception as exc:  # noqa: BLE001 - 记忆库缺失时给出可读提示
        emit(f"记忆库不可用: {exc}")
        return
    with db:
        store = MemoryStore(db)
        if sub == "search":
            if not rest:
                emit("用法: /memory search <关键词>")
                return
            hits = store.search(rest, limit=8)
            if not hits:
                emit("没有命中。")
                return
            lines = [f"## 记忆检索: {rest}"]
            for item in hits:
                lines.append(f"  [{item.layer}/{item.kind}] {item.name} — {item.summary}")
            emit("\n".join(lines))
            return
        if sub in ("", "index"):
            emit(store.render_l1(log=False))
            return
        emit("用法: /memory index | /memory search <关键词>")


def _cmd_resume(agent, arg: str, emit: Emit) -> None:
    if not arg:
        emit("用法: /resume <标题或前缀>（先用 /threads 查看；当前任务不受影响）")
        return
    from core import sessions
    try:
        rec, cands = sessions.find(arg)
    except Exception as exc:  # noqa: BLE001
        emit(f"会话注册表不可用: {exc}")
        return
    if rec is None:
        emit("匹配到多个会话：" + " / ".join(c[1] for c in cands[:5]))
        return
    arg = rec[0]                      # thread_id（LangGraph 真主键）
    _ws = rec[2]                      # 会话绑定的工作目录
    setattr(agent, "workspace_root", os.path.dirname(_ws) if _ws else None)
    setattr(agent, "workspace_exact", False)
    setattr(agent, "graph_thread_id", arg)
    try:
        from engine.runner import resume_pending
    except Exception as exc:  # noqa: BLE001 - graph 依赖未安装时给出可读提示
        emit(f"graph 引擎不可用: {exc}")
        return
    try:
        class _Sink:
            def put(self, item):
                return None

        found, text, usage = resume_pending(agent, arg, display_queue=_Sink())
    except Exception as exc:  # noqa: BLE001 - 恢复失败不让整个 CLI 崩
        emit(f"恢复失败: {type(exc).__name__}: {exc}")
        return
    if not found:
        emit(f"会话 {arg} 没有挂起的中断；下一个任务将继续该 thread。")
        return
    if text:
        emit(text)
    if usage.get("requests"):
        emit(f"[usage] req={usage['requests']} in={usage['input']} out={usage['output']}")
    if getattr(agent, "pending_interrupts", []):
        emit("仍有挂起输入，可再次 /resume 回答。")


def _cmd_plan(agent, args: str, emit: Emit) -> None:
    if args:
        cand = args.strip().strip('"').strip("'")
        if not os.path.isabs(cand):
            cand = os.path.join(_ROOT, cand)
        if not os.path.isfile(cand):
            alt = os.path.join(_ROOT, "temp", args.strip())
            if os.path.isfile(alt):
                cand = alt
            else:
                emit(f"找不到计划文件: {args}")
                return
        bound = plan_state.bind_plan_path(agent, cand, _ROOT)
        if not bound:
            emit(f"计划文件为空或不可绑定: {cand}")
            return
        emit(f"已绑定计划: {bound}")

    path = plan_state.resolve_path(agent, messages=_messages(agent))
    if not path:
        emit("未检测到计划。用法: /plan <plan.md> 绑定，/plan 查看进度。")
        return
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        emit(f"读取计划失败: {exc}")
        return
    items = plan_state.extract(text)
    done, total = plan_state.summary(items)
    lines = [f"计划: {path}", f"进度: {done}/{total}"]
    if not items:
        lines.append("（未解析到 - [ ] / - [x] 条目）")
    for idx, (content, status) in enumerate(items, 1):
        lines.append(f"  {'✔' if status == 'done' else '○'} {idx}. {content}")
    emit("\n".join(lines))


def handle(agent, raw_query: str, emit: Emit = print) -> Optional[str]:
    """分发斜杠命令。返回 None 表示已消费，返回 str 表示要投递给 agent 的查询。"""
    s = (raw_query or "").strip()
    if not s.startswith("/"):
        return raw_query

    cmd, _, rest = s.partition(" ")
    cmd = cmd.lower()
    rest = rest.strip()

    if cmd in ("/help", "/?", "/h"):
        emit(HELP)
        return None
    if cmd in ("/exit", "/quit"):
        setattr(agent, "_exit_requested", True)
        emit("Bye.")
        return None
    if cmd == "/model":
        _cmd_model(agent, rest, emit)
        return None
    if cmd == "/effort":
        _cmd_effort(agent, rest, emit)
        return None
    if cmd == "/workspace":
        _cmd_workspace(agent, rest, emit)
        return None
    if cmd == "/cost":
        _cmd_cost(agent, emit)
        return None
    if cmd == "/new":
        if hasattr(agent, "new_session"):
            agent.new_session()
        else:
            setattr(agent, "graph_thread_id", "")   # 下个任务自动注册为新会话
        emit("已开新会话" + (f"，标题候选：{rest[:10]}" if rest else "；标题将取自你的第一句话") + "。")
        return None
    if cmd == "/del":
        from core import sessions
        rec, cands = sessions.find(rest)
        if rec is None:
            emit("无匹配会话" + (f"：{' / '.join(c[1] for c in cands[:5])}" if cands else f"（{rest}）"))
            return None
        sessions.delete(rec[0])
        emit(f"已删除会话「{rec[1]}」的对话与检查点。产物目录（如 {rec[2]}）未动，需清理请手动。")
        return None
    if cmd == "/continue":
        if rest:
            emit("/continue N 已随文本日志恢复一并移除；请用 /threads 选择会话后 /resume <id>。")
            return None
        _cmd_threads(emit)
        return None
    if cmd == "/review":
        body = review.parse_command(s)
        if body is None:
            return s
        result = review.handle(agent, body, emit)
        return None if result is None else result
    if cmd == "/plan":
        _cmd_plan(agent, rest, emit)
        return None
    if cmd == "/scheduler":
        _cmd_scheduler(rest, emit)
        return None
    if cmd == "/threads":
        _cmd_threads(emit)
        return None
    if cmd == "/resume":
        _cmd_resume(agent, rest, emit)
        return None
    if cmd == "/memory":
        _cmd_memory(rest, emit)
        return None
    if cmd == "/rewind":
        _cmd_rewind(agent, rest, emit)
        return None
    if cmd in ("/goal", "/team", "/autorun", "/distill", "/update"):
        prompt = modes.prompt_for(cmd, rest)
        return prompt or s
    return s

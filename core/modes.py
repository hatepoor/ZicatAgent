"""斜杠命令 prompt 构造器 + 调度任务发现。

Goal: 供 CLI / 任意调用方复用的「模式入口」提示词构造器（与 UI 无关）。
调用方只需把 `/update`, `/autorun`, `/distill`, `/goal`, `/team`
转发到对应的 `build_*_prompt(args)`，并用
`list_scheduler_tasks()` / `start_scheduler_task()` 支撑 `/scheduler`。

设计（按用户 2026-05-27 要求）：
- 除 `/scheduler` 外的命令都是*prompt 注入*：我们构造一段 system 风格的请求，
  作为普通用户消息喂给主 agent（调用方可以自行决定是否把原始 `/cmd ...`
  显示成可见气泡）。这样 agent 始终留在会话内，能照常用上原本该用的
  所有工具/SOP，本文件也就不含任何 LLM 逻辑。
- `/scheduler` 是唯一例外 —— 它直接操作本地 FS 状态（`sche_tasks/*.json`）
  并复用已有的 scheduler 守护进程，不需要 LLM。
- 所有 prompt 都刻意*点名*相关 SOP 文件，让 agent 动手前先重读
  （对应 CONSTITUTION 规则 2：SOP 优先）。

本模块只依赖标准库 + rich，不依赖任何前端。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import subprocess
import time
from pathlib import Path
from typing import Optional


_USER_SHELL: tuple[list[str], str] | None = None


# Repo root = core/ 的父目录。
_ROOT = Path(__file__).resolve().parent.parent

# 语言解析放在这里（不作为正式参数传入），这样每个 prompt 构造器都保持单参数，
# TUI 调用点也不用关心哪个 prompt 恰好是双语的。真相来源依次为：
#   1. `ZICAT_LANG` 环境变量（可脚本化覆盖；与 tui_v3 约定一致）
#   2. tui_v3 持久化的设置文件（路径同 tui_v3.py:_SETTINGS_PATH）
#   3. 系统 locale（zh* → 'zh'，否则 'en'）
# 用户在 tui_v3 内切换语言（set_lang 会持久化）后，下次调用这里会自动跟上
# —— 没有正式耦合，只是一个共享文件。
_SETTINGS_PATH = _ROOT / "temp" / "tui_v3_settings.json"


def _current_lang() -> str:
    env = (os.environ.get("ZICAT_LANG") or "").strip().lower()
    if env in ("zh", "en"):
        return env
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            saved = (json.load(f) or {}).get("lang")
        if saved in ("zh", "en"):
            return saved
    except Exception:
        pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "")
        if v:
            return "zh" if v.lower().startswith("zh") else "en"
    return "en"


# ----- prompt 构造器（纯函数，无 I/O）--------------------------------------
# SOP 路径在下面每个构造器里以内联字面量字符串写出：字面量自带说明、就近可读，
# 而路径过期的故障半径为零（prompt 只是给智能 agent 的提示，它会自己重读目录 /
# 在 SOP 移位时发问）—— 所以我们刻意*不*把它包进「注册表 + 存在性检查」机制。

def _tail(args_text: str, label: str = "额外指示") -> str:
    """把斜杠命令之后的用户参数作为自由形式后缀追加。

    用户用法模式（2026-05-27）：基础 prompt 是固定注入、会点名 SOP 路径；
    用户在 `/cmd ` 后面输入的内容原样追加，用来补充本次调用的额外提示
    （例如 `/distill https://github.com/...` 或 `/goal 调研 X，预算 50k token`）。
    """
    extra = (args_text or "").strip()
    return f"\n\n{label}: {extra}" if extra else ""


def build_update_prompt(args_text: str = "") -> str:
    """纯 prompt 的 /update 编排：从当前 git remote 更新并报告影响面。"""
    root = str(_ROOT)
    if _current_lang() == "en":
        return f"""Update this zicatAgent checkout from its current git remote.
Run every git command from the repo root `{root}` (cd there first, or use `git -C "{root}"`):
your cwd is a subdirectory, where `-- <file>` pathspecs fail to match root-relative paths.
1. `git fetch --all --prune`; note the current branch and local commits ahead.
2. Preview incoming commits (short hash + subject + date) and a changed-files summary.
3. `git pull --ff-only`; if it fails, report the reason and stop. Do not force-push or hard-reset.
4. Summarize: branch HEAD, distance vs remote, per-file impact, actions the user must take.
{_tail(args_text, "Extra instructions")}"""
    return f"""请从当前 git remote 更新 zicatAgent 仓库。
所有 git 命令一律在仓库根目录 `{root}` 下执行（先 cd 过去，或用 `git -C "{root}"`）：
你的 cwd 是子目录，`-- <file>` 按 cwd 解析，匹配不上根相对路径。
1. `git fetch --all --prune`；确认当前分支及领先/落后情况。
2. 预览：即将合入的提交（短 hash + 标题 + 日期）及变更文件摘要。
3. `git pull --ff-only`；失败则报告原因并停止，不要强推或硬重置。
4. 小结：分支 HEAD、与远端差距、逐文件影响、需要用户处理的事项。
{_tail(args_text)}"""



def build_autorun_prompt(args_text: str = "") -> str:
    return (
        "请进入「自主探索 / autonomous 模式」：先读 "
        "memory/kb/autonomous_operation_sop.md。"
        "全程自驱，不可逆 / 高风险动作先 ask_user ，"
        "结案给一份简明回执（做了什么 / 产物在哪 / 下一步）。"
        f"{_tail(args_text, '任务种子')}"
    )


def build_distill_prompt(args_text: str = "") -> str:
    return (
        "请启用 Distill 模式吞噬 / 蒸馏外部项目到本仓库：先读 "
        "memory/kb/distill_sop.md。"
        "没有目标先 ask_user 取 GitHub 仓库 / 本地路径 / 能力描述。"
        f"{_tail(args_text, '目标技能/仓库')}"
    )


def build_goal_prompt(args_text: str = "") -> str:
    return (
        "请进入 Goal 模式：先读 memory/kb/goal_mode_sop.md。"
        "若未给目标，先 ask_user 一次性问清：一句话目标 + condition 约束。"
        f"{_tail(args_text, '用户目标')}"
    )


def build_team_prompt(args_text: str = "") -> str:
    return (
        "请进入 Goal Team 模式（多 worker 协作版 goal）：先读 "
        "memory/kb/goal_team_sop.md。"
        "集群目标 / worker 配额 / 终止条件未明确时先 ask_user 补齐再启动。"
        f"{_tail(args_text, '集群目标')}"
    )


# ----- /scheduler：reflect 任务发现 + 启动 -------------------------------

# ----- 可自启动的服务（当前只有 reflect/ 下的监控脚本）--------------------

_SERVICE_EXCLUDES = {"goal_mode.py"}


def _sniff_doc(p) -> str:
    """尽力取出模块 docstring 的首行（只读前 ~40 行，开销很低）。"""
    try:
        head = p.read_text(encoding="utf-8", errors="ignore").splitlines()[:40]
        joined = "\n".join(head)
        for q in ('"""', "'''"):
            i = joined.find(q)
            if i != -1:
                j = joined.find(q, i + 3)
                if j != -1:
                    body = joined[i + 3:j].strip()
                    if body:
                        return body.splitlines()[0].strip()
    except Exception:
        pass
    return ""


def list_launchable_services() -> list[dict]:
    """列出可自启动的服务——当前只含 `reflect/` 下的监控脚本。

    来源：
      • reflect/*.py   （不以 '_' 开头、不在排除名单内）
          → cmd = [python, agentmain.py, --reflect, reflect/<f>]

    返回 [{name, cmd, doc, kind}]，其中 `name` 是仓库相对路径
    （'reflect/foo.py'），同时充当选择器的取值。
    """
    out: list[dict] = []
    refl = _ROOT / "reflect"
    if refl.is_dir():
        for p in sorted(refl.glob("*.py")):
            if p.name.startswith("_") or p.name in _SERVICE_EXCLUDES:
                continue
            rel = "reflect/" + p.name
            out.append({
                "name": rel,
                "cmd": [sys.executable, "agentmain.py", "--reflect", rel],
                "doc": _sniff_doc(p),
                "kind": "reflect",
            })
    return out


# ----- 运行状态探查（bug#4）-----------------------------------------------
# 为什么用 psutil 扫 cmdline，而不是维护一份「由我们启动的 pid」注册表？
#   • 上一次运行留下的进程、或由其他启动器启动的服务也必须能被认出 —— 否则
#     /scheduler 会毫无顾忌地再起一个重复实例。
#   • 绑定在本进程上的注册表会随本进程重启而消失，但服务本身仍在跑
#     （CREATE_NEW_PROCESS_GROUP）。跨启动器、跨重启都成立的唯一真相来源，
#     只有扫 cmdline。
# 代价：每次打开 /scheduler 多花约 30ms，且按 cmdline 尾部匹配，所以两份 zicatAgent
# 检出可能撞车。我们接受这一点 —— 用两个 clone 跑两份 zicatAgent 本来就不是受支持
# 的配置。

def _match_service(cmdline: list[str], svc: dict) -> bool:
    """这个 OS 进程是否属于 `svc`？按末尾的脚本参数匹配
    （当前只有 reflect 任务，形如 `reflect/foo.py`），
    该参数在 `python` / `pythonw` / venv shim 之间都不变。

    reflect 检测过去要求 cmdline 里同时有 `agentmain.py` 和 reflect 路径。
    这会把直接启动的任务拒之门外（`python reflect/scheduler.py`，由开发脚本
    或更早用过其他启动器拉起）——它们明明活着，在 /scheduler 里却显示未勾选。
    只匹配路径能同时覆盖两种方式；`running_services` 的 Python 进程预过滤
    则挡住误报（grep、开着该文件的编辑器）。"""
    if not cmdline:
        return False
    rel = svc["name"]  # 'reflect/foo.py'
    rel_norm = rel.replace("/", os.sep)
    return any(rel_norm in (a or "") or rel in (a or "")
               for a in cmdline)


# 2s TTL 缓存 + 名称预过滤：冷启动 ~2.1s → ~1.0s，热路径 ~0ms。
# cmdline() 是每个进程的开销；只对 python 类幸存者付这笔钱。
_RUNNING_CACHE: tuple[float, dict[str, int]] | None = None
_RUNNING_TTL = 2.0


def invalidate_running_cache() -> None:
    """丢弃快照。启动/停止后调用，让下一次读取拿到最新状态。"""
    global _RUNNING_CACHE
    _RUNNING_CACHE = None


def running_services(use_cache: bool = True) -> dict[str, int]:
    """存活服务的 {service_name: pid}。psutil 缺失时返回 {}。"""
    global _RUNNING_CACHE
    if use_cache and _RUNNING_CACHE and time.time() - _RUNNING_CACHE[0] < _RUNNING_TTL:
        return dict(_RUNNING_CACHE[1])
    try:
        import psutil  # type: ignore
    except Exception:
        return {}
    svcs = list_launchable_services()
    out: dict[str, int] = {}
    me = os.getpid()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["pid"] == me:
                continue
            nm = (proc.info.get("name") or "").lower()
            if "python" not in nm and "py.exe" not in nm:
                continue
            cmd = proc.cmdline()
        except Exception:
            continue
        for svc in svcs:
            if svc["name"] not in out and _match_service(cmd, svc):
                out[svc["name"]] = proc.info["pid"]
                break
    _RUNNING_CACHE = (time.time(), dict(out))
    return out


def stop_service(name: str) -> tuple[bool, str]:
    """若服务 `name` 正在运行则终止它。返回 (ok, message)。

    发送等价于 SIGTERM 的信号（Windows 上 Popen.terminate = TerminateProcess），
    最多等 3s，再升级为强杀。同时回收明显的子进程（例如
    `python -m streamlit` 会拉起真正的 streamlit worker），免得留下孤儿进程。
    """
    try:
        import psutil  # type: ignore
    except Exception:
        return False, "未安装 psutil，无法停止服务"
    running = running_services()
    pid = running.get(name)
    if pid is None:
        return False, f"{name} 未在运行"
    try:
        parent = psutil.Process(pid)
        kids = parent.children(recursive=True)
        for p in [parent, *kids]:
            try:
                p.terminate()
            except Exception:
                pass
        gone, alive = psutil.wait_procs([parent, *kids], timeout=3.0)
        for p in alive:
            try:
                p.kill()
            except Exception:
                pass
        invalidate_running_cache()
        return True, f"已停止 {name} (pid={pid})"
    except psutil.NoSuchProcess:
        invalidate_running_cache()
        return True, f"{name} 已退出"
    except Exception as e:
        return False, f"停止失败: {type(e).__name__}: {e}"


def list_scheduler_tasks() -> list[dict]:
    """返回每个 sche_tasks/*.json 的 [{name, path, schedule, enabled}]。

    供 /scheduler 选择器使用，让用户也能开关传统的 cron 任务，
    而不只是 reflect.* 脚本。
    """
    out: list[dict] = []
    sd = _ROOT / "sche_tasks"
    if not sd.is_dir():
        return out
    for p in sorted(sd.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        out.append({
            "name": p.stem,
            "path": str(p),
            "schedule": data.get("schedule") or data.get("cron") or data.get("every") or "",
            "enabled": bool(data.get("enabled", True)),
        })
    return out


def start_reflect_task(name: str) -> tuple[bool, str]:
    """脱离父进程启动 `agentmain.py --reflect reflect/<name>.py`。

    reflect 脚本只有 INTERVAL / check() 契约，自身没有主循环；必须由
    agentmain 的 --reflect 模式加载。之所以脱离：reflect 任务都是长跑的，
    不该随 TUI 一起死掉。Windows 上用
    CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW，避免弹出控制台窗口
    （遵从 CONSTITUTION 规则 14：只在启动层做，不 monkey-patch
    subprocess.Popen）。
    """
    script = _ROOT / "reflect" / f"{name}.py"
    entry = _ROOT / "agentmain.py"
    if not script.is_file():
        return False, f"reflect/{name}.py 不存在"
    if not entry.is_file():
        return False, "agentmain.py 不存在"
    try:
        flags = 0
        if os.name == "nt":
            flags = 0x00000200 | 0x08000000  # NEW_PROCESS_GROUP | NO_WINDOW
        subprocess.Popen(
            [sys.executable, str(entry), "--reflect", f"reflect/{name}.py"],
            cwd=str(_ROOT),
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return True, f"已启动 reflect/{name}.py"
    except Exception as e:
        return False, f"启动失败: {type(e).__name__}: {e}"


# ----- 供 TUI 注册的 dispatch 表 -----------------------------------------

# (cmd, arg_hint, desc)  —— v2 与 v3 保持完全一致，好让命令面板在各前端
# 之间保持一致。
PALETTE_ENTRIES: list[tuple[str, str, str]] = [
    ("/update",    "[note]",    "git pull 更新 zicatAgent 仓库并报告影响面"),
    ("/autorun",   "[seed]",    "进入 autonomous_operation 自主模式"),
    ("/distill", "[target]",  "启用 Distill 蒸馏 / 吞噬外部技能"),
    ("/goal",      "[goal]",    "进入 Goal 模式（需 condition 约束）"),
    ("/team",      "[target]",  "进入 Team 多 worker 协作模式"),
    ("/scheduler", "",          "多选启动/停止 reflect 任务（cron 由 reflect/scheduler.py 驱动）"),
    ("/resume",    "",           "列出最近会话并恢复其中一个（zicatAgent 端展开 prompt）"),
]


def prompt_for(cmd: str, args_text: str) -> Optional[str]:
    """返回某个斜杠命令应注入的用户消息；若不属于本模块（例如 /scheduler
    由 TUI 直接处理）则返回 None。

    语言在关心它的构造器内部解析（见 `_current_lang()`）；调用方从不透传，
    因此两个 TUI 的调用点都能保持统一。
    """
    table = {
        "/update":    build_update_prompt,
        "/autorun":   build_autorun_prompt,
        "/distill": build_distill_prompt,
        "/goal":      build_goal_prompt,
        "/team":      build_team_prompt,
    }
    fn = table.get(cmd)
    return fn(args_text) if fn else None
